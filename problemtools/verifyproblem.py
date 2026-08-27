#! /usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
import glob
import logging
import os
import random
import re
import shutil
import sys
import tempfile
import traceback
import uuid
from abc import ABC
from pathlib import Path
from re import Pattern
from types import TracebackType
from typing import ClassVar, NoReturn, Self

from pydantic import ValidationError

from . import checks, languages, metadata, model, problem2html, problem2pdf, run, statement_util
from .context import PROBLEM_PARTS, Context
from .diagnostics import Diagnostics, LoggingDiagnostics, VerifyError
from .formatversion import FormatVersion, get_format_version
from .judge import SubmissionResult, validate_output
from .version import add_version_arg

random.seed(42)


class ProblemAspect(ABC):
    _check_res: bool | None = None
    problem: Problem
    _diag: Diagnostics

    def __init__(self, name: str, problem: Problem) -> None:
        if self is not problem:
            self._diag = problem._diag.child(name)
        self.problem = problem

    @property
    def errors(self) -> int:
        return self._diag.errors

    @property
    def warnings(self) -> int:
        return self._diag.warnings

    def fatal(self, msg: str, additional_info: str | None = None) -> NoReturn:
        self._check_res = False
        self._diag.fatal(msg, additional_info)

    def error(self, msg: str, additional_info: str | None = None) -> None:
        self._check_res = False
        self._diag.error(msg, additional_info)

    def warning(self, msg: str, additional_info: str | None = None) -> None:
        self._diag.warning(msg, additional_info)

    def error_in_2023_07(self, msg: str, additional_info: str | None = None) -> None:
        if self.problem.format is FormatVersion.LEGACY:
            self.warning(msg, additional_info)
        else:
            self.error(msg, additional_info)

    def info(self, msg: str) -> None:
        self._diag.info(msg)

    def debug(self, msg: str) -> None:
        self._diag.debug(msg)

    def msg(self, msg: str) -> None:
        print(msg)

    def warn_directory(self, name: str, prop: str) -> None:
        """Warns if a directory meant for a different problem format version exists"""
        good_dir = getattr(self.problem.format, prop)
        bad_dirs = {getattr(version, prop) for version in FormatVersion} - {good_dir}
        problem_root = Path(self.problem.probdir)
        for directory in bad_dirs:
            if (problem_root / directory).exists():
                self.warning(f'Found directory "{directory}". Version {self.problem.format} looks for {name} in "{good_dir}"')


class ProblemPart(ProblemAspect):
    """Baseclass for all parts that can be included in a problem-format."""

    """Should always be overridden by the subclass. Specifies the name that will be used to refer
    to the part e.g for logs.
    """
    PART_NAME: ClassVar[str]

    def __init__(self, problem: Problem) -> None:
        if self.PART_NAME is None:
            raise NotImplementedError('Every problem-part must override PART_NAME')
        super().__init__(self.PART_NAME, problem)
        self.setup()

    def setup(self) -> None:
        pass

    def start_background_work(self, context: Context) -> None:
        pass

    def check(self, context: Context) -> bool:
        return True


