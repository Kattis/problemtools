#! /usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import math
import glob
import string
import hashlib
import collections
import os
import re
import shutil
import logging
import tempfile
import sys
import random
import traceback
import uuid
import difflib
from pathlib import Path

import yaml

from . import config
from . import languages
from . import metadata
from . import problem2html
from . import problem2pdf
from . import run
from . import statement_util
from .context import Context, PROBLEM_PARTS
from .diagnostics import Diagnostics, LoggingDiagnostics, VerifyError
from .formatversion import FormatVersion, get_format_version
from .judge import CacheKey, SubmissionJudge, SubmissionResult, Verdict, validate_output
from .version import add_version_arg

from abc import ABC
from functools import cached_property
from typing import Any, Callable, ClassVar, Literal, Pattern, Match, ParamSpec, TypeVar
from pydantic import ValidationError

random.seed(42)


_T = TypeVar('_T')
_P = ParamSpec('_P')


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

    def fatal(self, msg: str, additional_info: str | None = None) -> None:
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

    def msg(self, msg):
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


class TestCase(ProblemAspect):
    is_group: Literal[False] = False  # Temporary workaround for a circular import in judge/submission_judge.py

    def __init__(self, problem: Problem, base: str, testcasegroup: TestCaseGroup) -> None:
        super().__init__(f'test.{testcasegroup.name}.{os.path.basename(base)}', problem)
        self._base = base
        self.infile = f'{base}.in'
        self.ansfile = f'{base}.ans'
        self._problem = problem
        self.testcasegroup = testcasegroup
        self.counter = len(problem.testcase_by_infile)
        problem.testcase_by_infile[self.infile] = self

    def check_newlines(self, filename: str) -> None:
        with open(filename, 'rb') as f:
            rawdata = f.read()
            try:
                data = rawdata.decode('utf-8', 'strict')
            except UnicodeDecodeError:
                self.warning(f'The file {filename} could not be decoded as utf-8')
                return
        if data.find('\r') != -1:
            self.warning(f'The file {filename} contains non-standard line breaks.')
        if len(data) > 0 and data[-1] != '\n':
            self.warning(f"The file {filename} does not end with '\\n'.")

    def check_size_limits(self, filename: str) -> None:
        filesize = os.path.getsize(filename) / 1024.0 / 1024.0
        if filesize > 1000:
            self.error(f'The file {filename} ({filesize:.1f} Mb) is larger than 1000 Mb and can not be installed.')
        elif filesize > 100:
            self.warning(
                f'The file {filename} ({filesize:.1f} Mb) is larger than 100 Mb. This may cause performance issues and is not recommended.'
            )

    def strip_path_prefix(self, path: str) -> str:
        return os.path.relpath(path, os.path.join(self._problem.probdir, 'data'))

    # Temporary properties for use while refactoring verifyproblem into judge/
    @property
    def infile_path(self) -> Path:
        return Path(self.infile)

    @property
    def ansfile_path(self) -> Path:
        return Path(self.ansfile)

    @property
    def output_validator_flags(self) -> list[str]:
        return (
            self._problem.metadata.legacy_validator_flags.split()
            + self.testcasegroup.config.get('output_validator_flags', '').split()
        )

    @cached_property
    def reuse_key(self) -> CacheKey:
        return CacheKey(
            input_hash=hashlib.sha256(self.infile_path.read_bytes()).digest(),
            ans_hash=hashlib.sha256(self.ansfile_path.read_bytes()).digest(),
            validator_flags=tuple(self.output_validator_flags),
        )

    def is_in_sample_group(self) -> bool:
        return self.strip_path_prefix(self.infile).startswith('sample')

    def check(self, context: Context) -> bool:
        if self._check_res is not None:
            return self._check_res
        self._check_res = True
        self.check_newlines(self.infile)
        self.check_newlines(self.ansfile)
        self.check_size_limits(self.infile)
        self.check_size_limits(self.ansfile)
        self._problem.input_validators.validate(self)
        anssize = os.path.getsize(self.ansfile) / 1024.0 / 1024.0
        outputlim = self._problem.metadata.limits.output
        if anssize > outputlim:
            self.error(
                f'Answer file ({anssize:.1f} Mb) is larger than output limit ({outputlim} Mb), you need to increase output limit'
            )
        elif 2 * anssize > outputlim:
            self.warning(
                f'Answer file ({anssize:.1f} Mb) is within 50% of output limit ({outputlim} Mb), you might want to increase output limit'
            )
        if not self._problem.is_interactive() and not self._problem.is_multi_pass():
            val_res = validate_output(
                testcase=self,
                submission_output=Path(self.ansfile),
                output_validator=self._problem.output_validators.output_validator,
                metadata=self._problem.metadata,
                base_dir=Path(self._problem.tmpdir),
                diag=self._diag,
            )
            if val_res.verdict != 'AC':
                if self.is_in_sample_group():
                    self.error(f'judge answer file got {val_res} on testcase {self.strip_path_prefix(self.ansfile)}')
                else:
                    self.warning(f'judge answer file got {val_res} on testcase {self.strip_path_prefix(self.ansfile)}')
        return self._check_res

    def __str__(self) -> str:
        return f'testcase {self.strip_path_prefix(self._base)}'

    def matches_filter(self, filter_re: Pattern[str]) -> bool:
        return filter_re.search(self.strip_path_prefix(self._base)) is not None

    def get_all_testcases(self) -> list[TestCase]:
        return [self]


