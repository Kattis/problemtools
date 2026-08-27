from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..languages import Languages
from ..run import Program, find_programs
from . import Verdict
from .includes import Includes


@dataclass(frozen=True)
class Submission:
    """A single example submission.

    `path` is relative to the submissions directory, e.g. for
    submissions/accepted/hello.java, path is accepted/hello.java."""

    program: Program
    path: Path

    def __post_init__(self) -> None:
        if len(self.path.parts) != 2:
            raise ValueError(f'Submission path must be on the form directory/name, got {self.path}')

    @property
    def directory(self) -> str:
        """The submission's top-level directory under submissions/."""
        return self.path.parts[0]


_VERDICT_BY_DIRECTORY: dict[str, Verdict] = {
    'accepted': 'AC',
    'partially_accepted': 'AC',
    'wrong_answer': 'WA',
    'run_time_error': 'RTE',
    'time_limit_exceeded': 'TLE',
}


@dataclass(frozen=True)
class LegacyPolicy:
    """The directory-name-based policy for what's expected of a submission, used by problem
    formats that predate submissions.yaml: everything is inferred purely from which of the
    well-known directories (if any) a submission's path starts with.

    This is a placeholder for the richer (and eventually per-testcase) policy that
    submissions.yaml will bring.
    """

    def matches(self, submission: Submission) -> bool:
        """Whether this submission is recognized by the policy at all, i.e. sits in a well-known directory."""
        return self.expected_verdict(submission) is not None

    def expected_verdict(self, submission: Submission) -> Verdict | None:
        """The expected verdict for this submission, or None if it isn't in a well-known directory."""
        return _VERDICT_BY_DIRECTORY.get(submission.directory)

    def lower_bounds_time_limit(self, submission: Submission) -> bool:
        """Whether this submission's runtime should be used to lower-bound the time limit."""
        return submission.directory == 'accepted'

    def expects_full_score(self, submission: Submission) -> bool:
        """Whether this submission is expected to achieve full score."""
        return submission.directory == 'accepted'


@dataclass(frozen=True)
class Submissions:
    """All example submissions for a problem."""

    submissions: list[Submission] = field(default_factory=list)
    policy: LegacyPolicy = field(default_factory=LegacyPolicy)


def load_submissions(probdir: Path, language_config: Languages, includes: Includes) -> Submissions:
    subs_root = probdir / 'submissions'
    if not subs_root.is_dir():
        return Submissions()

    submissions = []
    for entry in sorted(subs_root.iterdir()):
        if entry.is_dir():
            for program in find_programs(str(entry), language_config=language_config, includes=includes):
                submissions.append(Submission(program=program, path=Path(entry.name) / program.name))
    return Submissions(submissions=submissions)
