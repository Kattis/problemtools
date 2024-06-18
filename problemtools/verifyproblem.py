#! /usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

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

import argparse
import shlex

import yaml

from . import problem2pdf
from . import problem2html

from . import config
from . import languages
from . import run

from typing import Any, Callable, Literal, Pattern, Match, ParamSpec, TypeVar

log = logging.getLogger(__name__)

Verdict = Literal['AC', 'TLE', 'OLE', 'MLE', 'RTE', 'WA', 'PAC', 'JE']

def is_TLE(status: int, may_signal_with_usr1: bool=False) -> bool:
    return (os.WIFSIGNALED(status) and
            (os.WTERMSIG(status) == signal.SIGXCPU or
             (may_signal_with_usr1 and os.WTERMSIG(status) == signal.SIGUSR1)))


def is_RTE(status: int) -> bool:
    return not os.WIFEXITED(status) or bool(os.WEXITSTATUS(status))

class SubmissionResult:
    def __init__(self, verdict: str, score: float|None=None, reason: str|None=None, additional_info: str|None=None):
        self.verdict = verdict
        self.score = score
        self.reason = reason
        self.additional_info = additional_info
        self.testcase: TestCase|None = None
        self.runtime_testcase: TestCase|None = None
        self.runtime = -1.0
        self.ac_runtime = -1.0
        self.ac_runtime_testcase: TestCase|None = None
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


_T = TypeVar("_T")
_P = ParamSpec("_P")

class Context:
    def __init__(self, args: argparse.Namespace, executor: ThreadPoolExecutor|None) -> None:
        self.data_filter: Pattern[str] = args.data_filter
        self.submission_filter: Pattern[str] = args.submission_filter
        self.fixed_timelim: int|None = args.fixed_timelim
        self.compile_generators: bool = ('compile_generators' not in args or args.compile_generators)
        self.executor = executor
        self._background_work: list[concurrent.futures.Future[object]] = []

    def submit_background_work(self, job: Callable[_P, _T], *args: _P.args, **kwargs: _P.kwargs) -> None:
        assert self.executor
        self._background_work.append(self.executor.submit(job, *args, **kwargs))

    def wait_for_background_work(self) -> None:
        concurrent.futures.wait(self._background_work)


class ProblemAspect:
    max_additional_info = 15
    errors = 0
    warnings = 0
    bail_on_error = False
    _check_res: bool|None = None
    consider_warnings_errors = False
    basename_regex = re.compile('^[a-zA-Z0-9][a-zA-Z0-9_.-]*[a-zA-Z0-9]$')
    name: str

    @staticmethod
    def __append_additional_info(msg: str, additional_info: str|None) -> str:
        if additional_info is None or ProblemAspect.max_additional_info <= 0:
            return msg
        additional_info = additional_info.rstrip()
        if not additional_info:
            return msg
        lines = additional_info.split('\n')
        if len(lines) == 1:
            return f'{msg} ({lines[0]})'
        if len(lines) > ProblemAspect.max_additional_info:
            lines = lines[:ProblemAspect.max_additional_info] \
                + [f'[.....truncated to {ProblemAspect.max_additional_info} lines.....]']

        return f'{msg}:\n' + '\n'.join(' '*8 + line for line in lines)

    def __init__(self, name: str) -> None:
        self.log = log.getChild(name)

    def error(self, msg: str, additional_info: str|None=None, *args) -> None:
        self._check_res = False
        ProblemAspect.errors += 1
        self.log.error(ProblemAspect.__append_additional_info(msg, additional_info), *args)
        if ProblemAspect.bail_on_error:
            raise VerifyError(msg)

    def warning(self, msg: str, additional_info: str|None=None, *args) -> None:
        if ProblemAspect.consider_warnings_errors:
            self.error(msg, additional_info, *args)
            return
        ProblemAspect.warnings += 1
        self.log.warning(ProblemAspect.__append_additional_info(msg, additional_info), *args)

    def info(self, msg: str, *args) -> None:
        self.log.info(msg, *args)

    def debug(self, msg: str, *args) -> None:
        self.log.debug(msg, *args)

    def msg(self, msg):
        # TODO Should this be silent?
        print(msg)

    def check_basename(self, path: str) -> None:
        basename = os.path.basename(path)
        if not self.basename_regex.match(basename):
            self.error(f"Invalid name '{basename}' (should match '{self.basename_regex.pattern}')")

    def start_background_work(self, context: Context) -> None:
        pass

