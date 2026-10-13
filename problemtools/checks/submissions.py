"""Checks for a problem package's submissions."""

from __future__ import annotations

import math
import os
from collections.abc import Callable
from pathlib import Path

from ..context import Context
from ..diagnostics import Diagnostics, pluralize
from ..judge import SubmissionJudge, SubmissionResult, SubmissionsJudge
from ..metadata import FormatVersion, Metadata
from ..model import Graders, LegacyPolicy, Submission, Submissions, TestDataGroup
from ..run import Program
from ..submission_rules import FinalVerdictRule, Rule


def check_submissions(
    submissions: Submissions,
    metadata: Metadata,
    testdata: TestDataGroup,
    output_validator: Program,
    graders: Graders,
    work_dir: Path,
    probdir: Path,
    context: Context,
    set_timelim: Callable[[float], None],
    diag: Diagnostics,
) -> None:
    """Run all checks on a problem's submissions."""
    policy = submissions.policy
    rules_by_submission = _check_matches_policy(submissions, policy, testdata, metadata, diag)
    known_submissions = list(rules_by_submission)
    included_submissions = [s for s in known_submissions if context.submission_filter.search(str(s.path))]
    ignored_submissions = len(known_submissions) - len(included_submissions)
    msg = f'Checking {pluralize(len(included_submissions), "submission")}'
    if ignored_submissions:
        msg += f' (ignoring {pluralize(ignored_submissions, "submission")} due to filters)'
    diag.msg(msg)

    _check_has_accepted_submission(submissions, diag)

    seen_oob_score_groups: set[int] = set()

    has_testcases = any(tc.matches_filter(context.data_filter) for tc in testdata.get_all_testcases())
    if not has_testcases:
        diag.warning('Found no test cases to run on. Did you filter them all out?')

    compile_result = output_validator.compile(work_dir)
    if compile_result.executable is None:
        diag.error(f'Compile error for output validator {output_validator}', compile_result.errmsg)
        return

    submissions_judge = context.submissions_judge_factory(
        root=testdata,
        output_validator=compile_result.executable,
        metadata=metadata,
        base_dir=work_dir,
        context=context,
        graders=graders,
        diag=diag,
    )

    timelim, timelim_high, fixed_limit = _initial_time_limit(metadata, context, diag)
    lower_bound_submissions = [sub for sub in included_submissions if policy.lower_bounds_time_limit(sub)]
    all_submission_results = _check_submission_group(
        lower_bound_submissions,
        rules_by_submission,
        metadata,
        submissions_judge,
        probdir,
        seen_oob_score_groups,
        timelim,
        timelim_high,
        has_testcases,
        diag,
    )

    if all_submission_results:
        timelim, timelim_high = _compute_time_limit(metadata, fixed_limit, all_submission_results, context, diag)
        set_timelim(timelim)
    elif fixed_limit is not None:
        # Corner case. The user may have filtered for only one (non-AC) sub, and set a fixed time limit.
        # It's a bit unclear if we want to set_timelim() here (exposing it in the result of check), but
        # I think it's preferable to do so.
        set_timelim(timelim)
    else:
        diag.error(
            'Could not determine a time limit automatically: no submission produced timing data to lower-bound it, '
            f'and no fixed time limit is set. Falling back to a {_fmt_number(timelim)}s cap.'
        )

    # Run TLE submissions last (as they're presumably the slowest)
    rest = sorted(
        (sub for sub in included_submissions if sub not in lower_bound_submissions),
        key=lambda sub: (
            any(isinstance(r, FinalVerdictRule) and r.verdict == 'TLE' for r in rules_by_submission[sub]),
            str(sub.path),
        ),
    )
    all_submission_results.extend(
        _check_submission_group(
            rest,
            rules_by_submission,
            metadata,
            submissions_judge,
            probdir,
            seen_oob_score_groups,
            timelim,
            timelim_high,
            has_testcases,
            diag,
        )
    )

    if all_submission_results:
        _print_results_table(all_submission_results, testdata, metadata.is_scoring(), diag)


def _check_has_accepted_submission(submissions: Submissions, diag: Diagnostics) -> None:
    if not any(sub.directory == 'accepted' for sub in submissions.submissions):
        diag.error('Require at least one "accepted" submission')


