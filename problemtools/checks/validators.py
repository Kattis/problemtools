"""Checks for a problem package's input/output validators."""

from __future__ import annotations

import os
import random
import re
import string
import tempfile
from collections.abc import Callable
from pathlib import Path
from re import Match

from ..diagnostics import Diagnostics
from ..formatversion import FormatVersion
from ..judge import SubmissionResult, validate_output
from ..metadata import Metadata
from ..model import InputValidators, OutputValidators, TestCase, TestDataGroup
from ..run import ProgramError, SourceCode

# Junk data. The validator should reject these cases
_JUNK_CASES: list[tuple[str, bytes]] = [
    ('an empty file', b''),
    ('a binary file with random bytes', random.Random(42).randbytes(1024)),
    ('a text file with the ASCII characters 32 up to 127', bytes(range(32, 127))),
    (
        'a random text file with printable ASCII characters',
        bytes(random.Random(42).choices(string.printable.encode('utf8'), k=200)),
    ),
]

# Try to crash the output validator, causing a judge error
_JUNK_CASES_CRASH = [
    ('a file with the number -1', b'-1'),
    ('a file with the number 2147483647', b'2147483647'),
    ('a file with the number 2147483648', b'2147483648'),
    ('a file with the number 9223372036854775808', b'9223372036854775808'),
    ('a file with the number 0', b'0'),
    ('a file with the number 1', b'1'),
    ('a file with the number 1.0', b'1.0'),
    ('a file with the string "a"', b'a'),
    ('a file with the contents "2\\n-1 1"', b'2\n-1 1'),
    ('a file with the contents "2\\n1"', b'2\n1'),
    ('a file with the contents "1\\n-1 1"', b'1\n-1 1'),
    ('a file with the contents "1\\na"', b'1\na'),
    ('a file with the contents "(()"', b'(()'),
    ('a file with the contents "1-"', b'1-'),
    ('a file with the contents "1/0"', b'1/0'),
    ('a file with the contents "2\\n<"', b'2\n<'),
    ('a file with the contents "NaN"', b'NaN'),
    ('a file with the contents "inf"', b'inf'),
    ('a file with the contents "\\x00"', b'\x00'),
    ('a file with the contents "\\x80"', b'\x80'),
]


def _build_junk_modifier(
    desc: str, pattern: str, repl: str | Callable[[Match[str]], str]
) -> tuple[str, Callable[[str], bool], Callable[[str], str]]:
    p = re.compile(pattern)
    return (desc, lambda text: p.search(text) is not None, lambda text: p.sub(repl, text))


_JUNK_MODIFICATIONS = [
    _build_junk_modifier('spaces added where there already is whitespace', r'\s', lambda m: m.group(0) + ' '),
    _build_junk_modifier('spaces added to the end of a line', r'\n', lambda m: m.group(0) + ' '),
    _build_junk_modifier('newlines added where there already are newlines', '\n', lambda m: '\n\n'),
    _build_junk_modifier('leading zeros added to integers', r'(^|[^.]\b)([0-9]+)\b', r'\g<1>0000000000\g<2>'),
    _build_junk_modifier('trailing zeros added to real number decimal portion', r'\.[0-9]+\b', r'\g<0>0000000000'),
    (
        'random junk added to the end of the file',
        lambda f: True,
        lambda f: f + ''.join(random.choice(string.printable) for _ in range(200)),
    ),
]


# Temporary helpers to keep code structure as similar as possible to old code from
# verifyproblem when extracting this to a separate module; ProblemAspect still owns the
# "real" versions of these, used by parts not yet extracted (e.g. ProblemStatement, ProblemConfig).
def _warn_directory(format: FormatVersion, probdir: Path, name: str, prop: str, diag: Diagnostics) -> None:
    good_dir = getattr(format, prop)
    bad_dirs = {getattr(version, prop) for version in FormatVersion} - {good_dir}
    for directory in bad_dirs:
        if (probdir / directory).exists():
            diag.warning(f'Found directory "{directory}". Version {format} looks for {name} in "{good_dir}"')


def _error_in_2023_07(format: FormatVersion, diag: Diagnostics, msg: str, additional_info: str | None = None) -> None:
    if format is FormatVersion.LEGACY:
        diag.warning(msg, additional_info)
    else:
        diag.error(msg, additional_info)


