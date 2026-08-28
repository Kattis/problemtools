from __future__ import annotations

import concurrent.futures
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from re import Pattern
from typing import ParamSpec, TypeVar

_T = TypeVar('_T')
_P = ParamSpec('_P')

#: Listed in the order they're checked in.
PROBLEM_PARTS = ['config', 'statement', 'validators', 'graders', 'data', 'submissions']


class Context:
    # Default values here must be kept in sync with the defaults in argparser().
    def __init__(
        self,
        data_filter: Pattern[str] = re.compile('.*'),
        submission_filter: Pattern[str] = re.compile('.*'),
        fixed_timelim: float | None = None,
        parts: list[str] | None = None,
        threads: int = 1,
    ) -> None:
        self.data_filter = data_filter
        self.submission_filter = submission_filter
        self.fixed_timelim = fixed_timelim
        self.parts: list[str] = parts if parts is not None else list(PROBLEM_PARTS)
        self.executor: ThreadPoolExecutor | None = ThreadPoolExecutor(threads) if threads > 1 else None
        self._background_work: list[concurrent.futures.Future[object]] = []

    def submit_background_work(self, job: Callable[_P, _T], *args: _P.args, **kwargs: _P.kwargs) -> None:
        assert self.executor
        self._background_work.append(self.executor.submit(job, *args, **kwargs))

    def cancel_background_work(self) -> None:
        for future in self._background_work:
            future.cancel()

    def wait_for_background_work(self) -> None:
        concurrent.futures.wait(self._background_work)