class TestCaseGroup(ProblemAspect):
    name: str
    _DEFAULT_CONFIG = config.load_config('testdata.yaml')
    _SCORING_ONLY_KEYS = ['accept_score', 'reject_score', 'range']
    is_group: Literal[True] = True  # Temporary workaround for a circular import in judge/submission_judge.py

    def __init__(self, problem: Problem, datadir: str | None = None, parent: TestCaseGroup | None = None):
        self._parent = parent
        self._problem = problem
        datadir = datadir or os.path.join(problem.probdir, 'data')
        self._datadir = datadir
        self.name = os.path.relpath(os.path.abspath(self._datadir), os.path.abspath(self._problem.probdir)).replace('/', '.')

        super().__init__(f'test.{self.name}', problem)

        self._seen_oob_scores = False
        self.debug(f'Loading test data group {datadir}')
        configfile = os.path.join(self._datadir, 'testdata.yaml')
        self.config: dict[str, Any] = {}
        if os.path.isfile(configfile):
            try:
                with open(configfile) as f:
                    self.config = yaml.safe_load(f)
            except Exception as e:
                self.error(str(e))
            if self.config is None:
                self.config = {}

        # For non-root groups, missing properties are inherited from the parent group
        if parent:
            for field, parent_value in parent.config.items():
                if field not in self.config:
                    self.config[field] = parent_value

        # TODO: Decide if these should stay
        # Some deprecated properties are inherited from problem config during a transition period
        legacy_grading = problem.metadata.legacy_grading
        for key in ['accept_score', 'reject_score', 'range']:
            if getattr(legacy_grading, key) is not None:
                self.config[key] = getattr(legacy_grading, key)

        problem_on_reject = legacy_grading.on_reject
        if problem_on_reject == 'first_error':
            self.config['on_reject'] = 'break'
        if problem_on_reject == 'grade':
            self.config['on_reject'] = 'continue'

        if self._problem.is_pass_fail():
            for key in TestCaseGroup._SCORING_ONLY_KEYS:
                if key not in self.config:
                    self.config[key] = None

        for field, default in TestCaseGroup._DEFAULT_CONFIG.items():
            if field not in self.config:
                self.config[field] = default

        self._items: list[TestCaseGroup | TestCase] = []
        if os.path.isdir(datadir):
            for filename in sorted(os.listdir(datadir)):
                filename = os.path.join(datadir, filename)
                if os.path.isdir(filename):
                    self._items.append(TestCaseGroup(problem, filename, self))
                else:
                    base, ext = os.path.splitext(filename)
                    if ext == '.ans' and os.path.isfile(f'{base}.in'):
                        self._items.append(TestCase(problem, base, self))

    def start_background_work(self, context: Context) -> None:
        pass

    def __str__(self) -> str:
        return f'testcase group {self.name}'

    def matches_filter(self, filter_re: Pattern[str]) -> bool:
        return True

    def get_all_testcases(self) -> list[TestCase]:
        res: list = []
        for child in self._items:
            res += child.get_all_testcases()
        return res

    def get_testcases(self) -> list[TestCase]:
        return [child for child in self._items if isinstance(child, TestCase)]

    def get_subgroups(self) -> list[TestCaseGroup]:
        return [child for child in self._items if isinstance(child, TestCaseGroup)]

    def has_custom_groups(self) -> bool:
        return any(group.get_subgroups() for group in self.get_subgroups())

    def get_score_range(self) -> tuple[float, float]:
        try:
            score_range = self.config['range']
            min_score, max_score = list(map(float, score_range.split()))
            return (min_score, max_score)
        except Exception:
            return (float('-inf'), float('inf'))

    def check_score_in_bounds(self, sub: run.Program, score: float) -> None:
        # Don't warn twice on the same subgroup, since every submission is likely
        # to have the same error.
        min_score, max_score = self.get_score_range()
        if not (min_score <= score <= max_score) and not self._seen_oob_scores:
            self._seen_oob_scores = True
            groupname = os.path.relpath(self._datadir, self._problem.probdir)
            self.error(
                f'submission {sub} got score {score} on group {groupname}, which is outside of expected score range [{min_score}, {max_score}]'
            )

    def check(self, context: Context) -> bool:
        if self._check_res is not None:
            return self._check_res
        self._check_res = True

        if self.config['grading'] not in ['default', 'custom']:
            self.error('Invalid grading policy in testdata.yaml')

        if self.config['grading'] == 'custom' and self._problem.graders._grader is None:
            self._problem.graders.fatal(f'{self} has custom grading but no custom graders provided')
        if self.config['grading'] == 'default' and Graders._default_grader is None:
            self._problem.graders.fatal(f'{self} has default grading but I could not find default grader')

        if self.config['grading'] == 'default' and 'ignore_sample' in self.config['grader_flags'].split():
            if self._parent is not None:
                self.error("'grader_flags: ignore_sample' is specified, but that flag is only allowed at top level")
            elif self.config['on_reject'] == 'break':
                self.error(
                    "'grader_flags: ignore_sample' is specified, but 'on_reject: break' may cause secret data not to be judged"
                )

        for field in self.config.keys():
            if field not in TestCaseGroup._DEFAULT_CONFIG.keys():
                self.warning(f"Unknown key '{field}' in '{os.path.join(self._datadir, 'testdata.yaml')}'")

        if not self._problem.is_scoring():
            for key in TestCaseGroup._SCORING_ONLY_KEYS:
                if self.config.get(key) is not None:
                    self.error(f"Key '{key}' is only applicable for scoring problems, this is a pass-fail problem")

        if self.config['on_reject'] not in ['break', 'continue']:
            self.error(f"Invalid value '{self.config['on_reject']}' for on_reject policy")

        if self._problem.is_scoring():
            # Check grading
            try:
                score_range = self.config['range']
                min_score, max_score = list(map(float, score_range.split()))
                if min_score > max_score:
                    self.error(f"Invalid score range '{score_range}': minimum score cannot be greater than maximum score")
            except VerifyError:
                raise
            except Exception:
                self.error(f"Invalid format '{score_range}' for range: must be exactly two floats")

        if self._parent is None:
            seen_secret = False
            seen_sample = False
            for item in self._items:
                if not isinstance(item, TestCaseGroup):
                    self.error("Can't have individual test data files at top level")
                else:
                    name = os.path.basename(item._datadir)
                    if name == 'secret':
                        seen_secret = True
                    elif name == 'sample':
                        seen_sample = True
                    else:
                        self.error('Test data at top level can only have the groups sample and secret')
                        self.debug(str(self._items))
            if not seen_secret:
                self.error('No secret data provided')
            if not seen_sample:
                self.warning('No sample data provided')

            hashes = collections.defaultdict(list)
            for root, dirs, files in os.walk(self._datadir):
                for filename in files:
                    filepath = os.path.join(root, filename)
                    if filepath.endswith('.in') and not os.path.islink(filepath):
                        md5 = hashlib.md5()
                        with open(filepath, 'rb') as f:
                            for buf in iter(lambda: f.read(1024), b''):
                                md5.update(buf)
                        filehash = md5.digest()
                        hashes[filehash].append(os.path.relpath(filepath, self._problem.probdir))
            for _, files in hashes.items():
                if len(files) > 1:
                    self.warning(f"Identical input files: '{str(files)}'")

        infiles = glob.glob(os.path.join(self._datadir, '*.in'))
        ansfiles = glob.glob(os.path.join(self._datadir, '*.ans'))

        for infile in infiles:
            if os.path.isdir(infile):
                continue
            if f'{infile[:-3]}.ans' not in ansfiles:
                self.error(f"No matching answer file for input '{infile}'")
        for ansfile in ansfiles:
            if os.path.isdir(ansfile):
                continue
            if f'{ansfile[:-4]}.in' not in infiles:
                self.error(f"No matching input file for answer '{ansfile}'")

        if not self.get_subgroups() and not self.get_testcases():
            if os.path.basename(self._datadir) != 'sample':
                self.error(f'Testcase group {self._datadir} exists, but does not contain any testcases')
            else:
                if not (
                    (self._problem.is_interactive() or self._problem.is_multi_pass())
                    and glob.glob(os.path.join(self._datadir, '*.interaction'))
                ):
                    self.warning(f'Sample testcase group {self._datadir} exists, but does not contain any testcases')

        # Check whether a <= b according to a natural sorting where numeric components
        # are compactified, so that e.g. "a" < "a1" < "a2" < "a10" = "a010" < "a10a".
        def natural_sort_le(a: str, b: str) -> bool:
            a += '\0'
            b += '\0'
            i = j = 0

            def parse_num(s: str, i: int) -> tuple[int, int]:
                ret = 0
                while ord('0') <= ord(s[i]) <= ord('9'):
                    ret = ret * 10 + ord(s[i]) - ord('0')
                    i += 1
                return ret, i

            while i < len(a) and j < len(b):
                if ord('0') <= ord(a[i]) <= ord('9') and ord('0') <= ord(b[j]) <= ord('9'):
                    anum, i = parse_num(a, i)
                    bnum, j = parse_num(b, j)
                    if anum == bnum:
                        continue
                    return anum < bnum
                if a[i] == b[j]:
                    i += 1
                    j += 1
                    continue
                return a[i] < b[j]
            return True

        last_testgroup_name = ''
        for group in self.get_subgroups():
            name = os.path.relpath(group._datadir, self._problem.probdir)
            if natural_sort_le(name, last_testgroup_name):
                self.warning(f"Test data group '{last_testgroup_name}' will be ordered before '{name}'; consider zero-padding")
            last_testgroup_name = name

        for child in self._items:
            if child.matches_filter(context.data_filter):
                child.check(context)

        return self._check_res


