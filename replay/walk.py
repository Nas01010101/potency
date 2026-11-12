"""Does a multi-step walk over the joined graph name missed files better than one-step fusion?

Joined graph at the task's base commit: an edge f->g weighs c(f,g)/n(f) from commit history plus
1/deg(f) for an import edge. A random walk with restart at the agent's edited files (personalized
PageRank) ranks every other file. We compare it, alone and fused with issue BM25, against the
gate's one-step fusion on the same unresolved partial runs, and write those runs out as the
missing-file benchmark (bench/missing_file.jsonl).
Run: SETS=data/preds,data/preds_open uv run --with pandas --with pyarrow --with scipy replay/walk.py
"""
import json, os, subprocess, sys
from pathlib import Path
import numpy as np, pandas as pd
from scipy.sparse import csr_matrix
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from potency.gate import files, is_test, rank
from potency.graphs import BM25, TEXT_EXT, cochange_index, git, history, import_graph, read_tree, rrf, tokens

SETS = [Path(p) for p in os.environ.get('SETS', f'{ROOT}/data/preds,{ROOT}/data/preds_open').split(',')]
REPOS = Path(os.environ.get('REPOS', ROOT / 'data' / 'repos'))
K, ITERS = 5, 30
RESTART = (0.15, 0.5)   # both reported; neither was chosen on these runs
SUMMARY_ONLY = '--summary' in sys.argv   # recompute the tables from data/walk_rows.csv, skipping the walk


def transition(n, pair, imp):
    """Column-stochastic matrix of the joined graph, and its node order."""
    nodes = sorted(set(pair) | set(imp))
    ix = {f: i for i, f in enumerate(nodes)}
    r, c, v = [], [], []
    for f in nodes:
        w = {g: k / n[f] for g, k in pair.get(f, {}).items()}
        for g in imp.get(f, ()):
            w[g] = w.get(g, 0) + 1 / len(imp[f])
        tot = sum(w.values())
        for g, x in w.items():
            r.append(ix[g]); c.append(ix[f]); v.append(x / tot)
    return csr_matrix((v, (r, c)), shape=(len(nodes), len(nodes))), nodes, ix


def walk(P, nodes, ix, seeds, restart):
    s = np.zeros(len(nodes))
    for f in seeds:
        if f in ix:
            s[ix[f]] = 1
    if not s.sum():
        return []
    s /= s.sum()
    x = s.copy()
    for _ in range(ITERS):
        x = (1 - restart) * (P @ x) + restart * s
    return [nodes[i] for i in np.argsort(-x) if x[i] > 0]


def load(d):
    runs = pd.read_csv(d / 'harness_rows.csv')
    preds = {}
    for p in d.glob('*.jsonl'):
        h = p.stem.split('_', 1)[1][:28]
        for line in open(p):
            x = json.loads(line)
            preds[(h, x['instance_id'])] = {f for f in files(x.get('model_patch')) if not is_test(f)}
    res = {(a, b) for a, b, ok in zip(runs.h, runs.iid, runs.resolved) if ok}
    return sorted(runs.h.unique()), preds, res


sets = {d.name: load(d) for d in SETS}
gold = pd.read_parquet(SETS[0] / 'verified.parquet')
out, bench = [], []
for t in ([] if SUMMARY_ONLY else gold.itertuples()):
    G = files(t.patch)
    repo = REPOS / t.repo.split('/')[1]
    if len(G) < 2 or not repo.exists():
        continue
    if subprocess.run(['git', '-C', str(repo), 'cat-file', '-e', t.base_commit + '^{commit}']).returncode:
        continue
    allfiles = {f for f in git(repo, 'ls-tree', '-r', '--name-only', t.base_commit).split('\n') if f}
    n, pair = cochange_index(history(repo, t.base_commit))
    src = read_tree(repo, t.base_commit, lambda f: f.endswith(TEXT_EXT) and not f.startswith('docs/'))
    bm = BM25({f: tokens(f) * 3 + tokens(s[:20000]) for f, s in src.items()}).rank(t.problem_statement)
    imp = import_graph(src, [f for f in src if f.endswith('.py')])
    del src
    P, nodes, ix = transition(n, pair, imp)
    for name, (hs, preds, res) in sets.items():
        for h in hs:
            S = preds.get((h, t.instance_id), set()) & allfiles
            miss = G - S
            if not S or not miss or (h, t.instance_id) in res:
                continue   # the benchmark: unresolved runs that edited a source file and missed a gold file
            rk = rank(S, n, pair, bm, imp)
            for a in RESTART:
                w = walk(P, nodes, ix, S, a)
                rk[f'walk@{a}'] = w
                rk[f'walk@{a}+bm25'] = rrf(w, bm)
            for m, r in rk.items():
                top = [f for f in r if f not in S and not is_test(f) and f in allfiles][:K]
                out.append(dict(set=name, h=h, iid=t.instance_id, method=m, hit=bool(set(top) & miss)))
            bench.append(dict(set=name, harness=h, instance_id=t.instance_id, repo=t.repo,
                              base_commit=t.base_commit, edited=sorted(S), missing=sorted(miss)))
    print(t.instance_id, file=sys.stderr, flush=True)

if SUMMARY_ONLY:
    df = pd.read_csv(ROOT / 'data' / 'walk_rows.csv')
else:
    df = pd.DataFrame(out)
    df.to_csv(ROOT / 'data' / 'walk_rows.csv', index=False)
    (ROOT / 'bench').mkdir(exist_ok=True)
    with open(ROOT / 'bench' / 'missing_file.jsonl', 'w') as f:
        f.writelines(json.dumps(b) + '\n' for b in bench)
rng = np.random.default_rng(0)
for name, d in df.groupby('set'):
    w = d.pivot_table(index=['h', 'iid'], columns='method', values='hit').astype(float)
    print(f'\n{name}: {len(w)} unresolved runs missing a gold file, over {w.index.get_level_values("iid").nunique()} tasks')
    print(w.mean().round(3).sort_values(ascending=False).to_string())
    tasks = w.index.get_level_values('iid')
    ids = tasks.unique()
    by = {i: w[tasks == i] for i in ids}
    for m in [c for c in w.columns if c.startswith('walk')]:
        diff = [(lambda b: (b[m] - b['gate']).mean())(pd.concat([by[i] for i in rng.choice(ids, len(ids))]))
                for _ in range(2000)]
        print(f'{m} minus gate: {(w[m] - w["gate"]).mean():+.3f} [{np.percentile(diff, 2.5):+.3f}, {np.percentile(diff, 97.5):+.3f}]')
    # Table 3: fusion minus issue BM25, own generator so the walk intervals above stay as published
    r2 = np.random.default_rng(0)
    diff = [(lambda b: (b['gate'] - b['bm25_issue']).mean())(pd.concat([by[i] for i in r2.choice(ids, len(ids))]))
            for _ in range(4000)]
    print(f'gate minus bm25_issue: {(w["gate"] - w["bm25_issue"]).mean():+.3f} '
          f'[{np.percentile(diff, 2.5):+.3f}, {np.percentile(diff, 97.5):+.3f}] (4,000 task resamples)')
    ph = w.groupby(level='h')[['gate', 'bm25_issue']].mean()
    print(f'gate above bm25 in {(ph.gate > ph.bm25_issue).sum()} of {len(ph)} harnesses')
    print(ph.round(3).to_string())