class ProblemStatement(ProblemPart):
    statements: dict[str, list[Path]]  # Maps language code -> statement(s)
    PART_NAME = 'statement'

    def setup(self) -> None:
        self.debug('  Loading problem statement')
        self.statements = statement_util.find_statements(Path(self.problem.probdir), self.problem.format)

    def check(self, context: Context) -> bool:
        if self._check_res is not None:
            return self._check_res
        self._check_res = True

        self.warn_directory('problem statements', 'statement_directory')

        for ifilename in glob.glob(os.path.join(self.problem.probdir, 'data/sample/*.interaction')):
            if not self.problem.is_interactive() and not self.problem.is_multi_pass():
                self.error(f'Problem is not interactive, but there is an interaction sample {ifilename}')
            with open(ifilename, 'r') as interaction:
                for i, line in enumerate(interaction):
                    valid_new_pass = self.problem.is_multi_pass() and line.strip() == '---'
                    if len(line) == 0 or (line[0] != '<' and line[0] != '>' and not valid_new_pass):
                        self.error(
                            f'Interaction {ifilename}: line {i + 1} does not start with < or > {"or ---" if self.problem.is_multi_pass() else ""}'
                        )
                        break

        if not self.statements:
            if self.problem.format is FormatVersion.LEGACY:
                allowed_statements = ', '.join(
                    f'problem.{ext}, problem.<language>.{ext}' for ext in self.problem.format.statement_extensions
                )
            else:
                allowed_statements = ', '.join(f'problem.<language>.{ext}' for ext in self.problem.format.statement_extensions)

            self.error(
                f'No problem statements found (expected file of one of following forms in directory {self.problem.format.statement_directory}/: {allowed_statements})'
            )

        def _latex_heuristic(name: str) -> bool:
            return '\\' in name or '$' in name

        for lang, files in self.statements.items():
            if len(files) > 1:
                self.error(f'Found multiple statements in the same language {lang}: {", ".join(file.name for file in files)}')

            if lang not in self.problem.metadata.name:
                self.error(f'No problem name given in language {lang}')
            elif not self.problem.metadata.name[lang]:
                self.error(f'Problem name in language {lang} is empty')
            elif not self.problem.metadata.name[lang].strip():
                self.error(f'Problem name in language {lang} contains only whitespace')
            elif self.problem.format is FormatVersion.LEGACY and _latex_heuristic(self.problem.metadata.name[lang]):
                self.warning(f'Problem name in language {lang} looks like LaTeX. Consider using plainproblemname.')

            for file in files:
                try:
                    options = problem2pdf.get_parser().parse_args([''])
                    options.problem = self.problem.probdir
                    options.language = lang
                    options.nopdf = True
                    options.quiet = True
                    if not problem2pdf.convert(options, file):
                        self.error(
                            f'Could not compile problem statement for language "{lang}".  Run problem2pdf --language {lang} on the problem to diagnose.'
                        )
                except Exception as e:
                    self.error(
                        f'Error raised when checking problem statement for language {lang}:\n{e}\n{traceback.format_exc()}'
                    )

                try:
                    options = problem2html.get_parser().parse_args([''])
                    options.problem = self.problem.probdir
                    options.destdir = os.path.join(self.problem.tmpdir, 'html')
                    options.language = lang
                    options.quiet = True
                    problem2html.convert(options, file)
                except Exception as e:
                    self.error(
                        f'Could not convert problem statement to html for language "{lang}".  Run problem2html --language {lang} on the problem to diagnose.\n{e}\n{traceback.format_exc()}'
                    )

        return self._check_res

    def __str__(self) -> str:
        return 'problem statement'


