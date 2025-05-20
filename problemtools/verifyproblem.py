#! /usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
import threading
import queue
import glob
import string
import hashlib
import collections
import os
import signal
import re
import shutil
import logging
import tempfile
import sys
import copy
import random
import traceback
import uuid
from pathlib import Path

import colorlog
import yaml

from . import config
from . import languages
from . import metadata
from . import problem2html
from . import problem2pdf
from . import run
from . import statement_util
from .formatversion import FormatVersion, get_format_version

from abc import ABC
from typing import Any, Callable, ClassVar, Literal, Pattern, Match, ParamSpec, Type, TypeVar
from pydantic import ValidationError

log = logging.getLogger(__name__)

Verdict = Literal['AC', 'TLE', 'OLE', 'MLE', 'RTE', 'WA', 'PAC', 'JE']


def is_TLE(status: int, may_signal_with_usr1: bool = False) -> bool:
    return os.WIFSIGNALED(status) and (
        os.WTERMSIG(status) == signal.SIGXCPU or (may_signal_with_usr1 and os.WTERMSIG(status) == signal.SIGUSR1)
    )


def is_RTE(status: int) -> bool:
    return not os.WIFEXITED(status) or bool(os.WEXITSTATUS(status))


class SubmissionResult:
    def __init__(self, verdict: str, score: float | None = None, reason: str | None = None, additional_info: str | None = None):
        self.verdict = verdict
        self.score = score
        self.reason = reason
        self.additional_info = additional_info
        self.testcase: TestCase | None = None
        self.runtime_testcase: TestCase | None = None
        self.runtime = -1.0
        self.ac_runtime = -1.0
        self.ac_runtime_testcase: TestCase | None = None
        self.validator_first = False
        self.sample_failures: list[SubmissionResult] = []

    def set_ac_runtime(self) -> None:
        if self.verdict == 'AC':
            self.ac_runtime = self.runtime
            self.ac_runtime_testcase = self.runtime_testcase

    def __str__(self) -> str:
        verdict = self.verdict
        details = []

        if verdict == 'AC' and self.score is not None:
            verdict += f' ({self.score:.0f})'

        if self.reason is not None:
            details.append(self.reason)
        if self.testcase is not None:
            details.append(f'testcase: {self.testcase}')
        if self.runtime != -1:
            details.append(f'CPU: {self.runtime:.2f}s @ {self.runtime_testcase}')

        if len(details) == 0:
            return verdict
        return f'{verdict} [{", ".join(details)}]'


class VerifyError(Exception):
    pass


_T = TypeVar('_T')
_P = ParamSpec('_P')


class Context:
    def __init__(self, args: argparse.Namespace, executor: ThreadPoolExecutor | None) -> None:
        self.data_filter: Pattern[str] = args.data_filter
        self.submission_filter: Pattern[str] = args.submission_filter
        self.fixed_timelim: int | None = args.fixed_timelim
        self.executor = executor
        self._background_work: list[concurrent.futures.Future[object]] = []

    def submit_background_work(self, job: Callable[_P, _T], *args: _P.args, **kwargs: _P.kwargs) -> None:
        assert self.executor
        self._background_work.append(self.executor.submit(job, *args, **kwargs))

    def wait_for_background_work(self) -> None:
        concurrent.futures.wait(self._background_work)


class ProblemAspect(ABC):
    errors: int = 0
    warnings: int = 0
    _check_res: bool | None = None
    problem: Problem

    def __append_additional_info(self, msg: str, additional_info: str | None) -> str:
        max_additional_info = self.problem.max_additional_info()
        if additional_info is None or max_additional_info <= 0:
            return msg
        additional_info = additional_info.rstrip()
        if not additional_info:
            return msg
        lines = additional_info.split('\n')
        if len(lines) == 1:
            return f'{msg} ({lines[0]})'
        if len(lines) > max_additional_info:
            lines = lines[:max_additional_info] + [f'[.....truncated to {max_additional_info} lines.....]']

        return f'{msg}:\n' + '\n'.join(' ' * 8 + line for line in lines)

    def __init__(self, name: str, problem: Problem) -> None:
        self.log = log.getChild(name)
        self.problem = problem

    def fatal(self, msg: str, additional_info: str | None = None, *args) -> None:
        self._check_res = False
        self._add_error()
        self.log.critical(self.__append_additional_info(msg, additional_info), *args)
        raise VerifyError(msg)

    def error(self, msg: str, additional_info: str | None = None, *args) -> None:
        self._check_res = False
        self._add_error()
        self.log.error(self.__append_additional_info(msg, additional_info), *args)
        if self.problem.bail_on_error():
            raise VerifyError(msg)

    def warning(self, msg: str, additional_info: str | None = None, *args) -> None:
        if self.problem.consider_warnings_errors():
            self.error(msg, additional_info, *args)
            return
        self._add_warning()
        self.log.warning(self.__append_additional_info(msg, additional_info), *args)

    def error_in_2023_07(self, msg: str, additional_info: str | None = None, *args) -> None:
        if self.problem.format is FormatVersion.LEGACY:
            self.warning(msg, additional_info, *args)
        else:
            self.error(msg, additional_info, *args)

    def info(self, msg: str, *args) -> None:
        self.log.info(msg, *args)

    def debug(self, msg: str, *args) -> None:
        self.log.debug(msg, *args)

    def msg(self, msg):
        print(msg)

    def _add_error(self) -> None:
        self.errors += 1
        if self.problem is not self:
            self.problem._add_error()

    def _add_warning(self) -> None:
        self.warnings += 1
        if self.problem is not self:
            self.problem._add_warning()


class ProblemPart(ProblemAspect):
    """Baseclass for all parts that can be included in a problem-format."""

    """Should always be overridden by the subclass. Specifies the name that will be used to refer
    to the part e.g for logs.
    """
    PART_NAME: ClassVar[str]

    """Should return all classes that need to be initialized before this one. It is sufficient to be
    a subclass of the classes listed. There should be exactly one subclass of each dependency in the
    format that the problem-part is included in.
    
    Note that this will only ensure that the specified classes are initialized before this one, but
    they might be checked in a different order.
    """

    @staticmethod
    def setup_dependencies() -> set[type]:
        return set()

    def __init__(self, problem: Problem) -> None:
        if self.PART_NAME is None:
            raise NotImplementedError('Every problem-part must override PART_NAME')
        super().__init__(f'{problem.shortname}.{self.PART_NAME}', problem)

    """Override to setup data about this problem-part. The order in which problem-parts are setup 
    will be decided based on the dependencies that exist.

    Return value is the data made available by initializing this part.
    """

    def setup(self) -> dict:
        return {}

    def start_background_work(self, context: Context) -> None:
        pass

    def check(self, context: Context) -> bool:
        return True


