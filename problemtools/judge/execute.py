"""Single test case execution.

For each call to execute_testcase, a temporary directory (execution_dir) is
created under base_dir and cleaned up on return.  Its layout:

    feedback/               validator's structured output (score.txt,
                            judgemessage.txt, …); persists across multipass
                            passes so the validator can accumulate output
    submission_stdout       submission's stdout (batch) or unused (interactive)
    submission_stderr       submission's stderr
    val_stdout              output validator's stdout
    val_stderr              output validator's stderr
    interactive_output      interactive proxy's output (interactive only)
    input.in                next-pass input after nextpass.in is moved here
                            (multipass only)
"""

from __future__ import annotations

import math
import os
import re
import signal
import tempfile
from pathlib import Path

from typing import TYPE_CHECKING

from ..diagnostics import Diagnostics
from ..metadata import Metadata
from ..run import Program, get_tool

if TYPE_CHECKING:
    from ..verifyproblem import TestCase
from .result import SubmissionResult, TimeLimits, classify_result
from .validate import _parse_validator_result, _validate_output

_INTERACTIVE_OUTPUT_RE = re.compile(r'\d+ \d+\.\d+ \d+ \d+\.\d+ (validator|submission)')


def _is_TLE(status: int, may_signal_with_usr1: bool = False) -> bool:
    return os.WIFSIGNALED(status) and (
        os.WTERMSIG(status) == signal.SIGXCPU or (may_signal_with_usr1 and os.WTERMSIG(status) == signal.SIGUSR1)
    )


def _is_RTE(status: int) -> bool:
    return not os.WIFEXITED(status) or bool(os.WEXITSTATUS(status))


def _read_safe(path: Path) -> str | None:
    try:
        return path.read_text(errors='replace')
    except OSError:
        return None


def _run_normal(
    infile: Path,
    testcase: TestCase,
    sub: Program,
    output_validator: Program,
    metadata: Metadata,
    timelim: float,
    execution_dir: Path,
    diag: Diagnostics,
) -> SubmissionResult:
    """Run a submission once (non-interactive)"""
    outfile = execution_dir / 'submission_stdout'
    errfile = execution_dir / 'submission_stderr'
    status, runtime = sub.run(
        infile=str(infile),
        outfile=str(outfile),
        errfile=str(errfile),
        timelim=math.ceil(timelim) + 1,
        memlim=metadata.limits.memory,
        work_dir=sub.path,
    )
    if _is_TLE(status) or runtime > timelim:
        result = SubmissionResult('TLE')
    elif _is_RTE(status):
        result = SubmissionResult('RTE', additional_info=_read_safe(errfile))
    else:
        result = _validate_output(testcase, outfile, output_validator, metadata, execution_dir, diag, infile=infile)
    result.runtime = runtime
    return result


