"""Run the E4B reason checker over every REASON line of a binding-arm run and score it.

A reason is wrong when its file is in the task's reference fix. The checker should answer DOUBT on
those and HOLDS on the rest. Writes one JSON line per reason and prints the two DOUBT rates.
Run: PREDS=... REPOS=... CHECKER_BASE=... CHECKER_KEY=... python live/audit_run.py runs/bind.jsonl runs/audit.jsonl
"""
import json, os, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from potency import audit, gate, report  # noqa: E402

PREDS, REPOS = Path(os.environ['PREDS']), Path(os.environ['REPOS'])
gold = pd.read_parquet(PREDS / 'verified.parquet').set_index('instance_id')
src = lambda p: {f for f in gate.files(p) if not gate.is_test(f)}
jobs = []
for r in map(json.loads, open(sys.argv[1])):
    g, B = gold.loc[r['instance_id']], src(r['patch_b'] or r['patch_a'] or '')
    ref = gate.files(g['patch'])
    for f, why in (r.get('reasons') or {}).items():
        if f not in B and why.strip():
            jobs.append(dict(instance_id=r['instance_id'], file=f, reason=why, ref=f in ref,
                             evidence=r['evidence'].get(f, []), repo=REPOS / g['repo'].split('/')[1],
                             base=g['base_commit'], issue=g['problem_statement'], patch=r['patch_b'] or r['patch_a']))


def run(j):
    try:
        v, note = audit.check_reason(j['repo'], j['base'], j['issue'], j['patch'], j['file'], j['reason'], j['evidence'])
    except Exception as e:  # a failed call is recorded, not retried, so the counts stay honest
        v, note = 'ERROR', str(e)[:200]
    return {k: j[k] for k in ('instance_id', 'file', 'reason', 'ref')} | {'verdict': v, 'note': note}


with ThreadPoolExecutor(16) as ex:
    out = list(ex.map(run, jobs))
Path(sys.argv[2]).write_text(''.join(json.dumps(o) + '\n' for o in out))
for lab, name in ((True, 'reasons for files in the reference fix (wrong reasons)'), (False, 'reasons for other files')):
    s = [o for o in out if o['ref'] == lab]
    d = sum(o['verdict'] == 'DOUBT' for o in s)
    print(f'{name}: {len(s)}, checker DOUBT {d}' + (f' ({d / len(s):.0%})' if s else ''))
print('unparsed or failed:', sum(o['verdict'] in ('UNPARSED', 'ERROR') for o in out))
for o in out:
    if o['ref']:
        print(f"\nexample: {o['instance_id']} `{o['file']}` (in the reference fix)\n  agent: {o['reason']}\n  E4B: {o['verdict']}: {o['note']}")
        break
