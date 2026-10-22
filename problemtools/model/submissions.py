from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from ..globs import Glob
from ..languages import Languages
from ..metadata import Metadata
from ..run import SourceCode
from ..submission_rules import FinalVerdictRule, PermittedRule, Rule, ScoreRule
from .files import EntryKind, Files
from .includes import Includes
from .paths import RelativePath, relpath
from .programs import find_source_programs
from .testdata import TestDataGroup


@dataclass(frozen=True)
class TimeLimitBound:
    """The submission's runtime on the test cases in `scope` bounds the time limit: from below
    (the time limit must be comfortably above the runtime) or from above (comfortably below it)."""

    scope: Glob
    direction: Literal['lower', 'upper']


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
class SubmissionsEntry:
    """What's expected of the submissions matched by `glob` (covering, so a directory matches all
    submissions in it). Comes from the defaults for the problem format, or (in the future) from a key in
    submissions.yaml. `is_default` is set for entries from the defaults."""

    glob: Glob
    rules: list[Rule] = field(default_factory=list)
    time_limit_bounds: list[TimeLimitBound] = field(default_factory=list)
    is_default: bool = False


@dataclass(frozen=True)
class SubmissionsPolicy:
    """All entries describing what's expected of submissions. A submission gets the rules and time
    limit bounds of every entry matching it."""

    entries: list[SubmissionsEntry]

    def entries_for(self, path: RelativePath) -> list[SubmissionsEntry]:
        """The entries matching a submission, `path` being relative to the submissions directory."""
        return [entry for entry in self.entries if entry.glob.covers(path)]


@dataclass(frozen=True)
class Submissions:
    """All example submissions for a problem, and the policy their expectations come from."""

    policy: SubmissionsPolicy
    submissions: list[Submission] = field(default_factory=list)


def load_submissions(
    files: Files, language_config: Languages, includes: Includes, testdata: TestDataGroup, metadata: Metadata
) -> Submissions:
    policy = SubmissionsPolicy(entries=_legacy_entries(testdata, metadata))
    submissions = []
    for directory in files.listdir(files.root / 'submissions', EntryKind.DIR):
        for program in find_source_programs(files, directory, language_config=language_config, includes=includes):
            path = relpath(Path(directory.name) / program.name)
            matching = policy.entries_for(path)
            submissions.append(
                Submission(
                    program=program,
                    path=path,
                    rules=tuple(rule for entry in matching for rule in entry.rules),
                    time_limit_bounds=tuple(bound for entry in matching for bound in entry.time_limit_bounds),
                )
            )
    return Submissions(policy=policy, submissions=submissions)


def _legacy_entries(testdata: TestDataGroup, metadata: Metadata) -> list[SubmissionsEntry]:
    """The directory-name-based expectations used by problem formats that predate submissions.yaml.

    Problemtools has traditionally only checked a submission's final verdict, so that's an error,
    while violating the (stricter) per test case expectations is only a warning.
    """
    all_testdata = Glob('')
    lower = [TimeLimitBound(scope=all_testdata, direction='lower')]
    upper = [TimeLimitBound(scope=all_testdata, direction='upper')]

    # show_details=False: when the final verdict is wrong, the permitted rule shows the failing test case
    accepted: list[Rule] = [
        PermittedRule(verdicts=frozenset({'AC'}), is_error=False),
        FinalVerdictRule(verdict='AC', show_details=False),
    ]
    partially_accepted: list[Rule] = [FinalVerdictRule(verdict='AC')]
    if metadata.is_scoring():
        min_score, max_score = testdata.get_score_range()
        best = min_score if metadata.legacy_grading.objective == 'min' else max_score
        # For some heuristic problems, not attaining full score is expected. Thus, only warn.
        if math.isfinite(best):
            hint = 'if full score is attainable, consider moving it to partially_accepted'
            accepted.append(ScoreRule(min_score=best, max_score=best, is_error=False, hint=hint))

        hint = 'consider moving it to accepted'
        # If the best score is infinite, so is the bound (inf - 0.01 == inf), and the rule accepts any score
        if metadata.legacy_grading.objective == 'min':
            partially_accepted.append(ScoreRule(min_score=min_score + 0.01, max_score=max_score, is_error=False, hint=hint))
        else:
            partially_accepted.append(ScoreRule(min_score=min_score, max_score=max_score - 0.01, is_error=False, hint=hint))

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
        SubmissionsEntry(glob=Glob('accepted'), rules=accepted, time_limit_bounds=lower, is_default=True),
        SubmissionsEntry(glob=Glob('partially_accepted'), rules=partially_accepted, is_default=True),
        SubmissionsEntry(glob=Glob('wrong_answer'), rules=wrong_answer, is_default=True),
        SubmissionsEntry(glob=Glob('time_limit_exceeded'), rules=time_limit_exceeded, time_limit_bounds=upper, is_default=True),
        SubmissionsEntry(glob=Glob('run_time_error'), rules=run_time_error, is_default=True),
    ]