class ProblemStatement(ProblemPart):
    statements: dict[str, list[Path]]  # Maps language code -> statement(s)
    PART_NAME = 'statement'

    def setup(self):
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
                self.error(f'Found multiple statements in the same language {lang}: {", ".join((file.name for file in files))}')

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

    def setup(self):
        self.debug('  Loading problem config')
        try:
            self._metadata, self._origdata = metadata.load_metadata(Path(self.problem.probdir))
            self.problem._set_metadata(self._metadata)
        except ValidationError as e:
            error_str = '\n'.join([f'    {"->".join((str(loc) for loc in err["loc"]))}: {err["msg"]}' for err in e.errors()])
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
            and self.problem.testdata.has_custom_groups()
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

    def setup(self):
        attachments_dir = Path(self.problem.probdir) / 'attachments'
        self.attachments = [p for p in attachments_dir.iterdir()] if attachments_dir.is_dir() else []
        self.debug(f'Adding attachments {str(self.attachments)}')

    def check(self, context: Context) -> bool:
        if self._check_res is not None:
            return self._check_res
        self._check_res = True

        for attachment_path in self.attachments:
            if os.path.isdir(attachment_path):
                self.error(f'Directories are not allowed as attachments ({attachment_path} is a directory)')

        return self._check_res

    def get_attachment_paths(self):
        return self.attachments

    def __str__(self) -> str:
        return 'attachments'


