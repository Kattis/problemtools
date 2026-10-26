import textwrap
from pathlib import Path

import pytest
import yaml

from problemtools.globs import Glob
from problemtools.model import SubmissionsEntry, TimeLimitBound, parse_submissions_yaml
from problemtools.submission_rules import PermittedRule, RequiredRule, ScoreRule

ALL = Glob('')
LANGUAGES = {'cpp', 'python3'}


def parse(text: str) -> tuple[list[SubmissionsEntry], list[str]]:
    return parse_submissions_yaml(yaml.safe_load(textwrap.dedent(text)), LANGUAGES)


def parse_ok(text: str) -> list[SubmissionsEntry]:
    entries, errors = parse(text)
    assert errors == []
    return entries


def test_empty() -> None:
    assert parse('') == ([], [])
    assert parse('{}') == ([], [])


def test_submission_level_requirements() -> None:
    entries = parse_ok("""
        accepted/sol.py:
          permitted: [AC, TLE]
          required: [TLE]
          score: 50
          use_for_time_limit: lower
    """)
    assert entries == [
        SubmissionsEntry(
            glob=Glob('accepted/sol.py'),
            rules=[
                PermittedRule(scope=ALL, verdicts=frozenset({'AC', 'TLE'})),
                RequiredRule(scope=ALL, verdicts=frozenset({'TLE'})),
                ScoreRule(scope=ALL, min_score=50, max_score=50),
            ],
            time_limit_bounds=[TimeLimitBound(scope=ALL, direction='lower')],
        )
    ]


def test_test_data_requirements() -> None:
    entries = parse_ok("""
        time_limit_exceeded/solves_easy_cases.py:
          sample:
            permitted: [AC]
          secret/*-hard:
            permitted: [AC, TLE]
            required: [TLE]
            score: [0, 10.5]
            use_for_time_limit: upper
    """)
    hard = Glob('secret/*-hard')
    assert entries == [
        SubmissionsEntry(
            glob=Glob('time_limit_exceeded/solves_easy_cases.py'),
            rules=[
                PermittedRule(scope=Glob('sample'), verdicts=frozenset({'AC'})),
                PermittedRule(scope=hard, verdicts=frozenset({'AC', 'TLE'})),
                RequiredRule(scope=hard, verdicts=frozenset({'TLE'})),
                ScoreRule(scope=hard, min_score=0, max_score=10.5),
            ],
            time_limit_bounds=[TimeLimitBound(scope=hard, direction='upper')],
        )
    ]


def test_time_limit_bound_on_test_data_subset() -> None:
    entries = parse_ok("""
        slow_on_large:
          permitted: [AC]
          '{sample,secret/small-*}':
            use_for_time_limit: lower
    """)
    small = Glob('{sample,secret/small-*}')
    assert entries == [
        SubmissionsEntry(
            glob=Glob('slow_on_large'),
            rules=[PermittedRule(scope=ALL, verdicts=frozenset({'AC'}))],
            time_limit_bounds=[TimeLimitBound(scope=small, direction='lower')],
        )
    ]
    assert small.covers(Path('sample/1'))
    assert small.covers(Path('secret/small-1'))
    assert not small.covers(Path('secret/large-1'))


def test_submission_metadata() -> None:
    entries = parse_ok("""
        accepted/{a,b}.py:
          language: python3
          entrypoint: a.py
          model_solution: true
          authors: [Someone, Someone Else]
    """)
    assert entries == [
        SubmissionsEntry(glob=Glob('accepted/{a,b}.py'), language='python3', entrypoint='a.py', model_solution=True)
    ]


def test_several_entries() -> None:
    entries = parse_ok("""
        accepted:
          permitted: [AC]
        accepted/*:
          permitted: [AC, WA]
    """)
    assert [entry.glob for entry in entries] == [Glob('accepted'), Glob('accepted/*')]


@pytest.mark.parametrize(
    'text',
    [
        '[accepted]',
        'accepted',
        '{accepted: [AC]}',
        '{accepted: }',
        '{1: {permitted: [AC]}}',
        '{"accepted/**": {permitted: [AC]}}',
        '{"accepted/[ab].py": {permitted: [AC]}}',
    ],
)
def test_invalid_entry_is_dropped(text: str) -> None:
    entries, errors = parse(text)
    assert entries == []
    assert len(errors) == 1


@pytest.mark.parametrize(
    'requirement',
    [
        'permitted: AC',
        'permitted: [AC, XX]',
        'permitted: [MLE]',
        'permitted: {AC: 1}',
        'permitted: [[AC]]',
        'score: high',
        'score: true',
        'score: [1]',
        'score: [1, 2, 3]',
        'score: [10, 5]',
        'use_for_time_limit: false',
        'use_for_time_limit: true',
        'use_for_time_limit: sideways',
    ],
)
def test_invalid_requirement_is_dropped(requirement: str) -> None:
    # Both at the submission level, and for test data. Other requirements are kept.
    for text in [
        f'{{accepted: {{required: [AC], {requirement}}}}}',
        f'{{accepted: {{secret: {{required: [AC], {requirement}}}}}}}',
    ]:
        entries, errors = parse(text)
        assert len(errors) == 1
        assert len(entries) == 1
        assert entries[0].glob == Glob('accepted')
        assert [type(rule) for rule in entries[0].rules] == [RequiredRule]
        assert entries[0].time_limit_bounds == []


@pytest.mark.parametrize(
    'setting',
    [
        'language: 3',
        'language: nosuchlanguage',
        'entrypoint: [a.py]',
        'model_solution: yes please',
    ],
)
def test_invalid_metadata_is_dropped(setting: str) -> None:
    entries, errors = parse(f'{{accepted: {{required: [AC], {setting}}}}}')
    assert len(errors) == 1
    assert entries == [SubmissionsEntry(glob=Glob('accepted'), rules=[RequiredRule(scope=ALL, verdicts=frozenset({'AC'}))])]


@pytest.mark.parametrize(
    'test_data',
    [
        '"secret/**": {permitted: [AC]}',
        '1: {permitted: [AC]}',
        # Catches typos of requirement keys
        'permited: [AC]',
        'secret: {permited: [AC]}',
        'secret: {language: python3}',
    ],
)
def test_invalid_test_data_requirements(test_data: str) -> None:
    entries, errors = parse(f'{{accepted: {{required: [AC], {test_data}}}}}')
    assert len(errors) == 1
    assert entries == [SubmissionsEntry(glob=Glob('accepted'), rules=[RequiredRule(scope=ALL, verdicts=frozenset({'AC'}))])]


def test_errors_are_collected() -> None:
    entries, errors = parse("""
        accepted:
          permitted: [XX]
          secret:
            required: TLE
        "wrong_answer/**":
          permitted: [AC]
        time_limit_exceeded:
          required: [TLE]
    """)
    assert len(errors) == 3
    assert [entry.glob for entry in entries] == [Glob('accepted'), Glob('time_limit_exceeded')]