def _check_matches_policy(
    submissions: Submissions, policy: LegacyPolicy, testdata: TestDataGroup, metadata: Metadata, diag: Diagnostics
) -> dict[Submission, list[Rule]]:
    """Get the rules for every submission matching the policy. Emit an error for, and exclude, any
    submission that doesn't match the policy at all (i.e. sits in an unrecognized directory). Such
    a submission is never compiled or tested."""
    rules_by_submission = {}
    for sub in submissions.submissions:
        rules = policy.rules_for(sub, testdata, metadata)
        if rules is not None:
            rules_by_submission[sub] = rules
        else:
            diag.error(f'Submission {sub.path} does not match any known submissions directory; ignoring it')
    return rules_by_submission


def _check_submission_group(
    subs: list[Submission],
    rules_by_submission: dict[Submission, list[Rule]],
    metadata: Metadata,
    submissions_judge: SubmissionsJudge,
    probdir: Path,
    seen_oob_score_groups: set[int],
    timelim: float,
    timelim_high: float,
    has_testcases: bool,
    diag: Diagnostics,
) -> list[tuple[Submission, list[SubmissionResult]]]:
    """Compile and (if has_testcases) judge every submission in subs.

    Note that the returned list can be shorter than subs. Submissions failing to compile
    return nothing (but give an error), and we return an empty list if not has_testcases.
    """
    outcomes = submissions_judge.precompute(subs, timelim_high)

    submission_results = []
    for sub in subs:
        if sub.program.code_size() > 1024 * metadata.limits.code:
            diag.error(
                f'{sub} has size {sub.program.code_size() / 1024.0:.1f} kiB, exceeds code size limit of {metadata.limits.code} kiB'
            )

        result = outcomes[sub]
        if not result.success:
            diag.error(f'Compile error for {sub}', additional_info=result.errmsg)
            continue

        if not has_testcases:
            continue

        judge = submissions_judge.judges()[sub]
        sub_results = _check_submission(
            sub,
            judge,
            rules_by_submission[sub],
            metadata,
            probdir,
            seen_oob_score_groups,
            timelim,
            timelim_high,
            diag,
        )
        submission_results.append((sub, sub_results))

    return submission_results


def _check_submission(
    sub: Submission,
    judge: SubmissionJudge,
    rules: list[Rule],
    metadata: Metadata,
    probdir: Path,
    seen_oob_score_groups: set[int],
    timelim: float,
    timelim_high: float,
    diag: Diagnostics,
) -> list[SubmissionResult]:
    results_high = judge.judge(timelim_high)
    if not results_high:
        diag.fatal('_check_submission called, but found no test cases to run on.')

    results = judge.judge(timelim)
    result = results[-1]

    # Check if scores were outside of the range for any groups
    if metadata.is_scoring():
        for r in results:
            if r.score is not None and isinstance(r.test_node, TestDataGroup):
                _check_score_in_bounds(r.test_node, sub.program, r.score, probdir, seen_oob_score_groups, diag)

    time_limit_sensitivity = _time_limit_sensitivity(judge, results_high, timelim, timelim_high, sub, metadata)

    # Use a list rather than any() on a generator, so that every rule gets checked
    reported_errors = [rule.check(sub, results, diag) for rule in rules]
    if time_limit_sensitivity is not None:
        if any(reported_errors):
            # Already reported as an error, but knowing how the result depends on the time limit may help fix it
            diag.msg(f'   {time_limit_sensitivity}')
        else:
            diag.warning(time_limit_sensitivity)
    if not any(reported_errors):
        diag.msg(f'   {sub} OK: {result}')

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


def _same_result(a: SubmissionResult, b: SubmissionResult) -> bool:
    return a.verdict == b.verdict and a.score == b.score


