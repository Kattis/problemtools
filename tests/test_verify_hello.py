import logging
import pathlib

from problemtools import checks, model
from problemtools.diagnostics import LoggingDiagnostics


def _make_diag(shortname: str) -> LoggingDiagnostics:
    return LoggingDiagnostics.create(shortname, log_level=logging.WARNING)


def test_load_hello():
    probdir = (pathlib.Path(__file__).parent / 'hello').resolve()

    diag = _make_diag('hello')
    problem = model.load_problem(probdir, diag)
    assert problem.shortname == 'hello'

    # pytest and fork don't go along very well, so just run checks that work without run
    checks.check_config(problem.metadata, problem.format_version, problem.statements, problem.testdata, diag)
    checks.check_attachments(problem.attachments, diag)
    assert diag.errors == 0

    assert problem.metadata.is_pass_fail()
    assert not problem.metadata.is_scoring()
    assert not problem.metadata.is_interactive()
    assert not problem.metadata.is_multi_pass()
    assert not problem.metadata.is_submit_answer()


def test_load_twice():
    probdir = (pathlib.Path(__file__).parent / 'hello').resolve()

    model.load_problem(probdir, _make_diag('hello'))
    model.load_problem(probdir, _make_diag('hello'))