def _run_interactive(
    infile: Path,
    testcase: TestCase,
    sub: Program,
    output_validator: Program,
    metadata: Metadata,
    timelim: float,
    execution_dir: Path,
    diag: Diagnostics,
) -> SubmissionResult:
    """Run a submission once (interactive)"""
    interactive = get_tool('interactive')
    if interactive is None:
        diag.error('Could not locate interactive runner')
        return SubmissionResult('JE', reason='Could not locate interactive runner')

    if not output_validator.compile()[0]:
        return SubmissionResult('JE', reason=f'output validator {output_validator} failed to compile')

    feedback_dir = execution_dir / 'feedback'
    interactive_out = execution_dir / 'interactive_output'

    i_status, _ = interactive.run(
        outfile=str(interactive_out),
        args=(
            ['1', str(math.ceil(2 * timelim))]
            + output_validator.get_runcmd(memlim=metadata.limits.validation_memory)
            + [str(infile), str(testcase.ansfile_path), str(feedback_dir) + os.sep]
            + [';']
            + sub.get_runcmd(memlim=metadata.limits.memory)
        ),
        work_dir=sub.path,
    )

    if _is_RTE(i_status):
        diag.error(f'Interactive runner crashed, status {i_status}')
        return SubmissionResult('JE', reason=f'Interactive runner crashed, status {i_status}')

    output = interactive_out.read_text()
    diag.debug(f'Interactive output: "{output}"')

    if not _INTERACTIVE_OUTPUT_RE.match(output):
        diag.error(f'Interactive runner produced unexpected output: "{output}"')
        return SubmissionResult('JE', reason=f'Interactive runner produced unexpected output: "{output}"')

    val_status_str, _, sub_status_str, sub_runtime_str, first = output.split()
    val_status = int(val_status_str)
    sub_status = int(sub_status_str)
    sub_runtime = float(sub_runtime_str)

    val_JE = not os.WIFEXITED(val_status) or os.WEXITSTATUS(val_status) not in [42, 43]
    val_WA = os.WIFEXITED(val_status) and os.WEXITSTATUS(val_status) == 43

    if val_JE or (val_WA and first == 'validator'):
        # Validator crashed or exited first with WA — follow validator verdict.
        # Cap runtime, as the submission can behave erratically and time out
        # after the validator exited.
        result = _parse_validator_result(output_validator, val_status, feedback_dir, metadata)
        sub_runtime = min(sub_runtime, timelim)
    elif _is_TLE(sub_status, may_signal_with_usr1=True) or sub_runtime > timelim:
        result = SubmissionResult('TLE')
    elif _is_RTE(sub_status):
        result = SubmissionResult('RTE')
    else:
        result = _parse_validator_result(output_validator, val_status, feedback_dir, metadata)

    result.runtime = sub_runtime
    result.validator_first = first == 'validator'
    return result


def _run_pass(
    infile: Path,
    testcase: TestCase,
    sub: Program,
    output_validator: Program,
    metadata: Metadata,
    timelim: float,
    execution_dir: Path,
    diag: Diagnostics,
) -> SubmissionResult:
    """Run a submission once (the common case, or one pass for a multi-pass problem)"""
    if metadata.is_interactive():
        return _run_interactive(infile, testcase, sub, output_validator, metadata, timelim, execution_dir, diag)
    return _run_normal(infile, testcase, sub, output_validator, metadata, timelim, execution_dir, diag)


def _run_multipass(
    testcase: TestCase,
    sub: Program,
    output_validator: Program,
    metadata: Metadata,
    timelim: float,
    execution_dir: Path,
    diag: Diagnostics,
) -> SubmissionResult:
    infile = testcase.infile_path
    slowest = 0.0
    feedback_dir = execution_dir / 'feedback'
    for _ in range(metadata.limits.validation_passes):
        result = _run_pass(infile, testcase, sub, output_validator, metadata, timelim, execution_dir, diag)
        slowest = max(slowest, result.runtime)
        result.runtime = slowest
        nextpass = feedback_dir / 'nextpass.in'
        if result.verdict != 'AC':
            if nextpass.is_file():
                return SubmissionResult('JE', reason='Output validator produced nextpass.in despite non-42 exit code')
            return result
        if not nextpass.is_file():
            return result
        infile = execution_dir / 'input.in'
        nextpass.rename(infile)
    return SubmissionResult('JE', reason=f'Validator did not give verdict within {metadata.limits.validation_passes} passes')


def execute_testcase(
    testcase: TestCase,
    sub: Program,
    output_validator: Program,
    metadata: Metadata,
    timelimits: TimeLimits,
    base_dir: Path,
    diag: Diagnostics,
) -> tuple[SubmissionResult, SubmissionResult, SubmissionResult]:
    """Run sub on testcase and return (nominal, low, high) SubmissionResults."""
    with tempfile.TemporaryDirectory(dir=base_dir) as exec_dir:
        execution_dir = Path(exec_dir)
        (execution_dir / 'feedback').mkdir()
        if metadata.is_multi_pass():
            raw = _run_multipass(testcase, sub, output_validator, metadata, timelimits.high, execution_dir, diag)
        else:
            raw = _run_pass(testcase.infile_path, testcase, sub, output_validator, metadata, timelimits.high, execution_dir, diag)
    return classify_result(raw, timelimits)