def _time_limit_sensitivity(
    judge: SubmissionJudge,
    results_high: list[SubmissionResult],
    timelim: float,
    timelim_high: float,
    sub: Submission,
    metadata: Metadata,
) -> str | None:
    """Describe how sub's result changes for time limits between lo and timelim_high, listing each runtime where
    it changes, or None if it doesn't change. lo is the largest runtime that wouldn't have affected the time limit,
    had the submission been used to compute it."""
    multipliers = metadata.limits.time_multipliers
    lo = timelim / multipliers.ac_to_time_limit
    steps = [(lo, judge.judge(lo)[-1])]
    # Only try the largest runtime per printed value, so we don't list several changes at the same printed time
    runtimes: dict[str, float] = {}
    for r in results_high:
        if lo < r.runtime <= timelim_high:
            runtimes[f'{r.runtime:.2f}'] = max(r.runtime, runtimes.get(f'{r.runtime:.2f}', 0))
    for t in sorted(runtimes.values()):
        result = judge.judge(t)[-1]
        if not _same_result(result, steps[-1][1]):
            steps.append((t, result))

    def fmt(result: SubmissionResult) -> str:
        return result.format(fields=['score'])

    if len(steps) == 1:
        return None
    if len(steps) == 2:
        t, result = steps[1]
        if t > timelim:
            return f'{sub} would get {fmt(result)} with time limit >= {t:.2f}s'
        factor_name = 'time_multiplier' if metadata.problem_format_version == FormatVersion.LEGACY else 'ac_to_time_limit'
        return (
            f'{sub} is within {factor_name} ({_fmt_number(multipliers.ac_to_time_limit)}) of time limit '
            f'{_fmt_number(timelim)}s. It takes {t:.2f}s to get {fmt(result)}.'
        )
    parts = []
    for i, (t, result) in enumerate(steps):
        if i > 0 and steps[i - 1][0] <= timelim < t:
            parts.append(f'[time limit {_fmt_number(timelim)}s]')
        parts.append(f'{t:.2f}s -> {fmt(result)}')
    return f'{sub} is sensitive to time limit. {", ".join(parts)}'


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
    all_submission_results: list[tuple[Submission, list[SubmissionResult]]],
    testdata: TestDataGroup,
    is_scoring: bool,
    diag: Diagnostics,
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

    diag.msg('Submission results:')
    indent = '   '
    diag.msg(indent + '  '.join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    for row in rows:
        diag.msg(indent + '  '.join(cell.ljust(widths[i]) for i, cell in enumerate(row)))


def _initial_time_limit(metadata: Metadata, context: Context, diag: Diagnostics) -> tuple[float, float, float | None]:
    limits = metadata.limits
    if limits.time_limit is not None and context.fixed_timelim is not None:
        diag.warning('There is a fixed time limit in problem.yaml, and you provided one on command line. Using command line.')
    fixed_limit = context.fixed_timelim if context.fixed_timelim is not None else limits.time_limit
    if fixed_limit is None:
        # 5 minutes is our currently hard coded upper bound for what to allow when we don't know the time limit yet
        return 300.0, 300.0, None
    return fixed_limit, fixed_limit * limits.time_multipliers.time_limit_to_tle, fixed_limit


def _compute_time_limit(
    metadata: Metadata,
    fixed_limit: float | None,
    all_submission_results: list[tuple[Submission, list[SubmissionResult]]],
    context: Context,
    diag: Diagnostics,
) -> tuple[float, float]:
    limits = metadata.limits
    lower_bound_runtime = max(results[-1].runtime for _, results in all_submission_results)
    exact_timelim = lower_bound_runtime * limits.time_multipliers.ac_to_time_limit
    tl_from_runtime = max(1, math.ceil(exact_timelim / limits.time_resolution)) * limits.time_resolution

    if fixed_limit is not None:
        timelim = fixed_limit
        if lower_bound_runtime * limits.time_multipliers.ac_to_time_limit > fixed_limit:
            msg = (
                f'Fixed time limit ({_fmt_number(fixed_limit)}) is tighter than the auto-computed limit '
                f'({_fmt_number(tl_from_runtime)}) — slowest AC: {_fmt_number(lower_bound_runtime)} x '
                f'multiplier {_fmt_number(limits.time_multipliers.ac_to_time_limit)}'
            )
            if context.fixed_timelim is not None:  # We just warn when the fixed time limit comes from command line
                diag.warning(msg)
            else:
                diag.error(msg)  # ... but if it came from problem.yaml, it's an error if bounds aren't kept

        if not math.isclose(fixed_limit, tl_from_runtime):
            diag.msg(
                f'   Solutions give timelim of {_fmt_number(tl_from_runtime)} seconds, but will use provided '
                f'fixed limit of {_fmt_number(fixed_limit)} seconds instead'
            )
    else:
        timelim = tl_from_runtime

    timelim_high = timelim * limits.time_multipliers.time_limit_to_tle
    diag.msg(
        f'   Slowest AC runtime: {_fmt_number(lower_bound_runtime)}, setting timelim to {_fmt_number(timelim)} secs, '
        f'safety margin to {_fmt_number(timelim_high)} secs'
    )
    return timelim, timelim_high


def _fmt_number(number: float | None) -> str:
    """Format a number with at most 3 decimals, dealing with None."""
    return f'{round(number, 3):g}' if number is not None else '-'
