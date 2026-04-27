from __future__ import annotations

import copy
from concurrent.futures import Future
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING

from ..context import Context
from ..diagnostics import Diagnostics
from ..metadata import Metadata
from ..run import Program, get_tool
from .cache import ResultStore
from .execute import execute_testcase
from .grade import grade_group
from .result import SubmissionResult

if TYPE_CHECKING:
    from ..verifyproblem import TestCase, TestCaseGroup


class _Cancelled:
    """Thread-safe set of cancelled testcase identities (by Path to infile)."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._ids: set[Path] = set()

    def __contains__(self, testcase: TestCase) -> bool:
        with self._lock:
            return testcase.infile_path in self._ids

    def add(self, testcase: TestCase) -> None:
        with self._lock:
            self._ids.add(testcase.infile_path)


class SubmissionJudge:
    """Run a submission against a test case group tree and collect results.

    The typical flow uses two phases:

      1. precompute(timelim) — submits all filtered testcases as background jobs that
         execute the submission and populate a result cache.  Returns immediately.
      2. judge(timelim) — walks the test tree in DFS order, consuming cached results
         (blocking on any still in-flight) or running synchronously if a worker missed
         a testcase.  Returns a flat list of SubmissionResults, one per testcase plus
         one aggregate per group, with the root group's result last.

    This lets the submission run on all testcases in parallel while the consumer
    processes results in order for grading and early-exit logic.

    When an on_reject:break group encounters a non-AC result, pending (not-yet-started)
    background jobs for the remaining testcases in that subtree are skipped.  In-flight
    jobs complete normally; their results are simply not consumed by judge().
    """

    _default_grader: Program | None = get_tool('default_grader')

    def __init__(
        self,
        sub: Program,
        output_validator: Program,
        metadata: Metadata,
        root: TestCaseGroup,
        base_dir: Path,
        context: Context,
        diag: Diagnostics,
        custom_grader: Program | None = None,
    ) -> None:
        self._sub = sub
        self._output_validator = output_validator
        self._metadata = metadata
        self._base_dir = base_dir
        self._context = context
        self._diag = diag
        self._custom_grader = custom_grader
        self._store = ResultStore()
        self._root = root
        self._cancelled = _Cancelled()
        self._precompute_started = False

    def precompute(self, timelim: float) -> None:
        """Submit all filtered testcases as background jobs.

        Returns immediately; workers run concurrently and deposit results into the
        cache as they finish.  Call judge() afterwards to consume results in DFS order.
        May be called at most once.
        """
        assert not self._precompute_started, 'precompute() called more than once'
        self._precompute_started = True
        filtered_testcases = (item for item in self._root.get_all_testcases() if item.matches_filter(self._context.data_filter))
        for testcase in filtered_testcases:
            self._context.submit_background_work(self._populate_cache_for_testcase, testcase, timelim)

    def judge(self, timelim: float) -> list[SubmissionResult]:
        """Walk the test tree in DFS order and return results as a flat list.

        Each SubmissionResult has test_node set to the TestCase or TestCaseGroup it
        covers.  Group results immediately follow all their descendants; the root
        group's result is the last element.  Returns an empty list if all testcases
        were filtered out.

        Blocks on any cache entry still being computed by a precompute() worker.
        Testcases not yet claimed by a worker are run synchronously.  Safe to call
        multiple times with different timelim values; subsequent calls almost always
        hit the cache without new work.  When querying multiple time limits, call
        with the largest first so that cached results can be reused for smaller limits.
        """
        return self._judge_group(self._root, timelim)

    def _run(self, testcase: TestCase, timelim: float) -> SubmissionResult:
        return execute_testcase(
            testcase,
            self._sub,
            self._output_validator,
            self._metadata,
            timelim,
            self._base_dir,
            self._diag,
        )

    def _populate_cache_for_testcase(self, testcase: TestCase, timelim: float) -> None:
        if testcase in self._cancelled:
            return
        if not self._store.claim(testcase):
            return  # duplicate testcase (same reuse_key) or already in store
        self._store.complete(testcase, self._run(testcase, timelim), timelim)

    def _judge_testcase(self, testcase: TestCase, timelim: float) -> SubmissionResult:
        val = self._store.get(testcase, timelim)
        if isinstance(val, Future):
            return val.result()  # block until worker finishes
        if val is not None:
            return val
        # Synchronous fallback: worker hasn't claimed this testcase yet, or second
        # judge() call with a timelim the store can't serve.  Claim so any pending
        # worker for it bails out rather than duplicating work.
        claimed = self._store.claim(testcase)
        result = self._run(testcase, timelim)
        if claimed:
            self._store.complete(testcase, result, timelim)
        return result

    def _cancel_subtree(self, group: TestCaseGroup) -> None:
        for testcase in group.get_all_testcases():
            self._cancelled.add(testcase)

    def _grader_for(self, group: TestCaseGroup) -> Program | None:
        if group.config.get('grading') == 'custom':
            return self._custom_grader
        return self._default_grader

    def _judge_group(self, group: TestCaseGroup, timelim: float) -> list[SubmissionResult]:
        all_results: list[SubmissionResult] = []  # Results of all children, groups and test cases, in DFS order. Our return value
        child_results: list[SubmissionResult] = []  # Results of our direct children, what we'll pass to the grader

        filtered_items = (item for item in group._items if item.matches_filter(self._context.data_filter))
        for item in filtered_items:
            if item.is_group:
                sub = self._judge_group(item, timelim)
                if not sub:  # If everything in a group is filtered, it returns an empty list.
                    continue
                all_results.extend(sub)
                result = sub[-1]  # last element is the subgroup's own result
            else:
                result = self._judge_testcase(item, timelim)
                # Apply default score here - after we've entered it into the cache, as it may also be present in other groups with different defaults
                if result.score is None:
                    result = copy.copy(result)
                    if result.verdict == 'AC':
                        result.score = group.config['accept_score']
                    else:
                        result.score = group.config['reject_score']
                all_results.append(result)

            child_results.append(result)
            if result.verdict != 'AC' and group.config.get('on_reject') == 'break':
                self._cancel_subtree(group)  # Stop starting more precomputations for submissions in this group or below
                break

        if not all_results:  # All our children were filtered
            return []

        judge_error = next((r for r in child_results if r.verdict == 'JE'), None)
        if judge_error:
            group_verdict = copy.copy(judge_error)
        else:
            grader = self._grader_for(group)
            if grader is None:
                group_verdict = SubmissionResult('JE', reason='grader not found')
            else:
                grader_flags = group.config.get('grader_flags', '').split()
                verdict, score = grade_group(child_results, grader, grader_flags, self._base_dir, self._diag)
                group_verdict = SubmissionResult(verdict, score=score)
                group_verdict.runtime = max(v.runtime for v in child_results)

        group_verdict.test_node = group
        all_results.append(group_verdict)
        return all_results
