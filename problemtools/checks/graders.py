"""Checks for a problem package's custom graders."""

from __future__ import annotations

from ..diagnostics import Diagnostics
from ..metadata import Metadata
from ..model import Graders


def check_graders(graders: Graders, metadata: Metadata, diag: Diagnostics) -> None:
    """Run all checks on a problem's custom graders."""
    if len(graders.graders) > 1:
        diag.fatal('There is more than one custom grader')

    grader = graders.grader
    if grader is None:
        return

    if metadata.is_pass_fail():
        diag.fatal('There is a grader but the problem is pass-fail')

    success, msg = grader.compile()
    if not success:
        diag.fatal(f'Compile error for {grader}', msg)
