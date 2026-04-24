from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from ..diagnostics import Diagnostics
from ..metadata import Metadata
from ..run import Program
from .result import SubmissionResult

if TYPE_CHECKING:
    from ..verifyproblem import TestCase


def _get_feedback(feedback_dir: Path) -> str | None:
    all_feedback = []
    for path in feedback_dir.iterdir():
        if path.stat().st_size == 0:
            continue
        all_feedback.append(f'=== {path.name}: ===')
        # Note: The file could contain non-unicode characters, "replace" to be on the safe side
        with open(path, errors='replace') as f:
            # Cap amount of feedback per file at some high-ish
            # size, so that a buggy validator spewing out lots of
            # data doesn't kill us.
            all_feedback.append(f.read(128 * 1024))
    return '\n'.join(all_feedback) if all_feedback else None


def _parse_validator_result(
    val: Program,
    status: int,
    feedback_dir: Path,
    metadata: Metadata,
) -> SubmissionResult:
    if not os.WIFEXITED(status):
        return SubmissionResult(
            'JE',
            reason=f'output validator {val} crashed, status {status}',
            additional_info=_get_feedback(feedback_dir),
        )

    ret = os.WEXITSTATUS(status)
    if ret not in [42, 43]:
        return SubmissionResult(
            'JE',
            reason=f'output validator {val} exited with status {ret}',
            additional_info=_get_feedback(feedback_dir),
        )

    if ret == 43:
        return SubmissionResult('WA', additional_info=_get_feedback(feedback_dir))

    # ret == 42 (AC); check score handling
    score_file = feedback_dir / 'score.txt'

    if not metadata.is_custom_score_allowed() and score_file.is_file():
        return SubmissionResult('JE', reason='validator produced "score.txt" but problem does not have custom scoring activated')

    score: float | None = None
    if metadata.is_custom_score_mandatory():
        if score_file.is_file():
            try:
                score = float(score_file.read_text())
            except Exception as e:
                return SubmissionResult('JE', reason=f'failed to parse validator score: {e}')
        elif metadata.is_multi_pass() and (feedback_dir / 'nextpass.in').is_file():
            score = 0.0
        else:
            return SubmissionResult('JE', reason='problem has custom scoring but validator did not produce "score.txt"')

    return SubmissionResult('AC', score=score)


def _validate_output(
    testcase: TestCase,
    submission_output: Path,
    output_validator: Program,
    metadata: Metadata,
    execution_dir: Path,
    diag: Diagnostics,
    infile: Path | None = None,
) -> SubmissionResult:
    feedback_dir = execution_dir / 'feedback'
    effective_infile = infile if infile is not None else testcase.infile_path
    flags = testcase.output_validator_flags
    val_timelim = metadata.limits.validation_time
    val_memlim = metadata.limits.validation_memory

    if not output_validator.compile()[0]:
        return SubmissionResult('JE', reason=f'output validator {output_validator} failed to compile')
    val_stdout = execution_dir / 'val_stdout'
    val_stderr = execution_dir / 'val_stderr'
    status, _ = output_validator.run(
        infile=str(submission_output),
        args=[str(effective_infile), str(testcase.ansfile_path), str(feedback_dir) + os.sep] + flags,
        timelim=val_timelim,
        memlim=val_memlim,
        outfile=str(val_stdout),
        errfile=str(val_stderr),
    )
    for label, path in [('stdout', val_stdout), ('stderr', val_stderr)]:
        try:
            if content := path.read_text(errors='replace'):
                diag.debug(f'Validator {label}: {content}')
        except OSError as e:
            diag.info(f'Failed to read validator output: {e}')
    return _parse_validator_result(output_validator, status, feedback_dir, metadata)


def validate_output(
    testcase: TestCase,
    submission_output: Path,
    output_validator: Program,
    metadata: Metadata,
    base_dir: Path,
    diag: Diagnostics,
) -> SubmissionResult:
    with tempfile.TemporaryDirectory(dir=base_dir) as exec_dir:
        execution_dir = Path(exec_dir)
        (execution_dir / 'feedback').mkdir()
        return _validate_output(testcase, submission_output, output_validator, metadata, execution_dir, diag)