class TestCase(ProblemAspect):
    Result = tuple[SubmissionResult, SubmissionResult, SubmissionResult]

    def __init__(self, problem: Problem, base: str, testcasegroup: TestCaseGroup) -> None:
        super().__init__(f"{problem.shortname}.test.{testcasegroup.name}.{os.path.basename(base)}")
        self._base = base
        self.infile = f'{base}.in'
        self.ansfile = f'{base}.ans'
        self._problem = problem
        self.testcasegroup = testcasegroup
        self.reuse_result_from: TestCase|None = None
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
            self.warning(f'The file {filename} ({filesize:.1f} Mb) is larger than 100 Mb. This may cause performance issues and is not recommended.')

    def strip_path_prefix(self, path: str) -> str:
        return os.path.relpath(path, os.path.join(self._problem.probdir, 'data'))

    def is_in_sample_group(self) -> bool:
        return self.strip_path_prefix(self.infile).startswith('sample')

    def check(self, context: Context) -> bool:
        if self._check_res is not None:
            return self._check_res
        self._check_res = True
        self.check_basename(self.infile)
        self.check_basename(self.ansfile)
        self.check_newlines(self.infile)
        self.check_newlines(self.ansfile)
        self.check_size_limits(self.infile)
        self.check_size_limits(self.ansfile)
        self._problem.input_validators.validate(self)
        anssize = os.path.getsize(self.ansfile) / 1024.0 / 1024.0
        outputlim = self._problem.config.get('limits')['output']
        if anssize > outputlim:
            self.error(f'Answer file ({anssize:.1f} Mb) is larger than output limit ({outputlim} Mb), you need to increase output limit')
        elif 2 * anssize > outputlim:
            self.warning(f'Answer file ({anssize:.1f} Mb) is within 50% of output limit ({outputlim} Mb), you might want to increase output limit')
        if not self._problem.is_interactive:
            val_res = self._problem.output_validators.validate(self, self.ansfile)
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
        if target in self._problem.testcase_by_infile:
            self.reuse_result_from = self._problem.testcase_by_infile[target]

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
        if self.testcasegroup.config['output_validator_flags'] != self.reuse_result_from.testcasegroup.config['output_validator_flags']:
            self.error(f"Symbolic link '{nicepath}' points to testcase with different output validator flags")
            return False
        return True

    def run_submission(self, sub, runner: Runner, context: Context) -> Result:
        (res, res_low, res_high), reused = runner.run(self)
        res = self._init_result_for_testcase(res)
        res_low = self._init_result_for_testcase(res_low)
        res_high = self._init_result_for_testcase(res_high)
        msg = "Reused test file result" if reused else "Test file result"
        self.info(f'{msg}: {res}')
        if res.verdict != 'AC' and self.is_in_sample_group():
            res.sample_failures.append(res)

        return (res, res_low, res_high)

    def run_submission_real(self, sub, context: Context, timelim: int, timelim_low: int, timelim_high: int) -> Result:
        # This may be called off-main thread.
        if self._problem.is_interactive:
            res_high = self._problem.output_validators.validate_interactive(self, sub, timelim_high, self._problem.submissions)
        else:
            outfile = os.path.join(self._problem.tmpdir, f'output-{self.counter}')
            errfile = os.path.join(self._problem.tmpdir, f'error-{self.counter}')
            status, runtime = sub.run(infile=self.infile, outfile=outfile, errfile=errfile,
                                      timelim=timelim_high+1,
                                      memlim=self._problem.config.get('limits')['memory'], set_work_dir=True)
            if is_TLE(status) or runtime > timelim_high:
                res_high = SubmissionResult('TLE')
            elif is_RTE(status):
                try:
                    with open(errfile, mode="rt") as f:
                        info = f.read()
                except IOError:
                    self.info("Failed to read error file %s", errfile)
                    info = None
                res_high = SubmissionResult('RTE', additional_info=info)
            else:
                res_high = self._problem.output_validators.validate(self, outfile)
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
    _DEFAULT_CONFIG = config.load_config('testdata.yaml')
    _SCORING_ONLY_KEYS = ['accept_score', 'reject_score', 'range']

    def __init__(self, problem: Problem, datadir: str, parent: TestCaseGroup|None=None):
        self._parent = parent
        self._problem = problem
        self._datadir = datadir
        self.name = os.path.relpath(os.path.abspath(self._datadir),
                                    os.path.abspath(self._problem.probdir)).replace("/", ".")

        super().__init__(f"{problem.shortname}.test.{self.name}")

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
                if not field in self.config:
                    self.config[field] = parent_value

        # Some deprecated properties are inherited from problem config during a transition period
        problem_grading = problem.config.get('grading')
        for key in ['accept_score', 'reject_score', 'range']:
            if key in problem.config.get('grading'):
                self.config[key] = problem_grading[key]

        problem_on_reject = problem_grading.get('on_reject')
        if problem_on_reject == 'first_error':
            self.config['on_reject'] = 'break'
        if problem_on_reject == 'grade':
            self.config['on_reject'] = 'continue'

        if self._problem.config.get('type') == 'pass-fail':
            for key in TestCaseGroup._SCORING_ONLY_KEYS:
                if key not in self.config:
                    self.config[key] = None

        for field, default in TestCaseGroup._DEFAULT_CONFIG.items():
            if field not in self.config:
                self.config[field] = default

        self._items: list[TestCaseGroup|TestCase] = []
        if os.path.isdir(datadir):
            for filename in sorted(os.listdir(datadir)):
                filename = os.path.join(datadir, filename)
                if os.path.isdir(filename):
                    self._items.append(TestCaseGroup(problem, filename, self))
                else:
                    base, ext = os.path.splitext(filename)
                    if ext == '.ans' and os.path.isfile(f'{base}.in'):
                        self._items.append(TestCase(problem, base, self))

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


    def get_subgroup(self, name: str) -> TestCaseGroup|None:
        return next((child for child in self._items if isinstance(child, TestCaseGroup) and os.path.basename(child._datadir) == name), None)


    def has_custom_groups(self) -> bool:
        return any(group.get_subgroups() for group in self.get_subgroups())


    def get_score_range(self) -> tuple[float, float]:
        try:
            score_range = self.config['range']
            min_score, max_score = list(map(float, score_range.split()))
            return (min_score, max_score)
        except:
            return (float('-inf'), float('inf'))


    def check(self, context: Context) -> bool:
        if self._check_res is not None:
            return self._check_res
        self._check_res = True

        self.check_basename(self._datadir)

        if self.config['grading'] not in ['default', 'custom']:
            self.error("Invalid grading policy in testdata.yaml")

        if self.config['grading'] == 'custom' and len(self._problem.graders._graders) == 0:
            self._problem.graders.error(f'{self} has custom grading but no custom graders provided')
        if self.config['grading'] == 'default' and Graders._default_grader is None:
            self._problem.graders.error(f'{self} has default grading but I could not find default grader')

        if self.config['grading'] == 'default' and 'ignore_sample' in self.config['grader_flags'].split():
            if self._parent is not None:
                self.error("'grader_flags: ignore_sample' is specified, but that flag is only allowed at top level")
            elif self.config['on_reject'] == 'break':
                self.error("'grader_flags: ignore_sample' is specified, but 'on_reject: break' may cause secret data not to be judged")

        for field in self.config.keys():
            if field not in TestCaseGroup._DEFAULT_CONFIG.keys():
                self.warning(f"Unknown key '{field}' in '{os.path.join(self._datadir, 'testdata.yaml')}'")

        if not self._problem.is_scoring:
            for key in TestCaseGroup._SCORING_ONLY_KEYS:
                if self.config.get(key) is not None:
                    self.error(f"Key '{key}' is only applicable for scoring problems, this is a pass-fail problem")

        if self.config['on_reject'] not in ['break', 'continue']:
            self.error(f"Invalid value '{self.config['on_reject']}' for on_reject policy")

        if self._problem.is_scoring:
            # Check grading
            try:
                score_range = self.config['range']
                min_score, max_score = list(map(float, score_range.split()))
                if min_score > max_score:
                    self.error(f"Invalid score range '{score_range}': minimum score cannot be greater than maximum score")
            except VerifyError:
                raise
            except:
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
                        self.error("Test data at top level can only have the groups sample and secret")
                        self.debug(str(self._items))
            if not seen_secret:
                self.error("No secret data provided")
            if not seen_sample:
                self.warning("No sample data provided")

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
            if os.path.isdir(infile): continue
            if not f'{infile[:-3]}.ans' in ansfiles:
                self.error(f"No matching answer file for input '{infile}'")
        for ansfile in ansfiles:
            if os.path.isdir(ansfile): continue
            if not f'{ansfile[:-4]}.in' in infiles:
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
                    anum,i = parse_num(a, i)
                    bnum,j = parse_num(b, j)
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

        return (self.aggregate_results(sub, subres),
                self.aggregate_results(sub, subres_low, shadow_result=True),
                self.aggregate_results(sub, subres_high, shadow_result=True))


    def aggregate_results(self, sub, sub_results: list[SubmissionResult], shadow_result: bool=False) -> SubmissionResult:
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
            res.verdict, score = self._problem.graders.grade(sub_results, self, shadow_result)
            if sub_results:
                res.testcase = sub_results[-1].testcase
                res.additional_info = sub_results[-1].additional_info
            if self._problem.is_scoring:
                res.score = score
                min_score, max_score = self.get_score_range()
                if score is not None and not (min_score <= score <= max_score) and not self._seen_oob_scores:
                    # Don't warn twice on the same subgroup, since every submission is likely
                    # to have the same error.
                    self._seen_oob_scores = True
                    groupname = os.path.relpath(self._datadir, self._problem.probdir)
                    self.error(f'submission {sub} got {res} on group {groupname}, which is outside of expected score range [{min_score}, {max_score}]')
        return res


    def all_datasets(self) -> list:
        res: list = []
        for child in self._items:
            res += child.all_datasets()
        return res