class TestCase(ProblemAspect):
    Result = tuple[SubmissionResult, SubmissionResult, SubmissionResult]

    def __init__(self, problem: Problem, aspect_name: str, base: str, testcasegroup: TestCaseGroup) -> None:
        super().__init__(f'{problem.shortname}.{aspect_name}.{testcasegroup.name}.{os.path.basename(base)}', problem)
        self._base = base
        self.infile = f'{base}.in'
        self.ansfile = f'{base}.ans'
        self._problem = problem
        self.testcasegroup = testcasegroup
        self.reuse_result_from: TestCase | None = None
        self.counter = len(problem.getProblemPart(ProblemTestCases).testcase_by_infile)
        problem.getProblemPart(ProblemTestCases).testcase_by_infile[self.infile] = self

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
        self._problem.getProblemPart(InputValidators).validate(self)
        anssize = os.path.getsize(self.ansfile) / 1024.0 / 1024.0
        outputlim = self._problem.getMetadata().limits.output
        if anssize > outputlim:
            self.error(
                f'Answer file ({anssize:.1f} Mb) is larger than output limit ({outputlim} Mb), you need to increase output limit'
            )
        elif 2 * anssize > outputlim:
            self.warning(
                f'Answer file ({anssize:.1f} Mb) is within 50% of output limit ({outputlim} Mb), you might want to increase output limit'
            )
        if not self._problem.getMetadata().is_interactive():
            val_res = self._problem.getProblemPart(OutputValidators).validate(self, self.ansfile)
            if val_res.verdict != 'AC':
                if self.is_in_sample_group():
                    self.error(f'judge answer file got {val_res}')
                else:
                    self.warning(f'judge answer file got {val_res}')
        self._check_symlinks()
        return self._check_res

    def __str__(self) -> str:
        return f'testcase {self.strip_path_prefix(self._base)}'

    def matches_filter(self, filter_re: Pattern[str]) -> bool:
        return filter_re.search(self.strip_path_prefix(self._base)) is not None

    def set_symlinks(self) -> None:
        if not os.path.islink(self.infile):
            return
        target = os.path.realpath(self.infile)
        if target in self._problem.getProblemPart(ProblemTestCases).testcase_by_infile:
            self.reuse_result_from = self._problem.getProblemPart(ProblemTestCases).testcase_by_infile[target]

    def _check_symlinks(self) -> bool:
        if not os.path.islink(self.infile):
            return True
        nicepath = os.path.relpath(self.infile, self._problem.probdir)
        in_target = os.path.realpath(self.infile)
        ans_target = os.path.realpath(self.ansfile)
        if not in_target.endswith('.in'):
            self.error(f"Symbolic link does not point to a .in file for input '{nicepath}'")
            return False
        if ans_target != f'{in_target[:-3]}.ans':
            self.error(f"Symbolic link '{nicepath}' must have a corresponding link for answer file")
            return False
        if self.reuse_result_from is None:
            self.error(f"Symbolic link points outside data/ directory for file '{nicepath}'")
            return False
        if (
            self.testcasegroup.config['output_validator_flags']
            != self.reuse_result_from.testcasegroup.config['output_validator_flags']
        ):
            self.error(f"Symbolic link '{nicepath}' points to testcase with different output validator flags")
            return False
        return True

    def run_submission(self, sub, runner: Runner, context: Context) -> Result:
        (res, res_low, res_high), reused = runner.run(self)
        res = self._init_result_for_testcase(res)
        res_low = self._init_result_for_testcase(res_low)
        res_high = self._init_result_for_testcase(res_high)
        msg = 'Reused test file result' if reused else 'Test file result'
        self.info(f'{msg}: {res}')
        if res.verdict != 'AC' and self.is_in_sample_group():
            res.sample_failures.append(res)

        return (res, res_low, res_high)

    def run_submission_real(self, sub, context: Context, timelim: int, timelim_low: int, timelim_high: int) -> Result:
        # This may be called off-main thread.
        if self._problem.getMetadata().is_interactive():
            res_high = self._problem.getProblemPart(OutputValidators).validate_interactive(
                self, sub, timelim_high, self._problem.getProblemPart(Submissions)
            )
        else:
            outfile = os.path.join(self._problem.tmpdir, f'output-{self.counter}')
            errfile = os.path.join(self._problem.tmpdir, f'error-{self.counter}')
            status, runtime = sub.run(
                infile=self.infile,
                outfile=outfile,
                errfile=errfile,
                timelim=timelim_high + 1,
                memlim=self._problem.getMetadata().limits.memory,
                work_dir=sub.path,
            )
            if is_TLE(status) or runtime > timelim_high:
                res_high = SubmissionResult('TLE')
            elif is_RTE(status):
                try:
                    with open(errfile, mode='rt') as f:
                        info = f.read()
                except IOError:
                    self.info('Failed to read error file %s', errfile)
                    info = None
                res_high = SubmissionResult('RTE', additional_info=info)
            else:
                res_high = self._problem.getProblemPart(OutputValidators).validate(self, outfile)
            res_high.runtime = runtime

        if res_high.runtime <= timelim_low:
            res_low = res_high
            res = res_high
        elif res_high.runtime <= timelim:
            res_low = SubmissionResult('TLE')
            res = res_high
        elif res_high.validator_first and res_high.verdict == 'WA':
            # WA can override TLE for interactive problems (see comment in validate_interactive).
            res = SubmissionResult('WA')
            res.validator_first = True
            res_low = res
            res_high.runtime = timelim_low
        else:
            res_low = SubmissionResult('TLE')
            res = res_low

        res.runtime = res_high.runtime
        res_low.runtime = res_high.runtime
        res.set_ac_runtime()
        res_low.set_ac_runtime()
        res_high.set_ac_runtime()
        return (res, res_low, res_high)

    def _init_result_for_testcase(self, res: SubmissionResult) -> SubmissionResult:
        res = copy.copy(res)
        res.testcase = self
        res.runtime_testcase = self
        if res.score is None:
            if res.verdict == 'AC':
                res.score = self.testcasegroup.config['accept_score']
            else:
                res.score = self.testcasegroup.config['reject_score']
        return res

    def get_all_testcases(self) -> list[TestCase]:
        return [self]

    def all_datasets(self) -> list[str]:
        return [self._base]


