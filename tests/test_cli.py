import subprocess, sys

from potency import cli


def test_help_lists_subcommands(capsys):
    assert cli.main([]) == 0
    assert 'gate, report, run' in capsys.readouterr().out


def test_unknown_subcommand_exits():
    try:
        cli.main(['nope'])
    except SystemExit as e:
        assert 'unknown subcommand' in str(e.code)
    else:
        raise AssertionError('no exit')


def test_gate_help_runs():
    r = subprocess.run([sys.executable, '-m', 'potency.cli', 'gate', '--help'], capture_output=True, text=True)
    assert r.returncode == 0 and '--patch' in r.stdout