class ProblemConfig(ProblemAspect):
    _MANDATORY_CONFIG = ['name']
    _OPTIONAL_CONFIG = config.load_config('problem.yaml')
    _VALID_LICENSES = ['unknown', 'public domain', 'cc0', 'cc by', 'cc by-sa', 'educational', 'permission']

    def __init__(self, problem: Problem):
        super().__init__(f"{problem.shortname}.config")
        self.debug('  Loading problem config')
        self._problem = problem
        self.configfile = os.path.join(problem.probdir, 'problem.yaml')
        self._data = {}

        if os.path.isfile(self.configfile):
            try:
                with open(self.configfile) as f:
                    self._data = yaml.safe_load(f)
                # Loading empty yaml yields None, for no apparent reason...
                if self._data is None:
                    self._data = {}
            except Exception as e:
                self.error(str(e))

        # Add config items from problem statement e.g. name
        self._data.update(problem.statement.get_config())

        # Populate rights_owner unless license is public domain
        if 'rights_owner' not in self._data and self._data.get('license') != 'public domain':
            if 'author' in self._data:
                self._data['rights_owner'] = self._data['author']
            elif 'source' in self._data:
                self._data['rights_owner'] = self._data['source']

        if 'license' in self._data:
            self._data['license'] = self._data['license'].lower()

        # Ugly backwards compatibility hack
        if 'name' in self._data and not isinstance(self._data['name'], dict):
            self._data['name'] = {'': self._data['name']}

        self._origdata = copy.deepcopy(self._data)

        for field, default in copy.deepcopy(ProblemConfig._OPTIONAL_CONFIG).items():
            if not field in self._data:
                self._data[field] = default
            elif isinstance(default, dict) and isinstance(self._data[field], dict):
                self._data[field] = dict(list(default.items()) + list(self._data[field].items()))

        val = self._data['validation'].split()
        self._data['validation-type'] = val[0]
        self._data['validation-params'] = val[1:]

        self._data['grading']['custom_scoring'] = False
        for param in self._data['validation-params']:
            if param == 'score':
                self._data['grading']['custom_scoring'] = True
            elif param == 'interactive':
                pass

        self._data['languages'] = self._data['languages'].split()

    def __str__(self) -> str:
        return 'problem configuration'

    def get(self, key: str|None=None) -> Any:
        if key:
            return self._data[key]
        return self._data

    def check(self, context: Context) -> bool:
        if self._check_res is not None:
            return self._check_res
        self._check_res = True

        if not os.path.isfile(self.configfile):
            self.error(f"No config file {self.configfile} found")

        for field in ProblemConfig._MANDATORY_CONFIG:
            if not field in self._data:
                self.error(f"Mandatory field '{field}' not provided")

        for field, value in self._origdata.items():
            if field not in ProblemConfig._OPTIONAL_CONFIG.keys() and field not in ProblemConfig._MANDATORY_CONFIG:
                self.warning(f"Unknown field '{field}' provided in problem.yaml")

        for field, value in self._data.items():
            if value is None:
                self.error(f"Field '{field}' provided in problem.yaml but is empty")
                self._data[field] = ProblemConfig._OPTIONAL_CONFIG.get(field, '')

        # Check type
        if not self._data['type'] in ['pass-fail', 'scoring']:
            self.error(f"Invalid value '{self._data['type']}' for type")

        # Check rights_owner
        if self._data['license'] == 'public domain':
            if self._data['rights_owner'].strip() != '':
                self.error('Can not have a rights_owner for a problem in public domain')
        elif self._data['license'] != 'unknown':
            if self._data['rights_owner'].strip() == '':
                self.error('No author, source or rights_owner provided')

        # Check source_url
        if (self._data['source_url'].strip() != '' and
            self._data['source'].strip() == ''):
            self.error('Can not provide source_url without also providing source')

        # Check license
        if not self._data['license'] in ProblemConfig._VALID_LICENSES:
            self.error(f"Invalid value for license: {self._data['license']}.\n  Valid licenses are {ProblemConfig._VALID_LICENSES}")
        elif self._data['license'] == 'unknown':
            self.warning("License is 'unknown'")

        if self._data['grading']['show_test_data_groups'] not in [True, False]:
            self.error(f"Invalid value for grading.show_test_data_groups: {self._data['grading']['show_test_data_groups']}")
        elif self._data['grading']['show_test_data_groups'] and self._data['type'] == 'pass-fail':
            self.error("Showing test data groups is only supported for scoring problems, this is a pass-fail problem")
        if self._data['type'] != 'pass-fail' and self._problem.testdata.has_custom_groups() and 'show_test_data_groups' not in self._origdata.get('grading', {}):
            self.warning("Problem has custom testcase groups, but does not specify a value for grading.show_test_data_groups; defaulting to false")

        if 'on_reject' in self._data['grading']:
            if self._data['type'] == 'pass-fail' and self._data['grading']['on_reject'] == 'grade':
                self.error(f"Invalid on_reject policy '{self._data['grading']['on_reject']}' for problem type '{self._data['type']}'")
            if not self._data['grading']['on_reject'] in ['first_error', 'worst_error', 'grade']:
                self.error(f"Invalid value '{self._data['grading']['on_reject']}' for on_reject policy")

        if self._data['grading']['objective'] not in ['min', 'max']:
            self.error(f"Invalid value '{self._data['grading']['objective']}' for objective")

        for deprecated_grading_key in ['accept_score', 'reject_score', 'range', 'on_reject']:
            if deprecated_grading_key in self._data['grading']:
                self.warning(f"Grading key '{deprecated_grading_key}' is deprecated in problem.yaml, use '{deprecated_grading_key}' in testdata.yaml instead")

        if not self._data['validation-type'] in ['default', 'custom']:
            self.error(f"Invalid value '{self._data['validation']}' for validation, first word must be 'default' or 'custom'")

        if self._data['validation-type'] == 'default' and len(self._data['validation-params']) > 0:
            self.error(f"Invalid value '{self._data['validation']}' for validation")

        if self._data['validation-type'] == 'custom':
            for param in self._data['validation-params']:
                if param not in['score', 'interactive']:
                    self.error(f"Invalid parameter '{param}' for custom validation")

        # Check limits
        if not isinstance(self._data['limits'], dict):
            self.error('Limits key in problem.yaml must specify a dict')
            self._data['limits'] = ProblemConfig._OPTIONAL_CONFIG['limits']

        if self._data['languages'] != '':
            for lang_id in self._data['languages']:
                if lang_id != 'all' and self._problem.language_config.get(lang_id) is None:
                    self.error("Unrecognized language id '%s'" % lang_id)

        # Some things not yet implemented
        if self._data['libraries'] != '':
            self.error("Libraries not yet supported")

        return self._check_res