class ProblemConfig(ProblemPart):
    PART_NAME = 'config'

    def setup(self) -> None:
        self.debug('  Loading problem config')
        try:
            self._metadata, self._origdata = metadata.load_metadata(Path(self.problem.probdir))
            self.problem._set_metadata(self._metadata)
        except ValidationError as e:
            error_str = '\n'.join([f'    {"->".join(str(loc) for loc in err["loc"])}: {err["msg"]}' for err in e.errors()])
            self.fatal(f'Failed parsing problem.yaml. Found {len(e.errors())} errors:\n{error_str}')
        except Exception as e:
            self.fatal(f'Failed loading problem configuration: {e}')

    def __str__(self) -> str:
        return 'problem configuration'

    def check(self, context: Context) -> bool:
        if self._check_res is not None:
            return self._check_res
        self._check_res = True

        INCOMPATIBLE_TYPES = [
            (metadata.ProblemType.PASS_FAIL, metadata.ProblemType.SCORING),
            (metadata.ProblemType.SUBMIT_ANSWER, metadata.ProblemType.MULTI_PASS),
            (metadata.ProblemType.SUBMIT_ANSWER, metadata.ProblemType.INTERACTIVE),
        ]
        for t1, t2 in INCOMPATIBLE_TYPES:
            if t1 in self._metadata.type and t2 in self._metadata.type:
                self.error(f'Problem has incompatible types: {t1}, {t2}')

        if self.problem.is_submit_answer():
            self.warning('The type submit-answer is not yet supported.')

        # Check rights_owner
        if self._metadata.license == metadata.License.PUBLIC_DOMAIN:
            if self._metadata.rights_owner:
                self.error('Can not have a rights_owner for a problem in public domain')
        elif self._metadata.license != metadata.License.UNKNOWN:
            if not self._metadata.rights_owner and not self._metadata.source and not self._metadata.credits.authors:
                self.error('No author, source or rights_owner provided')

        # Sanity check that the author name is parsed reasonably
        disallowed_in_name = [',', '&']
        for author in self._metadata.credits.authors:
            for disallowed_character in disallowed_in_name:
                if disallowed_character in author.name:
                    self.warning(f'Author name parsed to "{author.name}", which contains character "{disallowed_character}".')

        # Check license
        if self._metadata.license == metadata.License.UNKNOWN:
            self.warning("License is 'unknown'")

        if self._metadata.uuid is None:
            self.error_in_2023_07(f'Missing uuid from problem.yaml. Add "uuid: {uuid.uuid4()}" to problem.yaml.')

        names_with_no_statement = [lang for lang in self._metadata.name if lang not in self.problem.statement.statements]
        if names_with_no_statement:
            self.error(f'Names exist for languages without problem statements: {", ".join(names_with_no_statement)}')

        if self._metadata.legacy_grading.show_test_data_groups and self.problem.is_pass_fail():
            self.error('Showing test data groups is only supported for scoring problems, this is a pass-fail problem')
        if (
            not self.problem.is_pass_fail()
            and self.problem.testdata.testdata.has_custom_groups()
            and 'show_test_data_groups' not in self._origdata.get('grading', {})
            and self.problem.format is FormatVersion.LEGACY
        ):
            self.warning(
                'Problem has custom testcase groups, but does not specify a value for grading.show_test_data_groups; defaulting to false'
            )

        if self._metadata.legacy_grading.on_reject is not None:
            if self.problem.is_pass_fail() and self._metadata.legacy_grading.on_reject == 'grade':
                self.error("Invalid on_reject policy 'grade' for problem type 'pass-fail'")

        for deprecated_grading_key in ['accept_score', 'reject_score', 'range', 'on_reject']:
            if getattr(self._metadata.legacy_grading, deprecated_grading_key) is not None:
                self.warning(
                    f"Grading key '{deprecated_grading_key}' is deprecated in problem.yaml, use '{deprecated_grading_key}' in testdata.yaml instead"
                )

        if self._metadata.legacy_validation:
            val = self._metadata.legacy_validation.split()
            validation_type = val[0]
            validation_params = val[1:]
            if validation_type not in ['default', 'custom']:
                self.error(f"Invalid value '{validation_type}' for validation, first word must be 'default' or 'custom'")

            if validation_type == 'default' and len(validation_params) > 0:
                self.error(f"Invalid value '{self._metadata.legacy_validation}' for validation")

            if validation_type == 'custom':
                for param in validation_params:
                    if param not in ['score', 'interactive']:
                        self.error(f"Invalid parameter '{param}' for custom validation")

        if self._metadata.limits.time_limit is not None and not self._metadata.limits.time_limit.is_integer():
            self.warning(
                'Time limit configured to non-integer value. This can be fragile, and may not be supported by your CCS (Kattis does not).'
            )
        if not self._metadata.limits.time_resolution.is_integer():
            self.warning(
                'Time resolution is not an integer. This can be fragile, and may not be supported by your CCS (Kattis does not).'
            )

        return self._check_res


