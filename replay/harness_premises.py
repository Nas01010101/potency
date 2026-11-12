"""Premise checks for framework components, on real patches from 8 SWE-bench Verified harnesses.

For every (harness, task): files the harness modified (existing files only; new scratch files are
ignored) vs files the gold patch modifies, and whether the harness resolved the task.
Run: uv run --with pandas --with pyarrow harness_premises.py
"""
import collections, glob, json, os, re
from pathlib import Path
import pandas as pd

D = Path(os.environ.get('PREDS', Path(__file__).resolve().parent.parent / 'data' / 'preds'))   # data/preds or data/preds_open


def files(patch):
    old = re.findall(r'^--- (?:a/)?(\S+)', patch or '', re.M)
    return {o for o in old if o != '/dev/null'}


def is_test(f):
    return bool(re.search(r'(^|/)(tests?|testing)(/|$)|(^|/)test_[^/]*\.py$|_tests?\.py$|conftest\.py$', f))


gold = pd.read_parquet(D / 'verified.parquet')
G = {r.instance_id: files(r.patch) for r in gold.itertuples()}
rows = []
for p in sorted(glob.glob(str(D / '*.jsonl'))):
    h = Path(p).stem
    res = set(json.load(open(D / f'{h}.results.json'))['resolved'])
    for line in open(p):
        x = json.loads(line)
        iid = x['instance_id']
        if iid not in G:
            continue
        P = files(x.get('model_patch'))
        Psrc = {f for f in P if not is_test(f)}
        g = G[iid]
        rows.append(dict(h=h.split('_', 1)[1][:28], iid=iid, resolved=iid in res, ngold=len(g),
                         empty=not P, touches_test=bool(P - Psrc),
                         miss=bool(g - Psrc) and bool(g & Psrc),       # partial: some gold files, not all
                         disjoint=bool(Psrc) and not (g & Psrc),       # wrong files entirely
                         extra=bool(Psrc - g),                         # source files beyond gold
                         covered=g <= Psrc,                            # every gold file edited
                         exact=Psrc == g))
df = pd.DataFrame(rows)
print('harness resolve rates (n tasks):')
print(df.groupby('h').resolved.agg(['mean', 'size']).round(3).to_string())

fail = df[~df.resolved]
print('\nFailure anatomy (share of UNRESOLVED runs, pooled over harnesses):')
for c in ['empty', 'disjoint', 'miss', 'extra', 'touches_test']:
    print(f'  {c:13s} {fail[c].mean():.3f}')
mf = df[df.ngold > 1]
print(f'\nMulti-file gold tasks: {mf.iid.nunique()} tasks, {len(mf)} runs; resolve {mf.resolved.mean():.3f} vs single-file {df[df.ngold == 1].resolved.mean():.3f}')
print(f'  partial edit (missed >=1 gold file) in {mf.miss.mean():.3f} of multi-file runs; resolve when partial {mf[mf.miss].resolved.mean():.3f}, when all gold covered {mf[mf.covered].resolved.mean():.3f}')
print(f'  at least one gold file unedited in {(~mf.covered).mean():.3f}; edited no gold file (incl. empty) {(~mf.covered & ~mf.miss).mean():.3f}')

print('\nResolve rate conditioned on each signal (pooled; lift = with - without):')
for c in ['disjoint', 'miss', 'extra', 'touches_test', 'exact']:
    a, b = df[df[c]].resolved.mean(), df[~df[c]].resolved.mean()
    print(f'  {c:13s} with={a:.3f} (n={df[c].sum()}) without={b:.3f} lift={a - b:+.3f}')

# Cross-harness selection by file-set consensus: pick the patch whose source-file set is the most
# common among the 8 harnesses (ties -> harness with higher overall rate). No test outcomes used.
rate = df.groupby('h').resolved.mean()
pf = {}
for p in sorted(glob.glob(str(D / '*.jsonl'))):
    h = Path(p).stem.split('_', 1)[1][:28]
    for line in open(p):
        x = json.loads(line)
        pf[(h, x['instance_id'])] = frozenset(f for f in files(x.get('model_patch')) if not is_test(f))
sel = []
for iid, g in df.groupby('iid'):
    votes = collections.Counter(pf.get((h, iid), frozenset()) for h in g.h if pf.get((h, iid)))
    if not votes:
        sel.append(False); continue
    top = votes.most_common(1)[0][0]
    cands = [h for h in g.h if pf.get((h, iid)) == top]
    best = max(cands, key=lambda h: rate[h])
    sel.append(bool(g[g.h == best].resolved.iloc[0]))
print(f'\nSelection over {df.h.nunique()} harnesses: best single {rate.max():.3f} | file-set consensus {sum(sel) / len(sel):.3f} | any-harness oracle {df.groupby("iid").resolved.any().mean():.3f}')
df.to_csv(D / 'harness_rows.csv', index=False)
