from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

from ..formatversion import FormatVersion
from ..globs import Glob
from ..languages import Languages
from ..metadata import Metadata
from ..run import SourceCode
from ..submission_rules import FinalVerdictRule, PermittedRule, RequiredRule, Rule, ScoreRule
from .files import EntryKind, Files
from .includes import Includes
from .paths import RelativePath, relpath
from .programs import get_source_program
from .submissions_policy import SubmissionsEntry, SubmissionsPolicy, TimeLimitBound, parse_submissions_yaml
from .testdata import TestDataGroup


@dataclass(frozen=True)
class Submission:
    """A single example submission, and what's expected of it.

    `path` is relative to the submissions directory, e.g. for
    submissions/accepted/hello.java, path is accepted/hello.java.

    `rules` is empty if nothing is expected of the submission, e.g. for a legacy problem
    when it's not in a well-known directory. That's an error, and such a submission is ignored.

    `rules` and `time_limit_bounds` are tuples rather than lists to keep Submission hashable,
    as it's used as a dict key."""

    program: SourceCode
    path: RelativePath
    rules: tuple[Rule, ...]
    time_limit_bounds: tuple[TimeLimitBound, ...]

    def __post_init__(self) -> None:
        if len(self.path.parts) != 2:
            raise ValueError(f'Submission path must be on the form directory/name, got {self.path}')

    @property
    def directory(self) -> str:
        """The submission's top-level directory under submissions/."""
        return self.path.parts[0]

    def __str__(self) -> str:
        return f'{self.directory}/{self.program}'


@dataclass(frozen=True)
class Submissions:
    """All example submissions for a problem, and the policy their expectations come from."""

    policy: SubmissionsPolicy
    submissions: list[Submission] = field(default_factory=list)


def load_submissions(
    files: Files, language_config: Languages, includes: Includes, testdata: TestDataGroup, metadata: Metadata
) -> Submissions:
    parsed_entries, parse_errors = _load_submissions_yaml(files, language_config)
    policy = SubmissionsPolicy(entries=_default_entries(testdata, metadata) + parsed_entries, parse_errors=parse_errors)
    submissions = []
    for directory in files.listdir(files.root / 'submissions', EntryKind.DIR):
        for program_path in files.listdir(directory):
            path = relpath(Path(directory.name) / program_path.name)
            matching = policy.entries_for(path)
            # Later entries take precedence. Conflicting entries are reported by checks.
            language_codes = [entry.language for entry in matching if entry.language is not None]
            language = language_config.languages[language_codes[-1]] if language_codes else None
            program = get_source_program(files, program_path, language_config, includes=includes, language=language)
            if program is None:
                continue
            submissions.append(
                Submission(
                    program=program,
                    path=path,
                    rules=tuple(rule for entry in matching for rule in entry.rules),
                    time_limit_bounds=tuple(bound for entry in matching for bound in entry.time_limit_bounds),
                )
            )
    return Submissions(policy=policy, submissions=submissions)


def _load_submissions_yaml(files: Files, language_config: Languages) -> tuple[list[SubmissionsEntry], list[str]]:
    """The entries from submissions/submissions.yaml (if any), and errors from parsing it."""
    path = files.root / 'submissions' / 'submissions.yaml'
    if not files.is_file(path):
        return [], []
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        return [], [f'invalid YAML: {e}']
    return parse_submissions_yaml(data, language_config.languages.keys())


def _default_entries(testdata: TestDataGroup, metadata: Metadata) -> list[SubmissionsEntry]:
    """The expectations from the problem format's default directories."""
    match metadata.problem_format_version:
        case FormatVersion.LEGACY:
            return _legacy_entries(testdata, metadata)
        case FormatVersion.V_2023_07:
            return _entries_2023_07(testdata, metadata)