class Attachments(ProblemPart):
    """Represents the attachments of a problem.

    Attributes:
        attachments: The absolute paths to the attachment files for this problem.
    """

    attachments: list[Path]

    PART_NAME = 'attachments'

    def setup(self) -> None:
        attachments_dir = Path(self.problem.probdir) / 'attachments'
        self.attachments = [p for p in attachments_dir.iterdir()] if attachments_dir.is_dir() else []
        self.debug(f'Adding attachments {self.attachments!s}')

    def check(self, context: Context) -> bool:
        if self._check_res is not None:
            return self._check_res
        self._check_res = True

        for attachment_path in self.attachments:
            if os.path.isdir(attachment_path):
                self.error(f'Directories are not allowed as attachments ({attachment_path} is a directory)')

        return self._check_res

    def get_attachment_paths(self) -> list[Path]:
        return self.attachments

    def __str__(self) -> str:
        return 'attachments'


class InputValidators(ProblemPart):
    """Seam to integrate a model + checks setup into verifyproblem in a somewhat clean way"""

    PART_NAME = 'input_validator'

    def setup(self) -> None:
        self.input_validators = model.load_input_validators(
            Path(self.problem.probdir), self.problem.language_config, self.problem.tmpdir
        )

    def __str__(self) -> str:
        return 'input format validators'

    def start_background_work(self, context: Context) -> None:
        for val in self.input_validators.validators:
            context.submit_background_work(lambda v: v.compile(), val)

    def check(self, context: Context) -> bool:
        if self._check_res is not None:
            return self._check_res
        self._check_res = True

        errors_before = self.errors
        checks.check_input_validators(self.input_validators, self.problem.testdata.testdata, self.problem.tmpdir, self._diag)
        if self.errors > errors_before:
            self._check_res = False

        return self._check_res


class Graders(ProblemPart):
    _default_grader = run.get_tool('default_grader')

    PART_NAME = 'grader'

    def setup(self) -> None:
        graders: list = run.find_programs(
            os.path.join(self.problem.probdir, 'graders'),
            language_config=self.problem.language_config,
            work_dir=self.problem.tmpdir,
        )
        if len(graders) > 1:
            self.fatal('There is more than one custom grader')
        self._grader = graders[0] if graders else None

    def __str__(self) -> str:
        return 'graders'

    def check(self, context: Context) -> bool:
        if self._check_res is not None:
            return self._check_res
        self._check_res = True

        if self._grader:
            if self.problem.is_pass_fail() and self._grader:
                self.fatal('There is a grader but the problem is pass-fail')

            success, msg = self._grader.compile()
            if not success:
                self.fatal(f'Compile error for {self._grader}', msg)
        return self._check_res


class OutputValidators(ProblemPart):
    """Seam to integrate a model + checks setup into verifyproblem in a somewhat clean way"""

    PART_NAME = 'output_validator'

    def setup(self) -> None:
        self.output_validators = model.load_output_validators(
            Path(self.problem.probdir), self.problem.format, self.problem.language_config, self.problem.tmpdir
        )
        self._has_precompiled = False

    @property
    def output_validator(self) -> run.Program:
        validator = self.output_validators.select(self.problem.format, self.problem.metadata)
        if validator is None:
            self.fatal('Unable to locate default validator')
        return validator

    def __str__(self) -> str:
        return 'output validators'

    def start_background_work(self, context: Context) -> None:
        if not self._has_precompiled:
            context.submit_background_work(lambda v: v.compile(), self.output_validator)
            self._has_precompiled = True

    def check(self, context: Context) -> bool:
        if self._check_res is not None:
            return self._check_res
        self._check_res = True

        errors_before = self.errors
        checks.check_output_validators(
            self.output_validators,
            self.problem.format,
            self.problem.metadata,
            self.problem.testdata.testdata,
            Path(self.problem.probdir),
            self.problem.tmpdir,
            self._diag,
        )
        if self.errors > errors_before:
            self._check_res = False

        return self._check_res


class Includes(ProblemPart):
    """Seam to integrate a model + checks setup into verifyproblem in a somewhat clean way"""

    PART_NAME = 'includes'

    def setup(self) -> None:
        self.includes = model.load_includes(Path(self.problem.probdir), self.problem.language_config)

    def check(self, context: Context) -> bool:
        if self._check_res is not None:
            return self._check_res
        self._check_res = True

        errors_before = self.errors
        checks.check_includes(self.includes, self.problem.language_config, self.problem.format, self._diag)
        if self.errors > errors_before:
            self._check_res = False

        return self._check_res

    def __str__(self) -> str:
        return 'includes'


