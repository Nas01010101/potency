"""Run the tests and both replays on a fresh Colab CPU VM, writing everything to /content/replay_out.txt.

Expects the repository as /content/potency.tgz (uploaded), or clones REPO_URL.
Driver: scripts/colab-run.sh run --hours 2 --upload potency.tgz:/content/potency.tgz \
        --fetch /content/replay_out.txt:replay_out.txt colab/replay.py
"""
import os, subprocess, sys, tarfile, time

OUT = open('/content/replay_out.txt', 'w', buffering=1)


def run(cmd, env=None):
    t = time.time()
    OUT.write(f'\n$ {cmd}\n')
    p = subprocess.run(cmd, shell=True, text=True, capture_output=True, env={**os.environ, **(env or {})})
    OUT.write(p.stdout + (p.stderr[-3000:] if p.returncode else ''))
    OUT.write(f'[exit {p.returncode}, {time.time() - t:.0f}s]\n')
    print(cmd, p.returncode, flush=True)


src = '/content/potency.tgz'
if os.path.exists(src):
    tarfile.open(src).extractall('/content')
else:
    subprocess.run(['git', 'clone', '-q', os.environ['REPO_URL'], '/content/upstream-agent'], check=True)
os.chdir('/content/upstream-agent')
run('pip -q install awscli pandas pyarrow numpy pytest')
run(f'{sys.executable} -m pytest -q tests')
run('bash replay/fetch.sh')
for d in ('data/preds', 'data/preds_open'):
    run(f'{sys.executable} replay/harness_premises.py', {'PREDS': d})
    run(f'{sys.executable} replay/completion_recovery.py', {'PREDS': d})
    run(f'{sys.executable} replay/per_harness.py {d}/recovery_rows.csv')
OUT.close()
