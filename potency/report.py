"""Binding completion check and the maintainer report built from it.

For each file the gate expects to change with the agent's edit, the agent must either edit it or
give a reason. `check` returns the expected files still unanswered; a harness refuses the submit
while that list is non-empty. `render` writes the one-screen report a maintainer reads with the
patch: files changed, each expected file with the evidence for it, and the agent's reason for
every expected file it left alone.

CLI: python -m potency.report --repo PATH --base SHA --issue ISSUE.txt --patch PATCH.diff
     [--reasons REASONS.json]     exits 1 while an expected file has no edit and no reason
"""
import argparse, json, sys
from pathlib import Path

from . import gate


def evidence(seeds, f, n, pair, imp):
    """Why the repository ties f to the edited files: shared commits and import edges."""
    ev = []
    for s in sorted(seeds):
        c = pair[s].get(f, 0)
        if c:
            ev.append(f'changed with {s} in {c} of its last {n[s]} commits')
        if f in imp.get(s, ()):
            ev.append(f'linked to {s} by an import')
    return ev or ['matches the issue text']


def expected(repo, base, issue, patch, k=gate.K):
    """[(file, [evidence])] for the gate's proposals, plus the seeds."""
    seeds, prop = gate.propose(repo, base, issue, patch, k)
    _, n, pair, _, imp = gate.indices(repo, base, issue)
    return seeds, [(f, evidence(seeds, f, n, pair, imp)) for f in prop]


def check(exp, reasons):
    """Expected files that have neither an edit (they would be seeds) nor a non-empty reason."""
    return [f for f, _ in exp if not (reasons.get(f) or '').strip()]


def render(seeds, exp, reasons):
    out = ['## Change report', '', f'Edited ({len(seeds)}): ' + ', '.join(f'`{s}`' for s in sorted(seeds)), '',
           '| Expected by the repository | Evidence | Status |', '|---|---|---|']
    for f, ev in exp:
        r = (reasons.get(f) or '').strip()
        out.append(f'| `{f}` | {"; ".join(ev)} | {"left alone: " + r if r else "**unanswered**"} |')
    if not exp:
        out.append('| (none) | | |')
    return '\n'.join(out) + '\n'


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--repo', required=True, type=Path)
    ap.add_argument('--base', required=True)
    ap.add_argument('--issue', required=True, type=Path)
    ap.add_argument('--patch', required=True, type=Path)
    ap.add_argument('--reasons', type=Path, help='JSON object {file: reason it needs no change}')
    ap.add_argument('-k', type=int, default=gate.K)
    a = ap.parse_args()
    reasons = json.loads(a.reasons.read_text()) if a.reasons else {}
    seeds, exp = expected(a.repo, a.base, a.issue.read_text(), a.patch.read_text(), a.k)
    print(render(seeds, exp, reasons))
    sys.exit(1 if check(exp, reasons) else 0)


if __name__ == '__main__':
    main()
