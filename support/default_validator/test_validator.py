#!/usr/bin/env python3
import unittest
import subprocess
import tempfile
from pathlib import Path


class TestDefaultValidator(unittest.TestCase):
    VALIDATOR_PATH = Path(__file__).parent / 'default_validator'
    TESTS_DIR = Path(__file__).parent / 'tests'

    @classmethod
    def setUpClass(cls):
        # Compile the validator before running tests.
        try:
            subprocess.run(['make', 'default_validator'], cwd=Path(__file__).parent, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f'Failed to compile default_validator: {e.stderr}') from e

        if not cls.VALIDATOR_PATH.is_file():
            raise FileNotFoundError(f'Validator executable not found at {cls.VALIDATOR_PATH} after compilation.')

    def _run_test_case(self, test_dir: Path):
        judge_ans = test_dir / 'judge.ans'
        user_out = test_dir / 'user.out'
        args_file = test_dir / 'args.txt'
        expected_exit_code_file = test_dir / 'expected_exit_code.txt'
        expected_message_file = test_dir / 'expected_message.txt'

        self.assertTrue(judge_ans.is_file(), f'judge.ans not found in {test_dir}')
        self.assertTrue(user_out.is_file(), f'user.out not found in {test_dir}')
        self.assertTrue(expected_exit_code_file.is_file(), f'expected_exit_code.txt not found in {test_dir}')

        args = []
        if args_file.is_file():
            args = args_file.read_text().split()

        expected_exit_code = int(expected_exit_code_file.read_text().strip())

        with tempfile.TemporaryDirectory() as feedback_dir, open(user_out, 'r') as user_out_f:
            # The validator expects judge_in, judge_ans, feedback_dir
            # judge_in is not used by the validator for comparison, so we can pass a dummy file.
            with tempfile.NamedTemporaryFile() as dummy_judge_in:
                cmd = [str(self.VALIDATOR_PATH), str(dummy_judge_in.name), str(judge_ans), feedback_dir, *args]

                result = subprocess.run(cmd, stdin=user_out_f, capture_output=True, text=True)

                self.assertEqual(result.returncode, expected_exit_code, f'Wrong exit code. Stderr: {result.stderr}')

                if expected_message_file.is_file():
                    judgemessage_path = Path(feedback_dir) / 'judgemessage.txt'
                    self.assertTrue(judgemessage_path.is_file(), 'judgemessage.txt was not created')
                    actual_message = judgemessage_path.read_text().strip()
                    expected_message = expected_message_file.read_text().strip()
                    self.assertEqual(actual_message, expected_message)


# --- Dynamic Test Creation ---
def create_test_method(test_dir):
    """Creates a test method for a given test case directory."""

    def test_method(self):
        self._run_test_case(test_dir)

    return test_method


if TestDefaultValidator.TESTS_DIR.is_dir():
    test_cases = [d for d in TestDefaultValidator.TESTS_DIR.iterdir() if d.is_dir() and d.name.startswith('test_')]
    for test_case_dir in test_cases:
        test_name = test_case_dir.name
        test_method = create_test_method(test_case_dir)
        setattr(TestDefaultValidator, test_name, test_method)
# --- End of Dynamic Test Creation ---


if __name__ == '__main__':
    unittest.main()
