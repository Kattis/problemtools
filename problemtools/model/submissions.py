from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from ..languages import Languages
from ..metadata import Metadata
from ..run import Program, find_programs
from ..submission_rules import FinalVerdictRule, PermittedRule, Rule, ScoreRule
from .includes import Includes
from .paths import RelativePath, relpath, resolve
from .testdata import TestDataGroup


@dataclass(frozen=True)
class Submission:
    """A single example submission.

    `path` is relative to the submissions directory, e.g. for
    submissions/accepted/hello.java, path is accepted/hello.java."""

    program: Program
    path: RelativePath

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
class LegacyPolicy:
    """The directory-name-based policy for what's expected of a submission, used by problem
    formats that predate submissions.yaml: everything is inferred purely from which of the
    well-known directories (if any) a submission's path starts with.

    Problemtools has traditionally only checked a submission's final verdict, so that's an
    error, while violating the (stricter) per test case expectations is only a warning.
    """

    def rules_for(self, submission: Submission, testdata: TestDataGroup, metadata: Metadata) -> list[Rule] | None:
        """The rules for this submission, or None if it isn't in a well-known directory."""
        match submission.directory:
            case 'accepted':
                # show_details=False: when the final verdict is wrong, the permitted rule shows the failing test case
                rules: list[Rule] = [
                    PermittedRule(verdicts=frozenset({'AC'}), is_error=False),
                    FinalVerdictRule(verdict='AC', show_details=False),
                ]
                if metadata.is_scoring():
                    best = _best_score(testdata, metadata)
                    # For some heuristic problems, not attaining full score is expected. Thus, only warn.
                    if math.isfinite(best):
                        hint = 'if full score is attainable, consider moving it to partially_accepted'
                        rules.append(ScoreRule(min_score=best, max_score=best, is_error=False, hint=hint))
                return rules
            case 'partially_accepted':
                rules = [FinalVerdictRule(verdict='AC')]
                if metadata.is_scoring():
                    min_score, max_score = testdata.get_score_range()
                    hint = 'consider moving it to accepted'
                    # If the best score is infinite, so is the bound (inf - 0.01 == inf), and the rule accepts any score
                    if metadata.legacy_grading.objective == 'min':
                        rules.append(ScoreRule(min_score=min_score + 0.01, max_score=max_score, is_error=False, hint=hint))
                    else:
                        rules.append(ScoreRule(min_score=min_score, max_score=max_score - 0.01, is_error=False, hint=hint))
                return rules
            case 'wrong_answer':
                return [
                    PermittedRule(verdicts=frozenset({'AC', 'WA'}), is_error=False),
                    FinalVerdictRule(verdict='WA', show_details=False),
                ]
            case 'time_limit_exceeded':
                return [
                    PermittedRule(verdicts=frozenset({'AC', 'WA', 'TLE'}), is_error=False),
                    # Details are needed when the final verdict is WA, which the permitted rule allows
                    FinalVerdictRule(verdict='TLE'),
                ]
            case 'run_time_error':
                return [FinalVerdictRule(verdict='RTE')]
            case _:
                return None

    def lower_bounds_time_limit(self, submission: Submission) -> bool:
        """Whether this submission's runtime should be used to lower-bound the time limit."""
        return submission.directory == 'accepted'


@dataclass(frozen=True)
class Submissions:
    """All example submissions for a problem."""

    submissions: list[Submission] = field(default_factory=list)
    policy: LegacyPolicy = field(default_factory=LegacyPolicy)


def load_submissions(probdir: Path, language_config: Languages, includes: Includes) -> Submissions:
    subs_root = resolve(probdir) / 'submissions'
    if not subs_root.is_dir():
        return Submissions()

    submissions = []
    for entry in sorted(subs_root.iterdir()):
        if entry.is_dir():
            for program in find_programs(str(entry), language_config=language_config, includes=includes):
                submissions.append(Submission(program=program, path=relpath(Path(entry.name) / program.name)))
    return Submissions(submissions=submissions)


def _best_score(testdata: TestDataGroup, metadata: Metadata) -> float:
    min_score, max_score = testdata.get_score_range()
    return min_score if metadata.legacy_grading.objective == 'min' else max_score