class Submissions(ProblemPart):
    """Seam to integrate a model + checks setup into verifyproblem in a somewhat clean way"""

    PART_NAME = 'submission'

    def setup(self) -> None:
        self.submissions = model.load_submissions(
            Path(self.problem.probdir), self.problem.language_config, self.problem.tmpdir, self.problem.includes.includes
        )

    def __str__(self) -> str:
        return 'submissions'

    def start_background_work(self, context: Context) -> None:
        # Send off an early background compile job for each submission and
        # validator, to avoid a bottleneck step at the start of each test run.
        self.problem.output_validators.start_background_work(context)
        policy = self.submissions.policy
        for sub in self.submissions.submissions:
            if policy.matches(sub) and context.submission_filter.search(str(sub.path)):
                context.submit_background_work(lambda s: s.compile(), sub.program)

    def check(self, context: Context) -> bool:
        if self._check_res is not None:
            return self._check_res
        self._check_res = True

        errors_before = self.errors
        checks.check_submissions(
            self.submissions,
            self.problem.metadata,
            self.problem.testdata.testdata,
            self.problem.output_validators.output_validator,
            self.problem.graders._grader,
            self.problem.tmpdir,
            Path(self.problem.probdir),
            context,
            self.problem._set_timelim,
            self._diag,
        )
        if self.errors > errors_before:
            self._check_res = False

        return self._check_res


class TestData(ProblemPart):
    """Seam to integrate a model + checks setup into verifyproblem in a somewhat clean way"""

    PART_NAME = 'data'

    def setup(self) -> None:
        self.testdata = model.load_testdata(Path(self.problem.probdir), self.problem.metadata)

    def __str__(self) -> str:
        return 'test data'

    def check(self, context: Context) -> bool:
        if self._check_res is not None:
            return self._check_res
        self._check_res = True

        errors_before = self.errors

        def validate_input(testcase: model.TestCase, diag: Diagnostics) -> None:
            checks.check_testcase_input(self.problem.input_validators.input_validators, testcase, self.problem.tmpdir, diag)

        def validate_answer(testcase: model.TestCase, diag: Diagnostics) -> SubmissionResult:
            return validate_output(
                testcase=testcase,
                submission_output=testcase.ansfile,
                output_validator=self.problem.output_validators.output_validator,
                metadata=self.problem.metadata,
                base_dir=Path(self.problem.tmpdir),
                diag=diag,
            )

        checks.check_testdata(
            self.testdata,
            context,
            self.problem.metadata,
            Path(self.problem.probdir),
            self.problem.graders._grader is not None,
            Graders._default_grader is not None,
            validate_input,
            validate_answer,
            self._diag,
        )
        if self.errors > errors_before:
            self._check_res = False

        return self._check_res


