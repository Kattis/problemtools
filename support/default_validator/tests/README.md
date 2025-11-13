# Default Validator Tests

This directory contains test cases for the `default_validator`. Each test case resides in its own subdirectory, named `test_<description>` (e.g., `test_simple_ac` for a simple test that should be Accepted, or `test_float_wa` for a float comparison that should result in Wrong Answer).

## Structure of a Test Case

Each test case directory should contain the following files:

*   `judge.ans`: The reference answer file. This is what the `default_validator` will compare against.
*   `user.out`: The user's output file that the `default_validator` will evaluate.
*   `args.txt`: (Optional) A plain text file containing command-line arguments to be passed to the `default_validator`. Each argument should be space-separated. For example: `case_sensitive float_absolute_tolerance 0.001`.
*   `expected_exit_code.txt`: Contains the expected exit code of the `default_validator` for this test case (e.g., `42` for Accepted, `43` for Wrong Answer).
*   `expected_message.txt`: (Optional) Contains the exact error message expected from the `default_validator` if the test case results in a Wrong Answer. This file should only exist if a message is expected.

## Adding a New Test Case

To add a new test case:

1.  Create a new directory within `support/default_validator/tests/` (e.g., `tests/test_my_new_feature_ac`).
2.  Inside this new directory, create `judge.ans` and `user.out` files with the desired content for your test.
3.  If your test requires specific command-line arguments for the `default_validator` (e.g., `case_sensitive`, `float_tolerance`), create an `args.txt` file in the directory with these arguments.
4.  Use the `run_and_generate_expected.py` script to automatically generate `expected_exit_code.txt` and optionally `expected_message.txt`:
    ```bash
    cd support/default_validator/
    ./run_and_generate_expected.py tests/test_my_new_feature_ac
    ```
    This script will run the `default_validator` with your provided inputs and arguments, capture its exit code and any feedback message, and write them to the respective `expected_*.txt` files.

## Updating an Existing Test Case

If you modify `judge.ans`, `user.out`, or `args.txt` for an existing test case, you need to update its expected output:

```bash
cd support/default_validator/tests/
./run_and_generate_expected.py test_case_to_update
```

This will regenerate the `expected_exit_code.txt` and `expected_message.txt` files based on your changes. Check with `git diff` and commit if the changes are what you expected.

## Running the Tests

To run all the test cases for `default_validator`:

```bash
cd support/default_validator/
./test_validator.py
```
