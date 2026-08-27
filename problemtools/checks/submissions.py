"""Checks for a problem package's submissions."""

from __future__ import annotations

import math
import os
from collections.abc import Callable
from pathlib import Path

from ..context import Context
from ..diagnostics import Diagnostics
from ..judge import SubmissionJudge, SubmissionResult
from ..metadata import Metadata
from ..model import Graders, LegacyPolicy, Submission, Submissions, TestCase, TestDataGroup
from ..run import Program

# Temporary consts to keep code structure as similar as possible to old code from
# verifyproblem when extracting this to a separate module.
_DIRECTORIES: list[str] = ['accepted', 'partially_accepted', 'wrong_answer', 'run_time_error', 'time_limit_exceeded']
_DISPLAY_LABEL_BY_DIRECTORY: dict[str, str] = {
    'accepted': 'AC',
    'partially_accepted': 'PAC',
    'wrong_answer': 'WA',
    'run_time_error': 'RTE',
    'time_limit_exceeded': 'TLE',
}


def check_submissions(
    submissions: Submissions,
    metadata: Metadata,
    testdata: TestDataGroup,
    output_validator: Program,
    graders: Graders,
    tmpdir: str,
    probdir: Path,
    context: Context,
    set_timelim: Callable[[float], None],
    diag: Diagnostics,
) -> None:
    """Run all checks on a problem's submissions."""
    _check_has_accepted_submission(submissions, diag)

    policy = submissions.policy
    known_submissions = _check_matches_policy(submissions, policy, diag)
    seen_oob_score_groups: set[int] = set()

    limits = metadata.limits
    ac_to_time_limit = limits.time_multipliers.ac_to_time_limit

    fixed_limit: float | None = context.fixed_timelim if context.fixed_timelim is not None else limits.time_limit
    lower_bound_runtime: float | None = None  # The runtime of the slowest submission used to lower bound the time limit.

    if limits.time_limit is not None and context.fixed_timelim is not None:
        diag.warning('There is a fixed time limit in problem.yaml, and you provided one on command line. Using command line.')

    has_testcases = any(tc.matches_filter(context.data_filter) for tc in testdata.get_all_testcases())
    if not has_testcases:
        diag.warning('Found no test cases to run on. Did you filter them all out?')

    all_submission_results: list[tuple[Submission, list[SubmissionResult]]] = []

    for directory in _DIRECTORIES:
        label = _DISPLAY_LABEL_BY_DIRECTORY[directory]
        runtimes = []

        for sub in known_submissions:
            if sub.directory != directory:
                continue
            if not context.submission_filter.search(str(sub.path)):
                continue

            diag.info(f'Check {label} submission {sub.program}')

            if sub.program.code_size() > 1024 * limits.code:
                diag.error(
                    f'{label} submission {sub.program} has size {sub.program.code_size() / 1024.0:.1f} kiB, '
                    f'exceeds code size limit of {limits.code} kiB'
                )
                continue

            success, msg = sub.program.compile()
            if not success:
                diag.error(f'Compile error for {label} submission {sub.program}', additional_info=msg)
                continue

            if has_testcases:
                timelim, timelim_high = _compute_time_limit(metadata, fixed_limit, lower_bound_runtime)
                sub_results = _check_submission(
                    sub,
                    policy,
                    context,
                    metadata,
                    testdata,
                    output_validator,
                    graders,
                    tmpdir,
                    probdir,
                    seen_oob_score_groups,
                    timelim,
                    timelim_high,
                    diag,
                )
                runtimes.append(sub_results[-1].runtime)
                all_submission_results.append((sub, sub_results))

        if directory == 'accepted' and has_testcases:
            if len(runtimes) > 0:
                lower_bound_runtime = max(runtimes)

            if fixed_limit is not None and lower_bound_runtime is not None:
                tl_from_subs, _ = _compute_time_limit(metadata, None, lower_bound_runtime)
                if lower_bound_runtime * ac_to_time_limit > fixed_limit:
                    msg = (
                        f'Fixed time limit ({_fmt_number(fixed_limit)}) is tighter than the auto-computed limit '
                        f'({_fmt_number(tl_from_subs)}) — slowest AC: {_fmt_number(lower_bound_runtime)} x '
                        f'multiplier {_fmt_number(ac_to_time_limit)}'
                    )
                    if context.fixed_timelim is not None:  # We just warn when the fixed time limit comes from command line
                        diag.warning(msg)
                    else:
                        diag.error(msg)  # ... but if it came from problem.yaml, it's an error if bounds aren't kept

                if not math.isclose(fixed_limit, tl_from_subs):
                    print(
                        f'   Solutions give timelim of {_fmt_number(tl_from_subs)} seconds, but will use provided '
                        f'fixed limit of {_fmt_number(fixed_limit)} seconds instead'
                    )

            timelim, timelim_margin = _compute_time_limit(metadata, fixed_limit, lower_bound_runtime)
            print(
                f'   Slowest AC runtime: {_fmt_number(lower_bound_runtime)}, setting timelim to {_fmt_number(timelim)} secs, '
                f'safety margin to {_fmt_number(timelim_margin)} secs'
            )
            set_timelim(timelim)

    if all_submission_results:
        _print_results_table(all_submission_results, testdata, metadata.is_scoring())