class Generators(ProblemAspect):
    _TESTCASE_OPTIONS = ['input', 'solution', 'visualizer', 'random_salt']
    _NULLABLE_OPTIONS = ['input', 'solution', 'visualizer']
    _DATA_DIRECTORIES = {'sample', 'secret'}
    _VISUALIZER_EXTENSIONS = ['png', 'jpg', 'jpeg', 'svg', 'interaction', 'desc', 'hint']

    def __init__(self, problem: Problem):
        super().__init__(f"{problem.shortname}.generators")
        self.debug('  Loading generators')
        self._problem = problem
        self.configfile = os.path.join(problem.probdir, 'generators', 'generators.yaml')
        self._data = None
        self._generators: dict[str, str|list[str]|run.Program] = {}

        if os.path.isfile(self.configfile):
            try:
                with open(self.configfile) as f:
                    self._data = yaml.safe_load(f)
                # Loading empty yaml yields None, for no apparent reason...
                if self._data is None:
                    self._data = {}
            except Exception as e:
                self.error(str(e))

        if isinstance(self._data, dict):
            # The top-level dict always represents a directory, even if there
            # is no type key
            self._data['type'] = 'directory'

    def __str__(self) -> str:
        return 'generators'

    def _parse_command(self, key: str, state: dict) -> tuple[str, list[str]]|None:
        command = state[key]
        name = os.path.basename(state['path'])
        random_salt = str(state['random_salt'])

        def err() -> None:
            self.error('Invalid %s key for path %s in generators.yaml' % (key, state['path']))

        if not isinstance(command, str):
            err()
            return None

        seed = str(int(hashlib.sha512((random_salt + command).encode('utf-8')).hexdigest(), 16) % (2**31))

        parts = shlex.split(command)
        if not parts:
            err()
            return None

        for i, part in enumerate(parts):
            new = ''
            for j, group in enumerate(part.split('{')):
                if group.count('}') != (0 if j == 0 else 1):
                    err()
                    return None
                if j == 0:
                    new += group
                else:
                    group, rest = group.split('}')
                    if group.startswith('seed'):
                        new += seed
                    elif group == 'name':
                        new += name
                    else:
                        err()
                        return None
                    new += rest
            parts[i] = new

        program, arguments = parts[0], parts[1:]
        if program not in self._generators:
            self._generators[program] = program

        return (program, arguments)

    def _parse_testcase(self, data: dict, state: dict) -> None:
        if state['input'] is None:
            self.error('Path %s in generators.yaml must contain an input key' % state['path'])
        for key in ['input', 'solution', 'visualizer']:
            if state[key] is not None:
                state[key] = self._parse_command(key, state)

    def _parse_directory(self, data: dict, state: dict) -> None:
        # TODO: Process includes

        if 'testdata.yaml' in data:
            content = data['testdata.yaml']
            if content is None:
                content = {}

        cases = data.get('data', {})
        ordered = True
        if not isinstance(cases, list):
            ordered = False
            cases = [cases]

        case_counter = 0
        case_format = '%%0%dd' % len(str(len(cases)))
        for case in cases:
            if not isinstance(case, dict):
                self.error('Path %s/data in generators.yaml must contain a dict or a list of dicts' % state['path'])
                continue

            if ordered:
                case_counter += 1

            for name, value in sorted(case.items(), key=lambda kv: str(kv[0])):
                if ordered:
                    num = case_format % case_counter
                    name = num + ('' if name is None else '-' + str(name))
                else:
                    name = str(name)

                next_state = copy.deepcopy(state)
                next_state['path'] = '%s/%s' % (state['path'], name)
                self._parse_element(value, next_state)

    def _parse_element(self, data: dict, state: dict) -> None:
        if data is None:
            data = '/%s.in' % state['path']
            state['manual'] = True
        if isinstance(data, str):
            data = { 'input': data }
        if not isinstance(data, dict):
            self.error("Path %s in generators.yaml must specify a dict" % state['path'])
            return

        state.update({
            key: data[key]
            for key in Generators._TESTCASE_OPTIONS
            if key in data
        })

        if data.get('type', 'testcase') == 'testcase':
            self._parse_testcase(data, state)
        else:
            if data['type'] != 'directory':
                self.error("Type of %s in generators.yaml must be 'directory'" % state['path'])
            self._parse_directory(data, state)

    def _resolve_path(self, path: str) -> str:
        base_path = self._problem.probdir
        if path.startswith('/'):
            path = path[1:]
        else:
            base_path = os.path.join(base_path, 'generators')
        return os.path.join(*([base_path] + path.split('/')))

    def _compile_generators(self) -> None:
        for gen, files in list(self._generators.items()):
            implicit = True
            manual = False
            if isinstance(files, str):
                path = files
                files = []
                implicit = False
                if path.endswith('.in'):
                    manual = True
                    for ext in ['ans'] + Generators._VISUALIZER_EXTENSIONS:
                        other_path = path[:-2] + ext
                        if os.path.isfile(self._resolve_path(other_path)):
                            files.append(other_path)
                # Always add original file last, to ensure it is chosen as
                # the representative file
                files.append(path)
            if not isinstance(files, list) or not files:
                self.error('Invalid generator %s in generators.yaml' % gen)
                continue
            tmpdir = tempfile.mkdtemp(prefix='generator', dir=self._problem.tmpdir)
            ok = True
            for opath in files:
                if not isinstance(opath, str) or not opath:
                    self.error('Invalid generator %s in generators.yaml' % gen)
                    ok = False
                    break

                name = os.path.basename(opath)
                if implicit and opath == files[0]:
                    # In implicit generators, the first listed file should
                    # be the entry point. problemtools usually picks the
                    # lexicographically smallest filename as the entry
                    # point, unless there exists a file that starts with
                    # "main.". Thus the following renames the file that
                    # should be the entry point to "main.old.extension".
                    # TODO: Make problemtools support passing a different
                    # entry point than "main.", and remove this hack.
                    name = 'main' + os.path.splitext(name)[1]

                fpath = self._resolve_path(opath)
                dest = os.path.join(tmpdir, name)
                if os.path.exists(dest):
                    self.error('Duplicate entry for filename %s in generator %s' % (name, gen))
                    ok = False
                elif not os.path.exists(fpath):
                    self.error('Generator %s does not exist' % opath)
                    ok = False
                else:
                    try:
                        if os.path.isdir(fpath):
                            shutil.copytree(fpath, dest)
                        else:
                            shutil.copy2(fpath, dest)
                    except Exception as e:
                        self.error(str(e))
                        ok = False
            if ok:
                if manual:
                    self._generators[gen] = dest
                else:
                    prog = run.get_program(tmpdir if implicit else dest,
                                        language_config=self._problem.language_config,
                                        work_dir=self._problem.tmpdir)
                    if prog is None:
                        self.error('Could not load generator %s' % gen)
                        ok = False
                    else:
                        self._generators[gen] = prog
                        success, msg = prog.compile()
                        if not success:
                            self.error('Compile error for generator %s' % gen, msg)
                            ok = False
            if not ok and gen in self._generators:
                del self._generators[gen]

    def check(self, context: Context) -> bool:
        if self._check_res is not None:
            return self._check_res
        self._check_res = True

        if self._data is None:
            return self._check_res
        if not isinstance(self._data, dict):
            self.error('generators.yaml must specify a dict')
            return self._check_res

        self._generators = self._data.get('generators') or {}
        if not isinstance(self._generators, dict):
            self.error('Generators key in generators.yaml must specify a dict')
            self._generators = {}

        # Check the shape of the top-level data dict
        if isinstance(self._data.get('data'), list):
            self.error('Top-level data key in generators.yaml must specify a dict')
            self._data['data'] = {}

        if isinstance(self._data.get('data'), dict):
            invalid = []
            for key, value in self._data['data'].items():
                valid = False
                if key not in Generators._DATA_DIRECTORIES:
                    self.warning("Invalid key '%s' in generators.yaml, expected one of %s" % (key, Generators._DATA_DIRECTORIES))
                elif not isinstance(value, dict):
                    self.warning("Key '%s' in generators.yaml must specify a dict" % key)
                elif value.get('type') != 'directory':
                    self.warning("Type of %s in generators.yaml must be 'directory'" % key)
                else:
                    valid = True
                if not valid:
                    invalid.append(key)
            for key in invalid:
                del self._data['data'][key]

        # Run a depth-first search through generators.yaml and generate a
        # flattened list of testcases
        default_state: dict[str, str|bool|None] = { key: None for key in Generators._TESTCASE_OPTIONS }
        default_state.update({
            'path': 'data',
            'manual': False,
            'random_salt': '',
        })

        self._parse_element(self._data, default_state)

        if context.compile_generators:
            self._compile_generators()

        return self._check_res


