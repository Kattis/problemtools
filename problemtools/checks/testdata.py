"""Checks for a problem package's test data."""

from __future__ import annotations

import collections
import glob
import hashlib
import os
from collections.abc import Callable, Iterator
from pathlib import Path

from ..context import Context
from ..diagnostics import Diagnostics
from ..formatversion import FormatVersion
from ..judge import SubmissionResult, validate_output
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

    if metadata.is_scoring():
        _warn_reject_score(testdata, diag)

        # Whether the selected output validator might emit an arbitrary score via score.txt,
        # making a test case's score unbounded as far as _check_score_range is concerned.
        custom_scoring_possible = (
            not output_validators.uses_default(format_version, metadata) and metadata.is_custom_score_allowed()
        )
        _check_score_range(testdata, custom_scoring_possible, diag)

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
        diag,
    )

    _check_answers(testdata, context, metadata, output_validator, work_dir, diag)


def _all_groups(group: TestDataGroup) -> Iterator[TestDataGroup]:
    """`group` and all its descendant groups."""
    yield group
    for subgroup in group.get_subgroups():
        yield from _all_groups(subgroup)


def _warn_reject_score(testdata: TestDataGroup, diag: Diagnostics) -> None:
    """Warn about reject_score usage."""
    groups = list(_all_groups(testdata))

    nonzero_reject = [(g, g.config['reject_score']) for g in groups if g.config['reject_score'] != 0]
    if nonzero_reject:
        example_group, example_score = nonzero_reject[0]
        diag.warning(
            f'{len(nonzero_reject)} testcase group(s) configure a non-zero reject_score (e.g. {example_group} '
            f'has reject_score {example_score:g}); submissions with non-AC final verdict always have score 0, '
            'so this is usually a mistake'
        )


#: Score aggregators for `grading: default`, matching support/default_grader's `score_aggregators`.
#: All are monotonic non-decreasing in each argument, which is what makes _check_score_range below
#: correct: the range of an aggregate over a fixed set of children is the aggregator applied to
#: their lower bounds, and separately to their upper bounds (or, with `on_reject: break`, applied
#: to each prefix of children, since the set the aggregator sees can then vary).
_SCORE_AGGREGATORS: dict[str, Callable[[list[float]], float]] = {
    'sum': sum,
    'avg': lambda scores: sum(scores) / len(scores),
    'min': min,
    'max': max,
}


def _check_score_range(group: TestDataGroup, custom_scoring_possible: bool, diag: Diagnostics) -> tuple[float, float]:
    """Recursively check `group`'s declared score `range` against what can be inferred from its
    grading configuration and test data. Returns group's effective range."""
    children = group.items
    if group.is_root and 'ignore_sample' in group.config['grader_flags'].split():
        children = [child for child in children if not (isinstance(child, TestDataGroup) and child.datadir.name == 'sample')]

    if not children:
        aggregate = (0.0, 0.0)
    elif group.config['grading'] == 'custom':
        # A custom grader can't be reasoned about.
        aggregate = (float('-inf'), float('inf'))
    else:
        child_ranges = []
        for child in children:
            if isinstance(child, TestDataGroup):
                child_ranges.append(_check_score_range(child, custom_scoring_possible, diag))
            elif custom_scoring_possible:
                child_ranges.append((float('-inf'), float('inf')))
            else:
                accept_score, reject_score = group.config['accept_score'], group.config['reject_score']
                child_ranges.append((min(accept_score, reject_score), max(accept_score, reject_score)))

        aggregator_name = 'sum'
        for flag in group.config['grader_flags'].split():
            if flag in _SCORE_AGGREGATORS:
                aggregator_name = flag  # last one wins, matching default_grader
        aggregator = _SCORE_AGGREGATORS[aggregator_name]

        lows = [lo for lo, _hi in child_ranges]
        highs = [hi for _lo, hi in child_ranges]
        if group.config['on_reject'] == 'break':
            # A non-AC child makes submission_judge stop grading the rest of this group (see
            # SubmissionJudge._judge_group), so the aggregator may see any prefix of the children,
            # not just all of them -- e.g. an 'avg' over a shorter prefix has a smaller denominator.
            # This bound may not be realistic (e.g., the max value here is for the case where we
            # have a non-AC child which gets max score)
            aggregate = (
                min(aggregator(lows[:i]) for i in range(1, len(lows) + 1)),
                max(aggregator(highs[:i]) for i in range(1, len(highs) + 1)),
            )
        else:
            aggregate = (aggregator(lows), aggregator(highs))

    score_range = group.config['range']
    try:
        min_score, max_score = list(map(float, score_range.split()))
    except Exception:
        diag.error(f"Invalid format '{score_range}' for range: must be exactly two floats")
        return aggregate

    if min_score > max_score:
        diag.error(f"Invalid score range '{score_range}': minimum score cannot be greater than maximum score")
        return aggregate

    return _warn_score_range(group, (min_score, max_score), aggregate, diag)


