from __future__ import annotations

import os
import signal
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from ..verifyproblem import TestCase

Verdict = Literal['AC', 'TLE', 'OLE', 'MLE', 'RTE', 'WA', 'PAC', 'JE']


def is_TLE(status: int, may_signal_with_usr1: bool = False) -> bool:
    return os.WIFSIGNALED(status) and (
        os.WTERMSIG(status) == signal.SIGXCPU or (may_signal_with_usr1 and os.WTERMSIG(status) == signal.SIGUSR1)
    )


def is_RTE(status: int) -> bool:
    return not os.WIFEXITED(status) or bool(os.WEXITSTATUS(status))


class SubmissionResult:
    def __init__(
        self,
        verdict: str,
        score: float | None = None,
        reason: str | None = None,
        additional_info: str | None = None,
    ) -> None:
        self.verdict = verdict
        self.score = score
        self.reason = reason
        self.additional_info = additional_info
        self.testcase: TestCase | None = None
        self.runtime_testcase: TestCase | None = None
        self.runtime = -1.0
        self.ac_runtime = -1.0
        self.ac_runtime_testcase: TestCase | None = None
        self.validator_first = False
        self.sample_failures: list[SubmissionResult] = []

    def set_ac_runtime(self) -> None:
        if self.verdict == 'AC':
            self.ac_runtime = self.runtime
            self.ac_runtime_testcase = self.runtime_testcase

    def __str__(self) -> str:
        verdict = self.verdict
        details = []
        if verdict == 'AC' and self.score is not None:
            verdict += f' ({self.score:.0f})'
        if self.reason is not None:
            details.append(self.reason)
        if self.testcase is not None:
            details.append(f'testcase: {self.testcase}')
        if self.runtime != -1:
            details.append(f'CPU: {self.runtime:.2f}s @ {self.runtime_testcase}')
        return verdict if not details else f'{verdict} [{", ".join(details)}]'
