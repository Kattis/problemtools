from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..languages import Languages
from ..run import Program, find_programs, get_program
from .includes import Includes


@dataclass(frozen=True)
class Submission:
    """A single example submission.

    `path` is relative to the submissions directory, e.g. for
    submissions/accepted/hello.java, path is accepted/hello.java."""

    program: Program
    path: Path


@dataclass(frozen=True)
class Submissions:
    """All example submissions for a problem."""

    submissions: list[Submission] = field(default_factory=list)


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
