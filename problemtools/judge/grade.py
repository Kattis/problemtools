from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import cast

from ..diagnostics import Diagnostics
from ..model import Verdict
from ..run import Program
from .result import SubmissionResult

_GRADER_OUTPUT_RE = re.compile(r'^((AC)|(WA)|(TLE)|(RTE)|(MLE)|(OLE)|(JE))\s+-?[0-9.]+\s*$')


def grade_group(
    sub_results: list[SubmissionResult],
    grader: Program,
    grader_flags: list[str],
    base_dir: Path,
    diag: Diagnostics,
) -> tuple[Verdict, float | None]:
    """Run grader on sub_results and return (verdict, score).

    Returns ('AC', 0.0) immediately if sub_results is empty.
    Returns ('JE', None) on any grader error.
    """
    if not sub_results:
        return ('AC', 0.0)

    grader_executable = grader.compile(base_dir).executable
    if grader_executable is None:
        diag.error(f'Failed to compile grader {grader}')
        return ('JE', None)

    grader_input = ''.join(f'{r.verdict} {0 if r.score is None else r.score}\n' for r in sub_results)
    diag.debug(f'Grading {len(sub_results)} results:\n{grader_input}')
    diag.debug(f'Grader flags: {grader_flags}')

    with tempfile.TemporaryDirectory(dir=base_dir) as tmpdir:
        infile = Path(tmpdir) / 'grader_in'
        infile.write_text(grader_input)
        result = grader_executable.run_capture(Path(tmpdir), infile, args=grader_flags)

    if result.exitcode != 0:
        diag.error(f'Judge error: grader {grader} failed ({result}), expected exit code 0', result.stderr)
        diag.debug(f'Grader input:\n{grader_input}')
        return ('JE', None)

    if not _GRADER_OUTPUT_RE.match(result.stdout):
        diag.error('Judge error: invalid format of grader output')
        diag.debug(f'Output must match: "{_GRADER_OUTPUT_RE.pattern}"')
        diag.debug(f'Output was: "{result.stdout}"')
        return ('JE', None)

    verdict_str, score_str = result.stdout.split()
    diag.debug(f'Grader result: {verdict_str} ({score_str})')
    return cast(Verdict, verdict_str), float(score_str)