class ProblemStatement(ProblemAspect):
    def __init__(self, problem: Problem):
        super().__init__(f"{problem.shortname}.statement")
        self.debug('  Loading problem statement')
        self._problem = problem
        self.languages = []
        glob_path = os.path.join(problem.probdir, 'problem_statement', 'problem.')
        if glob.glob(glob_path + 'tex'):
            self.languages.append('')
        for f in glob.glob(glob_path + '[a-z][a-z].tex'):
            m = re.search("problem.([a-z][a-z]).tex$", f)
            assert m
            self.languages.append(m.group(1))

    def check(self, context: Context) -> bool:
        if self._check_res is not None:
            return self._check_res
        self._check_res = True

        if not self.languages:
            self.error('No problem statements found (expected problem.tex or problem.[a-z][a-z].tex in problem_statement directory)')
        if '' in self.languages and 'en' in self.languages:
            self.error("Can't supply both problem.tex and problem.en.tex")

        for lang in self.languages:
            try:
                options = problem2pdf.get_parser().parse_args([""])
                options.problem = self._problem.probdir
                options.language = lang
                options.nopdf = True
                options.quiet = True
                if not problem2pdf.convert(options):
                    langparam = f' --language {lang}' if lang != '' else ''
                    self.error(f'Could not compile problem statement for language "{lang}".  Run problem2pdf{langparam} on the problem to diagnose.')
            except Exception as e:
                self.error(f'Error raised when checking problem statement for language {lang}:\n{e}\n{traceback.format_exc()}')
            try:
                options = problem2html.get_parser().parse_args([""])
                options.problem = self._problem.probdir
                options.destdir = os.path.join(self._problem.tmpdir, 'html')
                options.language = lang
                options.quiet = True
                problem2html.convert(options)
            except Exception as e:
                langparam = f' --language {lang}' if lang != '' else ''
                self.error(f'Could not convert problem statement to html for language "{lang}".  Run problem2html{langparam} on the problem to diagnose.\n{e}\n{traceback.format_exc()}')
        return self._check_res

    def __str__(self) -> str:
        return 'problem statement'

    def get_config(self) -> dict[str, dict[str, str]]:
        ret: dict[str, dict[str, str]] = {}
        for lang in self.languages:
            filename = f'problem.{lang}.tex' if lang != '' else 'problem.tex'
            stmt = open(os.path.join(self._problem.probdir, 'problem_statement', filename)).read()
            patterns = [
                (r'\\problemname{(.*)}', 'name'),
                (r'^%%\s*plainproblemname:(.*)$', 'name'),
            ]
            for tup in patterns:
                pattern = tup[0]
                dest = tup[1]
                hit = re.search(pattern, stmt, re.MULTILINE)
                if hit:
                    if not dest in ret:
                        ret[dest] = {}
                    ret[dest][lang] = hit.group(1).strip()
        return ret


class Attachments(ProblemAspect):
    """Represents the attachments of a problem.

    Attributes:
        attachments: The absolute paths to the attachment files for this problem.

    """

    def __init__(self, problem: Problem):
        super().__init__(f"{problem.shortname}.attachments")
        attachments_path = os.path.join(problem.probdir, 'attachments')
        self.attachments: list[str] = []
        if os.path.isdir(attachments_path):
            self.attachments = [os.path.join(attachments_path, attachment_name) for attachment_name in os.listdir(attachments_path)]

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


_JUNK_CASES = [
    ('an empty file', b''),
    ('a binary file with random bytes', bytearray(random.Random(0).randbytes(1024))),
    ('a text file with the ASCII characters 32 up to 127', bytearray(x for x in range(32, 127))),
    ('a random text file with printable ASCII characters', bytearray(random.choice(string.printable.encode('utf8')) for _ in range(200))),
]

def _build_junk_modifier(desc: str, pattern: str, repl: str|Callable[[Match[str]], str]) -> tuple[str, Callable, Callable[[str], str]]:
    p = re.compile(pattern)
    return (desc, p.search, lambda text: p.sub(repl, text))

_JUNK_MODIFICATIONS = [
    _build_junk_modifier('spaces added where there already is whitespace', r'\s', lambda m: m.group(0) + ' ' * random.randint(1, 5)),
    _build_junk_modifier('newlines added where there already are newlines', '\n', lambda m: '\n' * random.randint(2, 5)),
    _build_junk_modifier('leading zeros added to integers', r'(^|[^.]\b)([0-9]+)\b', r'\g<1>0000000000\g<2>'),
    _build_junk_modifier('trailing zeros added to real number decimal portion', r'\.[0-9]+\b', r'\g<0>0000000000'),
    ('random junk added to the end of the file', lambda f: True, lambda f: f + ''.join(random.choice(string.printable) for _ in range(200))),
]

