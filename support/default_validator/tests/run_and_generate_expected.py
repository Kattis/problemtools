#!/usr/bin/env python3
#
# A script to run the default_validator on a test case and generate the expected output files.
#
# Usage: ./run_and_generate_expected.py <path_to_test_directory>
#
# The test directory must contain:
# - judge.ans: The correct output.
# - user.out: The output to validate.
# - args.txt: (Optional) arguments to pass to the validator.
#
# The script will create:
# - expected_exit_code.txt: The exit code of the validator.
# - expected_message.txt: The message from the validator, if any.
#

import argparse
import subprocess
import tempfile
from pathlib import Path
import sys


def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Run default_validator and generate expected output files.')
    parser.add_argument('test_dir', type=Path, help='Path to the test directory.')
    args = parser.parse_args()

    test_dir: Path = args.test_dir

    if not test_dir.is_dir():
        print(f'Error: Test directory not found at {test_dir}', file=sys.stderr)
        sys.exit(1)

    validator_path = Path(__file__).parent.parent / 'default_validator'
    if not validator_path.is_file():
        print('Compiling default_validator...', file=sys.stderr)
        try:
            subprocess.run(
                ['make', 'default_validator'],
                cwd=validator_path.parent,
                check=True,
                capture_output=True,
                text=True,
                encoding='utf-8',
            )
        except subprocess.CalledProcessError as e:
            print(f'Failed to compile default_validator: {e.stderr}', file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f'An unexpected error occurred during compilation: {e}', file=sys.stderr)
            sys.exit(1)

        if not validator_path.is_file():
            print(f'Validator executable not found at {validator_path} after compilation.', file=sys.stderr)
            sys.exit(1)

    judge_ans = test_dir / 'judge.ans'
    user_out = test_dir / 'user.out'
    args_file = test_dir / 'args.txt'

    if not judge_ans.is_file():
        print(f'Error: judge.ans not found in {test_dir}', file=sys.stderr)
        sys.exit(1)
    if not user_out.is_file():
        print(f'Error: user.out not found in {test_dir}', file=sys.stderr)
        sys.exit(1)

    validator_args = []
    if args_file.is_file():
        args_text = args_file.read_text(encoding='utf-8').strip()
        if args_text:
            validator_args = args_text.split()

    with tempfile.TemporaryDirectory() as feedback_dir:
        # The validator expects judge_in, judge_ans, feedback_dir
        # judge_in is not used by the validator for comparison, so we can pass a dummy file.
        with tempfile.NamedTemporaryFile() as dummy_judge_in, open(user_out, 'r', encoding='utf-8') as user_out_f:
            cmd = [str(validator_path), str(dummy_judge_in.name), str(judge_ans), feedback_dir, *validator_args]

            result = subprocess.run(cmd, stdin=user_out_f, capture_output=True, text=True, encoding='utf-8')

            # Write expected_exit_code.txt
            (test_dir / 'expected_exit_code.txt').write_text(str(result.returncode) + '\n', encoding='utf-8')
            print(f'Wrote exit code {result.returncode} to expected_exit_code.txt')

            # Write expected_message.txt if a message was generated
            judgemessage_path = Path(feedback_dir) / 'judgemessage.txt'
            if judgemessage_path.is_file():
                message = judgemessage_path.read_text(encoding='utf-8')
                if message:
                    (test_dir / 'expected_message.txt').write_text(message, encoding='utf-8')
                    print('Wrote message to expected_message.txt')
            else:
                # If there's no message, we should remove any existing expected_message.txt
                expected_message_file = test_dir / 'expected_message.txt'
                if expected_message_file.is_file():
                    expected_message_file.unlink()
                    print('Removed existing expected_message.txt as no message was generated.')


if __name__ == '__main__':
    main()
