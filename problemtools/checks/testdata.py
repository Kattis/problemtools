"""Checks for a problem package's test data."""

from __future__ import annotations

import collections
import glob
import hashlib
import os
from pathlib import Path

from ..context import Context
from ..diagnostics import Diagnostics, VerifyError
from ..formatversion import FormatVersion
from ..judge import validate_output
from ..metadata import Metadata
from ..model import (
    DEFAULT_CONFIG,
    DEFAULT_GRADER,
    SCORING_ONLY_KEYS,
    Graders,
    InputValidators,
    OutputValidators,
    TestCase,
    TestDataGroup,
)
from ..run import Program
from .validators import InputValidationCache


def check_testdata(
    testdata: TestDataGroup,
    context: Context,
    metadata: Metadata,
    probdir: Path,
    graders: Graders,
    input_validators: InputValidators,
    output_validators: OutputValidators,
    format_version: FormatVersion,
    work_dir: Path,
    diag: Diagnostics,
) -> None:
    """Run all checks on a problem's test data."""
    output_validator = output_validators.select(format_version, metadata)
    if output_validator is None:
        diag.fatal('Unable to locate default validator')

    has_custom_grader = graders.grader is not None
    has_default_grader = DEFAULT_GRADER is not None

    input_validation = InputValidationCache(input_validators, work_dir)
    input_validation.precompute(testdata, context)

    _check_group(
        testdata,
        context,
        metadata,
        probdir,
        has_custom_grader,
        has_default_grader,
        input_validation,
        output_validator,
        work_dir,
        diag,
    )


def _check_group(
    group: TestDataGroup,
    context: Context,
    metadata: Metadata,
    probdir: Path,
    has_custom_grader: bool,
    has_default_grader: bool,
    input_validation: InputValidationCache,
    output_validator: Program,
    work_dir: Path,
    diag: Diagnostics,
) -> None:
    if group.config['grading'] not in ['default', 'custom']:
        diag.error('Invalid grading policy in testdata.yaml')

    if group.config['grading'] == 'custom' and not has_custom_grader:
        diag.fatal(f'{group} has custom grading but no custom graders provided')
    if group.config['grading'] == 'default' and not has_default_grader:
        diag.fatal(f'{group} has default grading but I could not find default grader')

    if group.config['grading'] == 'default' and 'ignore_sample' in group.config['grader_flags'].split():
        if not group.is_root:
            diag.error("'grader_flags: ignore_sample' is specified, but that flag is only allowed at top level")
        elif group.config['on_reject'] == 'break':
            diag.error(
                "'grader_flags: ignore_sample' is specified, but 'on_reject: break' may cause secret data not to be judged"
            )

    for field in group.config:
        if field not in DEFAULT_CONFIG:
            diag.warning(f"Unknown key '{field}' in '{group.datadir / 'testdata.yaml'}'")

    if not metadata.is_scoring():
        for key in SCORING_ONLY_KEYS:
            if group.config.get(key) is not None:
                diag.error(f"Key '{key}' is only applicable for scoring problems, this is a pass-fail problem")

    if group.config['on_reject'] not in ['break', 'continue']:
        diag.error(f"Invalid value '{group.config['on_reject']}' for on_reject policy")

    if metadata.is_scoring():
        # Check grading
        try:
            score_range = group.config['range']
            min_score, max_score = list(map(float, score_range.split()))
            if min_score > max_score:
                diag.error(f"Invalid score range '{score_range}': minimum score cannot be greater than maximum score")
        except VerifyError:
            raise
        except Exception:
            diag.error(f"Invalid format '{score_range}' for range: must be exactly two floats")

    if group.is_root:
        seen_secret = False
        seen_sample = False
        for item in group.items:
            if not isinstance(item, TestDataGroup):
                diag.error("Can't have individual test data files at top level")
            else:
                name = item.datadir.name
                if name == 'secret':
                    seen_secret = True
                elif name == 'sample':
                    seen_sample = True
                else:
                    diag.error('Test data at top level can only have the groups sample and secret')
                    diag.debug(str(group.items))
        if not seen_secret:
            diag.error('No secret data provided')
        if not seen_sample:
            diag.warning('No sample data provided')

        hashes = collections.defaultdict(list)
        for root, _dirs, files in os.walk(group.datadir):
            for filename in files:
                filepath = os.path.join(root, filename)
                if filepath.endswith('.in') and not os.path.islink(filepath):
                    md5 = hashlib.md5(usedforsecurity=False)
                    with open(filepath, 'rb') as f:
                        for buf in iter(lambda: f.read(1024), b''):
                            md5.update(buf)
                    filehash = md5.digest()
                    hashes[filehash].append(os.path.relpath(filepath, probdir))
        for files in hashes.values():
            if len(files) > 1:
                diag.warning(f"Identical input files: '{files!s}'")

    infiles = glob.glob(os.path.join(str(group.datadir), '*.in'))
    ansfiles = glob.glob(os.path.join(str(group.datadir), '*.ans'))

    for infile in infiles:
        if os.path.isdir(infile):
            continue
        if f'{infile[:-3]}.ans' not in ansfiles:
            diag.error(f"No matching answer file for input '{infile}'")
    for ansfile in ansfiles:
        if os.path.isdir(ansfile):
            continue
        if f'{ansfile[:-4]}.in' not in infiles:
            diag.error(f"No matching input file for answer '{ansfile}'")

    if not group.get_subgroups() and not group.get_testcases():
        if group.datadir.name != 'sample':
            diag.error(f'Testcase group {group.datadir} exists, but does not contain any testcases')
        else:
            if not (
                (metadata.is_interactive() or metadata.is_multi_pass())
                and glob.glob(os.path.join(str(group.datadir), '*.interaction'))
            ):
                diag.warning(f'Sample testcase group {group.datadir} exists, but does not contain any testcases')

    last_testgroup_name = ''
    for subgroup in group.get_subgroups():
        name = os.path.relpath(subgroup.datadir, probdir)
        if _natural_sort_le(name, last_testgroup_name):
            diag.warning(f"Test data group '{last_testgroup_name}' will be ordered before '{name}'; consider zero-padding")
        last_testgroup_name = name

    for child in group.items:
        if not child.matches_filter(context.data_filter):
            continue
        if isinstance(child, TestDataGroup):
            _check_group(
                child,
                context,
                metadata,
                probdir,
                has_custom_grader,
                has_default_grader,
                input_validation,
                output_validator,
                work_dir,
                diag,
            )
        else:
            _check_testcase(child, metadata, input_validation, output_validator, work_dir, diag)


