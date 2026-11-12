"""The ADK skill script (working tree) and the library gate (git objects at base) agree."""
import subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'agents/potency/skills/complete/scripts'))
import complete  # noqa: E402
from potency import gate  # noqa: E402
from test_gate import PATCH, make_repo  # noqa: E402


def test_skill_matches_library(tmp_path):
    repo, base = make_repo(tmp_path)
    (repo / 'pkg/parser.py').write_text('from pkg import util\n# edited\n')
    seeds, out, why = complete.propose(str(repo), 'parser fails on empty input')
    lib_seeds, lib_out = gate.propose(repo, base, 'parser fails on empty input', PATCH)
    assert seeds == lib_seeds == {'pkg/parser.py'}
    assert out == lib_out
    assert 'imports' in why['pkg/util.py'] and 'co-change' in why['pkg/writer.py']


def test_skill_no_edit_no_history(tmp_path):
    repo = tmp_path / 'r'
    repo.mkdir()
    subprocess.run(['git', '-C', str(repo), 'init', '-q'], check=True)
    assert complete.propose(str(repo), 'x') == (set(), [], {})


def test_skill_ignores_test_edits(tmp_path):
    repo, _ = make_repo(tmp_path)
    (repo / 'tests/test_parser.py').write_text('from pkg import parser\n# edited\n')
    assert complete.propose(str(repo), 'x')[0] == set()
