"""Rules for what's expected of an example submission's judging results."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .diagnostics import Diagnostics, pluralize
from .globs import Glob
from .model import Verdict
from .model.testdata import TestCase, TestDataGroup  # Not from .model, as model.submissions imports us

if TYPE_CHECKING:
    from .judge import SubmissionResult
    from .judge.result import ResultField
    from .model import Submission

#: A violation of a rule: a message (without the submission name), and optional additional info
#: such as the judge's output.
Violation = tuple[str, str | None]

#: The scope of a rule applying to all test data.
_ALL_TEST_DATA = Glob('')

#: Verdicts that can't be expressed in a rule, and the verdict they count as when checking rules.
_RULE_VERDICT_REMAP: dict[Verdict, Verdict] = {'OLE': 'WA', 'MLE': 'RTE'}


def _rule_verdict(verdict: Verdict) -> Verdict:
    """The verdict a result counts as when checking rules."""
    return _RULE_VERDICT_REMAP.get(verdict, verdict)


@dataclass(frozen=True, kw_only=True)
class Rule(ABC):
    """`scope` is a glob on test data paths (relative to data/), where the empty glob means all
    test data. What a rule does with its scope is determined by its applies_to()."""

    scope: Glob = _ALL_TEST_DATA
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
        return isinstance(node, TestCase) and self.scope.covers(node.path)

    def _check(self, results: list[SubmissionResult]) -> list[Violation]:
        """One violation per disallowed verdict, showing the first test case getting it."""
        disallowed_by_verdict: dict[str, list[SubmissionResult]] = {}
        for r in results:
            if _rule_verdict(r.verdict) not in self.verdicts:
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
class RequiredRule(Rule):
    """At least one test case in scope must get one of `verdicts`.

    If no test case in scope was judged, e.g. because test data was filtered on the command line,
    there's no violation. Note that filtering can still cause a spurious violation, if it excludes
    exactly the test cases that would have gotten a required verdict."""

    verdicts: frozenset[Verdict]

    def applies_to(self, node: TestCase | TestDataGroup) -> bool:
        return isinstance(node, TestCase) and self.scope.covers(node.path)

    def _check(self, results: list[SubmissionResult]) -> list[Violation]:
        if not results or any(_rule_verdict(r.verdict) in self.verdicts for r in results):
            return []
        required = ', '.join(sorted(self.verdicts))
        got = ', '.join(sorted({r.verdict for r in results}))
        where = f' in {self.scope}' if self.scope.pattern else ''
        cases = pluralize(len(results), 'test case')
        return [(f'got none of the required verdicts ({required}) on {cases}{where} (got: {got})', None)]


@dataclass(frozen=True, kw_only=True)
class FinalVerdictRule(Rule):
    """The group matched exactly by the scope (the root, for the empty glob) must get `verdict`.

    Not part of any version of the problem package format specification, and can't be set by
    users. We only generate it internally, to keep problemtools' traditional legacy behavior of
    checking a submission's final verdict.

    `show_details` controls whether a violation includes the judge's output. The policy turns it
    off when other rules (e.g. a PermittedRule) already report it for the failing test case."""

    verdict: Verdict
    show_details: bool = True

    def applies_to(self, node: TestCase | TestDataGroup) -> bool:
        return isinstance(node, TestDataGroup) and self.scope.matches(node.path)

    def _check(self, results: list[SubmissionResult]) -> list[Violation]:
        assert len(results) == 1, f'Expected exactly one result for group {self.scope!r}, got {len(results)}'
        result = results[0]
        if _rule_verdict(result.verdict) == self.verdict:
            return []
        additional_info = result.additional_info if self.show_details else None
        return [(f'got {_fmt_result(result)}, expected {self.verdict}', additional_info)]


@dataclass(frozen=True, kw_only=True)
class ScoreRule(Rule):
    """The groups matched exactly by the scope (the root, for the empty glob) must get a score in
    [min_score, max_score]. Never applies to test cases."""

    min_score: float = float('-inf')
    max_score: float = float('inf')

    def applies_to(self, node: TestCase | TestDataGroup) -> bool:
        return isinstance(node, TestDataGroup) and self.scope.matches(node.path)

    def _check(self, results: list[SubmissionResult]) -> list[Violation]:
        if self.min_score == self.max_score:
            expected = f'{self.min_score:g}'
        else:
            expected = f'[{self.min_score:g}, {self.max_score:g}]'
        violations: list[Violation] = []
        for r in results:
            # The score is None for judge errors (and for pass-fail problems, which can't have score rules)
            if r.score is None or self.min_score <= r.score <= self.max_score:
                continue
            assert isinstance(r.test_node, TestDataGroup)
            verdict = '' if r.verdict == 'AC' else f' ({r.verdict})'
            where = '' if r.test_node.is_root else f' on {r.test_node}'
            violations.append((f'got score {r.score:g}{verdict}{where}, expected {expected}', None))
        return violations


def _fmt_result(result: SubmissionResult) -> str:
    """Format a result for a rule's message. Include the runtime for TLE, as that's what the verdict is about."""
    fields: list[ResultField] = ['score', 'reason']
    if result.verdict == 'TLE':
        fields.append('runtime')
    return result.format(fields)
