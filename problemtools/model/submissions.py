from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..languages import Languages
from ..run import Program, find_programs, get_program
from . import Verdict
from .includes import Includes


@dataclass(frozen=True)
class Submission:
    """A single example submission.

    `path` is relative to the submissions directory, e.g. for
    submissions/accepted/hello.java, path is accepted/hello.java."""

    program: Program
    path: Path

    @property
    def directory(self) -> str:
        """The submission's top-level directory under submissions/, or '' for a loose file."""
        parts = self.path.parts
        return parts[0] if len(parts) > 1 else ''


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


def load_submissions(probdir: Path, language_config: Languages, work_dir: str, includes: Includes) -> Submissions:
    subs_root = probdir / 'submissions'
    if not subs_root.is_dir():
        return Submissions()

    submissions = []
    for entry in sorted(subs_root.iterdir()):
        if entry.is_dir():
            for program in find_programs(str(entry), language_config=language_config, work_dir=work_dir, includes=includes):
                submissions.append(Submission(program=program, path=Path(entry.name) / program.name))
        elif entry.name != 'submissions.yaml':
            # A loose file directly in submissions/, rather than in one of its subdirectories.
            loose_program = get_program(str(entry), language_config=language_config, work_dir=work_dir, includes=includes)
            if loose_program is not None:
                submissions.append(Submission(program=loose_program, path=Path(loose_program.name)))
    return Submissions(submissions=submissions)
