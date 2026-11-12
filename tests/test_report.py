"""The binding check and the maintainer report on the synthetic repository from test_gate."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from potency import report  # noqa: E402
from test_gate import PATCH, make_repo  # noqa: E402

BOTH = PATCH + '--- a/pkg/writer.py\n+++ b/pkg/writer.py\n@@ -1 +1 @@\n-a\n+b\n'


def test_evidence_names_shared_commits_and_imports(tmp_path):
    repo, base = make_repo(tmp_path)
    seeds, exp = report.expected(repo, base, 'parser fails', PATCH)
    ev = dict(exp)
    assert 'changed with pkg/parser.py in 4 of its last 4 commits' in ev['pkg/writer.py']
    assert 'linked to pkg/parser.py by an import' in ev['pkg/util.py']


def test_check_blocks_until_each_file_is_edited_or_explained(tmp_path):
    repo, base = make_repo(tmp_path)
    _, exp = report.expected(repo, base, 'parser fails', PATCH)
    assert 'pkg/writer.py' in report.check(exp, {})
    assert 'pkg/writer.py' not in report.check(exp, {'pkg/writer.py': 'writer does not read the parsed field'})
    assert 'pkg/writer.py' in report.check(exp, {'pkg/writer.py': '  '})   # a blank reason is no answer
    _, exp2 = report.expected(repo, base, 'parser fails', BOTH)             # editing the file answers it
    assert 'pkg/writer.py' not in [f for f, _ in exp2]
    assert not report.check(exp2, {f: 'n/a' for f, _ in exp2})


def test_render_marks_unanswered_and_reasons(tmp_path):
    repo, base = make_repo(tmp_path)
    seeds, exp = report.expected(repo, base, 'parser fails', PATCH)
    md = report.render(seeds, exp, {'pkg/util.py': 'constant unchanged'})
    assert 'left alone: constant unchanged' in md and '**unanswered**' in md
    assert 'Edited (1): `pkg/parser.py`' in md