class TestCaseGroup(ProblemAspect):
    name: str
    _DEFAULT_CONFIG = config.load_config('testdata.yaml')
    _SCORING_ONLY_KEYS = ['accept_score', 'reject_score', 'range']

    def __init__(self, problem: Problem, aspect_name: str, datadir: str | None = None, parent: TestCaseGroup | None = None):
        self._parent = parent
        self._problem = problem
        datadir = datadir or os.path.join(problem.probdir, 'data')
        self._datadir = datadir
        self.name = os.path.relpath(os.path.abspath(self._datadir), os.path.abspath(self._problem.probdir)).replace('/', '.')

        super().__init__(f'{problem.shortname}.{aspect_name}.{self.name}', problem)

        self._seen_oob_scores = False
        self.debug('Loading test data group %s', datadir)
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
        legacy_grading = problem.getMetadata().legacy_grading
        for key in ['accept_score', 'reject_score', 'range']:
            if getattr(legacy_grading, key) is not None:
                self.config[key] = getattr(legacy_grading, key)

        problem_on_reject = legacy_grading.on_reject
        if problem_on_reject == 'first_error':
            self.config['on_reject'] = 'break'
        if problem_on_reject == 'grade':
            self.config['on_reject'] = 'continue'

        if self._problem.getMetadata().is_pass_fail():
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
                    self._items.append(TestCaseGroup(problem, aspect_name, filename, self))
                else:
                    base, ext = os.path.splitext(filename)
                    if ext == '.ans' and os.path.isfile(f'{base}.in'):
                        self._items.append(TestCase(problem, aspect_name, base, self))

        if not parent:
            self.set_symlinks()

    def __str__(self) -> str:
        return f'testcase group {self.name}'

    def set_symlinks(self) -> None:
        for sub in self._items:
            sub.set_symlinks()

    def matches_filter(self, filter_re: Pattern[str]) -> bool:
        return True

    def get_all_testcases(self) -> list:
        res: list = []
        for child in self._items:
            res += child.get_all_testcases()
        return res

    def get_testcases(self) -> list[TestCase]:
        return [child for child in self._items if isinstance(child, TestCase)]

    def get_subgroups(self) -> list[TestCaseGroup]:
        return [child for child in self._items if isinstance(child, TestCaseGroup)]

    def get_subgroup(self, name: str) -> TestCaseGroup | None:
        return next(
            (child for child in self._items if isinstance(child, TestCaseGroup) and os.path.basename(child._datadir) == name),
            None,
        )

    def has_custom_groups(self) -> bool:
        return any(group.get_subgroups() for group in self.get_subgroups())

    def get_score_range(self) -> tuple[float, float]:
        try:
            score_range = self.config['range']
            min_score, max_score = list(map(float, score_range.split()))
            return (min_score, max_score)
        except Exception:
            return (float('-inf'), float('inf'))

    def check(self, context: Context) -> bool:
        if self._check_res is not None:
            return self._check_res
        self._check_res = True

        if self.config['grading'] not in ['default', 'custom']:
            self.error('Invalid grading policy in testdata.yaml')

        if self.config['grading'] == 'custom' and len(self._problem.getProblemPart(Graders)._graders) == 0:
            self._problem.getProblemPart(Graders).fatal(f'{self} has custom grading but no custom graders provided')
        if self.config['grading'] == 'default' and Graders._default_grader is None:
            self._problem.getProblemPart(Graders).fatal(f'{self} has default grading but I could not find default grader')

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

        if not self._problem.getMetadata().is_scoring():
            for key in TestCaseGroup._SCORING_ONLY_KEYS:
                if self.config.get(key) is not None:
                    self.error(f"Key '{key}' is only applicable for scoring problems, this is a pass-fail problem")

        if self.config['on_reject'] not in ['break', 'continue']:
            self.error(f"Invalid value '{self.config['on_reject']}' for on_reject policy")

        if self._problem.getMetadata().is_scoring():
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
                if ord('0') <= ord(a[i]) <= ord('9') and ord('0') <= ord(b[i]) <= ord('9'):
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

    def run_submission(self, sub, runner: Runner, context: Context) -> TestCase.Result:
        self.info(f'Running on {self}')
        subres: list[SubmissionResult] = []
        subres_low: list[SubmissionResult] = []
        subres_high: list[SubmissionResult] = []
        active_low, active = True, True
        on_reject = self.config['on_reject']
        broken = False
        for child in self._items:
            if not child.matches_filter(context.data_filter):
                continue
            res, res_low, res_high = child.run_submission(sub, runner, context)
            subres_high.append(res_high)
            if active:
                subres.append(res)
            if active_low:
                subres_low.append(res_low)
            if on_reject == 'break':
                active_low &= res_low.verdict == 'AC'
                active &= res.verdict == 'AC'
                if res_high.verdict != 'AC':
                    broken = True
                    break

        runner.mark_group_done(self, broken)

        return (
            self.aggregate_results(sub, subres),
            self.aggregate_results(sub, subres_low, shadow_result=True),
            self.aggregate_results(sub, subres_high, shadow_result=True),
        )

    def aggregate_results(self, sub, sub_results: list[SubmissionResult], shadow_result: bool = False) -> SubmissionResult:
        res = SubmissionResult('JE')

        for r in sub_results:
            if r.runtime > res.runtime:
                res.runtime = r.runtime
                res.runtime_testcase = r.runtime_testcase
            if r.ac_runtime > res.ac_runtime:
                res.ac_runtime = r.ac_runtime
                res.ac_runtime_testcase = r.ac_runtime_testcase
            res.sample_failures.extend(r.sample_failures)

        judge_error = next((r for r in sub_results if r.verdict == 'JE'), None)
        if judge_error:
            res.verdict = judge_error.verdict
            res.reason = judge_error.reason
            res.additional_info = judge_error.additional_info
            res.testcase = judge_error.testcase
        else:
            res.verdict, score = self._problem.getProblemPart(Graders).grade(sub_results, self, shadow_result)
            if sub_results:
                res.testcase = sub_results[-1].testcase
                res.additional_info = sub_results[-1].additional_info
            if self._problem.getMetadata().is_scoring():
                res.score = score
                min_score, max_score = self.get_score_range()
                if score is not None and not (min_score <= score <= max_score) and not self._seen_oob_scores:
                    # Don't warn twice on the same subgroup, since every submission is likely
                    # to have the same error.
                    self._seen_oob_scores = True
                    groupname = os.path.relpath(self._datadir, self._problem.probdir)
                    self.error(
                        f'submission {sub} got {res} on group {groupname}, which is outside of expected score range [{min_score}, {max_score}]'
                    )
        return res

    def all_datasets(self) -> list:
        res: list = []
        for child in self._items:
            res += child.all_datasets()
        return res