def _check_has_accepted_submission(submissions: Submissions, diag: Diagnostics) -> None:
    if not any(sub.directory == 'accepted' for sub in submissions.submissions):
        diag.error('Require at least one "accepted" submission')


def _check_matches_policy(submissions: Submissions, policy: LegacyPolicy, diag: Diagnostics) -> list[Submission]:
    """Emit an error for, and exclude, any submission that doesn't match the policy at all
    (i.e. sits in an unrecognized directory). Such a submission is never compiled or tested."""
    matched = []
    for sub in submissions.submissions:
        if policy.matches(sub):
            matched.append(sub)
        else:
            diag.error(f'Submission {sub.path} does not match any known submissions directory; ignoring it')
    return matched


def _check_submission(
    sub: Submission,
    policy: LegacyPolicy,
    context: Context,
    metadata: Metadata,
    testdata: TestDataGroup,
    output_validator: Program,
    graders: Graders,
    tmpdir: str,
    probdir: Path,
    seen_oob_score_groups: set[int],
    timelim: float,
    timelim_high: float,
    diag: Diagnostics,
) -> list[SubmissionResult]:
    expected_verdict = policy.expected_verdict(sub)
    assert expected_verdict is not None, '_check_submission called on a submission not matching the policy'
    partial = sub.directory == 'partially_accepted'
    desc = f'{_DISPLAY_LABEL_BY_DIRECTORY[sub.directory]} submission {sub.program}'

    judge = SubmissionJudge(
        sub=sub.program,
        output_validator=output_validator,
        metadata=metadata,
        root=testdata,
        base_dir=Path(tmpdir),
        context=context,
        graders=graders,
        diag=diag,
    )
    if context.executor is not None:
        judge.precompute(timelim_high)
    results_high = judge.judge(timelim_high)
    if not results_high:
        diag.fatal('_check_submission called, but found no test cases to run on.')
    result_high = results_high[-1]

    results = judge.judge(timelim)
    result = results[-1]

    # Check if scores were outside of the range for any groups
    if metadata.is_scoring():
        for r in results:
            if r.score is not None and isinstance(r.test_node, TestDataGroup):
                _check_score_in_bounds(r.test_node, sub.program, r.score, probdir, seen_oob_score_groups, diag)

    # Warn if AC (but not PAC) submissions fail on samples. It's not uncommon for sample cases to be
    # ignored, so failing on them could be silent otherwise. Skip warning if the result isn't AC -
    # then something worse has gone wrong, and we'll error later.
    if expected_verdict == 'AC' and not partial and result.verdict == 'AC':
        if sample_failure := _find_sample_failure(results):
            diag.warning(f'{desc} got {sample_failure.verdict} on sample: {sample_failure}')

    # Warn if a PAC submission would affect time limit, had it been use to compute the time limit. Only do this
    # if it gets AC on the computed time limit, otherwise we have other warnings below.
    if partial and result.verdict == 'AC':
        _warn_pac_too_slow(judge, results, timelim, desc, metadata, diag)

    if result.verdict != result_high.verdict or result.score != result_high.score:
        diag.warning(
            f'{desc} sensitive to time limit: limit of {timelim} secs -> {result}, limit of {timelim_high} secs -> {result_high}'
        )

    if partial and _fully_accepted(result, testdata, metadata):
        diag.warning(f'{desc} was fully accepted: {result}')
    elif result.verdict == expected_verdict:
        print(f'   {desc} OK: {result}')
        if (
            not partial
            and expected_verdict == 'AC'
            and not _fully_accepted(result, testdata, metadata)
            and _full_score_finite(testdata, metadata)
        ):
            # For some heuristic problems, this is expected. Thus, only warn.
            diag.warning(f'{desc} did not attain full score (consider moving it to partially_accepted)')
    elif result_high.verdict == expected_verdict and not (partial and _fully_accepted(result_high, testdata, metadata)):
        print(f'   {desc} OK with extra time: {result_high}')
    else:
        diag.error(f'{desc} got {result}', result_high.additional_info)

    return results


def _check_score_in_bounds(
    group: TestDataGroup, sub: Program, score: float, probdir: Path, seen_oob_score_groups: set[int], diag: Diagnostics
) -> None:
    """Warn if score is outside of group's expected score range.

    Don't warn twice for the same group, since every submission is likely to hit the same error;
    seen_oob_score_groups (keyed by id(group)) is owned by the caller, e.g. one set per problem check run.
    """
    if id(group) in seen_oob_score_groups:
        return
    min_score, max_score = group.get_score_range()
    if min_score <= score <= max_score:
        return
    seen_oob_score_groups.add(id(group))
    groupname = os.path.relpath(group.datadir, probdir)
    diag.error(
        f'submission {sub} got score {score} on group {groupname}, which is outside of expected score range [{min_score}, {max_score}]'
    )