def _natural_sort_le(a: str, b: str) -> bool:
    """Whether a <= b according to a natural sorting where numeric components are compactified,
    so that e.g. "a" < "a1" < "a2" < "a10" = "a010" < "a10a"."""
    a += '\0'
    b += '\0'
    i = j = 0

    def parse_num(s: str, i: int) -> tuple[int, int]:
        ret = 0
        while ord('0') <= ord(s[i]) <= ord('9'):
            ret = ret * 10 + ord(s[i]) - ord('0')
            i += 1
        return ret, i

    while i < len(a) and j < len(b):
        if ord('0') <= ord(a[i]) <= ord('9') and ord('0') <= ord(b[j]) <= ord('9'):
            anum, i = parse_num(a, i)
            bnum, j = parse_num(b, j)
            if anum == bnum:
                continue
            return anum < bnum
        if a[i] == b[j]:
            i += 1
            j += 1
            continue
        return a[i] < b[j]
    return True


def _check_testcase(
    testcase: TestCase,
    metadata: Metadata,
    input_validation: InputValidationCache,
    output_validator: Program,
    work_dir: Path,
    diag: Diagnostics,
) -> None:
    _check_newlines(testcase.infile, diag)
    _check_newlines(testcase.ansfile, diag)
    _check_size_limits(testcase.infile, diag)
    _check_size_limits(testcase.ansfile, diag)
    input_validation.check(testcase, diag)
    anssize = testcase.ansfile.stat().st_size / 1024.0 / 1024.0
    outputlim = metadata.limits.output
    if anssize > outputlim:
        diag.error(
            f'Answer file ({anssize:.1f} MiB) is larger than output limit ({outputlim} MiB), you need to increase output limit'
        )
    elif 2 * anssize > outputlim:
        diag.warning(
            f'Answer file ({anssize:.1f} MiB) is within 50% of output limit ({outputlim} MiB), you might want to increase output limit'
        )
    if not metadata.is_interactive() and not metadata.is_multi_pass():
        val_res = validate_output(
            testcase=testcase,
            submission_output=testcase.ansfile,
            output_validator=output_validator,
            metadata=metadata,
            base_dir=work_dir,
            diag=diag,
        )
        if val_res.verdict != 'AC':
            if testcase.is_in_sample_group():
                diag.error(f'judge answer file got {val_res} on testcase {testcase.path}')
            else:
                diag.warning(f'judge answer file got {val_res} on testcase {testcase.path}')


def _check_newlines(filename: Path, diag: Diagnostics) -> None:
    rawdata = filename.read_bytes()
    try:
        data = rawdata.decode('utf-8', 'strict')
    except UnicodeDecodeError:
        diag.warning(f'The file {filename} could not be decoded as utf-8')
        return
    if data.find('\r') != -1:
        diag.warning(f'The file {filename} contains non-standard line breaks.')
    if len(data) > 0 and data[-1] != '\n':
        diag.warning(f"The file {filename} does not end with '\\n'.")


def _check_size_limits(filename: Path, diag: Diagnostics) -> None:
    filesize = filename.stat().st_size / 1024.0 / 1024.0
    if filesize > 1000:
        diag.error(f'The file {filename} ({filesize:.1f} MiB) is larger than 1000 MiB and can not be installed.')
    elif filesize > 100:
        diag.warning(
            f'The file {filename} ({filesize:.1f} MiB) is larger than 100 MiB. This may cause performance issues and is not recommended.'
        )