# Junk data. The validator should reject these cases
_JUNK_CASES = [
    ('an empty file', b''),
    ('a binary file with random bytes', bytearray(random.Random(42).randbytes(1024))),
    ('a text file with the ASCII characters 32 up to 127', bytearray(x for x in range(32, 127))),
    (
        'a random text file with printable ASCII characters',
        (lambda rng: bytearray(rng.choice(string.printable.encode('utf8')) for _ in range(200)))(random.Random(42)),
    ),
]

# Try to crash the output validator, causing a judge error
_JUNK_CASES_CRASH = [
    ('a file with the number -1', b'-1'),
    ('a file with the number 2147483647', b'2147483647'),
    ('a file with the number 2147483648', b'2147483648'),
    ('a file with the number 9223372036854775808', b'9223372036854775808'),
    ('a file with the number 0', b'0'),
    ('a file with the number 1', b'1'),
    ('a file with the number 1.0', b'1.0'),
    ('a file with the string "a"', b'a'),
    ('a file with the contents "2\\n-1 1"', b'2\n-1 1'),
    ('a file with the contents "2\\n1"', b'2\n1'),
    ('a file with the contents "1\\n-1 1"', b'1\n-1 1'),
    ('a file with the contents "1\\na"', b'1\na'),
    ('a file with the contents "(()"', b'(()'),
    ('a file with the contents "1-"', b'1-'),
    ('a file with the contents "1/0"', b'1/0'),
    ('a file with the contents "2\\n<"', b'2\n<'),
    ('a file with the contents "NaN"', b'NaN'),
    ('a file with the contents "inf"', b'inf'),
    ('a file with the contents "\\x00"', b'\x00'),
    ('a file with the contents "\\x80"', b'\x80'),
]


def _build_junk_modifier(
    desc: str, pattern: str, repl: str | Callable[[Match[str]], str]
) -> tuple[str, Callable, Callable[[str], str]]:
    p = re.compile(pattern)
    return (desc, p.search, lambda text: p.sub(repl, text))


_JUNK_MODIFICATIONS = [
    _build_junk_modifier('spaces added where there already is whitespace', r'\s', lambda m: m.group(0) + ' '),
    _build_junk_modifier('spaces added to the end of a line', r'\n', lambda m: m.group(0) + ' '),
    _build_junk_modifier('newlines added where there already are newlines', '\n', lambda m: '\n\n'),
    _build_junk_modifier('leading zeros added to integers', r'(^|[^.]\b)([0-9]+)\b', r'\g<1>0000000000\g<2>'),
    _build_junk_modifier('trailing zeros added to real number decimal portion', r'\.[0-9]+\b', r'\g<0>0000000000'),
    (
        'random junk added to the end of the file',
        lambda f: True,
        lambda f: f + ''.join(random.choice(string.printable) for _ in range(200)),
    ),
]


