from pathlib import Path

from problemtools.run import Executable


def _sh(script: str, swap_exit_codes: bool = False) -> Executable:
    return Executable('sh', Path('/bin/sh'), args=['-c', script], swap_exit_codes=swap_exit_codes)


def test_run_capture(tmp_path: Path) -> None:
    result = _sh('echo out; echo err >&2; exit 3').run_capture(tmp_path)
    assert result.exitcode == 3
    assert result.stdout == 'out\n'
    assert result.stderr == 'err\n'
    assert result.output == 'out\n\nerr\n'
    assert list(tmp_path.iterdir()) == []


def test_run_capture_output_single_stream(tmp_path: Path) -> None:
    assert _sh('echo out').run_capture(tmp_path).output == 'out\n'
    assert _sh('echo err >&2').run_capture(tmp_path).output == 'err\n'


def test_run_capture_reads_infile(tmp_path: Path) -> None:
    infile = tmp_path / 'input'
    infile.write_text('hello\n')
    result = _sh('cat').run_capture(tmp_path, infile)
    assert result.exitcode == 0
    assert result.stdout == 'hello\n'


def test_run_capture_swaps_exit_codes(tmp_path: Path) -> None:
    assert _sh('exit 0', swap_exit_codes=True).run_capture(tmp_path).exitcode == 42


def test_run_capture_signal(tmp_path: Path) -> None:
    result = _sh('echo partial; kill -TERM $$').run_capture(tmp_path)
    assert result.exitcode is None
    assert str(result) == 'SIGTERM'
    assert result.stdout == 'partial\n'


def test_run_capture_invalid_utf8(tmp_path: Path) -> None:
    assert _sh(r"printf '\377'").run_capture(tmp_path).stdout == '�'
