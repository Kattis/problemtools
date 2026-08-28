#! /usr/bin/env python3
from __future__ import annotations

import argparse
import functools
import logging
import random
import re
import shutil
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from re import Pattern
from types import TracebackType
from typing import Self

from . import checks, model, run
from .context import PROBLEM_PARTS, Context
from .diagnostics import Diagnostics, LoggingDiagnostics, VerifyError
from .formatversion import FormatVersion
from .version import add_version_arg

random.seed(42)


@dataclass(frozen=True)
class _CheckStep:
    """One named check to run as part of verifying a problem.

    `part` is one of PROBLEM_PARTS -- it groups steps for the -p/--parts CLI
    filter and for the "Checking X" progress messages. `name` scopes the
    diagnostics `run` reports to (via Diagnostics.child)."""

    part: str
    name: str
    run: Callable[[Diagnostics], None]
    start_background_work: Callable[[Context], None] | None = None


@dataclass(frozen=True)
class CheckResult:
    """Result of ProblemVerifier.check()."""

    errors: int
    warnings: int
    #: Time limit computed from accepted submissions' runtimes, if the 'submissions'
    #: part was checked and had at least one accepted submission to measure.
    timelim: float | None


class ProblemVerifier:
    """Runs checks against a loaded problem.

    Owns the temporary work directory used to compile and run programs while
    checking -- use as a context manager."""

    def __init__(self, problem: model.Problem, diag: Diagnostics) -> None:
        self.problem = problem
        self._diag = diag
        self.work_dir: Path | None = None

    def __enter__(self) -> Self:
        self.work_dir = Path(tempfile.mkdtemp(prefix=f'verify-{self.problem.shortname}-'))
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        assert self.work_dir is not None
        shutil.rmtree(self.work_dir)
        self.work_dir = None

    def check(self, context: Context) -> CheckResult:
        """Runs checks on the problem. ProblemVerifier must be entered (as a context manager) first."""
        assert self.work_dir is not None, 'ProblemVerifier.check() called before __enter__'
        problem = self.problem
        diag = self._diag
        timelim: float | None = None

        def set_timelim(value: float) -> None:
            nonlocal timelim
            timelim = value

        @functools.cache
        def get_output_validator() -> run.Program:
            validator = problem.output_validators.select(problem.format_version, problem.metadata)
            if validator is None:
                diag.fatal('Unable to locate default validator')
            return validator

        try:
            if not re.match('^[a-z0-9]+$', problem.shortname):
                diag.error(f"Invalid shortname '{problem.shortname}' (must be [a-z0-9]+)")
            if problem.format_version is FormatVersion.V_2023_07:
                diag.warning(
                    f'Support for version {problem.format_version} is very incomplete. Verification may not work as expected.'
                )

            checks.check_problem_package(problem.probdir, problem.format_version, diag)
            run.limit.check_limit_capabilities(diag)

            steps = self._build_steps(context, get_output_validator, set_timelim)
            assert {step.part for step in steps} == set(PROBLEM_PARTS), 'CheckStep parts and PROBLEM_PARTS must be kept in sync'

            active_parts = [part for part in PROBLEM_PARTS if part in context.parts]

            if context.executor:
                for step in steps:
                    if step.part in active_parts and step.start_background_work:
                        step.start_background_work(context)

            for part in active_parts:
                print(f'Checking {part}')
                for step in steps:
                    if step.part == part:
                        step.run(diag.child(step.name))
        except VerifyError:
            pass
        except KeyboardInterrupt:
            # In multithreaded runs, we can queue up large chunks of work. If the
            # user presses ctrl-c, we want to cancel that to exit quickly.
            context.cancel_background_work()
            raise
        finally:
            # Wait for background work to finish before performing an rmtree on
            # the directory tree it uses.
            context.wait_for_background_work()

        return CheckResult(errors=diag.errors, warnings=diag.warnings, timelim=timelim)

    def _build_steps(
        self,
        context: Context,
        get_output_validator: Callable[[], run.Program],
        set_timelim: Callable[[float], None],
    ) -> list[_CheckStep]:
        problem = self.problem
        assert self.work_dir is not None
        work_dir = self.work_dir

        def start_input_validators(context: Context) -> None:
            for validator in problem.input_validators.validators:
                context.submit_background_work(validator.compile, work_dir)

        def start_output_validator(context: Context) -> None:
            context.submit_background_work(get_output_validator().compile, work_dir)

        def start_submissions(context: Context) -> None:
            # Precompile the output validator here too: submissions need it, and this step
            # runs even if the 'validators' part wasn't requested. Program.compile() caches
            # its result, so this is harmless if 'validators' already queued the same compile.
            context.submit_background_work(get_output_validator().compile, work_dir)
            policy = problem.submissions.policy
            for sub in problem.submissions.submissions:
                if policy.matches(sub) and context.submission_filter.search(str(sub.path)):
                    context.submit_background_work(sub.program.compile, work_dir)

        return [
            _CheckStep(
                'config',
                'config',
                lambda diag: checks.check_config(
                    problem.metadata, problem.format_version, problem.statements, problem.testdata, diag
                ),
            ),
            _CheckStep(
                'statement',
                'statement',
                lambda diag: checks.check_statements(
                    problem.statements, problem.metadata, problem.format_version, problem.probdir, work_dir, diag
                ),
            ),
            _CheckStep('statement', 'attachments', lambda diag: checks.check_attachments(problem.attachments, diag)),
            _CheckStep(
                'validators',
                'input_validator',
                lambda diag: checks.check_input_validators(problem.input_validators, problem.testdata, work_dir, diag),
                start_input_validators,
            ),
            _CheckStep(
                'validators',
                'output_validator',
                lambda diag: checks.check_output_validators(
                    problem.output_validators,
                    problem.format_version,
                    problem.metadata,
                    problem.testdata,
                    work_dir,
                    diag,
                ),
                start_output_validator,
            ),
            _CheckStep(
                'graders',
                'grader',
                lambda diag: checks.check_graders(problem.graders, problem.metadata, work_dir, diag),
            ),
            _CheckStep(
                'data',
                'data',
                lambda diag: checks.check_testdata(
                    problem.testdata,
                    context,
                    problem.metadata,
                    problem.probdir,
                    problem.graders,
                    problem.input_validators,
                    problem.output_validators,
                    problem.format_version,
                    work_dir,
                    diag,
                ),
            ),
            _CheckStep(
                'submissions',
                'includes',
                lambda diag: checks.check_includes(problem.includes, problem.language_config, problem.format_version, diag),
            ),
            _CheckStep(
                'submissions',
                'submission',
                lambda diag: checks.check_submissions(
                    problem.submissions,
                    problem.metadata,
                    problem.testdata,
                    get_output_validator(),
                    problem.graders,
                    work_dir,
                    problem.probdir,
                    context,
                    set_timelim,
                    diag,
                ),
                start_submissions,
            ),
        ]


