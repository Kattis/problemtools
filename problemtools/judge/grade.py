from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import cast

from ..diagnostics import Diagnostics
from ..run import Program
from .result import SubmissionResult, Verdict

_GRADER_OUTPUT_RE = re.compile(r'^((AC)|(WA)|(TLE)|(RTE)|(JE))\s+-?[0-9.]+\s*$')


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

    if not grader.compile()[0]:
        diag.error(f'Failed to compile grader {grader}')
        return ('JE', None)

    grader_input = ''.join(f'{r.verdict} {0 if r.score is None else r.score}\n' for r in sub_results)
    diag.debug(f'Grading {len(sub_results)} results:\n{grader_input}')
    diag.debug(f'Grader flags: {grader_flags}')

    with tempfile.TemporaryDirectory(dir=base_dir) as tmpdir:
        infile = Path(tmpdir) / 'grader_in'
        outfile = Path(tmpdir) / 'grader_out'
        errfile = Path(tmpdir) / 'grader_err'
        infile.write_text(grader_input)

        status, _runtime = grader.run(str(infile), str(outfile), str(errfile), args=grader_flags)

        grader_output = outfile.read_text(errors='replace') if outfile.exists() else ''
        stderr_content = errfile.read_text(errors='replace') if errfile.exists() else ''

    if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
        if not os.WIFEXITED(status):
            diag.error(f'Judge error: {grader} crashed')
        else:
            diag.error(f'Judge error: exit code {os.WEXITSTATUS(status)} for grader {grader}, expected 0')
        if stderr_content:
            diag.error(f'Grader stderr:\n{stderr_content}')
        diag.debug(f'Grader input:\n{grader_input}')
        return ('JE', None)

    if not _GRADER_OUTPUT_RE.match(grader_output):
        diag.error('Judge error: invalid format of grader output')
        diag.debug(f'Output must match: "{_GRADER_OUTPUT_RE.pattern}"')
        diag.debug(f'Output was: "{grader_output}"')
        return ('JE', None)

    verdict_str, score_str = grader_output.split()
    diag.debug(f'Grader result: {verdict_str} ({score_str})')
    return cast(Verdict, verdict_str), float(score_str)
