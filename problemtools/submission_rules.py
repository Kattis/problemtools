"""Rules for what's expected of an example submission's judging results."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .diagnostics import Diagnostics, pluralize
from .model import Verdict
from .model.testdata import TestCase, TestDataGroup  # Not from .model, as model.submissions imports us

if TYPE_CHECKING:
    from .judge import SubmissionResult
    from .judge.result import ResultField
    from .model import Submission

#: A violation of a rule: a message (without the submission name), and optional additional info
#: such as the judge's output.
Violation = tuple[str, str | None]


@dataclass(frozen=True, kw_only=True)
class Rule(ABC):
    """`scope` is a glob on test data paths (relative to data/), where '' means all test data.
    What a rule does with its scope is determined by its applies_to()."""

    scope: str = ''
    is_error: bool = True
    hint: str | None = None

    def check(self, sub: Submission, results: list[SubmissionResult], diag: Diagnostics) -> bool:
        """Check the results of judging `sub`, and report any violations to `diag`. Returns whether
        an error was reported."""
        violations = self._check([r for r in results if r.test_node is not None and self.applies_to(r.test_node)])
        for msg, additional_info in violations:
            if self.hint:
                msg += f' ({self.hint})'
            if self.is_error:
                diag.error(f'{sub} {msg}', additional_info)
            else:
                diag.warning(f'{sub} {msg}', additional_info)
        return self.is_error and bool(violations)

    @abstractmethod
    def applies_to(self, node: TestCase | TestDataGroup) -> bool:
        """Whether this rule constrains the result for `node`."""

    @abstractmethod
    def _check(self, results: list[SubmissionResult]) -> list[Violation]:
        """The violations among `results`, which only contains results this rule applies to."""


@dataclass(frozen=True, kw_only=True)
class PermittedRule(Rule):
    """Every test case in scope must get one of `verdicts`."""

    verdicts: frozenset[Verdict]

    def applies_to(self, node: TestCase | TestDataGroup) -> bool:
        return isinstance(node, TestCase) and _scope_covers(self.scope, node)

    def _check(self, results: list[SubmissionResult]) -> list[Violation]:
        """One violation per disallowed verdict, showing the first test case getting it."""
        disallowed_by_verdict: dict[str, list[SubmissionResult]] = {}
        for r in results:
            if r.verdict not in self.verdicts:
                disallowed_by_verdict.setdefault(r.verdict, []).append(r)

        permitted = ', '.join(sorted(self.verdicts))
        violations: list[Violation] = []
        for disallowed in disallowed_by_verdict.values():
            first = disallowed[0]
            more = f' (and {pluralize(len(disallowed) - 1, "more test case")})' if len(disallowed) > 1 else ''
            msg = f'got {_fmt_result(first)} on {first.test_node}{more}, which is not permitted (permitted: {permitted})'
            violations.append((msg, first.additional_info))
        return violations


@dataclass(frozen=True, kw_only=True)
class FinalVerdictRule(Rule):
    """The group whose path is the scope ('' for the root) must get `verdict`.

    Not part of any version of the problem package format specification, and can't be set by
    users. We only generate it internally, to keep problemtools' traditional legacy behavior of
    checking a submission's final verdict.

    `show_details` controls whether a violation includes the judge's output. The policy turns it
    off when other rules (e.g. a PermittedRule) already report it for the failing test case."""

    verdict: Verdict
    show_details: bool = True

    def applies_to(self, node: TestCase | TestDataGroup) -> bool:
        return isinstance(node, TestDataGroup) and node.path == Path(self.scope)

    def _check(self, results: list[SubmissionResult]) -> list[Violation]:
        assert len(results) == 1, f'Expected exactly one result for group {self.scope!r}, got {len(results)}'
        result = results[0]
        if result.verdict == self.verdict:
            return []
        additional_info = result.additional_info if self.show_details else None
        return [(f'got {_fmt_result(result)}, expected {self.verdict}', additional_info)]


@dataclass(frozen=True, kw_only=True)
class ScoreRule(Rule):
    """The groups matched by the scope ('' for the root) must get a score in [min_score, max_score]."""

    min_score: float = float('-inf')
    max_score: float = float('inf')

    def applies_to(self, node: TestCase | TestDataGroup) -> bool:
        # TODO: The scope should be a glob, possibly matching several groups. Glob matching isn't
        # implemented yet, so for now we only support the empty scope (the root group).
        if self.scope != '':
            raise NotImplementedError(f'Test data scopes in score rules are not yet supported (got {self.scope!r})')
        return isinstance(node, TestDataGroup) and node.path == Path(self.scope)

    def _check(self, results: list[SubmissionResult]) -> list[Violation]:
        if self.min_score == self.max_score:
            expected = f'{self.min_score:g}'
        else:
            expected = f'[{self.min_score:g}, {self.max_score:g}]'
        violations: list[Violation] = []
        for r in results:
            if r.verdict != 'AC' or r.score is None or self.min_score <= r.score <= self.max_score:
                continue
            assert isinstance(r.test_node, TestDataGroup)
            where = '' if r.test_node.is_root else f' on {r.test_node}'
            violations.append((f'got score {r.score:g}{where}, expected {expected}', None))
        return violations


def _scope_covers(scope: str, testcase: TestCase) -> bool:
    """Whether `scope` matches `testcase`, or any of its parent groups."""
    if scope != '':
        raise NotImplementedError(f'Test data scopes in rules are not yet supported (got {scope!r})')
    return True


def _fmt_result(result: SubmissionResult) -> str:
    """Format a result for a rule's message. Include the runtime for TLE, as that's what the verdict is about."""
    fields: list[ResultField] = ['score', 'reason']
    if result.verdict == 'TLE':
        fields.append('runtime')
    return result.format(fields)
