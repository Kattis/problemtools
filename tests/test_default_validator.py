#!/usr/bin/env python3
import pytest
import subprocess
import tempfile
from pathlib import Path

# The validator executable path, resolved relative to this test file.
VALIDATOR_PATH = Path(__file__).parent.parent / 'support' / 'default_validator' / 'default_validator'
# The directory containing test cases for the validator.
TESTS_DIR = Path(__file__).parent / 'default_validator_tests'


@pytest.fixture(scope='session')
def validator() -> Path:
    """
    A session-scoped fixture to compile the default_validator executable.
    This ensures the validator is compiled only once before any tests run.
    It returns the path to the compiled executable.
    """
    validator_parent_dir = VALIDATOR_PATH.parent
    # Compile the validator using 'make'.
    try:
        subprocess.run(
            ['make', 'default_validator'], cwd=validator_parent_dir, check=True, capture_output=True, text=True, encoding='utf-8'
        )
    except subprocess.CalledProcessError as e:
        pytest.fail(f'Failed to compile default_validator: {e.stderr}', pytrace=False)
    except FileNotFoundError:
        pytest.fail("'make' command not found. Please ensure 'make' is installed and in your PATH.", pytrace=False)

    if not VALIDATOR_PATH.is_file():
        pytest.fail(f'Validator executable not found at {VALIDATOR_PATH} after compilation.', pytrace=False)

    return VALIDATOR_PATH


def discover_test_cases():
    """
    Finds and returns a list of all test case directories.
    A test case directory is expected to start with 'test_'.
    """
    if not TESTS_DIR.is_dir():
        return []
    return [d for d in TESTS_DIR.iterdir() if d.is_dir() and d.name.startswith('test_')]


@pytest.mark.parametrize('test_dir', discover_test_cases(), ids=lambda d: d.name)
def test_default_validator(validator: Path, test_dir: Path):
    """
    Runs a single validator test case.
    The test is parametrized to run for each directory discovered by `discover_test_cases`.
    """
    judge_ans = test_dir / 'judge.ans'
    user_out = test_dir / 'user.out'
    args_file = test_dir / 'args.txt'
    expected_exit_code_file = test_dir / 'expected_exit_code.txt'
    expected_message_file = test_dir / 'expected_message.txt'

    assert judge_ans.is_file(), f"'judge.ans' not found in {test_dir}"
    assert user_out.is_file(), f"'user.out' not found in {test_dir}"
    assert expected_exit_code_file.is_file(), f"'expected_exit_code.txt' not found in {test_dir}"

    args = []
    if args_file.is_file():
        args_text = args_file.read_text(encoding='utf-8').strip()
        if args_text:
            args = args_text.split()

    expected_exit_code = int(expected_exit_code_file.read_text(encoding='utf-8').strip())

    with tempfile.TemporaryDirectory() as feedback_dir_str, open(user_out, 'rb') as user_out_f:
        feedback_dir = Path(feedback_dir_str)
        # The validator expects judge_in, judge_ans, feedback_dir.
        # judge_in is not currently used by the validator for comparison, so we pass a dummy file.
        with tempfile.NamedTemporaryFile() as dummy_judge_in:
            cmd = [str(validator), str(dummy_judge_in.name), str(judge_ans), str(feedback_dir), *args]

            result = subprocess.run(cmd, stdin=user_out_f, capture_output=True, text=True, encoding='utf-8')

            assert result.returncode == expected_exit_code, f'Wrong exit code. Stderr: {result.stderr}'

            judgemessage_path = feedback_dir / 'judgemessage.txt'
            if expected_message_file.is_file():
                assert judgemessage_path.is_file(), "'judgemessage.txt' was not created but was expected."
                actual_message = judgemessage_path.read_bytes()
                expected_message = expected_message_file.read_bytes()
                assert actual_message == expected_message, 'The validation message did not match the expected message.'
            else:
                # If no message is expected, assert that no message was generated.
                if judgemessage_path.is_file():
                    actual_message = judgemessage_path.read_bytes()
                    assert not actual_message, f'A validation message was generated but none was expected: {actual_message}'
