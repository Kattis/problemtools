from problemtools import checks, model
from problemtools.diagnostics import Diagnostics
from tests.conftest import example_directory


def test_load_hello(diag: Diagnostics) -> None:
    probdir = example_directory('hello')

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

    assert len(problem.testdata.get_all_testcases()) == 1, 'Hello should have exactly 1 test case'
    assert problem.graders.grader is None, 'Hello uses the default grader'
    assert problem.output_validators.uses_default(problem.format_version, problem.metadata), 'Hello uses the default validator'


def test_load_twice(diag: Diagnostics) -> None:
    probdir = example_directory('hello')

    model.load_problem(probdir, diag)
    model.load_problem(probdir, diag)