def check_input_validators(validators: InputValidators, testdata: TestDataGroup, work_dir: str, diag: Diagnostics) -> None:
    """Run all checks on a problem's input format validators."""
    if validators.uses_old_path:
        diag.warning('input_format_validators is a deprecated name; please use input_validators instead')

    errors_before = diag.errors
    if len(validators.validators) == 0:
        diag.error('No input format validators found')

    for val in validators.validators:
        try:
            success, msg = val.compile()
            if not success:
                diag.error(f'Compile error for {val}', msg)
        except ProgramError as e:
            diag.error(str(e))

    # Only sanity check input validators if they all actually compiled
    if diag.errors != errors_before:
        return

    all_flags: set[str] = set()

    def collect_flags(group: TestDataGroup, flags: set[str]) -> None:
        if len(group.get_testcases()) > 0:
            flags.add(group.config['input_validator_flags'])
        for subgroup in group.get_subgroups():
            collect_flags(subgroup, flags)

    collect_flags(testdata, all_flags)

    fd, file_name = tempfile.mkstemp()
    os.close(fd)
    for desc, case in _JUNK_CASES:
        with open(file_name, 'wb') as f:
            f.write(case)
        for flags_str in all_flags:
            flags = flags_str.split()
            for val in validators.validators:
                status, _ = val.run(file_name, args=flags, work_dir=work_dir)
                if os.WEXITSTATUS(status) != 42:
                    break
            else:
                diag.warning(f'No validator rejects {desc} with flags "{" ".join(flags)}"')

    def modified_input_validates(applicable: Callable[[str], bool], modifier: Callable[[str], str]) -> bool:
        for testcase in testdata.get_all_testcases():
            try:
                with open(testcase.infile) as infile:
                    infile_data = infile.read()
                if not applicable(infile_data):
                    continue
            except UnicodeDecodeError:
                continue

            with open(file_name, 'wb') as f:
                f.write(modifier(infile_data).encode('utf8'))

            for flags_str in all_flags:
                flags = flags_str.split()
                for val in validators.validators:
                    status, _ = val.run(file_name, args=flags, work_dir=work_dir)
                    if os.WEXITSTATUS(status) != 42:
                        # expected behavior; validator rejects modified input
                        return False

            # we found a file we could modify, and all validators
            # accepted the modifications
            return True

        # no files were modifiable
        return False

    for desc, applicable, modifier in _JUNK_MODIFICATIONS:
        if modified_input_validates(applicable, modifier):
            diag.warning(f'No validator rejects {desc}')

    os.unlink(file_name)


def check_testcase_input(validators: InputValidators, testcase: TestCase, work_dir: str, diag: Diagnostics) -> None:
    """Run the (already checked) input validators against a single test case's input file."""
    flags = testcase.input_validator_flags

    for val in validators.validators:
        # A validator that failed to compile was already reported by check_input_validators; skip it.
        success, _ = val.compile()
        if not success:
            continue

        with tempfile.NamedTemporaryFile() as outfile, tempfile.NamedTemporaryFile() as errfile:
            status, _ = val.run(str(testcase.infile), outfile.name, errfile.name, args=flags, work_dir=work_dir)
            if not os.WIFEXITED(status):
                emsg = f'Input format validator {val} crashed on input {testcase.infile}'
            elif os.WEXITSTATUS(status) != 42:
                emsg = f'Input format validator {val} did not accept input {testcase.infile}, exit code: {os.WEXITSTATUS(status)}'
            else:
                continue
            validator_stdout = outfile.read().decode('utf-8', 'replace')
            validator_stderr = errfile.read().decode('utf-8', 'replace')
            validator_output = '\n'.join(out for out in [validator_stdout, validator_stderr] if out)
            diag.error(emsg, validator_output)


def check_output_validators(
    validators: OutputValidators,
    format: FormatVersion,
    metadata: Metadata,
    testdata: TestDataGroup,
    probdir: Path,
    work_dir: str,
    diag: Diagnostics,
) -> None:
    """Run all checks on a problem's output validators."""
    _warn_directory(format, probdir, 'output validators', 'output_validator_directory', diag)

    errors_before = diag.errors

    selected = validators.select(format, metadata)

    if len(validators.validators) > 1:
        _error_in_2023_07(format, diag, f'Support for multiple output validators has been dropped. will only use {selected}')

    if selected is None:
        diag.fatal('Unable to locate default validator')

    safe_output_validator_languages = {'c', 'cpp', 'python3'}
    if isinstance(selected, SourceCode) and selected.language.lang_id not in safe_output_validator_languages:
        _error_in_2023_07(
            format,
            diag,
            f'Output validator in {selected.language.name}. Only {safe_output_validator_languages} are standardized. '
            'Check carefully if your CCS supports more (Kattis does not).',
        )

    if validators.uses_default(format, metadata) and validators.validators:
        diag.error('There are validator programs but problem.yaml has validation = "default"')
    elif not validators.uses_default(format, metadata) and not validators.validators:
        diag.fatal('problem.yaml specifies custom validator but no validator programs found')

    try:
        success, msg = selected.compile()
        if not success:
            diag.fatal(f'Compile error for output validator {selected}', msg)
    except ProgramError as e:
        diag.fatal(f'Compile error for output validator {selected}', str(e))

    # Only sanity check output validators if they all actually compiled
    if diag.errors != errors_before:
        return

    def run_junk_case(case_desc: str, junk_content: bytes, testcases: list[TestCase]) -> list[SubmissionResult]:
        results = []
        with tempfile.NamedTemporaryFile(mode='wb') as f:
            f.write(junk_content)
            f.flush()
            for testcase in testcases:
                result = validate_output(
                    testcase=testcase,
                    submission_output=Path(f.name),
                    output_validator=selected,
                    metadata=metadata,
                    base_dir=Path(work_dir),
                    diag=diag,
                )
                results.append(result)
                if result.verdict == 'JE':
                    diag.error(f'{case_desc} as output on test case {testcase} gave {result}')
                    break
        return results

    # Junk cases that the output validator should reject
    for desc, junk_case_content in _JUNK_CASES:
        results = run_junk_case(desc, junk_case_content, testdata.get_all_testcases())
        rejected = any(result.verdict != 'AC' for result in results)
        if not rejected:
            diag.warning(f'{desc} gets AC')

    # Malformed cases that a poorly-written output validator might crash on
    # Note that these might be valid output, so we only check if it crashes.
    # These bugs are rarely dependent on the actual test case, so we just
    # run on a few to keep things speedy.
    test_cases = testdata.get_all_testcases()[:3]
    for desc, junk_case_content in _JUNK_CASES_CRASH:
        run_junk_case(desc, junk_case_content, test_cases)