def _legacy_entries(testdata: TestDataGroup, metadata: Metadata) -> list[SubmissionsEntry]:
    """The directory-name-based expectations used by problem formats that predate submissions.yaml.

    Problemtools has traditionally only checked a submission's final verdict, so that's an error,
    while violating the (stricter) per test case expectations is only a warning.
    """
    # show_details=False: when the final verdict is wrong, the permitted rule shows the failing test case
    accepted: list[Rule] = [
        PermittedRule(verdicts=frozenset({'AC'}), is_error=False),
        FinalVerdictRule(verdict='AC', show_details=False),
        *_best_score_rules(testdata, metadata),
    ]
    wrong_answer: list[Rule] = [
        PermittedRule(verdicts=frozenset({'AC', 'WA'}), is_error=False),
        FinalVerdictRule(verdict='WA', show_details=False),
    ]
    time_limit_exceeded: list[Rule] = [
        PermittedRule(verdicts=frozenset({'AC', 'WA', 'TLE'}), is_error=False),
        # Details are needed when the final verdict is WA, which the permitted rule allows
        FinalVerdictRule(verdict='TLE'),
    ]
    run_time_error: list[Rule] = [FinalVerdictRule(verdict='RTE')]

    return [
        _default_entry('accepted', accepted, 'lower'),
        _default_entry('partially_accepted', _partially_accepted_rules(testdata, metadata)),
        _default_entry('wrong_answer', wrong_answer),
        _default_entry('time_limit_exceeded', time_limit_exceeded, 'upper'),
        _default_entry('run_time_error', run_time_error),
    ]


def _entries_2023_07(testdata: TestDataGroup, metadata: Metadata) -> list[SubmissionsEntry]:
    """The default directories from the 2023-07 specification.

    We extend the specification with the legacy partially_accepted directory, and for scoring
    problems, with a warning when an accepted submission doesn't get the best score."""
    accepted: list[Rule] = [
        PermittedRule(verdicts=frozenset({'AC'})),
        *_best_score_rules(testdata, metadata),
    ]
    rejected: list[Rule] = [RequiredRule(verdicts=frozenset({'RTE', 'TLE', 'WA'}))]
    wrong_answer: list[Rule] = [
        PermittedRule(verdicts=frozenset({'AC', 'WA'})),
        RequiredRule(verdicts=frozenset({'WA'})),
    ]
    time_limit_exceeded: list[Rule] = [
        PermittedRule(verdicts=frozenset({'AC', 'TLE'})),
        RequiredRule(verdicts=frozenset({'TLE'})),
    ]
    run_time_error: list[Rule] = [
        PermittedRule(verdicts=frozenset({'AC', 'RTE'})),
        RequiredRule(verdicts=frozenset({'RTE'})),
    ]
    brute_force: list[Rule] = [
        PermittedRule(verdicts=frozenset({'AC', 'RTE', 'TLE'})),
        RequiredRule(verdicts=frozenset({'RTE', 'TLE'})),
    ]

    return [
        _default_entry('accepted', accepted, 'lower'),
        _default_entry('partially_accepted', _partially_accepted_rules(testdata, metadata)),
        _default_entry('rejected', rejected),
        _default_entry('wrong_answer', wrong_answer),
        _default_entry('time_limit_exceeded', time_limit_exceeded, 'upper'),
        _default_entry('run_time_error', run_time_error),
        _default_entry('brute_force', brute_force),
    ]


def _default_entry(
    directory: str, rules: list[Rule], time_limit_bound: Literal['lower', 'upper'] | None = None
) -> SubmissionsEntry:
    """A default entry for all submissions in `directory`, optionally bounding the time limit on all test data."""
    bounds = [] if time_limit_bound is None else [TimeLimitBound(scope=Glob(''), direction=time_limit_bound)]
    return SubmissionsEntry(glob=Glob(directory), rules=rules, time_limit_bounds=bounds, is_default=True)


def _best_score_rules(testdata: TestDataGroup, metadata: Metadata) -> list[Rule]:
    """For scoring problems, a warning if an accepted submission doesn't get the best score."""
    if not metadata.is_scoring():
        return []
    min_score, max_score = testdata.get_score_range()
    best = min_score if metadata.legacy_grading.objective == 'min' else max_score
    # For some heuristic problems, not attaining full score is expected. Thus, only warn.
    if not math.isfinite(best):
        return []
    hint = 'if full score is attainable, consider moving it to partially_accepted'
    return [ScoreRule(min_score=best, max_score=best, is_error=False, hint=hint)]


def _partially_accepted_rules(testdata: TestDataGroup, metadata: Metadata) -> list[Rule]:
    """Accepted, and for scoring problems, a warning if the submission gets the best score."""
    rules: list[Rule] = [FinalVerdictRule(verdict='AC')]
    if metadata.is_scoring():
        min_score, max_score = testdata.get_score_range()
        hint = 'consider moving it to accepted'
        # If the best score is infinite, so is the bound (inf - 0.01 == inf), and the rule accepts any score
        if metadata.legacy_grading.objective == 'min':
            rules.append(ScoreRule(min_score=min_score + 0.01, max_score=max_score, is_error=False, hint=hint))
        else:
            rules.append(ScoreRule(min_score=min_score, max_score=max_score - 0.01, is_error=False, hint=hint))
    return rules
