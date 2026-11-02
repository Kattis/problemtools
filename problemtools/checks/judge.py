"""Checks that a problem is supported by the judge system described by judge.yaml.

These are not checks against the problem format specification, so they only give warnings.
"""

from __future__ import annotations

import math
from typing import Any

from ..config import ConfigError
from ..diagnostics import Diagnostics
from ..judge_config import JudgeConfig, LimitMaxima, load_judge_config
from ..metadata import Metadata
from ..model import EntryKind, Files, TestDataGroup

_MIB = 1024 * 1024

_LIMITS = {
    'memory': ('Memory limit', 'MiB'),
    'output': ('Output limit', 'MiB'),
    'code': ('Code size limit', 'KiB'),
    'compilation_time': ('Compilation time limit', 's'),
    'compilation_memory': ('Compilation memory limit', 'MiB'),
    'validation_time': ('Validation time limit', 's'),
    'validation_memory': ('Validation memory limit', 'MiB'),
    'validation_output': ('Validation output limit', 'MiB'),
}
assert set(_LIMITS) == set(LimitMaxima.model_fields)


def check_judge(metadata: Metadata, files: Files, testdata: TestDataGroup, diag: Diagnostics) -> None:
    """Run all checks that the problem is supported by the judge system.

    The judge system is described by judge.yaml, using the problem's parent directory as
    an extra override location."""
    try:
        judge_config = load_judge_config(files.root.parent)
    except ConfigError as e:
        diag.error(str(e))
        return
    if not judge_config.enabled:
        diag.msg('Not checking judge compatibility (disabled in judge.yaml)')
        return
    diag.msg(f'Checking compatibility with {judge_config.name}')
    shortname = files.root.name
    if judge_config.max_shortname_length is not None and len(shortname) > judge_config.max_shortname_length:
        diag.warning(
            f"Problem short name '{shortname}' is {len(shortname)} characters long, "
            f'above what {judge_config.name} normally supports ({judge_config.max_shortname_length} characters)'
        )
    _check_file_sizes(judge_config, files, testdata, diag)
    _check_config(judge_config, metadata, testdata, diag)


def _check_file_sizes(judge_config: JudgeConfig, files: Files, testdata: TestDataGroup, diag: Diagnostics) -> None:
    if judge_config.max_file_size is not None:
        for path in files.walk(files.root, EntryKind.FILE):
            size = path.stat().st_size
            if size > judge_config.max_file_size * _MIB:
                diag.warning(
                    f'File {path.relative_to(files.root.parent)} is {size / _MIB:.1f} MiB, '
                    f'above what {judge_config.name} normally supports ({judge_config.max_file_size} MiB)'
                )

    if judge_config.max_testdata_size is not None:
        # Count files with identical content once.
        size_by_digest: dict[bytes, int] = {}
        for testcase in testdata.get_all_testcases():
            size_by_digest[testcase.input_sha256] = testcase.infile.stat().st_size
            size_by_digest[testcase.answer_sha256] = testcase.ansfile.stat().st_size
        total = sum(size_by_digest.values())
        if total > judge_config.max_testdata_size * _MIB:
            diag.warning(
                f'Test data input and answer files are {total / _MIB:.1f} MiB in total (counting identical files once), '
                f'above what {judge_config.name} normally supports ({judge_config.max_testdata_size} MiB)'
            )


def _check_config(judge_config: JudgeConfig, metadata: Metadata, testdata: TestDataGroup, diag: Diagnostics) -> None:
    name = judge_config.name

    for key, (description, unit) in _LIMITS.items():
        maximum = getattr(judge_config.limits, key)
        value = getattr(metadata.limits, key)
        if maximum is not None and value > maximum:
            diag.warning(
                f'{description} (limits.{key}) is {value} {unit}, above what {name} normally supports ({maximum} {unit})'
            )

    if judge_config.integer_time_limit:
        if metadata.limits.time_limit is not None and not metadata.limits.time_limit.is_integer():
            diag.warning(f'Time limit configured to non-integer value, which is not supported by {name}')
        if not metadata.limits.time_resolution.is_integer():
            diag.warning(f'Time resolution is not an integer, which is not supported by {name}')

    if metadata.is_pass_fail():
        return

    if not judge_config.allow_minimization and metadata.legacy_grading.objective == 'min':
        diag.warning(f'Minimization problems (objective: min) are not supported by {name}')

    if not judge_config.allow_negative_scores:
        _check_negative_scores(judge_config, testdata, None, diag)


def _check_negative_scores(
    judge_config: JudgeConfig, group: TestDataGroup, parent_config: dict[str, Any] | None, diag: Diagnostics
) -> None:
    """Heuristic check for negative scores, based only on the score configuration in testdata.yaml.

    This is not a complete check: a grader or output validator can still produce negative scores.
    Catching those would require checking the scores actually seen when running submissions."""
    # Configuration is inherited, so only report values in the group where they are set.
    for key in ['accept_score', 'reject_score', 'range']:
        value = group.config.get(key)
        if value is None or (parent_config is not None and parent_config.get(key) == value):
            continue
        if _allows_negative_score(key, value):
            diag.warning(f'{group} has {key} {value}, but negative scores are not supported by {judge_config.name}')
    for subgroup in group.get_subgroups():
        _check_negative_scores(judge_config, subgroup, group.config, diag)


def _allows_negative_score(key: str, value: Any) -> bool:
    # Malformed values are reported by the test data checks, so we just ignore them here.
    try:
        if key == 'range':
            low, high = map(float, str(value).split())
            # The default range is unbounded, which we accept.
            return low < 0 and not (low == -math.inf and high == math.inf)
        return float(value) < 0
    except ValueError:
        return False
