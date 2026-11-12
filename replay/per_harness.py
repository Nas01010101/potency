"""Per-harness hit rates on partial runs, and fused minus BM25 on unresolved partial runs with a
4,000-resample task-clustered bootstrap. usage: python per_harness.py $PREDS/recovery_rows.csv
"""
import pandas as pd, numpy as np, sys
d = pd.read_csv(sys.argv[1]); p = d[d.partial]
t = p.pivot_table(index='h', columns='method', values='hit', aggfunc='mean')[['bm25_issue','cochange','imports','imports+cochange+bm25']].round(3)
t['n'] = p[p.method=='cochange'].groupby('h').size(); print(t.to_string())
u = p[~p.resolved]
w = u.pivot_table(index=['h','iid'], columns='method', values='hit').reset_index()
w['diff'] = w['imports+cochange+bm25'].astype(float) - w['bm25_issue'].astype(float)
g = w.groupby('iid')['diff']; tasks = list(g.groups); rng = np.random.default_rng(0)
s = {k: (v.sum(), len(v)) for k, v in g}
bs = []
for _ in range(4000):
    pick = rng.choice(tasks, len(tasks)); a = sum(s[k][0] for k in pick); b = sum(s[k][1] for k in pick); bs.append(a/b)
print(f'fused-bm25 unresolved partial: {w["diff"].mean():+.3f} CI [{np.percentile(bs,2.5):.3f},{np.percentile(bs,97.5):.3f}] tasks={len(tasks)}')