class InputValidators(ProblemPart):
    PART_NAME = 'input_validator'

    def setup(self):
        input_validators_path = os.path.join(self.problem.probdir, 'input_format_validators')
        if os.path.isdir(input_validators_path):
            self._uses_old_path = True
        else:
            self._uses_old_path = False
            new_input_validators_path = os.path.join(self.problem.probdir, 'input_validators')
            if os.path.isdir(new_input_validators_path):
                input_validators_path = new_input_validators_path
        self._validators = run.find_programs(
            input_validators_path,
            language_config=self.problem.language_config,
            allow_validation_script=True,
            work_dir=self.problem.tmpdir,
        )
        return {}

    def __str__(self) -> str:
        return 'input format validators'

    def start_background_work(self, context: Context) -> None:
        for val in self._validators:
            context.submit_background_work(lambda v: v.compile(), val)

    def check(self, context: Context | None) -> bool:
        if self._check_res is not None:
            return self._check_res
        if self._uses_old_path:
            self.warning('input_format_validators is a deprecated name; please use input_validators instead')
        self._check_res = True
        if len(self._validators) == 0:
            self.error('No input format validators found')

        for val in self._validators[:]:
            try:
                success, msg = val.compile()
                if not success:
                    self.error(f'Compile error for {val}', msg)
                    self._validators.remove(val)
            except run.ProgramError as e:
                self.error(str(e))

        # Only sanity check input validators if they all actually compiled
        if self._check_res:
            all_flags: set[str] = set()

            def collect_flags(group: TestCaseGroup, flags: set[str]) -> None:
                if len(group.get_testcases()) > 0:
                    flags.add(group.config['input_validator_flags'])
                for subgroup in group.get_subgroups():
                    collect_flags(subgroup, flags)

            collect_flags(self.problem.testdata, all_flags)

            fd, file_name = tempfile.mkstemp()
            os.close(fd)
            for desc, case in _JUNK_CASES:
                f = open(file_name, 'wb')
                f.write(case)
                f.close()
                for flags_str in all_flags:
                    flags = flags_str.split()
                    for val in self._validators:
                        status, _ = val.run(file_name, args=flags, work_dir=self.problem.tmpdir)
                        if os.WEXITSTATUS(status) != 42:
                            break
                    else:
                        self.warning(f'No validator rejects {desc} with flags "{" ".join(flags)}"')

            def modified_input_validates(applicable, modifier):
                for testcase in self.problem.testdata.get_all_testcases():
                    try:
                        with open(testcase.infile) as infile:
                            infile_data = infile.read()
                        if not applicable(infile_data):
                            continue
                    except UnicodeDecodeError:
                        continue

                    with open(file_name, 'wb') as f:
                        f.write(modifier(infile_data).encode('utf8'))

                    for flags_str in all_flags:
                        flags = flags_str.split()
                        for val in self._validators:
                            status, _ = val.run(file_name, args=flags, work_dir=self.problem.tmpdir)
                            if os.WEXITSTATUS(status) != 42:
                                # expected behavior; validator rejects modified input
                                return False

                    # we found a file we could modify, and all validators
                    # accepted the modifications
                    return True

                # no files were modifiable
                return False

            for desc, applicable, modifier in _JUNK_MODIFICATIONS:
                if modified_input_validates(applicable, modifier):
                    self.warning(f'No validator rejects {desc}')

            os.unlink(file_name)

        return self._check_res

    def validate(self, testcase: TestCase) -> None:
        flags = testcase.testcasegroup.config['input_validator_flags'].split()

        # Remove input validators that don't compile, even without -p validators
        self.check(None)

        for val in self._validators:
            with tempfile.NamedTemporaryFile() as outfile, tempfile.NamedTemporaryFile() as errfile:
                status, _ = val.run(testcase.infile, outfile.name, errfile.name, args=flags, work_dir=self.problem.tmpdir)
                if not os.WIFEXITED(status):
                    emsg = f'Input format validator {val} crashed on input {testcase.infile}'
                elif os.WEXITSTATUS(status) != 42:
                    emsg = f'Input format validator {val} did not accept input {testcase.infile}, exit code: {os.WEXITSTATUS(status)}'
                else:
                    continue
                validator_stdout = outfile.read().decode('utf-8', 'replace')
                validator_stderr = errfile.read().decode('utf-8', 'replace')
                validator_output = '\n'.join(out for out in [validator_stdout, validator_stderr] if out)
                testcase.error(emsg, validator_output)


class Graders(ProblemPart):
    _default_grader = run.get_tool('default_grader')

    PART_NAME = 'grader'

    def setup(self):
        graders: list = run.find_programs(
            os.path.join(self.problem.probdir, 'graders'),
            language_config=self.problem.language_config,
            work_dir=self.problem.tmpdir,
        )
        if len(graders) > 1:
            self.fatal('There is more than one custom grader')
        self._grader = graders[0] if graders else None
        return {}

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
    _default_validator = run.get_tool('default_validator')

    PART_NAME = 'output_validator'

    def setup(self):
        self._validators = run.find_programs(
            os.path.join(self.problem.probdir, self.problem.format.output_validator_directory),
            language_config=self.problem.language_config,
            work_dir=self.problem.tmpdir,
        )
        self._has_precompiled = False

    def uses_default_validator(self) -> bool:
        if self.problem.format is FormatVersion.LEGACY:
            return self.problem.metadata.legacy_validation == 'default'
        return not self._validators

    @property
    def output_validator(self) -> run.Program:
        if self.uses_default_validator() or not self._validators:
            return self._default_validator
        return self._validators[0]

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

        self.warn_directory('output validators', 'output_validator_directory')

        if len(self._validators) > 1:
            self.error_in_2023_07(
                f'Support for multiple output validators has been dropped. will only use {self.output_validator}'
            )

        safe_output_validator_languages = {'c', 'cpp', 'python3'}
        if (
            isinstance(self.output_validator, run.SourceCode)
            and self.output_validator.language.lang_id not in safe_output_validator_languages
        ):
            self.error_in_2023_07(
                f'Output validator in {self.output_validator.language.name}. Only {safe_output_validator_languages} are standardized. Check carefully if your CCS supports more (Kattis does not).'
            )

        if self.uses_default_validator() and self._validators:
            self.error('There are validator programs but problem.yaml has validation = "default"')
        elif not self.uses_default_validator() and not self._validators:
            self.fatal('problem.yaml specifies custom validator but no validator programs found')

        if self.uses_default_validator() and self._default_validator is None:
            self.fatal('Unable to locate default validator')

        try:
            success, msg = self.output_validator.compile()
            if not success:
                self.fatal(f'Compile error for output validator {self.output_validator}', msg)
        except run.ProgramError as e:
            self.fatal(f'Compile error for output validator {self.output_validator}', str(e))

        # Only sanity check output validators if they all actually compiled
        if self._check_res:
            # Sanity check cases that should be rejected by the output validator
            def run_junk_case(case_desc: str, junk_content: bytes, testcases: list[TestCase]) -> list[SubmissionResult]:
                results = []
                with tempfile.NamedTemporaryFile(mode='wb') as f:
                    f.write(junk_content)
                    f.flush()
                    for testcase in testcases:
                        result = validate_output(
                            testcase=testcase,
                            submission_output=Path(f.name),
                            output_validator=self.output_validator,
                            metadata=self.problem.metadata,
                            base_dir=Path(self.problem.tmpdir),
                            diag=self._diag,
                        )
                        results.append(result)
                        if result.verdict == 'JE':
                            self.error(f'{case_desc} as output on test case {testcase} gave {result}')
                            break
                return results

            # Junk cases that the output validator should reject
            for desc, junk_case_content in _JUNK_CASES:
                results = run_junk_case(desc, junk_case_content, self.problem.testdata.get_all_testcases())
                rejected = any(result.verdict != 'AC' for result in results)
                if not rejected:
                    self.warning(f'{desc} gets AC')

            # Malformed cases that a poorly-written output validator might crash on
            # Note that these might be valid output, so we only check if it crashes.
            # These bugs are rarely dependent on the actual test case, so we just
            # run on a few to keep things speedy.
            test_cases = self.problem.testdata.get_all_testcases()[:3]
            for desc, junk_case_content in _JUNK_CASES_CRASH:
                run_junk_case(desc, junk_case_content, test_cases)

        return self._check_res