class Problem(ProblemAspect):
    """Represents a checkable problem"""

    def __init__(self, probdir: str, diagnostics: Diagnostics):
        self.probdir = os.path.realpath(probdir)
        self.shortname: str = os.path.basename(self.probdir)
        self._diag = diagnostics
        super().__init__(self.shortname, self)
        self.language_config = languages.load_language_config(Path(self.probdir).parent)
        self.loaded = False
        self._metadata: metadata.Metadata | None = None
        self._timelim: float | None = None

    # Unfortunately must be before metadata, otherwise mypy gets confused about the type metadata.Metadata (feels like a bug)
    def _set_metadata(self, metadata: metadata.Metadata) -> None:  # Should only be called by ProblemConfig
        assert self._metadata is None, 'Attempted to set metadata twice'
        self._metadata = metadata

    @property
    def metadata(self) -> metadata.Metadata:
        assert self._metadata is not None, 'Attempted to access config before it was set. load() or check() first.'
        return self._metadata

    @property
    def timelim(self) -> float:
        assert self._timelim is not None, 'Attempted to access timelim before it was set. check() first.'
        return self._timelim

    def _set_timelim(self, timelim: float) -> None:  # Should only be called by Submissions
        assert self._timelim is None, 'Attempted to set timelim twice'
        self._timelim = timelim

    def is_pass_fail(self) -> bool:
        return self.metadata.is_pass_fail()

    def is_scoring(self) -> bool:
        return self.metadata.is_scoring()

    def is_interactive(self) -> bool:
        return self.metadata.is_interactive()

    def is_multi_pass(self) -> bool:
        return self.metadata.is_multi_pass()

    def is_submit_answer(self) -> bool:
        return self.metadata.is_submit_answer()

    def load(self) -> None:
        """Parses the problem package statically, loading up information with very little verification.

        Call this if you want to get a usable Problem object without expensive
        steps (such as compiling validators, and testing submissions).

        N.B., This api is EXPERIMENTAL. We eventually want to create a stable
        API from problemtools, this is a first move in that direction.

        Raises:
            VerifyError: if problem package is too broken to parse safely
        """

        if self.loaded:
            return

        if not os.path.isdir(self.probdir):
            self.fatal(f"Problem directory '{self.probdir}' not found")

        try:
            self.format = get_format_version(Path(self.probdir))
        except Exception as e:
            self.fatal(f'Failed loading problem version: {e}')
        self.config = ProblemConfig(self)  # Populates self.metadata as a side effect. Needs to run first.
        self.statement = ProblemStatement(self)
        self.attachments = Attachments(self)
        self.input_validators = InputValidators(self)
        self.output_validators = OutputValidators(self)
        self.graders = Graders(self)
        self.testdata = TestData(self)
        self.includes = Includes(self)
        # Submissions.setup() reads self.includes.includes, so includes must be loaded first.
        self.submissions = Submissions(self)
        self.loaded = True

    def __enter__(self) -> Self:
        self.tmpdir = tempfile.mkdtemp(prefix=f'verify-{self.shortname}-')
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        shutil.rmtree(self.tmpdir)

    def __str__(self) -> str:
        return str(self.shortname)

    def check(self, context: Context) -> tuple[int, int]:
        """Loads and checks the problem package

        Loads the problem package and runs checks. After this has completed,
        the Problem object is fully populated. You do not need to manually
        run load() first.

        Returns:
            Tuple with the number of errors, warnings found.

        Raises:
            VerifyError: if problem package is too broken to parse safely
        """
        try:
            self.load()
        except VerifyError:
            return self.errors, self.warnings

        try:
            part_mapping: dict[str, list] = {
                'config': [self.config],
                'statement': [self.statement, self.attachments],
                'validators': [self.input_validators, self.output_validators],
                'graders': [self.graders],
                'data': [self.testdata],
                'submissions': [self.includes, self.submissions],
            }
            assert sorted(part_mapping.keys()) == sorted(PROBLEM_PARTS), 'part_mapping and PROBLEM_PARTS must be kept in sync'

            if not re.match('^[a-z0-9]+$', self.shortname):
                self.error(f"Invalid shortname '{self.shortname}' (must be [a-z0-9]+)")
            if self.format is FormatVersion.V_2023_07:
                self.warning(f'Support for version {self.format} is very incomplete. Verification may not work as expected.')

            self._check_symlinks()
            self._check_file_and_directory_names()
            self._check_submission_directory_names()

            run.limit.check_limit_capabilities(self._diag)

            parts = [
                part for part in part_mapping if part in context.parts
            ]  # Parts from context in the order they appear in part_mapping
            if context.executor:
                for part in parts:
                    for item in part_mapping[part]:
                        item.start_background_work(context)

            for part in parts:
                self.msg(f'Checking {part}')
                for item in part_mapping[part]:
                    item.check(context)
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
        return self.errors, self.warnings

    def _check_submission_directory_names(self) -> None:
        """Heuristically check if submissions contain any directories that will be ignored because of typos or format mismatches"""
        submission_directories = [p.name for p in (Path(self.probdir) / 'submissions').glob('*') if p.is_dir()]
        if len(submission_directories) == 0:
            return

        def most_similar(present_dir: str, format_version: FormatVersion) -> tuple[str, float]:
            similarities = [
                (spec_dir, difflib.SequenceMatcher(None, present_dir, spec_dir).ratio())
                for spec_dir in format_version.submission_directories
            ]
            return max(similarities, key=lambda x: x[1])

        for present_dir in submission_directories:
            most_similar_dir, max_similarity = most_similar(present_dir, self.format)

            if max_similarity == 1:
                # Exact match, no typo
                continue

            if 0.75 <= max_similarity:
                self.warning(f'Potential typo: directory submissions/{present_dir} is similar to {most_similar_dir}')
            else:
                for other_version in [v for v in FormatVersion if v != self.format]:
                    _, max_similarity = most_similar(present_dir, other_version)
                    if max_similarity == 1:
                        self.warning(
                            f'Directory submissions/{present_dir} is not part of format version {self.format}, but part of {other_version}'
                        )
                        break

    def _check_symlinks(self) -> None:
        """Check that all symlinks point to something existing within the problem package"""
        probdir = os.path.realpath(self.probdir)
        for root, dirs, files in os.walk(probdir):
            for file in dirs + files:
                filename = os.path.join(root, file)
                if os.path.islink(filename):
                    target = os.path.realpath(filename)
                    # relfile is the filename of the symlink, relative to the problem root (only used for nicer error messages)
                    relfile = os.path.relpath(filename, self.probdir)
                    # reltarget is what the symlink points to (absolute, or relative to where the symlink is)
                    reltarget = os.readlink(filename)
                    if not os.path.exists(target):
                        self.error(f'Symlink {relfile} links to {reltarget} which does not exist')
                    if os.path.commonpath([probdir, target]) != probdir:
                        self.error(f'Symlink {relfile} links to {reltarget} which is outside of problem package')
                    if os.path.isabs(reltarget):
                        self.error(
                            f'Symlink {relfile} links to {reltarget} which is an absolute path. Symlinks must be relative.'
                        )

    def _check_file_and_directory_names(self) -> None:
        regex = re.compile(r'^[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,254}$')

        def _special_case_allowed_files(file: str, reldir: str) -> bool:
            return file == '.gitignore' or (file == '.timelimit' and reldir == os.path.basename(self.probdir))

        def _special_case_allowed_dirs(directory: str, reldir: str) -> bool:
            return directory == '.git' and reldir == os.path.basename(self.probdir)

        for root, dirs, files in os.walk(self.probdir):
            # Path of the directory we're in, starting with problem shortname. Only used for nicer error messages.
            reldir = os.path.relpath(root, os.path.dirname(self.probdir))
            for file in files:
                if not regex.match(file) and not _special_case_allowed_files(file, reldir):
                    self.error(f"Invalid file name '{file}' in {reldir}, should match {regex.pattern}")
            for directory in dirs:
                if not regex.match(directory) and not _special_case_allowed_dirs(directory, reldir):
                    self.error(f"Invalid directory name '{directory}' in {reldir}, should match {regex.pattern}")


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
        help=f'only test the indicated parts of the problem.  Each PROBLEM_PART can be one of {PROBLEM_PARTS}.',
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
            shortname = os.path.basename(os.path.realpath(problemdir))
            print(f'Loading problem {shortname}')
            diag = LoggingDiagnostics.create(
                shortname,
                log_level=getattr(logging, args.log_level.upper()),
                bail_on_error=args.bail_on_error,
                warnings_as_errors=args.werror,
                max_additional_info=args.max_additional_info,
            )
            with Problem(problemdir, diag) as prob:
                errors, warnings = prob.check(context)

                def p(x: int) -> str:
                    return '' if x == 1 else 's'

                print(f'{prob.shortname} tested: {errors} error{p(errors)}, {warnings} warning{p(warnings)}')
                total_errors += errors

    except KeyboardInterrupt:
        print('\naborting...')
    finally:
        if total_errors > 0:
            sys.exit(1)


if __name__ == '__main__':
    main()
