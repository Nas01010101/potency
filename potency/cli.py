"""`potency` command: gate, report and live runs behind one entry point.

    potency gate   --repo . --base HEAD --issue issue.txt --patch edit.diff
    potency report --repo . --base HEAD --issue issue.txt --patch edit.diff --reasons reasons.json
    potency run    --workers 20 --out live/runs/bind.jsonl     (binding arm, needs the [live] extra)
"""
import runpy, sys
from pathlib import Path

from . import gate, report

LIVE = Path(__file__).resolve().parent.parent / 'live' / 'gate_run.py'
USAGE = __doc__ + '\nsubcommands: gate, report, run\n'


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ('-h', '--help'):
        print(USAGE)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == 'gate':
        sys.argv = ['potency gate', *rest]
        return gate.main()
    if cmd == 'report':
        sys.argv = ['potency report', *rest]
        return report.main()
    if cmd == 'run':
        # the live runner sits next to the package in a source checkout, not in the wheel
        if not LIVE.exists():
            sys.exit('potency run needs a source checkout: live/gate_run.py not found')
        if '--arm' not in rest:
            rest = ['--arm', 'bind', *rest]
        sys.argv = [str(LIVE), *rest]
        runpy.run_path(str(LIVE), run_name='__main__')
        return 0
    sys.exit(f'unknown subcommand {cmd!r}\n{USAGE}')


if __name__ == '__main__':
    sys.exit(main())
