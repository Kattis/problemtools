from pathlib import Path

import pytest

from problemtools.checks.submissions import _check_globs_match, _check_language_and_entrypoint
from problemtools.globs import Glob
from problemtools.model import SubmissionsEntry, SubmissionsPolicy, TimeLimitBound
from problemtools.model.paths import relpath
from problemtools.submission_rules import PermittedRule, RequiredRule, Rule, ScoreRule
from tests.conftest import RecordingDiagnostics
from tests.test_load_submissions import V_2023_07, load
from tests.test_submission_rules import ROOT


def permitted(*verdicts: str, scope: str = '') -> PermittedRule:
    return PermittedRule(scope=Glob(scope), verdicts=frozenset(verdicts))  # type: ignore[arg-type]


def required(*verdicts: str, scope: str = '') -> RequiredRule:
    return RequiredRule(scope=Glob(scope), verdicts=frozenset(verdicts))  # type: ignore[arg-type]


def check_globs(*entries: SubmissionsEntry) -> list[str]:
    diag = RecordingDiagnostics()
    paths = [relpath(Path(p)) for p in ['accepted/sol.py', 'wrong_answer/sol.py']]
    _check_globs_match(SubmissionsPolicy(entries=list(entries)), paths, ROOT, diag)
    return [severity for severity, _ in diag.messages]


def test_globs_matching() -> None:
    assert (
        check_globs(
            SubmissionsEntry(glob=Glob('accepted')),
            SubmissionsEntry(
                glob=Glob('*/sol.py'),
                rules=[permitted('AC', scope='secret/g1'), ScoreRule(scope=Glob('secret/*'), min_score=1)],
                time_limit_bounds=[TimeLimitBound(scope=Glob('sample'), direction='lower')],
            ),
        )
        == []
    )


def test_glob_matching_no_submission() -> None:
    assert check_globs(SubmissionsEntry(glob=Glob('accepted/other.py'))) == ['warning']
    # Default entries are not reported, as there's no requirement to have submissions in every default directory
    assert check_globs(SubmissionsEntry(glob=Glob('run_time_error'), is_default=True)) == []


def test_glob_matching_no_test_data() -> None:
    assert check_globs(SubmissionsEntry(glob=Glob('accepted'), rules=[permitted('AC', scope='secret/g3')])) == ['warning']
    # Score rules only match groups, not test cases
    assert check_globs(SubmissionsEntry(glob=Glob('accepted'), rules=[ScoreRule(scope=Glob('secret/g1/1'))])) == ['warning']
    bound = TimeLimitBound(scope=Glob('large'), direction='lower')
    assert check_globs(SubmissionsEntry(glob=Glob('accepted'), time_limit_bounds=[bound])) == ['warning']
    # Several rules with the same unmatched scope give a single warning
    rules: list[Rule] = [permitted('AC', scope='large'), required('AC', scope='large')]
    assert check_globs(SubmissionsEntry(glob=Glob('accepted'), rules=rules)) == ['warning']


def check_language_and_entrypoint(tmp_path: Path, submissions_yaml: str, include_files: list[str] | None = None) -> list[str]:
    diag = RecordingDiagnostics()
    submissions = load(tmp_path, V_2023_07, ['accepted/a.py', 'accepted/b.py'], submissions_yaml, include_files)
    assert submissions.policy.parse_errors == []
    _check_language_and_entrypoint(submissions, diag)
    return [severity for severity, _ in diag.messages]


def test_language_and_entrypoint_consistent(tmp_path: Path) -> None:
    yaml = 'accepted:\n  language: python3\n  entrypoint: a.py\naccepted/a.py:\n  language: python3\n'
    assert check_language_and_entrypoint(tmp_path, yaml) == []


@pytest.mark.parametrize('key, values', [('language', ('python2', 'python3')), ('entrypoint', ('a.py', 'b.py'))])
def test_conflicting_language_or_entrypoint(tmp_path: Path, key: str, values: tuple[str, str]) -> None:
    yaml = f'accepted:\n  {key}: {values[0]}\naccepted/a.py:\n  {key}: {values[1]}\n'
    # Only accepted/a.py has conflicting values
    assert check_language_and_entrypoint(tmp_path, yaml) == ['error']


def test_entrypoint_with_include_mainfile(tmp_path: Path) -> None:
    yaml = 'accepted/a.py:\n  entrypoint: a.py\n'
    assert check_language_and_entrypoint(tmp_path, yaml, ['python3/main.py']) == ['warning']