def _warn_score_range(
    group: TestDataGroup, declared: tuple[float, float], aggregate: tuple[float, float], diag: Diagnostics
) -> tuple[float, float]:
    """Compare `group`'s declared score range to what its `aggregate` says can actually be achieved,
    warn about any mismatch, and return the effective (declared-trusting) range."""
    min_score, max_score = declared
    agg_min, agg_max = aggregate
    score_range = group.config['range']
    is_default_range = score_range == DEFAULT_CONFIG['range']
    if max_score < agg_min or min_score > agg_max:
        diag.warning(
            f"Declared score range '{score_range}' for {group} doesn't overlap with the computed range "
            f'[{agg_min:g}, {agg_max:g}] at all'
        )
        # We're in a bad state here, unclear what to return. Specified range probably ends up less spammy.
        return (min_score, max_score)
    elif min_score < agg_min or max_score > agg_max:
        if is_default_range:
            diag.warning(
                f'No score range declared for {group}, but a range of [{agg_min:g}, {agg_max:g}] can be '
                f"computed from its grading configuration and test data; consider adding 'range: {agg_min:g} {agg_max:g}'"
            )
        else:
            diag.warning(
                f"Declared score range '{score_range}' for {group} is looser than the computed range "
                f'[{agg_min:g}, {agg_max:g}]; consider tightening it'
            )
    elif group.is_root and is_default_range:
        # The default range -inf, inf basically never makes sense. Encourage tighter even when we can't compute a recommendation
        diag.warning(
            f'No score range declared for {group}, and none could be computed automatically; as '
            'the top-level group, its range is the overall score range for the problem -- consider '
            'declaring one explicitly'
        )
    elif group.is_root and min_score < 0:
        diag.warning(
            f"Declared score range '{score_range}' for {group} has a negative minimum; submissions with "
            'non-AC final verdict always have score 0, so a negative minimum is usually a mistake'
        )

    return (max(agg_min, min_score), min(agg_max, max_score))


def _check_group(
    group: TestDataGroup,
    context: Context,
    metadata: Metadata,
    probdir: Path,
    has_custom_grader: bool,
    has_default_grader: bool,
    input_validation: InputValidationCache,
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

    # Score range validity and tightness are checked by _check_score_range, called once for the
    # whole tree from check_testdata.

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
                diag,
            )
        else:
            _check_testcase(child, metadata, input_validation, diag)


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


def _check_answers(
    testdata: TestDataGroup,
    context: Context,
    metadata: Metadata,
    output_validator: Program,
    work_dir: Path,
    diag: Diagnostics,
) -> None:
    """Run the output validator on every judge answer file, checking that it is accepted."""
    if metadata.is_interactive() or metadata.is_multi_pass():
        return

    testcases = [tc for tc in testdata.get_all_testcases() if tc.matches_filter(context.data_filter)]
    sample = [tc for tc in testcases if tc.is_in_sample_group()]
    secret = [tc for tc in testcases if not tc.is_in_sample_group()]

    def validate(testcase: TestCase) -> SubmissionResult:
        return validate_output(
            testcase=testcase,
            submission_output=testcase.ansfile,
            output_validator=output_validator,
            metadata=metadata,
            base_dir=work_dir,
            diag=diag,
        )

    for testcase in sample:
        val_res = validate(testcase)
        if val_res.verdict != 'AC':
            diag.error(f'judge answer file got {val_res} on testcase {testcase.path}')

    results = [(testcase, validate(testcase)) for testcase in secret]
    for testcase, val_res in results:
        if val_res.verdict == 'JE':
            diag.error(f'judge answer file got {val_res} on testcase {testcase.path}')

    if rejected := [testcase for testcase, val_res in results if val_res.verdict != 'AC']:
        if any(val_res.verdict == 'AC' for _, val_res in results):
            diag.warning(
                f'judge answer file was not accepted by the output validator on {len(rejected)}/{len(secret)} secret '
                f'testcases (e.g. testcase {rejected[0].path}); this is fine if the answer files intentionally use a '
                'different format than what is expected from submissions, but is suspicious when only some of them do'
            )
        else:
            diag.info(
                f'judge answer file was not accepted by the output validator on any of the {len(secret)} secret '
                'testcases; this is fine if the answer files intentionally use a different format than what is '
                'expected from submissions'
            )


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