class Submissions(ProblemPart):
    # (verdict, directory, required)
    _VERDICTS: list[tuple[Verdict, str, bool]] = [
        ('AC', 'accepted', True),
        ('PAC', 'partially_accepted', False),
        ('WA', 'wrong_answer', False),
        ('RTE', 'run_time_error', False),
        ('TLE', 'time_limit_exceeded', False),
    ]

    PART_NAME = 'submission'

    def setup(self):
        self._submissions = {}
        srcdir = os.path.join(self.problem.probdir, 'submissions')
        for verdict in Submissions._VERDICTS:
            acr = verdict[0]
            self._submissions[acr] = run.find_programs(
                os.path.join(srcdir, verdict[1]),
                language_config=self.problem.language_config,
                work_dir=self.problem.tmpdir,
                include_dir=os.path.join(self.problem.probdir, 'include'),
            )
        return {}

    def __str__(self) -> str:
        return 'submissions'

    def check_submission(
        self, sub, context: Context, expected_verdict: Verdict, timelim: float, timelim_high: float
    ) -> list[SubmissionResult]:
        desc = f'{expected_verdict} submission {sub}'
        partial = expected_verdict == 'PAC'

        judge = SubmissionJudge(
            sub=sub,
            output_validator=self.problem.output_validators.output_validator,
            metadata=self.problem.metadata,
            root=self.problem.testdata,
            base_dir=Path(self.problem.tmpdir),
            context=context,
            diag=self._diag,
            custom_grader=self.problem.graders._grader,
        )
        if context.executor is not None:
            judge.precompute(timelim_high)
        results_high = judge.judge(timelim_high)
        if not results_high:
            self.fatal('check_submission called, but found no test cases to run on.')
        result_high = results_high[-1]

        results = judge.judge(timelim)
        result = results[-1]

        # Check if scores were outside of the range for any groups
        if self.problem.is_scoring():
            for r in results:
                if r.score is not None and isinstance(r.test_node, TestCaseGroup):
                    r.test_node.check_score_in_bounds(sub, r.score)

        # Warn if AC (but not PAC) submissions fail on samples. It's not uncommon for sample cases to be
        # ignored, so failing on them could be silent otherwise. Skip warning if the result isn't AC -
        # then something worse has gone wrong, and we'll error later.
        if expected_verdict == 'AC' and result.verdict == 'AC':
            if sample_failure := self._find_sample_failure(results):
                self.warning(f'{desc} got {sample_failure.verdict} on sample: {sample_failure}')

        # Warn if a PAC submission would affect time limit, had it been use to compute the time limit. Only do this
        # if it gets AC on the computed time limit, otherwise we have other warnings below.
        if partial and result.verdict == 'AC':
            self._warn_pac_too_slow(judge, results, timelim, desc)

        if result.verdict != result_high.verdict or result.score != result_high.score:
            self.warning(
                f'{desc} sensitive to time limit: limit of {timelim} secs -> {result}, limit of {timelim_high} secs -> {result_high}'
            )

        required_verdict: Verdict = 'AC' if partial else expected_verdict
        if partial and self.fully_accepted(result):
            self.warning(f'{desc} was fully accepted: {result}')
        elif result.verdict == required_verdict:
            self.msg(f'   {desc} OK: {result}')
            if not partial and required_verdict == 'AC' and not self.fully_accepted(result) and self.full_score_finite():
                # For some heuristic problems, this is expected. Thus, only warn.
                self.warning(f'{desc} did not attain full score (consider moving it to partially_accepted)')
        elif result_high.verdict == required_verdict and not (partial and self.fully_accepted(result_high)):
            self.msg(f'   {desc} OK with extra time: {result_high}')
        else:
            self.error(f'{desc} got {result}', result_high.additional_info)

        return results

    def _find_sample_failure(self, results: list[SubmissionResult]) -> SubmissionResult | None:
        for r in results:
            if r.verdict != 'AC' and isinstance(r.test_node, TestCase) and r.test_node.is_in_sample_group():
                return r
        return None

    def _warn_pac_too_slow(self, judge: SubmissionJudge, results: list[SubmissionResult], timelim: float, desc: str) -> None:
        """Warn if a PAC submission is slow enough that it would have affected the time limit."""
        runtime_without_affecting_tl = timelim / self.problem.metadata.limits.time_multipliers.ac_to_time_limit
        if judge.judge(runtime_without_affecting_tl)[-1].verdict == 'AC':
            return
        for t in sorted(r.runtime for r in results if r.runtime > runtime_without_affecting_tl):
            if judge.judge(t)[-1].verdict == 'AC':
                self.warning(f'{desc} is slower than all AC submissions. It needs {t:.2f}s to get AC')

    def _get_table_groups(self) -> list[TestCaseGroup]:
        """Return the groups to show as columns: expand any root child that has subgroups."""
        result = []
        for group in self.problem.testdata.get_subgroups():
            subgroups = group.get_subgroups()
            if subgroups:
                result.extend(subgroups)
            else:
                result.append(group)
        return result

    def _print_results_table(self, all_submission_results: list[tuple[run.Program, list[SubmissionResult]]]) -> None:
        groups = self._get_table_groups()
        is_scoring = self.problem.is_scoring()

        def cell_for_group(results: list[SubmissionResult], group: TestCaseGroup) -> str:
            for r in results:
                if r.test_node is group:
                    if r.verdict == 'AC':
                        if is_scoring and r.score is not None:
                            score_str = f'{int(r.score)}' if r.score == int(r.score) else f'{r.score:.2f}'
                            score_part = f'({score_str})'
                        else:
                            score_part = ''
                        return f'AC{score_part}:{r.runtime:.2f}s'
                    return r.verdict
            return '-'

        def cell_for_pts(results: list[SubmissionResult]) -> str:
            score = results[-1].score
            return f'{score:.0f}' if score is not None else '-'

        def cell_for_time(results: list[SubmissionResult]) -> str:
            t = results[-1].runtime
            return f'{t:.2f}s' if t >= 0 else '-'

        headers = ['Submission'] + [os.path.basename(g._datadir) for g in groups]
        if is_scoring:
            headers.append('Pts')
        headers.append('Time')

        rows = []
        for sub, results in all_submission_results:
            row = [sub.name]  # type: ignore
            for g in groups:
                row.append(cell_for_group(results, g))
            if is_scoring:
                row.append(cell_for_pts(results))
            row.append(cell_for_time(results))
            rows.append(row)

        widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                widths[i] = max(widths[i], len(cell))

        self.msg('Submission results:')
        indent = '   '
        self.msg(indent + '  '.join(h.ljust(widths[i]) for i, h in enumerate(headers)))
        for row in rows:
            self.msg(indent + '  '.join(cell.ljust(widths[i]) for i, cell in enumerate(row)))

    def full_score_finite(self) -> bool:
        min_score, max_score = self.problem.testdata.get_score_range()
        if self.problem.metadata.legacy_grading.objective == 'min':
            return min_score != float('-inf')
        else:
            return max_score != float('inf')

    def fully_accepted(self, result: SubmissionResult) -> bool:
        min_score, max_score = self.problem.testdata.get_score_range()
        best_score = min_score if self.problem.metadata.legacy_grading.objective == 'min' else max_score
        return result.verdict == 'AC' and (not self.problem.is_scoring() or result.score == best_score)

    def start_background_work(self, context: Context) -> None:
        # Send off an early background compile job for each submission and
        # validator, to avoid a bottleneck step at the start of each test run.
        self.problem.output_validators.start_background_work(context)
        for verdict in Submissions._VERDICTS:
            acr = verdict[0]
            for sub in self._submissions[acr]:
                sub_name = sub.name  # type: ignore
                if context.submission_filter.search(os.path.join(verdict[1], sub_name)):
                    context.submit_background_work(lambda s: s.compile(), sub)

    def _compute_time_limit(self, fixed_limit: float | None, lower_bound_runtime: float | None) -> tuple[float, float]:
        if fixed_limit is None and lower_bound_runtime is None:
            # 5 minutes is our currently hard coded upper bound for what to allow when we don't know the time limit yet
            return 300.0, 300.0

        limits = self.problem.metadata.limits
        if fixed_limit is not None:
            timelim = fixed_limit
        else:
            assert lower_bound_runtime is not None, 'Assert to keep mypy happy'
            exact_timelim = lower_bound_runtime * limits.time_multipliers.ac_to_time_limit
            timelim = max(1, math.ceil(exact_timelim / limits.time_resolution)) * limits.time_resolution

        return timelim, timelim * limits.time_multipliers.time_limit_to_tle

    def check(self, context: Context) -> bool:
        if self._check_res is not None:
            return self._check_res
        self._check_res = True

        limits = self.problem.metadata.limits
        ac_to_time_limit = limits.time_multipliers.ac_to_time_limit

        fixed_limit: float | None = context.fixed_timelim if context.fixed_timelim is not None else limits.time_limit
        lower_bound_runtime: float | None = None  # The runtime of the slowest submission used to lower bound the time limit.

        if limits.time_limit is not None and context.fixed_timelim is not None:
            self.warning('There is a fixed time limit in problem.yaml, and you provided one on command line. Using command line.')

        has_testcases = any(tc.matches_filter(context.data_filter) for tc in self.problem.testdata.get_all_testcases())
        if not has_testcases:
            self.warning('Found no test cases to run on. Did you filter them all out?')

        all_submission_results: list[tuple[run.Program, list[SubmissionResult]]] = []

        for verdict in Submissions._VERDICTS:
            acr = verdict[0]
            if verdict[2] and not self._submissions[acr]:
                self.error(f'Require at least one "{verdict[1]}" submission')

            runtimes = []

            for sub in self._submissions[acr]:
                sub_name = sub.name  # type: ignore
                if context.submission_filter.search(os.path.join(verdict[1], sub_name)):
                    self.info(f'Check {acr} submission {sub}')

                    if sub.code_size() > 1024 * limits.code:
                        self.error(
                            f'{acr} submission {sub} has size {sub.code_size() / 1024.0:.1f} kiB, exceeds code size limit of {limits.code} kiB'
                        )
                        continue

                    success, msg = sub.compile()
                    if not success:
                        self.error(f'Compile error for {acr} submission {sub}', additional_info=msg)
                        continue

                    if has_testcases:
                        timelim, timelim_high = self._compute_time_limit(fixed_limit, lower_bound_runtime)
                        sub_results = self.check_submission(sub, context, acr, timelim, timelim_high)
                        runtimes.append(sub_results[-1].runtime)
                        all_submission_results.append((sub, sub_results))

            if acr == 'AC' and has_testcases:
                if len(runtimes) > 0:
                    lower_bound_runtime = max(runtimes)

                # Helper function to format numbers with at most 3 decimals and dealing with None
                def _f_n(number: float | None) -> str:
                    return f'{round(number, 3):g}' if number is not None else '-'

                if fixed_limit is not None and lower_bound_runtime is not None:
                    if lower_bound_runtime * ac_to_time_limit > fixed_limit:
                        self.error(
                            f'Time limit fixed to {_f_n(fixed_limit)}, but slowest AC runs in {_f_n(lower_bound_runtime)} which is within a factor {_f_n(ac_to_time_limit)}.'
                        )
                    tl_from_subs, _ = self._compute_time_limit(None, lower_bound_runtime)
                    if not math.isclose(fixed_limit, tl_from_subs):
                        self.msg(
                            f'   Solutions give timelim of {_f_n(tl_from_subs)} seconds, but will use provided fixed limit of {_f_n(fixed_limit)} seconds instead'
                        )

                timelim, timelim_margin = self._compute_time_limit(fixed_limit, lower_bound_runtime)
                self.msg(
                    f'   Slowest AC runtime: {_f_n(lower_bound_runtime)}, setting timelim to {_f_n(timelim)} secs, safety margin to {_f_n(timelim_margin)} secs'
                )
                self.problem._set_timelim(timelim)

        if all_submission_results:
            self._print_results_table(all_submission_results)

        return self._check_res