def _find_sample_failure(results: list[SubmissionResult]) -> SubmissionResult | None:
    for r in results:
        if r.verdict != 'AC' and isinstance(r.test_node, TestCase) and r.test_node.is_in_sample_group():
            return r
    return None


def _warn_pac_too_slow(
    judge: SubmissionJudge, results: list[SubmissionResult], timelim: float, desc: str, metadata: Metadata, diag: Diagnostics
) -> None:
    """Warn if a PAC submission is slow enough that it would have affected the time limit."""
    runtime_without_affecting_tl = timelim / metadata.limits.time_multipliers.ac_to_time_limit
    if judge.judge(runtime_without_affecting_tl)[-1].verdict == 'AC':
        return
    for t in sorted(r.runtime for r in results if r.runtime > runtime_without_affecting_tl):
        if judge.judge(t)[-1].verdict == 'AC':
            diag.warning(f'{desc} is slower than all AC submissions. It needs {t:.2f}s to get AC')
            return


def _get_table_groups(testdata: TestDataGroup) -> list[TestDataGroup]:
    """Return the groups to show as columns: expand any root child that has subgroups."""
    result = []
    for group in testdata.get_subgroups():
        subgroups = group.get_subgroups()
        if subgroups:
            result.extend(subgroups)
        else:
            result.append(group)
    return result


def _print_results_table(
    all_submission_results: list[tuple[Submission, list[SubmissionResult]]], testdata: TestDataGroup, is_scoring: bool
) -> None:
    groups = _get_table_groups(testdata)

    def cell_for_group(results: list[SubmissionResult], group: TestDataGroup) -> str:
        for r in results:
            if r.test_node is group:
                if r.verdict == 'AC':
                    if is_scoring and r.score is not None:
                        score_str = f'{int(r.score)}' if r.score == int(r.score) else f'{r.score:.2f}'
                        score_part = f'({score_str})'
                    else:
                        score_part = ''
                    return f'AC{score_part}:{r.runtime:.2f}s'
                return r.verdict
        return '-'

    def cell_for_pts(results: list[SubmissionResult]) -> str:
        score = results[-1].score
        return f'{score:.0f}' if score is not None else '-'

    def cell_for_time(results: list[SubmissionResult]) -> str:
        t = results[-1].runtime
        return f'{t:.2f}s' if t >= 0 else '-'

    headers = ['Submission'] + [os.path.basename(g.datadir) for g in groups]
    if is_scoring:
        headers.append('Pts')
    headers.append('Time')

    rows = []
    for sub, results in all_submission_results:
        row = [sub.program.name]
        for g in groups:
            row.append(cell_for_group(results, g))
        if is_scoring:
            row.append(cell_for_pts(results))
        row.append(cell_for_time(results))
        rows.append(row)

    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    print('Submission results:')
    indent = '   '
    print(indent + '  '.join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    for row in rows:
        print(indent + '  '.join(cell.ljust(widths[i]) for i, cell in enumerate(row)))


def _compute_time_limit(metadata: Metadata, fixed_limit: float | None, lower_bound_runtime: float | None) -> tuple[float, float]:
    if fixed_limit is None and lower_bound_runtime is None:
        # 5 minutes is our currently hard coded upper bound for what to allow when we don't know the time limit yet
        return 300.0, 300.0

    limits = metadata.limits
    if fixed_limit is not None:
        timelim = fixed_limit
    else:
        assert lower_bound_runtime is not None, 'Assert to keep mypy happy'
        exact_timelim = lower_bound_runtime * limits.time_multipliers.ac_to_time_limit
        timelim = max(1, math.ceil(exact_timelim / limits.time_resolution)) * limits.time_resolution

    return timelim, timelim * limits.time_multipliers.time_limit_to_tle


def _full_score_finite(testdata: TestDataGroup, metadata: Metadata) -> bool:
    min_score, max_score = testdata.get_score_range()
    if metadata.legacy_grading.objective == 'min':
        return min_score != float('-inf')
    else:
        return max_score != float('inf')


def _fully_accepted(result: SubmissionResult, testdata: TestDataGroup, metadata: Metadata) -> bool:
    min_score, max_score = testdata.get_score_range()
    best_score = min_score if metadata.legacy_grading.objective == 'min' else max_score
    return result.verdict == 'AC' and (not metadata.is_scoring() or result.score == best_score)


def _fmt_number(number: float | None) -> str:
    """Format a number with at most 3 decimals, dealing with None."""
    return f'{round(number, 3):g}' if number is not None else '-'