def re_argument(s: str) -> Pattern[str]:
    try:
        r = re.compile(s)
        return r
    except re.error:
        raise argparse.ArgumentTypeError(f'{s} is not a valid regex')


def part_argument(s: str) -> str:
    if s not in PROBLEM_PARTS:
        raise argparse.ArgumentTypeError(f'Invalid problem part specified: {s}')
    return s


def argparser_basic_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('-b', '--bail_on_error', action='store_true', help='bail verification on first error')
    parser.add_argument('-l', '--log_level', default='warning', help='set log level (debug, info, warning, error, critical)')
    parser.add_argument('-e', '--werror', action='store_true', help='consider warnings as errors')
    parser.add_argument(
        '--max_additional_info',
        type=int,
        default=15,
        help='maximum number of lines of additional info (e.g. compiler output or validator feedback) to display about an error (set to 0 to disable additional info)',
    )


def argparser() -> argparse.ArgumentParser:
    # Default values here must be kept in sync with the defaults in Context.__init__().
    parser = argparse.ArgumentParser(description='Validate a problem package in the Kattis problem format.')
    parser.add_argument(
        '-s',
        '--submission_filter',
        metavar='SUBMISSIONS',
        type=re_argument,
        default=re.compile('.*'),
        help='run only submissions whose name contains this regex.  The name includes category (accepted, wrong_answer, etc), e.g. "accepted/hello.java" (for a single file submission) or "wrong_answer/hello" (for a directory submission)',
    )
    parser.add_argument(
        '-d',
        '--data_filter',
        metavar='DATA',
        type=re_argument,
        default=re.compile('.*'),
        help='use only data files whose name contains this regex.  The name includes path relative to the data directory but not the extension, e.g. "sample/hello" for a sample data file',
    )
    parser.add_argument(
        '-t',
        '--fixed_timelim',
        type=float,
        help='use this fixed time limit (useful in combination with -d and/or -s when all AC submissions might not be run on all data)',
    )
    parser.add_argument(
        '-p',
        '--parts',
        metavar='PROBLEM_PART',
        type=part_argument,
        nargs='+',
        default=PROBLEM_PARTS,
        help=f'only test the indicated parts of the problem.  Each PROBLEM_PART can be one of {sorted(PROBLEM_PARTS)}.',
    )
    parser.add_argument(
        '-j',
        '--threads',
        type=int,
        default=1,
        help='run validation using multiple threads. This will make timings less reliable, but can be convenient during development',
    )

    add_version_arg(parser)
    argparser_basic_arguments(parser)

    parser.add_argument('problemdir', nargs='+')
    return parser


def main() -> None:
    args = argparser().parse_args()

    total_errors = 0
    try:
        context = Context(
            data_filter=args.data_filter,
            submission_filter=args.submission_filter,
            fixed_timelim=args.fixed_timelim,
            parts=args.parts,
            threads=args.threads,
        )
        for problemdir in args.problemdir:
            probdir = Path(problemdir).resolve()
            shortname = probdir.name
            print(f'Loading problem {shortname}')
            diag = LoggingDiagnostics.create(
                shortname,
                log_level=getattr(logging, args.log_level.upper()),
                bail_on_error=args.bail_on_error,
                warnings_as_errors=args.werror,
                max_additional_info=args.max_additional_info,
            )
            try:
                problem = model.load_problem(probdir, diag)
            except VerifyError:
                result = CheckResult(errors=diag.errors, warnings=diag.warnings, timelim=None)
            else:
                with ProblemVerifier(problem, diag) as verifier:
                    result = verifier.check(context)

            def p(x: int) -> str:
                return '' if x == 1 else 's'

            print(f'{shortname} tested: {result.errors} error{p(result.errors)}, {result.warnings} warning{p(result.warnings)}')
            total_errors += result.errors

    except KeyboardInterrupt:
        print('\naborting...')
    finally:
        if total_errors > 0:
            sys.exit(1)


if __name__ == '__main__':
    main()