class ProblemStatement(ProblemPart):
    PART_NAME = 'statement'

    def setup(self):
        self.debug('  Loading problem statement')
        try:
            self.statements = statement_util.find_statements(Path(self.problem.probdir), self.problem.format)
        except OSError as e:
            self.error(f'Failed locating problem statements: {e}')
            self.statements = {}

    def check(self, context: Context) -> bool:
        if self._check_res is not None:
            return self._check_res
        self._check_res = True

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

        for lang, files in self.statements.items():
            if len(files) > 1:
                self.error(f'Found multiple statements in the same language {lang}: {", ".join((file.name for file in files))}')

            if lang not in self.problem.getMetadata().name:
                self.error(f'No problem name given in language {lang}')
            elif not self.problem.getMetadata().name[lang]:
                self.error(f'Problem name in language {lang} is empty')
            elif not self.problem.getMetadata().name[lang].strip():
                self.error(f'Problem name in language {lang} contains only whitespace')

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
            self.problem.setMetadata(self._metadata)
        except ValidationError as e:
            # This should likely be a fatal error, but I'm not sure there's a clean way to fail from setup
            error_str = '\n'.join([f'    {"->".join((str(loc) for loc in err["loc"]))}: {err["msg"]}' for err in e.errors()])
            self.fatal(f'Failed parsing problem.yaml. Found {len(e.errors())} errors:\n{error_str}')
        except Exception as e:
            # This should likely be a fatal error, but I'm not sure there's a clean way to fail from setup
            self.fatal(f'Failed loading problem configuration: {e}')
        return {}

    def __str__(self) -> str:
        return 'problem configuration'

    def check(self, context: Context) -> bool:
        if self._check_res is not None:
            return self._check_res
        self._check_res = True

        # Check rights_owner
        if self._metadata.license == metadata.License.PUBLIC_DOMAIN:
            if self._metadata.rights_owner:
                self.error('Can not have a rights_owner for a problem in public domain')
        elif self._metadata.license != metadata.License.UNKNOWN:
            if not self._metadata.rights_owner and not self._metadata.source and not self._metadata.credits.authors:
                self.error('No author, source or rights_owner provided')

        # Check license
        if self._metadata.license == metadata.License.UNKNOWN:
            self.warning("License is 'unknown'")

        if self._metadata.uuid is None:
            self.error_in_2023_07(f'Missing uuid from problem.yaml. Add "uuid: {uuid.uuid4()}" to problem.yaml.')

        if self._metadata.legacy_grading.show_test_data_groups and self._metadata.is_pass_fail():
            self.error('Showing test data groups is only supported for scoring problems, this is a pass-fail problem')
        if (
            not self._metadata.is_pass_fail()
            and self.problem.get(ProblemTestCases)['root_group'].has_custom_groups()
            and 'show_test_data_groups' not in self._origdata.get('grading', {})
            and self.problem.format is FormatVersion.LEGACY
        ):
            self.warning(
                'Problem has custom testcase groups, but does not specify a value for grading.show_test_data_groups; defaulting to false'
            )

        if self._metadata.legacy_grading.on_reject is not None:
            if self._metadata.is_pass_fail() and self._metadata.legacy_grading.on_reject == 'grade':
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
                'Time limit configured to non-integer value. Problemtools does not yet support non-integer time limits, and will truncate'
            )

        return self._check_res


class ProblemTestCases(ProblemPart):
    PART_NAME = 'testdata'

    @staticmethod
    def setup_dependencies():
        return {ProblemConfig}  # We need this as the TestCaseGroup constructor reads config

    def setup(self):
        self.testcase_by_infile = {}
        return {
            'root_group': TestCaseGroup(self.problem, self.PART_NAME),
        }

    def check(self, context: Context) -> bool:
        return self.problem.get(ProblemTestCases)['root_group'].check(context)


class Attachments(ProblemPart):
    """Represents the attachments of a problem.

    Attributes:
        attachments: The absolute paths to the attachment files for this problem.

    """

    PART_NAME = 'attachments'

    def setup(self):
        attachments_path = os.path.join(self.problem.probdir, 'attachments')
        self.attachments: list[str] = []
        if os.path.isdir(attachments_path):
            self.attachments = [
                os.path.join(attachments_path, attachment_name) for attachment_name in os.listdir(attachments_path)
            ]

        self.debug(f'Adding attachments {str(self.attachments)}')

        return {}

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


_JUNK_CASES = [
    ('an empty file', b''),
    ('a binary file with random bytes', bytearray(random.Random(0).randbytes(1024))),
    ('a text file with the ASCII characters 32 up to 127', bytearray(x for x in range(32, 127))),
    (
        'a random text file with printable ASCII characters',
        bytearray(random.choice(string.printable.encode('utf8')) for _ in range(200)),
    ),
]


def _build_junk_modifier(
    desc: str, pattern: str, repl: str | Callable[[Match[str]], str]
) -> tuple[str, Callable, Callable[[str], str]]:
    p = re.compile(pattern)
    return (desc, p.search, lambda text: p.sub(repl, text))


