"""Build swebench prediction files from runs/*.jsonl, and summarize A vs B once results exist.

  python analyze.py preds          -> runs/preds_{arm}_{A,B}.jsonl (B only where the patch changed)
  python analyze.py report         -> resolve and gold-file coverage, A vs B, per arm
Resolved ids are read from swebench report files runs/eval/{arm}_{A,B}*.json.
"""
import glob, json, os, sys
from math import comb
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from potency import gate  # noqa: E402

R = Path(__file__).resolve().parent / 'runs'
gold = pd.read_parquet(Path(os.environ.get('PREDS', R.parent.parent / 'data/preds')) / 'verified.parquet').set_index('instance_id')


def load(arm):
    rows = [json.loads(l) for l in open(R / f'{arm}.jsonl')]
    return {r['instance_id']: r for r in rows}   # last record wins


def preds():
    for arm in ('gate', 'reflect'):
        if not (R / f'{arm}.jsonl').exists():
            continue
        runs = load(arm)
        for side in ('A', 'B'):
            with open(R / f'preds_{arm}_{side}.jsonl', 'w') as f:
                for iid, r in runs.items():
                    p = r['patch_a'] if side == 'A' else r['patch_b']
                    if side == 'B' and p == r['patch_a']:
                        continue
                    f.write(json.dumps({'instance_id': iid, 'model_name_or_path': f'{arm}_{side}',
                                        'model_patch': p}) + '\n')


def resolved(name):
    ids = set()
    for p in glob.glob(str(R / 'eval' / f'{name}*.json')):
        ids |= set(json.load(open(p)).get('resolved_ids', []))
    return ids


def mcnemar(b, c):   # exact two-sided p for discordant pairs b (A only) vs c (B only)
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def cover(iid, patch):
    G = {f for f in gate.files(gold.loc[iid, 'patch']) if not gate.is_test(f)}
    P = {f for f in gate.files(patch) if not gate.is_test(f)}
    return len(G & P) / len(G), G <= P


def report():
    for arm in ('gate', 'reflect'):
        if not (R / f'{arm}.jsonl').exists():
            continue
        runs = load(arm)
        rA, rB = resolved(f'{arm}_A'), resolved(f'{arm}_B')
        rows = []
        for iid, r in runs.items():
            a = iid in rA
            b = a if r['patch_b'] == r['patch_a'] else iid in rB
            ca, fa = cover(iid, r['patch_a'])
            cb, fb = cover(iid, r['patch_b'])
            rows.append(dict(iid=iid, a=a, b=b, changed=r['patch_b'] != r['patch_a'], cov_a=ca, cov_b=cb,
                             full_a=fa, full_b=fb, submitted=bool(r['patch_a']), hit=bool(set(r['proposed']) & (
                                 {f for f in gate.files(gold.loc[iid, 'patch'])} - gate.files(r['patch_a'])))))
        d = pd.DataFrame(rows)
        lost, won = int((d.a & ~d.b).sum()), int((~d.a & d.b).sum())
        print(f'[{arm}] n={len(d)} submitted={d.submitted.sum()} patch changed after message={d.changed.sum()}')
        print(f'  resolve A={d.a.mean():.3f} ({d.a.sum()})  B={d.b.mean():.3f} ({d.b.sum()})  '
              f'won={won} lost={lost} McNemar p={mcnemar(lost, won):.3f}')
        print(f'  gold-file recall A={d.cov_a.mean():.3f} B={d.cov_b.mean():.3f} | all gold files A={d.full_a.mean():.3f} '
              f'B={d.full_b.mean():.3f}')
        if arm == 'gate':
            print(f'  gate proposed a missed gold file on {d.hit.sum()} of {(d.submitted & ~d.full_a).sum()} partial A patches')
        d.to_csv(R / f'summary_{arm}.csv', index=False)


if __name__ == '__main__':
    {'preds': preds, 'report': report}[sys.argv[1]]()
