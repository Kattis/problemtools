"""Checks for a problem package's config (problem.yaml)."""

from __future__ import annotations

import uuid

from ..diagnostics import Diagnostics
from ..formatversion import FormatVersion
from ..metadata import License, Metadata, ProblemType
from ..model import Statements, TestDataGroup

_INCOMPATIBLE_TYPES = [
    (ProblemType.PASS_FAIL, ProblemType.SCORING),
    (ProblemType.SUBMIT_ANSWER, ProblemType.MULTI_PASS),
    (ProblemType.SUBMIT_ANSWER, ProblemType.INTERACTIVE),
]

# Temporary local copy of checks/validators.py's _error_in_2023_07. Only two consumers so far;
# promote to a shared helper if a third one shows up.


def _error_in_2023_07(format_version: FormatVersion, diag: Diagnostics, msg: str, additional_info: str | None = None) -> None:
    if format_version is FormatVersion.LEGACY:
        diag.warning(msg, additional_info)
    else:
        diag.error(msg, additional_info)


def check_config(
    metadata: Metadata,
    format_version: FormatVersion,
    statements: Statements,
    testdata: TestDataGroup,
    diag: Diagnostics,
) -> None:
    """Run all checks on a problem's config (problem.yaml)."""
    for t1, t2 in _INCOMPATIBLE_TYPES:
        if t1 in metadata.type and t2 in metadata.type:
            diag.error(f'Problem has incompatible types: {t1}, {t2}')

    if metadata.is_submit_answer():
        diag.warning('The type submit-answer is not yet supported.')

    # Check rights_owner
    if metadata.license == License.PUBLIC_DOMAIN:
        if metadata.rights_owner:
            diag.error('Can not have a rights_owner for a problem in public domain')
    elif metadata.license != License.UNKNOWN:
        if not metadata.rights_owner and not metadata.source and not metadata.credits.authors:
            diag.error('No author, source or rights_owner provided')

    # Sanity check that the author name is parsed reasonably
    disallowed_in_name = [',', '&']
    for author in metadata.credits.authors:
        for disallowed_character in disallowed_in_name:
            if disallowed_character in author.name:
                diag.warning(f'Author name parsed to "{author.name}", which contains character "{disallowed_character}".')

    # Check license
    if metadata.license == License.UNKNOWN:
        diag.warning("License is 'unknown'")

    if metadata.uuid is None:
        _error_in_2023_07(format_version, diag, f'Missing uuid from problem.yaml. Add "uuid: {uuid.uuid4()}" to problem.yaml.')

    names_with_no_statement = [lang for lang in metadata.name if lang not in statements.by_language]
    if names_with_no_statement:
        diag.error(f'Names exist for languages without problem statements: {", ".join(names_with_no_statement)}')

    if metadata.legacy_grading.show_test_data_groups and metadata.is_pass_fail():
        diag.error('Showing test data groups is only supported for scoring problems, this is a pass-fail problem')
    if (
        not metadata.is_pass_fail()
        and testdata.has_custom_groups()
        and not metadata.show_test_data_groups_explicitly_set
        and format_version is FormatVersion.LEGACY
    ):
        diag.warning(
            'Problem has custom testcase groups, but does not specify a value for grading.show_test_data_groups; defaulting to false'
        )

    if metadata.legacy_grading.on_reject is not None:
        if metadata.is_pass_fail() and metadata.legacy_grading.on_reject == 'grade':
            diag.error("Invalid on_reject policy 'grade' for problem type 'pass-fail'")

    for deprecated_grading_key in ['accept_score', 'reject_score', 'range', 'on_reject']:
        if getattr(metadata.legacy_grading, deprecated_grading_key) is not None:
            diag.warning(
                f"Grading key '{deprecated_grading_key}' is deprecated in problem.yaml, use '{deprecated_grading_key}' in testdata.yaml instead"
            )

    if metadata.legacy_validation:
        val = metadata.legacy_validation.split()
        validation_type = val[0]
        validation_params = val[1:]
        if validation_type not in ['default', 'custom']:
            diag.error(f"Invalid value '{validation_type}' for validation, first word must be 'default' or 'custom'")

        if validation_type == 'default' and len(validation_params) > 0:
            diag.error(f"Invalid value '{metadata.legacy_validation}' for validation")

        if validation_type == 'custom':
            for param in validation_params:
                if param not in ['score', 'interactive']:
                    diag.error(f"Invalid parameter '{param}' for custom validation")

    if metadata.limits.time_limit is not None and not metadata.limits.time_limit.is_integer():
        diag.warning(
            'Time limit configured to non-integer value. This can be fragile, and may not be supported by your CCS (Kattis does not).'
        )
    if not metadata.limits.time_resolution.is_integer():
        diag.warning(
            'Time resolution is not an integer. This can be fragile, and may not be supported by your CCS (Kattis does not).'
        )
