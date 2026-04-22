import logging
import pathlib
import problemtools.verifyproblem as verify
from problemtools.diagnostics import LoggingDiagnostics


def _make_diag(shortname: str) -> LoggingDiagnostics:
    return LoggingDiagnostics.create(shortname, log_level=logging.WARNING)


def test_load_hello():
    directory = pathlib.Path(__file__).parent / 'hello'
    string = str(directory.resolve())

    context = verify.Context()

    with verify.Problem(string, _make_diag('hello')) as p:
        p.load()
        assert p.shortname == 'hello'
        # pytest and fork don't go along very well, so just run aspects that work without run
        assert p.config.check(context)
        assert p.attachments.check(context)
        assert p.is_pass_fail()
        assert not p.is_scoring()
        assert not p.is_interactive()
        assert not p.is_multi_pass()
        assert not p.is_submit_answer()


def test_load_twice():
    directory = pathlib.Path(__file__).parent / 'hello'
    string = str(directory.resolve())

    with verify.Problem(string, _make_diag('hello')) as p:
        p.load()
        p.load()
