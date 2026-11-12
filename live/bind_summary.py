"""Summary of the binding arm: what the agent did with each expected file after the check.

For runs whose first patch (A) missed a file of the reference fix: how often the gate listed a
missed file, and for each listed missed file whether the final patch (B) edits it or the agent
gave a reason. Prints one maintainer report as an example.
Run: PREDS=... python live/bind_summary.py live/runs/bind.jsonl
"""
import json, os, sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from potency import gate, report  # noqa: E402

PREDS = Path(os.environ.get('PREDS', Path(__file__).resolve().parent.parent / 'data' / 'preds'))
gold = pd.read_parquet(PREDS / 'verified.parquet').set_index('instance_id')
rows = [json.loads(l) for l in open(sys.argv[1])]
src = lambda p: {f for f in gate.files(p) if not gate.is_test(f)}
sub = [r for r in rows if r['patch_a']]
print(f'{len(rows)} runs, {len(sub)} submitted a patch')
part = listed = edited = reasoned = silent = cov_a = cov_b = 0
example = None
for r in sub:
    G, A, B = gate.files(gold.loc[r['instance_id'], 'patch']), src(r['patch_a']), src(r['patch_b'])
    cov_a += G <= A; cov_b += G <= B
    miss = G - A
    if not miss:
        continue
    part += 1
    hit = set(r['proposed']) & miss
    listed += bool(hit)
    for f in hit:
        if f in B: edited += 1
        elif r.get('reasons', {}).get(f): reasoned += 1; example = example or (r, f)
        else: silent += 1
print(f'first patch covers every reference file: {cov_a}/{len(sub)}; final patch: {cov_b}/{len(sub)}')
print(f'first patch missed a reference file: {part}; the check listed a missed file in {listed}')
print(f'listed missed files: {edited} edited after the check, {reasoned} left with a reason, {silent} left with none')
n_exp = sum(len(r['proposed']) for r in sub); n_r = sum(len(r.get('reasons', {})) for r in sub)
print(f'expected files listed: {n_exp}; reasons written: {n_r}; runs refused at least once: {sum(r.get("refusals", 0) > 0 for r in sub)}')
if example:
    r, f = example
    print(f'\nexample ({r["instance_id"]}; `{f}` is in the reference fix):\n')
    print(report.render(src(r['patch_b']), [(g, r['evidence'][g]) for g in r['proposed'] if g not in src(r['patch_b'])], r['reasons']))
