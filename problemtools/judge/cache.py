from __future__ import annotations

import copy
from concurrent.futures import Future
from dataclasses import dataclass
from threading import Lock
from typing import TYPE_CHECKING

from .result import SubmissionResult

if TYPE_CHECKING:
    from ..verifyproblem import TestCase


@dataclass(frozen=True)
class CacheKey:
    input_hash: bytes
    ans_hash: bytes
    validator_flags: tuple[str, ...]


@dataclass
class _CacheEntry:
    result: SubmissionResult
    run_timelim: float


def _reclassify(result: SubmissionResult, timelim: float) -> SubmissionResult:
    """Reclassify a cached result against a (possibly lower) time limit."""
    if result.runtime > timelim:
        if result.validator_first and result.verdict == 'WA':
            # Interactive: validator exited first with WA. This can cause the submission to run
            # longer than it should. Cap runtimes at timelim so this doesn't inflate the time limit.
            wa = copy.copy(result)
            wa.runtime = timelim
            return wa
        tle = SubmissionResult('TLE')
        tle.runtime = result.runtime
        return tle
    return result


def _with_test_item(result: SubmissionResult, testcase: TestCase) -> SubmissionResult:
    """Return result with test_item set to testcase, copying only if needed."""
    if result.test_item is testcase:
        return result
    result = copy.copy(result)
    result.test_item = testcase
    return result


class ResultStore:
    """Thread-safe store mapping testcase reuse keys to execution results.

    Background workers populate the store via claim()/complete(); the consumer
    reads results via get().  A key progresses through three states: absent
    (not yet claimed), in-flight (claimed, Future not yet resolved), and
    completed (_CacheEntry).

    Because results are always run at the high time limit, a completed entry
    can serve any query whose time limit is <= the run limit: a result whose
    runtime exceeds the query limit is reclassified as TLE. A query with a
    higher limit than the run limit cannot be served from cache and returns None.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._store: dict[CacheKey, Future[SubmissionResult] | _CacheEntry] = {}

    def claim(self, testcase: TestCase) -> bool:
        """Atomically claim testcase for execution.

        Returns True if the key was unclaimed; the caller must eventually call
        complete().  Returns False if the key is already in-flight or completed.
        """
        key = testcase.reuse_key
        with self._lock:
            if key in self._store:
                return False
            self._store[key] = Future()
            return True

    def complete(self, testcase: TestCase, result: SubmissionResult, run_timelim: float) -> None:
        """Store the completed result and wake any consumer waiting on the future."""
        key = testcase.reuse_key
        with self._lock:
            future = self._store[key]
            self._store[key] = _CacheEntry(result=result, run_timelim=run_timelim)
        assert isinstance(future, Future)
        future.set_result(result)  # outside lock — callbacks may acquire other locks

    def get(self, testcase: TestCase, timelim: float) -> SubmissionResult | Future[SubmissionResult] | None:
        """Look up a result for testcase at timelim.

        Returns:
            SubmissionResult  — completed result, already reclassified for timelim; use directly.
            Future            — in-flight; resolves to a reclassified SubmissionResult.
            None              — not present, or was run at a lower limit than timelim and
                                cannot be reused; caller must run the testcase synchronously.
        """
        key = testcase.reuse_key
        with self._lock:
            val = self._store.get(key)
        if val is None:
            return None
        if isinstance(val, Future):
            chained: Future[SubmissionResult] = Future()
            val.add_done_callback(lambda f: chained.set_result(_with_test_item(_reclassify(f.result(), timelim), testcase)))
            return chained
        if timelim > val.run_timelim:
            # Entry was produced at a lower limit; cannot safely reclassify upward.
            return None
        return _with_test_item(_reclassify(val.result, timelim), testcase)
