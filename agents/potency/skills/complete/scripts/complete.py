"""Name up to 5 files the current edit likely missed: imports + co-change + issue BM25, fused by RRF.

usage: python complete.py <issue term> [<issue term> ...]   (repo root: /workspace if present, else cwd)
Seeds are the tracked non-test files modified in the working tree (`git diff --name-only HEAD`).
Stdlib only, single file, so it runs inside the task sandbox. Mirrors potency/graphs.py and
potency/gate.py; tests/test_complete_skill.py checks the two agree.
"""
import ast, collections, math, os, re, subprocess, sys, warnings

warnings.filterwarnings("ignore", category=SyntaxWarning)  # ast.parse on old sources; keeps tool output clean

K = 5
MAX_COMMIT_FILES, MAX_COMMITS = 30, 3000
TEXT_EXT = ('.py', '.md', '.txt', '.toml', '.yml', '.yaml', '.rst', '.cfg', '.ini', '.json')
TEST = re.compile(r'(^|/)(tests?|testing)(/|$)|(^|/)test_[^/]*\.py$|_tests?\.py$|conftest\.py$')


def git(root, *args):
    r = subprocess.run(['git', '-C', root, *args], capture_output=True, text=True, errors='replace')
    return r.stdout if r.returncode == 0 else None


def tokens(s):
    s = re.sub(r'([a-z])([A-Z])', r'\1 \2', s)
    return [t for t in re.split(r'[^A-Za-z0-9]+', s.lower()) if len(t) > 2]


def bm25(docs, query, k1=1.2, b=0.75):
    tf = {n: collections.Counter(d) for n, d in docs.items()}
    avg = sum(sum(t.values()) for t in tf.values()) / max(1, len(tf))
    df = collections.Counter(w for t in tf.values() for w in t)
    idf = {w: math.log(1 + (len(tf) - d + 0.5) / (d + 0.5)) for w, d in df.items()}
    q, sc = set(tokens(query)), []
    for n, t in tf.items():
        L = sum(t.values())
        s = sum(idf[w] * t[w] * (k1 + 1) / (t[w] + k1 * (1 - b + b * L / avg)) for w in q if w in t)
        if s:
            sc.append((s, n))
    return [n for _, n in sorted(sc, reverse=True)]


def import_edges(src):
    py = [f for f in src if f.endswith('.py')]
    mod = {}
    for f in py:
        m = f[:-3].replace('/', '.')
        mod[m[:-9] if m.endswith('.__init__') else m] = f
    edges = collections.defaultdict(set)
    for f in py:
        try:
            tree = ast.parse(src[f])
        except (SyntaxError, ValueError):
            continue
        pkg = f[:-3].replace('/', '.').rsplit('.', 1)[0]
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ''
                if node.level:
                    parts = pkg.split('.')
                    base = '.'.join(parts[:len(parts) - node.level + 1] + ([base] if base else []))
                names = [base] + [f'{base}.{a.name}' for a in node.names]
            for nm in names:
                while nm:
                    if nm in mod and mod[nm] != f:
                        edges[f].add(mod[nm]); edges[mod[nm]].add(f)
                        break
                    nm = nm.rpartition('.')[0]
    return edges


def cochange(root):
    """Per-file commit counts and pair counts from local history; empty when there is no history."""
    n, pair = collections.Counter(), collections.defaultdict(collections.Counter)
    out = git(root, 'log', 'HEAD', '--no-merges', '--name-only', '--format=%x00', '-n', str(MAX_COMMITS)) or ''
    for c in out.split('\x00'):
        c = {l for l in c.split('\n') if l.strip()}
        if 0 < len(c) <= MAX_COMMIT_FILES:
            for f in c:
                n[f] += 1
                for g in c - {f}:
                    pair[f][g] += 1
    return n, pair


def rrf(*rankings, k=60):
    sc = collections.Counter()
    for r in rankings:
        for i, x in enumerate(r):
            sc[x] += 1 / (k + i)
    return [x for x, _ in sc.most_common()]


def propose(root, issue, k=K):
    tracked = set((git(root, 'ls-files') or '').split('\n')) - {''}
    changed = set((git(root, 'diff', '--name-only', 'HEAD') or '').split('\n')) - {''}
    seeds = {f for f in changed if f in tracked and not TEST.search(f) and os.path.exists(os.path.join(root, f))}
    if not seeds:
        return seeds, [], {}
    src = {}
    for f in tracked:
        # .adk_exec_* is the skill executor's own wrapper, written into the repo root
        if f.endswith(TEXT_EXT) and not f.startswith('docs/') and not os.path.basename(f).startswith('.adk_exec'):
            try:
                src[f] = open(os.path.join(root, f), encoding='utf-8', errors='replace').read()
            except OSError:
                pass
    imp, (n, pair) = import_edges(src), cochange(root)
    co = collections.Counter()
    for s in seeds:
        for g, c in pair[s].items():
            co[g] += c / n[s]
    imps = collections.Counter(g for s in seeds for g in imp.get(s, ()))
    ranks = {'imports': sorted(imps, key=lambda g: (-imps[g], -n[g])),
             'co-change': [g for g, _ in co.most_common()],
             'issue': bm25({f: tokens(f) * 3 + tokens(s[:20000]) for f, s in src.items()}, issue)}
    fused = rrf(ranks['imports'], ranks['co-change'], ranks['issue'])
    out = [f for f in fused if f not in seeds and not TEST.search(f) and f in tracked][:k]
    why = {f: [name for name, r in ranks.items() if f in r[:20]] for f in out}
    return seeds, out, why


def main():
    root = '/workspace' if os.path.isdir('/workspace') else os.getcwd()
    seeds, out, why = propose(root, ' '.join(sys.argv[1:]))
    if not seeds:
        print('no modified source files yet; edit first, then run this before submitting')
        return
    print('edited:', ' '.join(sorted(seeds)))
    for f in out:
        print(f'{f}  ({", ".join(why[f]) or "fused"})')


if __name__ == '__main__':
    main()
