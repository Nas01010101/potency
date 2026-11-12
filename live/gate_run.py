"""Paired live test of the completion gate with mini-swe-agent on SWE-bench Verified multi-file tasks.

On the agent's first submit we record patch A, then send one message and let it continue:
  gate    : names the files the completion gate proposes and asks whether the fix needs them
  reflect : the same message without the file list (control for "a second look")
The last submitted patch is B (B = A if the agent never resubmits). Model: Gemma 4 31B on vLLM.
Run: PYTHONPATH=$MSA python3.13 gate_run.py --arm gate --workers 20 --out runs/gate.jsonl
"""
import argparse, concurrent.futures as cf, json, os, re, sys, threading, time, traceback
from pathlib import Path

import pandas as pd
import yaml
from minisweagent.agents.default import DefaultAgent
from minisweagent.exceptions import Submitted
from minisweagent.models import get_model
from minisweagent.run.benchmarks.swebench import get_sb_environment

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from potency import gate, report  # noqa: E402

HERE = Path(__file__).resolve().parent
CFG = Path(os.environ['MSA']) / 'minisweagent/config/benchmarks'
DATA = Path(__file__).resolve().parent.parent / 'data'
PREDS = Path(os.environ.get('PREDS', DATA / 'preds'))
REPOS = Path(os.environ.get('REPOS', DATA / 'repos'))

HEAD = ("Before you finish: check whether your fix is complete. Bugs like this one often need matching "
        "changes in more than one file (callers, sibling implementations, mirrored or generated code, registries).")
CHECK = {
    'gate': (" These files are imported by, historically changed together with, or textually related to the ones you "
             "edited, and you did not touch them:{files}\nOpen each one (grep it for the names you changed) before "
             "deciding."),
    'reflect': (" Search the repository for other source files that use or mirror the names you changed (for example "
                "with grep -rn) before deciding."),
}
TAIL = (" If another file needs a change, make it, regenerate patch.txt with ALL modified source files, verify it, and "
        "submit again. If after this check the fix is complete, submit the same patch again.")
# A pilot message that only offered "submit the same patch again" was taken in one step in 6/6 runs;
# both arms are now asked to run a check before deciding, and differ only in whether the gate's list is given.


def gate_message(arm, t, patch):
    prop = [] if arm == 'reflect' else gate.propose(REPOS / t.repo.split('/')[1], t.base_commit,
                                                    t.problem_statement, patch)[1]
    if arm == 'gate' and not prop:   # no seed: fall back to the control check
        return HEAD + CHECK['reflect'] + TAIL, []
    return HEAD + CHECK[arm].format(files=''.join(f'\n- {f}' for f in prop)) + TAIL, prop


BIND = (" The repository ties these files to the ones you edited, and you did not touch them:{files}\nFor each "
        "file: open it and grep it for the names you changed. Then either change it, or write one line in your reply "
        "in exactly this form:\nREASON <path>: <why this file needs no change>\nYour submission is accepted only when "
        "every listed file is in the patch or has a REASON line. Then regenerate patch.txt with ALL modified source "
        "files and submit again.")
REFUSE = "Submission refused. These files have neither a change in the patch nor a REASON line:{files}\n" \
         "Change each one or write its REASON line, then submit again."
MAX_REFUSALS = 2


def bind_message(t, patch):
    """The binding arm's message, and [(file, evidence)] from the gate."""
    _, exp = report.expected(REPOS / t.repo.split('/')[1], t.base_commit, t.problem_statement, patch)
    if not exp:
        return HEAD + CHECK['reflect'] + TAIL, []
    return HEAD + BIND.format(files=''.join(f'\n- {f} ({"; ".join(ev)})' for f, ev in exp)), exp


class GateAgent(DefaultAgent):
    def __init__(self, *a, arm, task_row, extra_steps, **kw):
        super().__init__(*a, **kw)
        self.arm, self.t, self.extra_steps = arm, task_row, extra_steps
        self.subs, self.proposed, self.submit_step, self.msg_idx = [], [], None, None
        self.exp, self.reasons, self.refusals = [], {}, 0

    def execute_actions(self, message):
        try:
            return super().execute_actions(message)
        except Submitted as e:
            self.subs.append(e.messages[0]['extra']['submission'])
            if len(self.subs) > 1:
                if self.arm != 'bind' or not self.exp:
                    raise
                said = '\n'.join(str(m.get('content') or '') for m in self.messages[self.msg_idx:]
                                 if m.get('role') == 'assistant')
                self.reasons = {f: r.strip() for f, r in re.findall(r'REASON\s+`?([^\s:`]+)`?\s*:\s*(.+)', said)}
                edited = gate.files(self.subs[-1])
                open_ = [f for f in report.check(self.exp, self.reasons) if f not in edited]
                if not open_ or self.refusals >= MAX_REFUSALS:
                    raise
                self.refusals += 1
                self.config.step_limit = self.n_calls + 10
                return self.add_messages(self.model.format_message(
                    role='user', content=REFUSE.format(files=''.join(f'\n- {f}' for f in open_))))
            self.submit_step, self.msg_idx = self.n_calls, len(self.messages)
            if self.arm == 'bind':
                text, self.exp = bind_message(self.t, self.subs[0])
                self.proposed = [f for f, _ in self.exp]
            else:
                text, self.proposed = gate_message(self.arm, self.t, self.subs[0])
            self.config.step_limit = self.n_calls + self.extra_steps   # same extra budget in both arms
            return self.add_messages(self.model.format_message(role='user', content=text))