class InputValidators(ProblemAspect):

    def __init__(self, problem: Problem):
        super().__init__(f"{problem.shortname}.input_validator")
        self._problem = problem
        input_validators_path = os.path.join(problem.probdir, 'input_format_validators')
        if os.path.isdir(input_validators_path):
            self._uses_old_path = True
        else:
            self._uses_old_path = False
            new_input_validators_path = os.path.join(problem.probdir, 'input_validators')
            if os.path.isdir(new_input_validators_path):
                input_validators_path = new_input_validators_path
        self._validators = run.find_programs(input_validators_path,
                                             language_config=problem.language_config,
                                             allow_validation_script=True,
                                             work_dir=problem.tmpdir)


    def __str__(self) -> str:
        return 'input format validators'


    def start_background_work(self, context: Context) -> None:
        for val in self._validators:
            context.submit_background_work(lambda v: v.compile(), val)


    def check(self, context: Context|None) -> bool:
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
            collect_flags(self._problem.testdata, all_flags)

            fd, file_name = tempfile.mkstemp()
            os.close(fd)
            for (desc, case) in _JUNK_CASES:
                f = open(file_name, "wb")
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
                for testcase in self._problem.testdata.get_all_testcases():
                    with open(testcase.infile) as infile:
                        infile_data = infile.read()
                    if not applicable(infile_data):
                        continue

                    with open(file_name, "wb") as f:
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

            for (desc, applicable, modifier) in _JUNK_MODIFICATIONS:
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
                validator_output = "\n".join(
                    out for out in [validator_stdout, validator_stderr] if out)
                testcase.error(emsg, validator_output)


class Graders(ProblemAspect):
    _default_grader = run.get_tool('default_grader')

    def __init__(self, problem: Problem):
        super().__init__(f"{problem.shortname}.grader")
        self._problem = problem
        self._graders: list = run.find_programs(os.path.join(problem.probdir, 'graders'),
                                          language_config=problem.language_config,
                                          work_dir=problem.tmpdir)

    def __str__(self) -> str:
        return 'graders'

    def check(self, context: Context) -> bool:
        if self._check_res is not None:
            return self._check_res
        self._check_res = True

        if self._problem.config.get('type') == 'pass-fail' and len(self._graders) > 0:
            self.error('There are grader programs but the problem is pass-fail')

        for grader in self._graders:
            success, msg = grader.compile()
            if not success:
                self.error(f'Compile error for {grader}', msg)
        return self._check_res

    def grade(self, sub_results: list[SubmissionResult], testcasegroup: TestCaseGroup, shadow_result: bool=False) -> tuple[Verdict, float|None]:

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

                status, runtime = grader.run(infile, outfile,
                                             args=grader_flags)

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


class OutputValidators(ProblemAspect):
    _default_validator = run.get_tool('default_validator')


    def __init__(self, problem: Problem):
        super().__init__(f"{problem.shortname}.output_validator")
        self._problem = problem
        self._validators = run.find_programs(os.path.join(problem.probdir,
                                                          'output_validators'),
                                             language_config=problem.language_config,
                                             work_dir=problem.tmpdir)
        self._has_precompiled = False


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

        if self._problem.config.get('validation') == 'default' and self._validators:
            self.error('There are validator programs but problem.yaml has validation = "default"')
        elif self._problem.config.get('validation') != 'default' and not self._validators:
            self.error('problem.yaml specifies custom validator but no validator programs found')

        if self._problem.config.get('validation') == 'default' and self._default_validator is None:
            self.error('Unable to locate default validator')

        for val in self._validators[:]:
            try:
                success, msg = val.compile()
                if not success:
                    self.error(f'Compile error for output validator {val}', msg)
            except run.ProgramError as e:
                self.error(str(e))

        # Only sanity check output validators if they all actually compiled
        if self._check_res:
            flags = self._problem.config.get('validator_flags')

            fd, file_name = tempfile.mkstemp()
            os.close(fd)
            for (desc, case) in _JUNK_CASES:
                f = open(file_name, "wb")
                f.write(case)
                f.close()
                rejected = False
                for testcase in self._problem.testdata.get_all_testcases():
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
    def _get_feedback(feedback_dir: str) -> str|None:
        all_feedback = []
        for feedback_file in os.listdir(feedback_dir):
            feedback_path = os.path.join(feedback_dir, feedback_file)
            if os.path.getsize(feedback_path) == 0:
                continue
            all_feedback.append(f'=== {feedback_file}: ===')
            # Note: The file could contain non-unicode characters, "replace" to be on the safe side
            with open(feedback_path, 'r', errors="replace") as feedback:
                # Cap amount of feedback per file at some high-ish
                # size, so that a buggy validator spewing out lots of
                # data doesn't kill us.
                all_feedback.append(feedback.read(128*1024))
        if all_feedback:
            return '\n'.join(all_feedback)
        return None


    def _parse_validator_results(self, val, status: int, feedbackdir, testcase: TestCase) -> SubmissionResult:
        custom_score = self._problem.config.get('grading')['custom_scoring']
        score = None
        # TODO: would be good to have some way of displaying the feedback for debugging uses
        score_file = os.path.join(feedbackdir, 'score.txt')
        if not custom_score and os.path.isfile(score_file):
            return SubmissionResult('JE', reason='validator produced "score.txt" but problem does not have custom scoring activated')

        if not os.WIFEXITED(status):
            return SubmissionResult('JE',
                                    reason=f'output validator {val} crashed, status {status}',
                                    additional_info=OutputValidators._get_feedback(feedbackdir))
        ret = os.WEXITSTATUS(status)
        if ret not in [42, 43]:
            return SubmissionResult('JE',
                                    reason=f'output validator {val} exited with status {ret}',
                                    additional_info=OutputValidators._get_feedback(feedbackdir))

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
        if self._problem.config.get('validation') == 'default':
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
        submission_args = submission.get_runcmd(memlim=self._problem.config.get('limits')['memory'])

        val_timelim = self._problem.config.get('limits')['validation_time']
        val_memlim = self._problem.config.get('limits')['validation_memory']
        for val in self._actual_validators():
            if val.compile()[0]:
                feedbackdir = tempfile.mkdtemp(prefix='feedback', dir=self._problem.tmpdir)
                validator_args[2] = feedbackdir + os.sep
                f = tempfile.NamedTemporaryFile(delete=False)
                interactive_out = f.name
                f.close()
                i_status, _ = interactive.run(outfile=interactive_out,
                                              args=initargs + val.get_runcmd(memlim=val_memlim) + validator_args + [';'] + submission_args)
                if is_RTE(i_status):
                    errorhandler.error(f'Interactive crashed, status {i_status}')
                else:
                    interactive_output = open(interactive_out).read()
                    errorhandler.debug(f'Interactive output: "{interactive_output}"')
                    if not re.match(interactive_output_re, interactive_output):
                        errorhandler.error(f'Output from interactive does not follow expected format, got output "{interactive_output}"')
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
                        res.validator_first = (first == 'validator')

                os.unlink(interactive_out)
                shutil.rmtree(feedbackdir)
                if res.verdict != 'AC':
                    return res
        # TODO: check that all output validators give same result
        return res


    def validate(self, testcase: TestCase, submission_output: str) -> SubmissionResult:
        res = SubmissionResult('JE')
        val_timelim = self._problem.config.get('limits')['validation_time']
        val_memlim = self._problem.config.get('limits')['validation_memory']
        flags = self._problem.config.get('validator_flags').split() + testcase.testcasegroup.config['output_validator_flags'].split()
        for val in self._actual_validators():
            if val.compile()[0]:
                feedbackdir = tempfile.mkdtemp(prefix='feedback', dir=self._problem.tmpdir)
                validator_output = tempfile.mkdtemp(prefix='checker_out', dir=self._problem.tmpdir)
                outfile = validator_output + "/out.txt"
                errfile = validator_output + "/err.txt"
                status, runtime = val.run(submission_output,
                                          args=[testcase.infile, testcase.ansfile, feedbackdir] + flags,
                                          timelim=val_timelim, memlim=val_memlim,
                                          outfile=outfile, errfile=errfile)
                if self.log.isEnabledFor(logging.DEBUG):
                    try:
                        with open(outfile, mode="rt") as f:
                            output = f.read()
                        if output:
                            self.log.debug("Validator output:\n%s", output)
                        with open(errfile, mode="rt") as f:
                            error = f.read()
                        if error:
                            self.log.debug("Validator stderr:\n%s", error)
                    except IOError as e:
                        self.info("Failed to read validator output: %s", e)
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
        self._multithreaded = (context.executor is not None)
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

    def _gather_testcases(self, item: TestCase|TestCaseGroup) -> list[TestCase]:
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

    def _next_job(self) -> TestCase|None:
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
            for testcase in self._gather_testcases(self._problem.testdata):
                if testcase not in seen:
                    seen.add(testcase)
                    self._remaining_jobs.append(testcase)
                    if testcase not in self._queues:
                        self._queues[testcase] = queue.Queue(maxsize=1)
            self._remaining_jobs.reverse()


