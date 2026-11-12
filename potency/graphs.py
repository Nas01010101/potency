"""Repository graphs used by the completion gate, all read at a fixed commit.

history/cochange_index: co-change counts from `git log <base>` (the fix commit is never seen).
import_graph: undirected module-import edges between Python files, from the AST.
BM25: issue-text ranking over files. rrf: reciprocal rank fusion (Cormack et al. 2009).
"""
import ast, collections, math, re, subprocess, warnings

warnings.filterwarnings("ignore", category=SyntaxWarning)  # ast.parse on old sources (invalid escapes)

MAX_COMMIT_FILES = 30   # bulk commits carry no coupling signal
MAX_COMMITS = 3000
TEXT_EXT = ('.py', '.md', '.txt', '.toml', '.yml', '.yaml', '.rst', '.cfg', '.ini', '.json')

def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True,
                          errors='replace', check=True).stdout


def read_tree(repo, base, want):
    """{path: text} for paths selected by want(path), read in one git cat-file process."""
    ids = {}
    for line in git(repo, 'ls-tree', '-r', base).split('\n'):
        if line and '\t' in line:
            meta, path = line.split('\t', 1)
            if meta.split()[1] == 'blob' and want(path):
                ids[meta.split()[2]] = path
    p = subprocess.run(['git', '-C', str(repo), 'cat-file', '--batch'], input='\n'.join(ids).encode(),
                       capture_output=True, check=True).stdout
    out, i = {}, 0
    while i < len(p):
        nl = p.index(b'\n', i)
        sha, _, size = p[i:nl].split(b' ')
        size = int(size)
        out[ids[sha.decode()]] = p[nl + 1:nl + 1 + size].decode('utf-8', 'replace')
        i = nl + 1 + size + 1
    return out


def history(repo, base):
    out = git(repo, 'log', base, '--no-merges', '--name-only', '--format=%x00', '-n', str(MAX_COMMITS))
    commits = [set(l for l in c.split('\n') if l.strip()) for c in out.split('\x00')]
    return [c for c in commits if 0 < len(c) <= MAX_COMMIT_FILES]


def cochange_index(commits):
    n = collections.Counter()
    pair = collections.defaultdict(collections.Counter)
    for c in commits:
        for f in c:
            n[f] += 1
            for g in c:
                if g != f:
                    pair[f][g] += 1
    return n, pair


def tokens(s):
    s = re.sub(r'([a-z])([A-Z])', r'\1 \2', s)
    return [t for t in re.split(r'[^A-Za-z0-9]+', s.lower()) if len(t) > 2]


class BM25:
    def __init__(self, docs, k1=1.2, b=0.75):
        self.names = list(docs)
        self.tf = [collections.Counter(docs[n]) for n in self.names]
        self.len = [sum(t.values()) for t in self.tf]
        self.avg = sum(self.len) / max(1, len(self.len))
        df = collections.Counter(w for t in self.tf for w in t)
        N = len(self.names)
        self.idf = {w: math.log(1 + (N - d + 0.5) / (d + 0.5)) for w, d in df.items()}
        self.k1, self.b = k1, b

    def rank(self, query):
        q = set(tokens(query))
        sc = []
        for name, tf, L in zip(self.names, self.tf, self.len):
            s = 0.0
            for w in q:
                f = tf.get(w)
                if f:
                    s += self.idf[w] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * L / self.avg))
            if s:
                sc.append((s, name))
        return [n for _, n in sorted(sc, reverse=True)]


def import_graph(src, pyfiles):
    """Undirected module-import edges between repo .py files."""
    mod = {}
    for f in pyfiles:
        m = f[:-3].replace('/', '.')
        if m.endswith('.__init__'):
            m = m[:-9]
        mod[m] = f
    edges = collections.defaultdict(set)
    for f in pyfiles:
        try:
            tree = ast.parse(src[f])
        except Exception:
            continue
        pkg = f[:-3].replace('/', '.').rsplit('.', 1)[0]
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                base_mod = node.module or ''
                if node.level:
                    parts = pkg.split('.')
                    base_mod = '.'.join(parts[:len(parts) - node.level + 1] + ([base_mod] if base_mod else []))
                names = [base_mod] + [f'{base_mod}.{a.name}' for a in node.names]
            for nm in names:
                while nm:
                    if nm in mod and mod[nm] != f:
                        edges[f].add(mod[nm]); edges[mod[nm]].add(f)
                        break
                    nm = nm.rpartition('.')[0]
    return edges


def rrf(*rankings, k=60):
    sc = collections.Counter()
    for r in rankings:
        for i, x in enumerate(r):
            sc[x] += 1 / (k + i)
    return [x for x, _ in sc.most_common()]