def load_config(api_base, key, step_limit):
    c = yaml.safe_load(open(CFG / 'swebench_backticks.yaml'))
    c['environment'] = yaml.safe_load(open(CFG / 'swebench_modal.yaml'))['environment']
    c['agent'].update(step_limit=step_limit, cost_limit=0)
    c['model'].update(model_class='litellm_textbased', model_name='openai/gemma4', cost_tracking='ignore_errors',
                      model_kwargs={'api_base': api_base, 'api_key': key, 'temperature': 1.0, 'top_p': 0.95,
                                    'max_tokens': 4096, 'timeout': 600, 'drop_params': True})
    return c


def run_one(t, arm, cfg, extra_steps, lock, out):
    rec = dict(instance_id=t.instance_id, arm=arm, patch_a='', patch_b='', proposed=[], exit='', calls=0,
               submit_step=None, secs=0.0)
    t0, env = time.time(), None
    try:
        env = get_sb_environment(cfg, {'instance_id': t.instance_id})
        agent = GateAgent(get_model(config=dict(cfg['model'])), env, arm=arm, task_row=t,
                          extra_steps=extra_steps, **cfg['agent'])
        try:
            info = agent.run(t.problem_statement)
            rec['exit'] = info.get('exit_status', '')
        except Exception as e:
            rec['exit'] = f'{type(e).__name__}: {str(e)[:200]}'
        rec.update(patch_a=agent.subs[0] if agent.subs else '', patch_b=agent.subs[-1] if agent.subs else '',
                   proposed=agent.proposed, calls=agent.n_calls, submit_step=agent.submit_step,
                   resubmitted=len(agent.subs) > 1, reasons=agent.reasons, refusals=agent.refusals,
                   evidence=dict(agent.exp),
                   post=[str(m.get('content') or '')[-600:] for m in agent.messages[agent.msg_idx or len(agent.messages):]
                         if m.get('role') == 'assistant'])
    except Exception as e:
        rec['exit'] = f'setup {type(e).__name__}: {str(e)[:200]}'
        rec['tb'] = traceback.format_exc()[-800:]
    finally:
        try:
            if env is not None and hasattr(env, 'stop'):
                env.stop()
        except Exception:
            pass
    rec['secs'] = round(time.time() - t0, 1)
    with lock, open(out, 'a') as f:
        f.write(json.dumps(rec) + '\n')
    print(f"{t.instance_id} {arm} exit={rec['exit'][:40]} calls={rec['calls']} "
          f"A={bool(rec['patch_a'])} resub={rec.get('resubmitted')} {rec['secs']}s", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--arm', choices=['gate', 'reflect', 'bind'], required=True)
    ap.add_argument('--workers', type=int, default=16)
    ap.add_argument('--step-limit', type=int, default=60)
    ap.add_argument('--extra-steps', type=int, default=20)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--out', required=True)
    # a second client on another server takes tasks from the end so the two do not overlap
    ap.add_argument('--reverse', action='store_true')
    a = ap.parse_args()
    api_base = os.environ['VLLM_BASE'].rstrip('/') + '/v1'
    cfg = load_config(api_base, (HERE / '.vllm_key').read_text().strip(), a.step_limit)
    g = pd.read_parquet(PREDS / 'verified.parquet')
    tasks = [t for t in g.itertuples() if len(gate.files(t.patch)) >= 2
             and (REPOS / t.repo.split('/')[1]).exists()]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = {json.loads(l)['instance_id'] for l in open(out)} if out.exists() else set()
    tasks = [t for t in tasks if t.instance_id not in done][::-1 if a.reverse else 1][: a.limit or None]
    print(f'{len(tasks)} tasks, arm={a.arm}', flush=True)
    lock = threading.Lock()
    with cf.ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(lambda t: run_one(t, a.arm, cfg, a.extra_steps, lock, out), tasks))


if __name__ == '__main__':
    main()
