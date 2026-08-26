from __future__ import annotations

from ..model import TestCase, TestDataGroup


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
        self.test_node: TestCase | TestDataGroup | None = None
        self.runtime_testcase: TestCase | None = None
        self.runtime = -1.0
        self.validator_first = False  # Needed to work around interactive giving unreliable runtime on WA

    def __str__(self) -> str:
        verdict = self.verdict
        details = []
        if verdict == 'AC' and self.score is not None:
            verdict += f' ({self.score:.0f})'
        if self.reason is not None:
            details.append(self.reason)
        if isinstance(self.test_node, TestCase):
            details.append(f'testcase: {self.test_node}')
        if self.runtime != -1:
            details.append(f'CPU: {self.runtime:.2f}s @ {self.runtime_testcase}')
        return verdict if not details else f'{verdict} [{", ".join(details)}]'