_JUNK_MODIFICATIONS = [
    _build_junk_modifier(
        'spaces added where there already is whitespace', r'\s', lambda m: m.group(0) + ' ' * random.randint(1, 5)
    ),
    _build_junk_modifier('newlines added where there already are newlines', '\n', lambda m: '\n' * random.randint(2, 5)),
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

            collect_flags(self.problem.get(ProblemTestCases)['root_group'], all_flags)

            fd, file_name = tempfile.mkstemp()
            os.close(fd)
            for desc, case in _JUNK_CASES:
                f = open(file_name, 'wb')
                f.write(case)
                f.close()
                for flags_str in all_flags:
                    flags = flags_str.split()
                    for val in self._validators:
                        status, _ = val.run(file_name, args=flags)
                        if os.WEXITSTATUS(status) != 42:
                            break
                    else:
                        self.warning(f'No validator rejects {desc} with flags "{" ".join(flags)}"')

            def modified_input_validates(applicable, modifier):
                for testcase in self.problem.get(ProblemTestCases)['root_group'].get_all_testcases():
                    with open(testcase.infile) as infile:
                        infile_data = infile.read()
                    if not applicable(infile_data):
                        continue

                    with open(file_name, 'wb') as f:
                        f.write(modifier(infile_data).encode('utf8'))

                    for flags_str in all_flags:
                        flags = flags_str.split()
                        for val in self._validators:
                            status, _ = val.run(file_name, args=flags)
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
                status, _ = val.run(testcase.infile, outfile.name, errfile.name, args=flags)
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
        self._graders: list = run.find_programs(
            os.path.join(self.problem.probdir, 'graders'),
            language_config=self.problem.language_config,
            work_dir=self.problem.tmpdir,
        )
        return {}

    def __str__(self) -> str:
        return 'graders'

    def check(self, context: Context) -> bool:
        if self._check_res is not None:
            return self._check_res
        self._check_res = True

        if self.problem.getMetadata().is_pass_fail() and len(self._graders) > 0:
            self.error('There are grader programs but the problem is pass-fail')

        for grader in self._graders:
            success, msg = grader.compile()
            if not success:
                self.fatal(f'Compile error for {grader}', msg)
        return self._check_res

    def grade(
        self, sub_results: list[SubmissionResult], testcasegroup: TestCaseGroup, shadow_result: bool = False
    ) -> tuple[Verdict, float | None]:
        if testcasegroup.config['grading'] == 'default':
            graders = [self._default_grader]
        else:
            graders = self._graders

        grader_input = ''.join([f'{r.verdict} {0 if r.score is None else r.score}\n' for r in sub_results])
        grader_output_re = r'^((AC)|(WA)|(TLE)|(RTE)|(JE))\s+-?[0-9.]+\s*$'
        verdict: Verdict = 'AC'
        score: float = 0

        if not sub_results:
            self.info('No results on %s, so no graders ran' % (testcasegroup,))
            return (verdict, score)

        grader_flags = testcasegroup.config['grader_flags'].split()
        self.debug(f'Grading {len(sub_results)} results:\n{grader_input}')
        self.debug(f'Grader flags: {grader_flags}')

        for grader in graders:
            if grader is not None and grader.compile()[0]:
                fd, infile = tempfile.mkstemp()
                os.close(fd)
                fd, outfile = tempfile.mkstemp()
                os.close(fd)

                open(infile, 'w').write(grader_input)

                status, runtime = grader.run(infile, outfile, args=grader_flags)

                grader_output = open(outfile, 'r').read()
                os.remove(infile)
                os.remove(outfile)
                if not os.WIFEXITED(status):
                    self.error(f'Judge error: {grader} crashed')
                    self.debug(f'Grader input:\n{grader_input}')
                    return ('JE', None)
                ret = os.WEXITSTATUS(status)
                if ret != 0:
                    self.error(f'Judge error: exit code {ret} for grader {grader}, expected 0')
                    self.debug(f'Grader input: {grader_input}\n')
                    return ('JE', None)

                if not re.match(grader_output_re, grader_output):
                    self.error('Judge error: invalid format of grader output')
                    self.debug(f'Output must match: "{grader_output_re}"')
                    self.debug(f'Output was: "{grader_output}"')
                    return ('JE', None)

                verdict_str, score_str = grader_output.split()
                verdict = verdict_str  # type: ignore
                score = float(score_str)
        # TODO: check that all graders give same result

        if not shadow_result:
            self.debug(f'Grade on {testcasegroup} is {verdict} ({score})')

        return (verdict, score)


class OutputValidators(ProblemPart):
    _default_validator = run.get_tool('default_validator')

    PART_NAME = 'output_validator'

    def setup(self):
        if self.problem.format is FormatVersion.LEGACY and (Path(self.problem.probdir) / 'output_validators').exists():
            self.error('output_validators is not supported after Legacy; please use output_validator instead')

        self._validators = run.find_programs(
            os.path.join(self.problem.probdir, self.problem.format.output_validator_directory),
            language_config=self.problem.language_config,
            work_dir=self.problem.tmpdir,
        )
        self._has_precompiled = False
        return {}

    def __str__(self) -> str:
        return 'output validators'

    def start_background_work(self, context: Context) -> None:
        if not self._has_precompiled:
            for val in self._actual_validators():
                context.submit_background_work(lambda v: v.compile(), val)
            self._has_precompiled = True

    def check(self, context: Context) -> bool:
        if self._check_res is not None:
            return self._check_res
        self._check_res = True

        recommended_output_validator_languages = {'c', 'cpp', 'python3'}

        for v in self._validators:
            if isinstance(v, run.SourceCode) and v.language.lang_id not in recommended_output_validator_languages:
                self.warning('output validator language %s is not recommended' % v.language.name)

        if self.problem.getMetadata().legacy_validation == 'default' and self._validators:
            self.error('There are validator programs but problem.yaml has validation = "default"')
        elif self.problem.getMetadata().legacy_validation.startswith('custom') and not self._validators:
            self.fatal('problem.yaml specifies custom validator but no validator programs found')

        if self.problem.getMetadata().legacy_validation == 'default' and self._default_validator is None:
            self.fatal('Unable to locate default validator')

        for val in self._validators[:]:
            try:
                success, msg = val.compile()
                if not success:
                    self.fatal(f'Compile error for output validator {val}', msg)
            except run.ProgramError as e:
                self.error(str(e))

        # Only sanity check output validators if they all actually compiled
        if self._check_res:
            flags = self.problem.getMetadata().legacy_validator_flags

            fd, file_name = tempfile.mkstemp()
            os.close(fd)
            for desc, case in _JUNK_CASES:
                f = open(file_name, 'wb')
                f.write(case)
                f.close()
                rejected = False
                for testcase in self.problem.get(ProblemTestCases)['root_group'].get_all_testcases():
                    result = self.validate(testcase, file_name)
                    if result.verdict != 'AC':
                        rejected = True
                    if result.verdict == 'JE':
                        self.error(f'{desc} as output, and output validator flags "{" ".join(flags)}" gave {result}')
                        break
                if not rejected:
                    self.warning(f'{desc} gets AC')
            os.unlink(file_name)

        return self._check_res

    @staticmethod
    def _get_feedback(feedback_dir: str) -> str | None:
        all_feedback = []
        for feedback_file in os.listdir(feedback_dir):
            feedback_path = os.path.join(feedback_dir, feedback_file)
            if os.path.getsize(feedback_path) == 0:
                continue
            all_feedback.append(f'=== {feedback_file}: ===')
            # Note: The file could contain non-unicode characters, "replace" to be on the safe side
            with open(feedback_path, 'r', errors='replace') as feedback:
                # Cap amount of feedback per file at some high-ish
                # size, so that a buggy validator spewing out lots of
                # data doesn't kill us.
                all_feedback.append(feedback.read(128 * 1024))
        if all_feedback:
            return '\n'.join(all_feedback)
        return None

    def _parse_validator_results(self, val, status: int, feedbackdir, testcase: TestCase) -> SubmissionResult:
        custom_score = self.problem.getMetadata().legacy_custom_score
        score = None
        # TODO: would be good to have some way of displaying the feedback for debugging uses
        score_file = os.path.join(feedbackdir, 'score.txt')
        if not custom_score and os.path.isfile(score_file):
            return SubmissionResult(
                'JE', reason='validator produced "score.txt" but problem does not have custom scoring activated'
            )

        if not os.WIFEXITED(status):
            return SubmissionResult(
                'JE',
                reason=f'output validator {val} crashed, status {status}',
                additional_info=OutputValidators._get_feedback(feedbackdir),
            )
        ret = os.WEXITSTATUS(status)
        if ret not in [42, 43]:
            return SubmissionResult(
                'JE',
                reason=f'output validator {val} exited with status {ret}',
                additional_info=OutputValidators._get_feedback(feedbackdir),
            )

        if ret == 43:
            return SubmissionResult('WA', additional_info=OutputValidators._get_feedback(feedbackdir))

        if custom_score:
            if os.path.isfile(score_file):
                try:
                    score_str = open(score_file).read()
                    score = float(score_str)
                except Exception as e:
                    return SubmissionResult('JE', reason=f'failed to parse validator score: {e}')
            else:
                return SubmissionResult('JE', reason='problem has custom scoring but validator did not produce "score.txt"')

        return SubmissionResult('AC', score=score)

    def _actual_validators(self) -> list:
        vals = self._validators
        if self.problem.getMetadata().legacy_validation == 'default' or (
            self.problem.format is FormatVersion.V_2023_07 and not vals
        ):
            vals = [self._default_validator]
        return [val for val in vals if val is not None]

    def validate_interactive(self, testcase: TestCase, submission, timelim: int, errorhandler: Submissions) -> SubmissionResult:
        # This may be called off-main thread.
        interactive_output_re = r'\d+ \d+\.\d+ \d+ \d+\.\d+ (validator|submission)'
        res = SubmissionResult('JE')
        interactive = run.get_tool('interactive')
        if interactive is None:
            errorhandler.error('Could not locate interactive runner')
            return res
        # file descriptor, wall time lim
        initargs = ['1', str(2 * timelim)]
        validator_args = [testcase.infile, testcase.ansfile, '<feedbackdir>']
        submission_args = submission.get_runcmd(memlim=self.problem.getMetadata().limits.memory)

        val_memlim = self.problem.getMetadata().limits.validation_memory
        for val in self._actual_validators():
            if val.compile()[0]:
                feedbackdir = tempfile.mkdtemp(prefix='feedback', dir=self.problem.tmpdir)
                validator_args[2] = feedbackdir + os.sep
                f = tempfile.NamedTemporaryFile(delete=False)
                interactive_out = f.name
                f.close()
                i_status, _ = interactive.run(
                    outfile=interactive_out,
                    args=initargs + val.get_runcmd(memlim=val_memlim) + validator_args + [';'] + submission_args,
                    work_dir=submission.path,
                )
                if is_RTE(i_status):
                    errorhandler.error(f'Interactive crashed, status {i_status}')
                else:
                    interactive_output = open(interactive_out).read()
                    errorhandler.debug(f'Interactive output: "{interactive_output}"')
                    if not re.match(interactive_output_re, interactive_output):
                        errorhandler.error(
                            f'Output from interactive does not follow expected format, got output "{interactive_output}"'
                        )
                    else:
                        val_status_str, _, sub_status_str, sub_runtime_str, first = interactive_output.split()
                        sub_status = int(sub_status_str)
                        sub_runtime = float(sub_runtime_str)
                        val_status = int(val_status_str)
                        val_JE = not os.WIFEXITED(val_status) or os.WEXITSTATUS(val_status) not in [42, 43]
                        val_WA = os.WIFEXITED(val_status) and os.WEXITSTATUS(val_status) == 43
                        if val_JE or (val_WA and first == 'validator'):
                            # If the validator crashed, or exited first with WA,
                            # always follow validator verdict, even if that early
                            # exit caused the submission to behave erratically and
                            # time out.
                            if sub_runtime > timelim:
                                sub_runtime = timelim
                            res = self._parse_validator_results(val, val_status, feedbackdir, testcase)
                        elif is_TLE(sub_status, True):
                            res = SubmissionResult('TLE')
                        elif is_RTE(sub_status):
                            res = SubmissionResult('RTE')
                        else:
                            res = self._parse_validator_results(val, val_status, feedbackdir, testcase)

                        res.runtime = sub_runtime
                        res.validator_first = first == 'validator'

                os.unlink(interactive_out)
                shutil.rmtree(feedbackdir)
                if res.verdict != 'AC':
                    return res
        # TODO: check that all output validators give same result
        return res

    def validate(self, testcase: TestCase, submission_output: str) -> SubmissionResult:
        res = SubmissionResult('JE')
        val_timelim = self.problem.getMetadata().limits.validation_time
        val_memlim = self.problem.getMetadata().limits.validation_memory
        flags = (
            self.problem.getMetadata().legacy_validator_flags.split()
            + testcase.testcasegroup.config['output_validator_flags'].split()
        )
        for val in self._actual_validators():
            if val.compile()[0]:
                feedbackdir = tempfile.mkdtemp(prefix='feedback', dir=self.problem.tmpdir)
                validator_output = tempfile.mkdtemp(prefix='checker_out', dir=self.problem.tmpdir)
                outfile = validator_output + '/out.txt'
                errfile = validator_output + '/err.txt'
                status, runtime = val.run(
                    submission_output,
                    args=[testcase.infile, testcase.ansfile, feedbackdir] + flags,
                    timelim=val_timelim,
                    memlim=val_memlim,
                    outfile=outfile,
                    errfile=errfile,
                )
                if self.log.isEnabledFor(logging.DEBUG):
                    try:
                        with open(outfile, mode='rt') as f:
                            output = f.read()
                        if output:
                            self.log.debug('Validator output:\n%s', output)
                        with open(errfile, mode='rt') as f:
                            error = f.read()
                        if error:
                            self.log.debug('Validator stderr:\n%s', error)
                    except IOError as e:
                        self.info('Failed to read validator output: %s', e)
                res = self._parse_validator_results(val, status, feedbackdir, testcase)
                shutil.rmtree(feedbackdir)
                shutil.rmtree(validator_output)
                if res.verdict != 'AC':
                    return res

        # TODO: check that all output validators give same result
        return res


class Runner:
    def __init__(self, problem: Problem, sub, context: Context, timelim: int, timelim_low: int, timelim_high: int) -> None:
        self._problem = problem
        self._sub = sub
        self._context = context
        self._multithreaded = context.executor is not None
        self._timelim = timelim
        self._timelim_low = timelim_low
        self._timelim_high = timelim_high
        self._cache: dict[TestCase, TestCase.Result] = {}
        if self._multithreaded:
            self._queues: dict[TestCase, queue.Queue[TestCase.Result]] = {}
            self._lock = threading.Lock()
            self._started_jobs: set[TestCase] = set()
            self._done_groups: set[TestCaseGroup] = set()
            self._remaining_jobs: list[TestCase] = []
            self._recompute_jobs()

    def __enter__(self) -> Runner:
        if self._multithreaded:
            for i in range(len(self._remaining_jobs)):
                self._context.submit_background_work(self._work)
        return self

    def __exit__(self, *exc) -> None:
        if self._multithreaded:
            with self._lock:
                self._remaining_jobs = []

    def run(self, testcase: TestCase) -> tuple[TestCase.Result, bool]:
        while testcase.reuse_result_from:
            testcase = testcase.reuse_result_from

        if testcase in self._cache:
            return (self._cache[testcase], True)

        if sys.stdout.isatty():
            msg = f'Running {self._sub} on {testcase}...'
            sys.stdout.write(msg)
            sys.stdout.flush()

        if self._multithreaded:
            result = self._queues[testcase].get()
        else:
            result = self._run_submission_real(testcase)

        if sys.stdout.isatty():
            sys.stdout.write('\b \b' * len(msg))

        self._cache[testcase] = result
        return (result, False)

    def mark_group_done(self, group: TestCaseGroup, broken: bool) -> None:
        if self._multithreaded:
            self._done_groups.add(group)
            if broken:
                # Since a group was broken out of, some test cases may no
                # longer be relevant to run. Recompute the work list.
                self._recompute_jobs()

    def _run_submission_real(self, item: TestCase) -> TestCase.Result:
        return item.run_submission_real(self._sub, self._context, self._timelim, self._timelim_low, self._timelim_high)

    def _work(self) -> None:
        item = self._next_job()
        if item:
            res = self._run_submission_real(item)
            self._queues[item].put(res)

    def _gather_testcases(self, item: TestCase | TestCaseGroup) -> list[TestCase]:
        if not item.matches_filter(self._context.data_filter):
            return []
        if isinstance(item, TestCase):
            if item.reuse_result_from:
                return self._gather_testcases(item.reuse_result_from)
            else:
                return [item]
        elif item not in self._done_groups:
            ret = []
            for child in item.get_testcases() + item.get_subgroups():
                ret.extend(self._gather_testcases(child))
            return ret
        else:
            return []

    def _next_job(self) -> TestCase | None:
        with self._lock:
            if self._remaining_jobs:
                job = self._remaining_jobs.pop()
                self._started_jobs.add(job)
                return job
            else:
                return None

    def _recompute_jobs(self) -> None:
        with self._lock:
            seen = set(self._started_jobs)
            self._remaining_jobs = []
            for testcase in self._gather_testcases(self._problem.get(ProblemTestCases)['root_group']):
                if testcase not in seen:
                    seen.add(testcase)
                    self._remaining_jobs.append(testcase)
                    if testcase not in self._queues:
                        self._queues[testcase] = queue.Queue(maxsize=1)
            self._remaining_jobs.reverse()


class Submissions(ProblemPart):
    _SUB_REGEXP = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.-]*[a-zA-Z0-9](\.c\+\+)?$')
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
                pattern=Submissions._SUB_REGEXP,
                work_dir=self.problem.tmpdir,
                include_dir=os.path.join(self.problem.probdir, 'include'),
            )
        return {}

    def __str__(self) -> str:
        return 'submissions'

    def check_submission(
        self, sub, context: Context, expected_verdict: Verdict, timelim: int, timelim_low: int, timelim_high: int
    ) -> SubmissionResult:
        desc = f'{expected_verdict} submission {sub}'
        partial = False
        if expected_verdict == 'PAC':
            # For partially accepted solutions, use the low timelim instead of the real one,
            # to make sure we have margin in both directions.
            expected_verdict = 'AC'
            partial = True
        else:
            timelim_low = timelim

        with Runner(self.problem, sub, context, timelim, timelim_low, timelim_high) as runner:
            result, result_low, result_high = self.problem.get(ProblemTestCases)['root_group'].run_submission(
                sub, runner, context
            )

        if result.verdict == 'AC' and expected_verdict == 'AC' and not partial and result.sample_failures:
            res = result.sample_failures[0]
            self.warning(f'{desc} got {res.verdict} on sample: {res}')

        if result_low.verdict != result_high.verdict or result_low.score != result_high.score:
            r1, r2 = (
                (result_low, result_high)
                if result_low.verdict == result_high.verdict
                else (result_low.verdict, result_high.verdict)
            )
            self.warning(
                f'{desc} sensitive to time limit: limit of {timelim_low} secs -> {r1}, limit of {timelim_high} secs -> {r2}'
            )

        if partial and self.fully_accepted(result):
            self.warning(f'{desc} got {result}')
        elif result.verdict == expected_verdict:
            self.msg(f'   {desc} OK: {result}')
            if expected_verdict == 'AC' and not partial and not self.fully_accepted(result) and self.full_score_finite():
                # For some heuristic problems, this is expected. Thus, only warn.
                self.warning(f'{desc} did not attain full score (consider moving it to partially_accepted)')
        elif result_high.verdict == expected_verdict and not (partial and self.fully_accepted(result_high)):
            self.msg(f'   {desc} OK with extra time: {result_high}')
        else:
            self.error(f'{desc} got {result}', result_high.additional_info)

        return result

    def full_score_finite(self) -> bool:
        min_score, max_score = self.problem.get(ProblemTestCases)['root_group'].get_score_range()
        if self.problem.getMetadata().legacy_grading.objective == 'min':
            return min_score != float('-inf')
        else:
            return max_score != float('inf')

    def fully_accepted(self, result: SubmissionResult) -> bool:
        min_score, max_score = self.problem.get(ProblemTestCases)['root_group'].get_score_range()
        best_score = min_score if self.problem.getMetadata().legacy_grading.objective == 'min' else max_score
        return result.verdict == 'AC' and (not self.problem.getMetadata().is_scoring() or result.score == best_score)

    def start_background_work(self, context: Context) -> None:
        # Send off an early background compile job for each submission and
        # validator, to avoid a bottleneck step at the start of each test run.
        self.problem.getProblemPart(OutputValidators).start_background_work(context)
        for acr in self._submissions:
            for sub in self._submissions[acr]:
                context.submit_background_work(lambda s: s.compile(), sub)

    def check(self, context: Context) -> bool:
        if self._check_res is not None:
            return self._check_res
        self._check_res = True

        limits = self.problem.getMetadata().limits
        time_multiplier = limits.time_multipliers.ac_to_time_limit
        safety_margin = limits.time_multipliers.time_limit_to_tle

        timelim_margin_lo = 300  # 5 minutes
        timelim_margin = 300
        timelim = 300

        if limits.time_limit is not None:
            timelim = timelim_margin = int(limits.time_limit)  # TODO: Support non-integer time limits
        if context.fixed_timelim is not None:
            timelim = context.fixed_timelim
            timelim_margin = int(round(timelim * safety_margin))

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

                    res = self.check_submission(sub, context, acr, timelim, timelim_margin_lo, timelim_margin)
                    runtimes.append(res.runtime)

            if acr == 'AC':
                if len(runtimes) > 0:
                    max_runtime = max(runtimes)
                    exact_timelim = max_runtime * time_multiplier
                    max_runtime_str = f'{max_runtime:.3f}'
                    timelim = max(1, int(0.5 + exact_timelim))
                    timelim_margin_lo = max(1, min(int(0.5 + exact_timelim / safety_margin), timelim - 1))
                    timelim_margin = max(timelim + 1, int(0.5 + exact_timelim * safety_margin))
                else:
                    max_runtime_str = None
                if context.fixed_timelim is not None and context.fixed_timelim != timelim:
                    self.msg(
                        f'   Solutions give timelim of {timelim} seconds, but will use provided fixed limit of {context.fixed_timelim} seconds instead'
                    )
                    timelim = context.fixed_timelim
                    timelim_margin = round(timelim * safety_margin)  # TODO: properly support 2023-07 time limit computation

                self.msg(
                    f'   Slowest AC runtime: {max_runtime_str}, setting timelim to {timelim} secs, safety margin to {timelim_margin} secs'
                )

        return self._check_res


