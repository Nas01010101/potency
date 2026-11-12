"""Would a completion alert have caught the gold files real harnesses missed?

For each SWE-bench Verified multi-file task and each of 8 harnesses: seeds = source files the
harness edited. A ranker proposes 5 more files (seeds excluded). On runs that missed gold files
(partial), we score whether a missed gold file is proposed; on runs that covered all gold files,
a confident alert is a false alarm. Graphs are built from the repo at base_commit only.
Run: uv run --with pandas --with pyarrow completion_recovery.py
"""
import collections, json, os, re, subprocess, sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from potency.graphs import BM25, cochange_index, history, import_graph, read_tree, rrf, tokens, git, TEXT_EXT


# Same definitions as harness_premises.py (that file runs its analysis at import time).
def files(patch):
    return {o for o in re.findall(r'^--- (?:a/)?(\S+)', patch or '', re.M) if o != '/dev/null'}


def is_test(f):
    return bool(re.search(r'(^|/)(tests?|testing)(/|$)|(^|/)test_[^/]*\.py$|_tests?\.py$|conftest\.py$', f))


D = Path(os.environ.get('PREDS', Path(__file__).resolve().parent.parent / 'data' / 'preds'))
REPOS = Path(os.environ.get('REPOS', Path(__file__).resolve().parent.parent / 'data' / 'repos'))
K = 5

gold = pd.read_parquet(D / 'verified.parquet')
runs = pd.read_csv(D / 'harness_rows.csv')
preds = {}
for p in D.glob('*.jsonl'):
    h = p.stem.split('_', 1)[1][:28]
    for line in open(p):
        x = json.loads(line)
        preds[(h, x['instance_id'])] = {f for f in files(x.get('model_patch')) if not is_test(f)}

out = []
for t in gold.itertuples():
    G = files(t.patch)
    repo = REPOS / t.repo.split('/')[1]
    if len(G) < 2 or not repo.exists():
        continue
    base = t.base_commit
    if subprocess.run(['git', '-C', str(repo), 'cat-file', '-e', base + '^{commit}']).returncode:
        continue   # repo still cloning or commit unreachable
    allfiles = set(f for f in git(repo, 'ls-tree', '-r', '--name-only', base).split('\n') if f)
    n, pair = cochange_index(history(repo, base))
    src = read_tree(repo, base, lambda f: f.endswith(TEXT_EXT) and not f.startswith('docs/'))
    bm_rank = BM25({f: tokens(f) * 3 + tokens(s[:20000]) for f, s in src.items()}).rank(t.problem_statement)
    imp = import_graph(src, [f for f in src if f.endswith('.py')])
    del src
    for h in runs.h.unique():
        S = preds.get((h, t.instance_id), set()) & allfiles
        if not S:
            continue
        miss = G - S
        co = collections.Counter()
        for s in S:
            for g, c in pair[s].items():
                co[g] += c / n[s]
        imps = collections.Counter(g for s in S for g in imp.get(s, ()))
        dirs = {s.rsplit('/', 1)[0] for s in S}
        rk = {
            'cochange': [g for g, _ in co.most_common()],
            'imports': sorted(imps, key=lambda g: (-imps[g], -n[g])),
            'samedir': sorted((f for f in allfiles if f.rsplit('/', 1)[0] in dirs and not is_test(f)), key=lambda f: -n[f]),
            'bm25_issue': bm_rank,
        }
        rk['imports+cochange'] = rrf(rk['imports'], rk['cochange'])
        rk['imports+cochange+bm25'] = rrf(rk['imports'], rk['cochange'], rk['bm25_issue'])
        top_conf = max(co.values()) / len(S) if co else 0.0
        for m, r in rk.items():
            r = [f for f in r if f not in S and not is_test(f) and f in allfiles][:K]
            out.append(dict(h=h, iid=t.instance_id, method=m, partial=bool(miss), hit=bool(set(r) & miss),
                            rec=len(set(r) & miss) / len(miss) if miss else None, conf=top_conf,
                            resolved=bool(runs[(runs.h == h) & (runs.iid == t.instance_id)].resolved.any())))
    print(t.instance_id, len(G), file=sys.stderr, flush=True)

df = pd.DataFrame(out)
df.to_csv(D / 'recovery_rows.csv', index=False)
p = df[df.partial]
print(f'partial runs: {p[p.method == "cochange"].shape[0]} over {p.iid.nunique()} tasks')
print('alert surfaces >=1 missed gold file in top-5 (partial runs), and recall of missed files:')
print(p.groupby('method').agg(hit=('hit', 'mean'), rec=('rec', 'mean')).round(3).to_string())
print('\nsame, restricted to UNRESOLVED partial runs:')
u = p[~p.resolved]
print(u.groupby('method').agg(hit=('hit', 'mean'), rec=('rec', 'mean'), n=('hit', 'size')).round(3).to_string())
c = df[(df.method == 'cochange')]
for th in (0.2, 0.3, 0.5):
    fire = c.conf >= th
    print(f'cochange alert conf>={th}: fires on {fire[c.partial].mean():.2f} of partial runs, '
          f'{fire[~c.partial].mean():.2f} of complete runs; hit|fire on partial {c[fire & c.partial].hit.mean():.2f}')
