from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from problemtools.globs import Glob
from problemtools.judge import SubmissionResult
from problemtools.model.paths import abspath, relpath
from problemtools.model.testdata import TestCase, TestDataGroup
from problemtools.submission_rules import FinalVerdictRule, PermittedRule, RequiredRule, Rule, ScoreRule
from tests.conftest import RecordingDiagnostics

if TYPE_CHECKING:
    from problemtools.model import Submission

# Not test classes -- just named that way by the model. Tell pytest not to collect them.
TestCase.__test__ = False  # type: ignore[attr-defined]
TestDataGroup.__test__ = False  # type: ignore[attr-defined]


def make_testcase(path: str) -> TestCase:
    return TestCase(
        infile=abspath(Path('/data', path).with_suffix('.in')),
        ansfile=abspath(Path('/data', path).with_suffix('.ans')),
        path=relpath(Path(path)),
        input_validator_flags=[],
        output_validator_flags=[],
    )


def make_group(path: str, items: list[TestCase | TestDataGroup]) -> TestDataGroup:
    return TestDataGroup(
        name=path,
        datadir=abspath(Path('/data', path)),
        path=relpath(Path(path)),
        config={},
        is_root=path == '',
        items=items,
    )


# data/
#   sample/1
#   secret/g1/{1,2}
#   secret/g2/1
SAMPLE_1 = make_testcase('sample/1')
G1_1 = make_testcase('secret/g1/1')
G1_2 = make_testcase('secret/g1/2')
G2_1 = make_testcase('secret/g2/1')
SAMPLE = make_group('sample', [SAMPLE_1])
G1 = make_group('secret/g1', [G1_1, G1_2])
G2 = make_group('secret/g2', [G2_1])
SECRET = make_group('secret', [G1, G2])
ROOT = make_group('', [SAMPLE, SECRET])
TESTCASES = [SAMPLE_1, G1_1, G1_2, G2_1]
GROUPS = [ROOT, SAMPLE, SECRET, G1, G2]
ALL_NODES: list[TestCase | TestDataGroup] = [*TESTCASES, *GROUPS]


class FakeSubmission:
    def __str__(self) -> str:
        return 'accepted/sol.py'


SUB = cast('Submission', FakeSubmission())


def result(node: TestCase | TestDataGroup, verdict: str, score: float | None = None) -> SubmissionResult:
    r = SubmissionResult(verdict, score=score)
    r.test_node = node
    return r


def results_for(*verdicts: str) -> list[SubmissionResult]:
    """Results for all test cases, in order SAMPLE_1, G1_1, G1_2, G2_1."""
    return [result(tc, v) for tc, v in zip(TESTCASES, verdicts, strict=True)]


def check(rule: Rule, results: list[SubmissionResult]) -> list[str]:
    """The severities of the violations reported, e.g. ['error', 'error']."""
    diag = RecordingDiagnostics()
    rule.check(SUB, results, diag)
    return [severity for severity, _ in diag.messages]


def applies_to(rule: Rule) -> list[TestCase | TestDataGroup]:
    return [node for node in ALL_NODES if rule.applies_to(node)]


@pytest.mark.parametrize(
    'scope, expected',
    [
        ('', TESTCASES),
        ('secret', [G1_1, G1_2, G2_1]),
        ('secret/g1', [G1_1, G1_2]),
        ('secret/g1/2', [G1_2]),
        ('secret/*', [G1_1, G1_2, G2_1]),
        ('*/1', [SAMPLE_1]),
        ('{sample,secret/g2}', [SAMPLE_1, G2_1]),
        ('nonexistent', []),
    ],
)
def test_testcase_rules_apply_to_covered_testcases(scope: str, expected: list[TestCase]) -> None:
    for rule in [
        PermittedRule(scope=Glob(scope), verdicts=frozenset({'AC'})),
        RequiredRule(scope=Glob(scope), verdicts=frozenset({'AC'})),
    ]:
        assert applies_to(rule) == expected


@pytest.mark.parametrize(
    'scope, expected',
    [
        ('', [ROOT]),
        ('secret', [SECRET]),
        ('secret/*', [G1, G2]),
        ('*', [SAMPLE, SECRET]),
        ('secret/g1/1', []),  # A test case, which score rules never apply to
    ],
)
def test_score_rule_applies_to_matched_groups(scope: str, expected: list[TestDataGroup]) -> None:
    assert applies_to(ScoreRule(scope=Glob(scope), min_score=0)) == expected


def test_final_verdict_rule_applies_to_root_only() -> None:
    assert applies_to(FinalVerdictRule(verdict='AC')) == [ROOT]


def test_permitted_rule() -> None:
    rule = PermittedRule(scope=Glob('secret'), verdicts=frozenset({'AC', 'TLE'}))
    # The WA on the sample is out of scope
    assert check(rule, results_for('WA', 'AC', 'TLE', 'AC')) == []
    # One violation per disallowed verdict
    assert check(rule, results_for('AC', 'WA', 'WA', 'RTE')) == ['error', 'error']


def test_permitted_rule_warning() -> None:
    rule = PermittedRule(scope=Glob(''), verdicts=frozenset({'AC'}), is_error=False)
    assert check(rule, results_for('AC', 'AC', 'WA', 'AC')) == ['warning']


def test_required_rule_satisfied() -> None:
    rule = RequiredRule(scope=Glob('secret'), verdicts=frozenset({'TLE', 'RTE'}))
    assert check(rule, results_for('AC', 'AC', 'RTE', 'AC')) == []
    assert check(rule, results_for('AC', 'TLE', 'AC', 'WA')) == []


def test_required_rule_violated() -> None:
    rule = RequiredRule(scope=Glob('secret'), verdicts=frozenset({'TLE', 'RTE'}))
    # The TLE on the sample is out of scope
    assert check(rule, results_for('TLE', 'AC', 'WA', 'AC')) == ['error']


def test_required_rule_warning() -> None:
    rule = RequiredRule(scope=Glob(''), verdicts=frozenset({'WA'}), is_error=False)
    assert check(rule, results_for('AC', 'AC', 'AC', 'AC')) == ['warning']


def test_required_rule_with_no_results_in_scope() -> None:
    # E.g. if test data was filtered on the command line
    rule = RequiredRule(scope=Glob('secret'), verdicts=frozenset({'TLE'}))
    assert check(rule, [result(SAMPLE_1, 'AC')]) == []
    assert check(rule, []) == []


def test_score_rule() -> None:
    rule = ScoreRule(scope=Glob('secret/*'), min_score=10, max_score=20)
    # The root's score is out of range, but also out of scope
    assert check(rule, [result(G1, 'AC', 15), result(G2, 'AC', 20), result(ROOT, 'AC', 40)]) == []
    assert check(rule, [result(G1, 'AC', 15), result(G2, 'AC', 25), result(ROOT, 'AC', 40)]) == ['error']
    assert check(rule, [result(G1, 'AC', 9), result(G2, 'AC', 25), result(ROOT, 'AC', 40)]) == ['error', 'error']


def test_score_rule_on_root() -> None:
    rule = ScoreRule(min_score=100, max_score=100)
    assert check(rule, [result(G1, 'AC', 50), result(ROOT, 'AC', 100)]) == []
    assert check(rule, [result(G1, 'AC', 50), result(ROOT, 'AC', 90)]) == ['error']