class Problem(ProblemAspect):
    """Represents a checkable problem"""

    def __init__(self, probdir: str, diagnostics: Diagnostics):
        self.probdir = os.path.realpath(probdir)
        self.shortname: str = os.path.basename(self.probdir)
        self._diag = diagnostics
        super().__init__(self.shortname, self)
        self.language_config = languages.load_language_config(Path(self.probdir).parent)
        self.testcase_by_infile: dict[str, TestCase] = {}
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
        self.testdata = TestCaseGroup(self, os.path.join(self.probdir, 'data'))
        self.submissions = Submissions(self)
        self.loaded = True

    def __enter__(self) -> Problem:
        self.tmpdir = tempfile.mkdtemp(prefix=f'verify-{self.shortname}-')
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback) -> None:
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
                'submissions': [self.submissions],
            }
            assert sorted(part_mapping.keys()) == sorted(PROBLEM_PARTS), 'part_mapping and PROBLEM_PARTS must be kept in sync'

            if not re.match('^[a-z0-9]+$', self.shortname):
                self.error(f"Invalid shortname '{self.shortname}' (must be [a-z0-9]+)")
            if self.format is FormatVersion.V_2023_07:
                self.warning(f'Support for version {self.format} is very incomplete. Verification may not work as expected.')

            self._check_symlinks()
            self._check_file_and_directory_names()
            self._check_submission_directory_names()

            run.limit.check_limit_capabilities(self)

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
        finally:
            # Wait for background work to finish before performing an rmtree on
            # the directory tree it uses.
            context.wait_for_background_work()
        return self.errors, self.warnings

    def _check_submission_directory_names(self):
        """Heuristically check if submissions contain any directories that will be ignored because of typos or format mismatches"""
        submission_directories = [p.name for p in (Path(self.probdir) / 'submissions').glob('*') if p.is_dir()]
        if len(submission_directories) == 0:
            return

        def most_similar(present_dir: str, format_version: FormatVersion):
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

    def _check_symlinks(self):
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

    def _check_file_and_directory_names(self):
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
