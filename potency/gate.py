"""Completion gate: given the files an agent edited, name up to K files it likely missed.

Reciprocal-rank fusion of three rankings over the repository at the task's base commit:
files linked to a seed by imports, files that changed together with the seeds in history before
the base commit, and BM25 of the issue over source files. Seeds and test files are excluded.

CLI: python -m potency.gate --repo PATH --base SHA --issue ISSUE.txt --patch PATCH.diff
"""
import argparse, collections, re, threading
from pathlib import Path

from .graphs import BM25, TEXT_EXT, cochange_index, git, history, import_graph, read_tree, rrf, tokens

K = 5
CACHE = 2   # indices for a large repo take hundreds of MB; keep few in memory
_lock = threading.Lock()
_cache = collections.OrderedDict()


def files(patch):
    """Files a unified diff modifies that existed before it (new files have no graph edges)."""
    return {o for o in re.findall(r'^--- (?:a/)?(\S+)', patch or '', re.M) if o != '/dev/null'}


def is_test(f):
    return bool(re.search(r'(^|/)(tests?|testing)(/|$)|(^|/)test_[^/]*\.py$|_tests?\.py$|conftest\.py$', f))


def indices(repo, base, issue):
    key = (str(repo), base, hash(issue))
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    allfiles = {f for f in git(repo, 'ls-tree', '-r', '--name-only', base).split('\n') if f}
    n, pair = cochange_index(history(repo, base))
    src = read_tree(repo, base, lambda f: f.endswith(TEXT_EXT) and not f.startswith('docs/'))
    bm = BM25({f: tokens(f) * 3 + tokens(s[:20000]) for f, s in src.items()}).rank(issue)
    imp = import_graph(src, [f for f in src if f.endswith('.py')])
    _cache[key] = (allfiles, n, pair, bm, imp)
    while len(_cache) > CACHE:
        _cache.popitem(last=False)
    return _cache[key]


def rank(seeds, n, pair, bm, imp):
    """The three rankings for a seed set, and their fusion."""
    co = collections.Counter()
    for s in seeds:
        for g, c in pair[s].items():
            co[g] += c / n[s]
    imps = collections.Counter(g for s in seeds for g in imp.get(s, ()))
    r = {'imports': sorted(imps, key=lambda g: (-imps[g], -n[g])),
         'cochange': [g for g, _ in co.most_common()],
         'bm25_issue': bm}
    r['gate'] = rrf(r['imports'], r['cochange'], r['bm25_issue'])
    return r


def propose(repo, base, issue, patch, k=K):
    """Return (seeds, up to k proposed files) for an agent's patch on repo at base."""
    with _lock:
        allfiles, n, pair, bm, imp = indices(repo, base, issue)
        seeds = {f for f in files(patch) if not is_test(f)} & allfiles
        if not seeds:
            return seeds, []
        fused = rank(seeds, n, pair, bm, imp)['gate']
        return seeds, [f for f in fused if f not in seeds and not is_test(f) and f in allfiles][:k]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--repo', required=True, type=Path)
    ap.add_argument('--base', required=True)
    ap.add_argument('--issue', required=True, type=Path, help='file holding the issue text')
    ap.add_argument('--patch', required=True, type=Path, help='unified diff of the agent edit')
    ap.add_argument('-k', type=int, default=K)
    a = ap.parse_args()
    seeds, prop = propose(a.repo, a.base, a.issue.read_text(), a.patch.read_text(), a.k)
    print('seeds:', ' '.join(sorted(seeds)) or '(none)')
    print('\n'.join(prop))


if __name__ == '__main__':
    main()
