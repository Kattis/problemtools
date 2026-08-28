from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..languages import Languages
from ..run import Program, find_programs, get_tool

DEFAULT_GRADER = get_tool('default_grader')


@dataclass(frozen=True)
class Graders:
    """A problem's graders: custom grader programs found on disk, if any."""

    graders: list[Program] = field(default_factory=list)

    @property
    def grader(self) -> Program | None:
        """The custom grader, if there's exactly one; None if there are zero (default grading is used).

        Does not validate that there's at most one grader; callers that care about the invalid
        case of more than one custom grader must check `len(graders)` themselves and report it."""
        return self.graders[0] if len(self.graders) == 1 else None


def load_graders(probdir: Path, language_config: Languages) -> Graders:
    graders = find_programs(str(probdir / 'graders'), language_config=language_config)
    return Graders(graders=graders)