PROBLEM_FORMATS: dict[FormatVersion, dict[str, list[Type[ProblemPart]]]] = {
    FormatVersion.LEGACY: {
        'config': [ProblemConfig],
        'statement': [ProblemStatement, Attachments],
        'validators': [InputValidators, OutputValidators],
        'graders': [Graders],
        'data': [ProblemTestCases],
        'submissions': [
            OutputValidators,
            Submissions,
        ],  # OutputValidators duplicated to fatal() early if we can't find a validator. We should find a cleaner solution
    },
    FormatVersion.V_2023_07: {  # TODO: Add all the parts
        'config': [ProblemConfig],
        'statement': [ProblemStatement, Attachments],
        'validators': [InputValidators, OutputValidators],
        'graders': [Graders],
        'data': [ProblemTestCases],
        'submissions': [
            OutputValidators,
            Submissions,
        ],  # OutputValidators duplicated to fatal() early if we can't find a validator. We should find a cleaner solution
    },
}

# parts tested in alphabetical order
PROBLEM_PARTS = [*sorted({part for format in PROBLEM_FORMATS.values() for part in format})]

_ProblemPartT = TypeVar('_ProblemPartT', bound=ProblemPart)


class Problem(ProblemAspect):
    """Represents a checkable problem"""

    """
    Needs a problem-format in the form of a parts-dictionary, where all classes that verify the
    problem are listed. These should all be a subclass of ProblemPart. The dictionary is in the form
    of category -> part-types. You could for example have 'validators' -> [InputValidators, OutputValidators].
    """

    def __init__(
        self, probdir: str, args: argparse.Namespace, parts: dict[str, list[type]] = PROBLEM_FORMATS[FormatVersion.LEGACY]
    ):
        self.part_mapping: dict[str, list[Type[ProblemPart]]] = parts
        self.aspects: set[type] = {v for s in parts.values() for v in s}
        self.probdir = os.path.realpath(probdir)
        self.shortname: str = os.path.basename(self.probdir)
        super().__init__(self.shortname, self)
        self.language_config = languages.load_language_config()
        self.format = get_format_version(Path(self.probdir))
        self._data: dict[str, dict] = {}
        self._metadata: metadata.Metadata | None = None
        self.debug(f'Problem-format: {parts}')
        self._args = args
        self.loaded = False

    def get(self, part) -> dict:
        if isinstance(part, type) and issubclass(part, ProblemPart):
            part = part.PART_NAME
        assert part in self._data
        return self._data[part]

    def getMetadata(self) -> metadata.Metadata:
        assert self._metadata is not None, 'Attempted to access Config before it was set'
        return self._metadata

    def setMetadata(self, metadata: metadata.Metadata) -> None:
        assert self._metadata is None, 'Attempted to set Config twice'
        self._metadata = metadata

    def getProblemPart(self, part: Type[_ProblemPartT]) -> _ProblemPartT:
        return self._classes[part.PART_NAME]  # type: ignore

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

        # Initialize the classes, making sure to resolve dependencies first
        initialized = set()
        self._classes: dict[str, ProblemPart] = {}

        def init(_class):
            if _class.PART_NAME in initialized:
                return

            # A bit ugly but want to allow for subclasses
            for dependency in _class.setup_dependencies():
                cnt = 0
                for cl in self.aspects:
                    if issubclass(cl, dependency):
                        init(cl)
                        cnt += 1
                if cnt != 1:
                    raise NotImplementedError(
                        f'Part "{_class.PART_NAME}" depends on part "{dependency.PART_NAME}" which showed up {cnt} times in problem-format (should have showed up exactly once)'
                    )
            self.debug(f'Initializing {_class.PART_NAME} ({_class})')
            assert _class.PART_NAME not in initialized
            self._classes[_class.PART_NAME] = _class(self)
            self._data[_class.PART_NAME] = self._classes[_class.PART_NAME].setup()
            initialized.add(_class.PART_NAME)

        for c in self.aspects:
            init(c)

    def __enter__(self) -> Problem:
        self.tmpdir = tempfile.mkdtemp(prefix=f'verify-{self.shortname}-')
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback) -> None:
        shutil.rmtree(self.tmpdir)

    def __str__(self) -> str:
        return str(self.shortname)

    def check(self) -> tuple[int, int]:
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

        executor = ThreadPoolExecutor(self._args.threads) if self._args.threads > 1 else None
        context = Context(self._args, executor)

        try:
            if not re.match('^[a-z0-9]+$', self.shortname):
                self.error(f"Invalid shortname '{self.shortname}' (must be [a-z0-9]+)")
            if self.format is FormatVersion.V_2023_07:
                self.warning(f'Support for version {self.format} is very incomplete. Verification may not work as expected.')

            self._check_symlinks()
            self._check_file_and_directory_names()

            run.limit.check_limit_capabilities(self)

            # Skip any parts that do not belong to the format
            parts = [part for part in self._args.parts if part in self.part_mapping]

            if executor:
                for part in parts:
                    for item in self.part_mapping[part]:
                        self._classes[item.PART_NAME].start_background_work(context)

            for part in parts:
                self.msg(f'Checking {part}')
                for item in self.part_mapping[part]:
                    self._classes[item.PART_NAME].check(context)
        except VerifyError:
            pass
        finally:
            # Wait for background work to finish before performing an rmtree on
            # the directory tree it uses.
            context.wait_for_background_work()

        return self.errors, self.warnings

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
        filename_regex = re.compile(r'^[a-z0-9][a-z0-9_.-]{0,253}[a-z0-9]$', re.I)
        directory_regex = re.compile(r'^[a-z0-9]([a-z0-9_-]{0,253}[a-z0-9])?$', re.I)
        for root, dirs, files in os.walk(self.probdir):
            # Path of the directory we're in, starting with problem shortname. Only used for nicer error messages.
            reldir = os.path.relpath(root, os.path.dirname(self.probdir))
            for file in files:
                if not filename_regex.match(file):
                    self.error(f"Invalid file name '{file}' in {reldir} (should match {filename_regex.pattern} ignoring case)")
            for directory in dirs:
                if not directory_regex.match(directory):
                    self.error_in_2023_07(
                        f"Invalid directory name '{directory}' in {reldir} (should match {directory_regex.pattern} ignoring case)"
                    )

    def bail_on_error(self) -> bool:
        return self._args.bail_on_error

    def consider_warnings_errors(self) -> bool:
        return self._args.werror

    def max_additional_info(self) -> int:
        return self._args.max_additional_info


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
    parser.add_argument(
        '-v',
        '--problem_format',
        default='automatic',
        choices=list(PROBLEM_FORMATS.keys()) + ['automatic'],
        help='which problem format should the package be interpreted as, or "automatic" if it should be figured out from problem.yaml',
    )


def argparser() -> argparse.ArgumentParser:
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
        type=int,
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

    argparser_basic_arguments(parser)

    parser.add_argument('problemdir', nargs='+')
    return parser


def initialize_logging(args: argparse.Namespace) -> None:
    fmt = '%(log_color)s%(levelname)s %(message)s'
    colorlog.basicConfig(stream=sys.stdout, format=fmt, level=getattr(logging, args.log_level.upper()))


def main() -> None:
    args = argparser().parse_args()

    initialize_logging(args)

    total_errors = 0
    try:
        for problemdir in args.problemdir:
            try:
                if args.problem_format == 'automatic':
                    formatversion = get_format_version(Path(problemdir))
                else:
                    formatversion = FormatVersion(args.problem_format)
            except Exception as e:
                total_errors += 1
                print(f'ERROR: problem version could not be decided for {os.path.basename(os.path.realpath(problemdir))}: {e}')
                continue

            print(f'Loading problem {os.path.basename(os.path.realpath(problemdir))} with format version {formatversion}')
            with Problem(problemdir, args, PROBLEM_FORMATS[formatversion]) as prob:
                errors, warnings = prob.check()

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