class Submissions(ProblemAspect):
    _SUB_REGEXP = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.-]*[a-zA-Z0-9](\.c\+\+)?$')
    # (verdict, directory, required)
    _VERDICTS: list[tuple[Verdict, str, bool]] = [
        ('AC', 'accepted', True),
        ('PAC', 'partially_accepted', False),
        ('WA', 'wrong_answer', False),
        ('RTE', 'run_time_error', False),
        ('TLE', 'time_limit_exceeded', False),
    ]

    def __init__(self, problem: Problem):
        super().__init__(f"{problem.shortname}.submission")
        self._submissions = {}
        self._problem = problem
        srcdir = os.path.join(problem.probdir, 'submissions')
        for verdict in Submissions._VERDICTS:
            acr = verdict[0]
            self._submissions[acr] = run.find_programs(os.path.join(srcdir, verdict[1]),
                                                       language_config=problem.language_config,
                                                       pattern=Submissions._SUB_REGEXP,
                                                       work_dir=problem.tmpdir,
                                                       include_dir=os.path.join(problem.probdir,
                                                                                    'include'))

    def __str__(self) -> str:
        return 'submissions'

    def check_submission(self, sub, context: Context, expected_verdict: Verdict, timelim: int, timelim_low: int, timelim_high: int) -> SubmissionResult:
        desc = f'{expected_verdict} submission {sub}'
        partial = False
        if expected_verdict == 'PAC':
            # For partially accepted solutions, use the low timelim instead of the real one,
            # to make sure we have margin in both directions.
            expected_verdict = 'AC'
            partial = True
        else:
            timelim_low = timelim

        with Runner(self._problem, sub, context, timelim, timelim_low, timelim_high) as runner:
            result, result_low, result_high = self._problem.testdata.run_submission(sub, runner, context)

        if result.verdict == 'AC' and expected_verdict == 'AC' and not partial and result.sample_failures:
            res = result.sample_failures[0]
            self.warning(f'{desc} got {res.verdict} on sample: {res}')

        if result_low.verdict != result_high.verdict or result_low.score != result_high.score:
            r1, r2 = (result_low, result_high) if result_low.verdict == result_high.verdict else (result_low.verdict, result_high.verdict)
            self.warning(f'{desc} sensitive to time limit: limit of {timelim_low} secs -> {r1}, limit of {timelim_high} secs -> {r2}')

        if partial and self.fully_accepted(result):
            self.warning(f'{desc} got {result}')
        elif result.verdict == expected_verdict:
            self.msg(f'   {desc} OK: {result}')
            if (expected_verdict == 'AC' and not partial
                    and not self.fully_accepted(result)
                    and self.full_score_finite()):
                # For some heuristic problems, this is expected. Thus, only warn.
                self.warning(f'{desc} did not attain full score (consider moving it to partially_accepted)')
        elif result_high.verdict == expected_verdict and not (partial and self.fully_accepted(result_high)):
            self.msg(f'   {desc} OK with extra time: {result_high}')
        else:
            self.error(f'{desc} got {result}', result_high.additional_info)

        return result

    def full_score_finite(self) -> bool:
        min_score, max_score = self._problem.testdata.get_score_range()
        if self._problem.config.get('grading')['objective'] == 'min':
            return min_score != float('-inf')
        else:
            return max_score != float('inf')

    def fully_accepted(self, result: SubmissionResult) -> bool:
        min_score, max_score = self._problem.testdata.get_score_range()
        best_score = min_score if self._problem.config.get('grading')['objective'] == 'min' else max_score
        return result.verdict == 'AC' and (not self._problem.is_scoring or result.score == best_score)

    def start_background_work(self, context: Context) -> None:
        # Send off an early background compile job for each submission and
        # validator, to avoid a bottleneck step at the start of each test run.
        self._problem.output_validators.start_background_work(context)
        for acr in self._submissions:
            for sub in self._submissions[acr]:
                context.submit_background_work(lambda s: s.compile(), sub)

    def check(self, context: Context) -> bool:
        if self._check_res is not None:
            return self._check_res
        self._check_res = True

        limits = self._problem.config.get('limits')
        time_multiplier = limits['time_multiplier']
        safety_margin = limits['time_safety_margin']

        timelim_margin_lo = 300  # 5 minutes
        timelim_margin = 300
        timelim = 300

        if 'time_for_AC_submissions' in limits:
            timelim = timelim_margin = limits['time_for_AC_submissions']
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

                    if sub.code_size() > 1024*limits['code']:
                        self.error(f'{acr} submission {sub} has size {sub.code_size() / 1024.0:.1f} kiB, exceeds code size limit of {limits["code"]} kiB')
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
                    timelim_margin = max(timelim + 1,
                                         int(0.5 + exact_timelim * safety_margin))
                else:
                    max_runtime_str = None
                if context.fixed_timelim is not None and context.fixed_timelim != timelim:
                    self.msg(f"   Solutions give timelim of {timelim} seconds, but will use provided fixed limit of {context.fixed_timelim} seconds instead")
                    timelim = context.fixed_timelim
                    timelim_margin = timelim * safety_margin

                self.msg(f"   Slowest AC runtime: {max_runtime_str}, setting timelim to {timelim} secs, safety margin to {timelim_margin} secs")
            limits['time'] = timelim

        return self._check_res

