from __future__ import annotations

from collections.abc import Collection
from typing import Literal

from ..model import TestCase, TestDataGroup

#: The optional parts of a formatted SubmissionResult.
ResultField = Literal['score', 'reason', 'testcase', 'runtime']
ALL_RESULT_FIELDS: tuple[ResultField, ...] = ('score', 'reason', 'testcase', 'runtime')


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

    def format(self, fields: Collection[ResultField] = ALL_RESULT_FIELDS) -> str:
        """Format the verdict, followed by whichever of `fields` are available, e.g.
        'AC (50) [CPU: 0.12s @ testcase secret/3]' or 'RTE [SIGABRT, testcase: testcase secret/1]'."""
        verdict = self.verdict
        if 'score' in fields and verdict == 'AC' and self.score is not None:
            verdict += f' ({self.score:g})'
        details = []
        if 'reason' in fields and self.reason is not None:
            details.append(self.reason)
        if 'testcase' in fields and isinstance(self.test_node, TestCase):
            details.append(f'testcase: {self.test_node}')
        if 'runtime' in fields and self.runtime != -1:
            details.append(f'CPU: {self.runtime:.2f}s @ {self.runtime_testcase}')
        return verdict if not details else f'{verdict} [{", ".join(details)}]'

    def __str__(self) -> str:
        return self.format()
