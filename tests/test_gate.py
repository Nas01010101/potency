"""The gate on a small synthetic repository with known import and co-change structure."""
import subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from potency import gate  # noqa: E402


def sh(repo, *args):
    subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True)


def commit(repo, files, msg):
    for name, text in files.items():
        p = repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    sh(repo, 'add', '-A')
    sh(repo, '-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', msg)


def make_repo(tmp_path):
    repo = tmp_path / 'r'
    repo.mkdir()
    sh(repo, 'init', '-q')
    commit(repo, {'pkg/__init__.py': '', 'pkg/parser.py': 'from pkg import util\n',
                  'pkg/util.py': 'X = 1\n', 'pkg/writer.py': 'Y = 1\n', 'pkg/other.py': 'Z = 1\n',
                  'tests/test_parser.py': 'from pkg import parser\n'}, 'init')
    # parser and writer change together three times; other never does
    for i in range(3):
        commit(repo, {'pkg/parser.py': f'from pkg import util\n# {i}\n', 'pkg/writer.py': f'Y = {i}\n'}, f'c{i}')
    base = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
    return repo, base


PATCH = '--- a/pkg/parser.py\n+++ b/pkg/parser.py\n@@ -1 +1 @@\n-a\n+b\n'


def test_proposes_import_and_cochange_neighbors(tmp_path):
    repo, base = make_repo(tmp_path)
    seeds, prop = gate.propose(repo, base, 'parser fails on empty input', PATCH)
    assert seeds == {'pkg/parser.py'}
    assert 'pkg/util.py' in prop          # imported by the seed
    assert 'pkg/writer.py' in prop        # co-changed with the seed
    assert prop.index('pkg/writer.py') < prop.index('pkg/other.py') if 'pkg/other.py' in prop else True


def test_excludes_seeds_and_tests(tmp_path):
    repo, base = make_repo(tmp_path)
    _, prop = gate.propose(repo, base, 'parser test fails', PATCH)
    assert 'pkg/parser.py' not in prop
    assert not any(gate.is_test(f) for f in prop)


def test_no_source_seed_gives_no_proposal(tmp_path):
    repo, base = make_repo(tmp_path)
    test_only = '--- a/tests/test_parser.py\n+++ b/tests/test_parser.py\n'
    assert gate.propose(repo, base, 'x', test_only) == (set(), [])
    assert gate.propose(repo, base, 'x', '') == (set(), [])


def test_new_files_are_not_seeds():
    assert gate.files('--- /dev/null\n+++ b/new.py\n') == set()
    assert gate.files(PATCH) == {'pkg/parser.py'}


def test_history_before_base_only(tmp_path):
    repo, base = make_repo(tmp_path)
    # a later commit couples parser with other; it must not be seen at base
    for i in range(5):
        commit(repo, {'pkg/parser.py': f'from pkg import util\n# late {i}\n', 'pkg/other.py': f'Z = {i}\n'}, f'late{i}')
    allfiles, n, pair, bm, imp = gate.indices(repo, base, 'x')
    assert pair['pkg/parser.py']['pkg/other.py'] == 1   # the initial commit only, not the 5 later ones
    assert pair['pkg/parser.py']['pkg/writer.py'] == 4   # initial commit + 3