PROBLEM_PARTS = ['config', 'statement', 'validators', 'graders', 'generators', 'data', 'submissions']

class Problem(ProblemAspect):
    def __init__(self, probdir: str):
        self.probdir = os.path.realpath(probdir)
        self.shortname: str|None = os.path.basename(self.probdir)
        super().__init__(self.shortname)
        self.language_config = languages.load_language_config()

    def __enter__(self) -> Problem:
        self.tmpdir = tempfile.mkdtemp(prefix=f'verify-{self.shortname}-')
        if not os.path.isdir(self.probdir):
            self.error(f"Problem directory '{self.probdir}' not found")
            self.shortname = None
            return self

        self.statement = ProblemStatement(self)
        self.attachments = Attachments(self)
        self.config = ProblemConfig(self)
        available_languages = self.config.get('languages')
        if 'all' not in available_languages:
            language_config = languages.Languages()
            for lang_id in available_languages:
                lang_spec = self.language_config.get(lang_id)
                if lang_spec is not None:
                    language_config.update({lang_id: self.language_config.get(lang_id)})
            self.language_config = language_config

        self.is_interactive = 'interactive' in self.config.get('validation-params')
        self.is_scoring = (self.config.get('type') == 'scoring')
        self.input_validators = InputValidators(self)
        self.output_validators = OutputValidators(self)
        self.graders = Graders(self)
        self.testcase_by_infile: dict[str, TestCase] = {}
        self.testdata = TestCaseGroup(self, os.path.join(self.probdir, 'data'))
        self.submissions = Submissions(self)
        self.generators = Generators(self)
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback) -> None:
        shutil.rmtree(self.tmpdir)

    def __str__(self) -> str:
        return str(self.shortname)

    def check(self, args: argparse.Namespace) -> tuple[int, int]:
        if self.shortname is None:
            return 1, 0

        ProblemAspect.errors = 0
        ProblemAspect.warnings = 0
        ProblemAspect.bail_on_error = args.bail_on_error
        ProblemAspect.consider_warnings_errors = args.werror

        executor = ThreadPoolExecutor(args.threads) if args.threads > 1 else None
        context = Context(args, executor)

        try:
            part_mapping: dict[str, list] = {
                'config': [self.config],
                'statement': [self.statement, self.attachments],
                'validators': [self.input_validators, self.output_validators],
                'graders': [self.graders],
                'generators': [self.generators],
                'data': [self.testdata],
                'submissions': [self.submissions],
            }

            if not re.match('^[a-z0-9]+$', self.shortname):
                self.error(f"Invalid shortname '{self.shortname}' (must be [a-z0-9]+)")

            self._check_symlinks()

            run.limit.check_limit_capabilities(self)

            if executor:
                for part in args.parts:
                    for item in part_mapping[part]:
                        item.start_background_work(context)

            for part in args.parts:
                self.msg(f'Checking {part}')
                for item in part_mapping[part]:
                    item.check(context)
        except VerifyError:
            pass
        finally:
            # Wait for background work to finish before performing an rmtree on
            # the directory tree it uses.
            context.wait_for_background_work()
        return ProblemAspect.errors, ProblemAspect.warnings

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
                        self.error(
                            f"Symlink {relfile} links to {reltarget} which does not exist"
                        )
                    if os.path.commonpath([probdir, target]) != probdir:
                        self.error(
                            f"Symlink {relfile} links to {reltarget} which is outside of problem package"
                        )
                    if os.path.isabs(reltarget):
                        self.error(
                            f"Symlink {relfile} links to {reltarget} which is an absolute path. Symlinks must be relative."
                        )

def re_argument(s: str) -> Pattern[str]:
    try:
        r = re.compile(s)
        return r
    except re.error:
        raise argparse.ArgumentTypeError(f'{s} is not a valid regex')


def part_argument(s: str) -> str:
    if s not in PROBLEM_PARTS:
        raise argparse.ArgumentTypeError(f"Invalid problem part specified: {s}")
    return s


def argparser_basic_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('-b', '--bail_on_error',
                        action='store_true',
                        help='bail verification on first error')
    parser.add_argument('-l', '--log_level',
                        default='warning',
                        help='set log level (debug, info, warning, error, critical)')
    parser.add_argument('-e', '--werror',
                        action='store_true',
                        help='consider warnings as errors')
    parser.add_argument('--max_additional_info',
                        type=int, default=15,
                        help='maximum number of lines of additional info (e.g. compiler output or validator feedback) to display about an error (set to 0 to disable additional info)')


def argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Validate a problem package in the Kattis problem format.')
    parser.add_argument('-s', '--submission_filter', metavar='SUBMISSIONS',
                        type=re_argument, default=re.compile('.*'),
                        help='run only submissions whose name contains this regex.  The name includes category (accepted, wrong_answer, etc), e.g. "accepted/hello.java" (for a single file submission) or "wrong_answer/hello" (for a directory submission)')
    parser.add_argument('-d', '--data_filter', metavar='DATA',
                        type=re_argument, default=re.compile('.*'),
                        help='use only data files whose name contains this regex.  The name includes path relative to the data directory but not the extension, e.g. "sample/hello" for a sample data file')
    parser.add_argument('-t', '--fixed_timelim',
                        type=int,
                        help='use this fixed time limit (useful in combination with -d and/or -s when all AC submissions might not be run on all data)')
    parser.add_argument('-p', '--parts', metavar='PROBLEM_PART',
                        type=part_argument, nargs='+', default=PROBLEM_PARTS,
                        help=f'only test the indicated parts of the problem.  Each PROBLEM_PART can be one of {PROBLEM_PARTS}.')
    parser.add_argument('-j', '--threads', type=int, default=1,
                        help='run validation using multiple threads. This will make timings less reliable, but can be convenient during development')

    argparser_basic_arguments(parser)

    parser.add_argument('problemdir', nargs='+')
    return parser


def initialize_logging(args: argparse.Namespace) -> None:
    ProblemAspect.max_additional_info = args.max_additional_info

    # fmt = "%(levelname)s %(message)s"
    fmt = "%(message)s"
    logging.basicConfig(stream=sys.stdout,
                        format=fmt,
                        level=getattr(logging, args.log_level.upper()))


def main() -> None:
    args = argparser().parse_args()

    initialize_logging(args)

    total_errors = 0
    for problemdir in args.problemdir:
        print(f'Loading problem {os.path.basename(os.path.realpath(problemdir))}')
        with Problem(problemdir) as prob:
            errors, warnings = prob.check(args)
            p = lambda x: '' if x == 1 else 's'
            print(f'{prob.shortname} tested: {errors} error{p(errors)}, {warnings} warning{p(warnings)}')
            total_errors += errors

    if total_errors > 0:
        sys.exit(1)

if __name__ == '__main__':
    main()
