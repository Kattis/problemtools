#! /usr/bin/env python3
# -*- coding: utf-8 -*-
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
import argparse
import shlex

import yaml

from . import problem2pdf
from . import problem2html

from . import config
from . import languages
from . import run


def is_TLE(status, may_signal_with_usr1=False):
    return (os.WIFSIGNALED(status) and
            (os.WTERMSIG(status) == signal.SIGXCPU or
             (may_signal_with_usr1 and os.WTERMSIG(status) == signal.SIGUSR1)))


def is_RTE(status):
    return not os.WIFEXITED(status) or os.WEXITSTATUS(status)

class SubmissionResult:
    def __init__(self, verdict, score=None, testcase=None, reason=None, additional_info=None):
        self.verdict = verdict
        self.score = score
        self.testcase = testcase
        self.reason = reason
        self.additional_info = additional_info
        self.runtime = -1.0
        self.runtime_testcase = None
        self.ac_runtime = -1.0
        self.ac_runtime_testcase = None
        self.validator_first = False
        self.sample_failures = []

    def set_ac_runtime(self):
        if self.verdict == 'AC':
            self.ac_runtime = self.runtime
            self.ac_runtime_testcase = self.runtime_testcase

    def __str__(self):
        verdict = self.verdict
        details = []

        if verdict == 'AC' and self.score is not None:
            verdict += f' ({self.score:.0f})'

        if self.reason is not None:
            details.append(self.reason)
        if self.verdict != 'AC' and self.testcase is not None:
            details.append(f'test case: {self.testcase}')
        if self.runtime != -1:
            details.append(f'CPU: {self.runtime:.2f}s @ {self.runtime_testcase}')

        if len(details) == 0:
            return verdict
        return f'{verdict} [{", ".join(details)}]'



class VerifyError(Exception):
    pass


class ProblemAspect:
    max_additional_info = 15
    errors = 0
    warnings = 0
    bail_on_error = False
    _check_res = None
    basename_regex = re.compile('^[a-zA-Z0-9][a-zA-Z0-9_.-]*[a-zA-Z0-9]$')

    @staticmethod
    def __append_additional_info(msg, additional_info):
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

    def error(self, msg, additional_info=None):
        self._check_res = False
        ProblemAspect.errors += 1
        logging.error('in %s: %s', self, ProblemAspect.__append_additional_info(msg, additional_info))
        if ProblemAspect.bail_on_error:
            raise VerifyError(msg)

    def warning(self, msg, additional_info=None):
        if ProblemAspect.consider_warnings_errors:
            self.error(msg)
            return
        ProblemAspect.warnings += 1
        logging.warning('in %s: %s', self, ProblemAspect.__append_additional_info(msg, additional_info))

    def msg(self, msg):
        print(msg)

    def info(self, msg):
        logging.info(': %s', msg)

    def debug(self, msg):
        logging.debug(': %s', msg)

    def check_basename(self, path):
        basename = os.path.basename(path)
        if not self.basename_regex.match(basename):
            self.error(f"Invalid name '{basename}' (should match '{self.basename_regex.pattern}')")

class TestCase(ProblemAspect):
    def __init__(self, problem, base, testcasegroup):
        self._base = base
        self.infile = f'{base}.in'
        self.ansfile = f'{base}.ans'
        self._problem = problem
        self.testcasegroup = testcasegroup
        self.reuse_result_from = None
        self._result_cache = (None, None)
        problem.testcase_by_infile[self.infile] = self

    def check_newlines(self, filename):
        with open(filename, 'r') as f:
            data = f.read()
        if data.find('\r') != -1:
            self.warning(f'The file {filename} contains non-standard line breaks.')
        if len(data) > 0 and data[-1] != '\n':
            self.warning(f"The file {filename} does not end with '\\n'.")

    def strip_path_prefix(self, path):
        return os.path.relpath(path, os.path.join(self._problem.probdir, 'data'))

    def is_in_sample_group(self):
        return self.strip_path_prefix(self.infile).startswith('sample')

    def check(self, args):
        if self._check_res is not None:
            return self._check_res
        self._check_res = True
        self.check_basename(self.infile)
        self.check_basename(self.ansfile)
        self.check_newlines(self.infile)
        self.check_newlines(self.ansfile)
        self._problem.input_format_validators.validate(self)
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

    def __str__(self):
        return f'test case {self.strip_path_prefix(self._base)}'

    def matches_filter(self, filter_re):
        return filter_re.search(self.strip_path_prefix(self._base)) is not None

    def set_symlinks(self):
        if not os.path.islink(self.infile):
            return
        target = os.path.realpath(self.infile)
        if target in self._problem.testcase_by_infile:
            self.reuse_result_from = self._problem.testcase_by_infile[target]

    def _check_symlinks(self):
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
            self.error(f"Symbolic link '{nicepath}' points to test case with different output validator flags")
            return False
        return True

    def run_submission(self, sub, args, timelim, timelim_low, timelim_high):
        res, res_low, res_high, reused = self._run_submission_real(sub, args, timelim, timelim_low, timelim_high)
        res = self._init_result_for_testcase(res)
        res_low = self._init_result_for_testcase(res_low)
        res_high = self._init_result_for_testcase(res_high)
        msg = "Reused test file result" if reused else "Test file result"
        self.info(f'{msg}: {res}')
        if res.verdict != 'AC' and self.is_in_sample_group():
            res.sample_failures.append(res)

        return (res, res_low, res_high)

    def _run_submission_real(self, sub, args, timelim, timelim_low, timelim_high):
        if self.reuse_result_from is not None:
            return self.reuse_result_from._run_submission_real(sub, args, timelim, timelim_low, timelim_high)

        cache_key = (sub, args, timelim, timelim_low, timelim_high)
        if self._result_cache[0] == cache_key:
            res, res_low, res_high = self._result_cache[1]
            return (res, res_low, res_high, True)

        outfile = os.path.join(self._problem.tmpdir, 'output')
        if sys.stdout.isatty():
            msg = f'Running {sub} on {self}...'
            sys.stdout.write(msg)
            sys.stdout.flush()

        if self._problem.is_interactive:
            res_high = self._problem.output_validators.validate_interactive(self, sub, timelim_high, self._problem.submissions)
        else:
            status, runtime = sub.run(self.infile, outfile,
                                      timelim=timelim_high+1,
                                      memlim=self._problem.config.get('limits')['memory'])
            if is_TLE(status) or runtime > timelim_high:
                res_high = SubmissionResult('TLE')
            elif is_RTE(status):
                res_high = SubmissionResult('RTE')
            else:
                res_high = self._problem.output_validators.validate(self, outfile)
            res_high.runtime = runtime
        if sys.stdout.isatty():
            sys.stdout.write('\b \b' * (len(msg)))
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
        self._result_cache = (cache_key, (res, res_low, res_high))
        return (res, res_low, res_high, False)

    def _init_result_for_testcase(self, res):
        res = copy.copy(res)
        res.testcase = self
        res.runtime_testcase = self
        if res.score is None:
            if res.verdict == 'AC':
                res.score = self.testcasegroup.config['accept_score']
            else:
                res.score = self.testcasegroup.config['reject_score']
        return res

    def get_all_testcases(self):
        return [self]

    def all_datasets(self):
        return [self._base]


class TestCaseGroup(ProblemAspect):
    _DEFAULT_CONFIG = config.load_config('testdata.yaml')
    _SCORING_ONLY_KEYS = ['accept_score', 'reject_score', 'range']

    def __init__(self, problem, datadir, parent=None):
        self._parent = parent
        self._problem = problem
        self._datadir = datadir
        self._seen_oob_scores = False
        self.debug(f'  Loading test data group {datadir}')
        configfile = os.path.join(self._datadir, 'testdata.yaml')
        self.config = {}
        if os.path.isfile(configfile):
            try:
                with open(configfile) as f:
                    self.config = yaml.safe_load(f)
            except Exception as e:
                self.error(e)
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

        self._items = []
        if os.path.isdir(datadir):
            for f in sorted(os.listdir(datadir)):
                f = os.path.join(datadir, f)
                if os.path.isdir(f):
                    self._items.append(TestCaseGroup(problem, f, self))
                else:
                    base, ext = os.path.splitext(f)
                    if ext == '.ans' and os.path.isfile(f'{base}.in'):
                        self._items.append(TestCase(problem, base, self))

        if not parent:
            self.set_symlinks()


    def __str__(self):
        return f'test case group {os.path.relpath(self._datadir, os.path.join(self._problem.probdir))}'

    def set_symlinks(self):
        for sub in self._items:
            sub.set_symlinks()


    def matches_filter(self, filter_re):
        return True


    def get_all_testcases(self):
        res = []
        for child in self._items:
            res += child.get_all_testcases()
        return res


    def get_testcases(self):
        return [child for child in self._items if isinstance(child, TestCase)]


    def get_subgroups(self):
        return [child for child in self._items if isinstance(child, TestCaseGroup)]


    def get_subgroup(self, name):
        return next((child for child in self._items if isinstance(child, TestCaseGroup) and os.path.basename(child._datadir) == name), None)


    def has_custom_groups(self):
        return any(group.get_subgroups() for group in self.get_subgroups())


    def get_score_range(self):
        try:
            score_range = self.config['range']
            min_score, max_score = list(map(float, score_range.split()))
            return (min_score, max_score)
        except:
            return (-float('inf'), float('inf'))


    def check(self, args):
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
                        self.debug(self._items)
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

        for f in infiles:
            if os.path.isdir(f): continue
            if not f'{f[:-3]}.ans' in ansfiles:
                self.error(f"No matching answer file for input '{f}'")
        for f in ansfiles:
            if os.path.isdir(f): continue
            if not f'{f[:-4]}.in' in infiles:
                self.error(f"No matching input file for answer '{f}'")

        if not self.get_subgroups() and not self.get_testcases():
            self.error('Test case group is empty')

        # Check whether a <= b according to a natural sorting where numeric components
        # are compactified, so that e.g. "a" < "a1" < "a2" < "a10" = "a010" < "a10a".
        def natural_sort_le(a, b):
            a += '\0'
            b += '\0'
            i = j = 0
            def parse_num(s, i):
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
            if child.matches_filter(args.data_filter):
                child.check(args)

        return self._check_res


    def run_submission(self, sub, args, timelim, timelim_low, timelim_high):
        self.info(f'Running on {self}')
        subres = []
        subres_low = []
        subres_high = []
        active_low, active = True, True
        on_reject = self.config['on_reject']
        for child in self._items:
            if not child.matches_filter(args.data_filter):
                continue
            res, res_low, res_high = child.run_submission(sub, args, timelim, timelim_low, timelim_high)
            subres_high.append(res_high)
            if active:
                subres.append(res)
            if active_low:
                subres_low.append(res_low)
            if on_reject == 'break':
                active_low &= res_low.verdict == 'AC'
                active &= res.verdict == 'AC'
                if res_high.verdict != 'AC':
                    break

        return (self.aggregate_results(sub, subres),
                self.aggregate_results(sub, subres_low, shadow_result=True),
                self.aggregate_results(sub, subres_high, shadow_result=True))


    def aggregate_results(self, sub, sub_results, shadow_result=False):
        res = SubmissionResult(None)

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


    def all_datasets(self):
        res = []
        for child in self._items:
            res += child.all_datasets()
        return res


class ProblemConfig(ProblemAspect):
    _MANDATORY_CONFIG = ['name']
    _OPTIONAL_CONFIG = config.load_config('problem.yaml')
    _VALID_LICENSES = ['unknown', 'public domain', 'cc0', 'cc by', 'cc by-sa', 'educational', 'permission']

    def __init__(self, problem):
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
                self.error(e)

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

    def __str__(self):
        return 'problem configuration'

    def get(self, key=None):
        if key:
            return self._data[key]
        return self._data

    def check(self, args):
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
            self.warning("Problem has custom test case groups, but does not specify a value for grading.show_test_data_groups; defaulting to false")

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

    def __init__(self, problem):
        self.debug('  Loading generators')
        self._problem = problem
        self.configfile = os.path.join(problem.probdir, 'generators', 'generators.yaml')
        self._data = None
        self._testcases = []
        self._testdata_yaml = {}
        self._data_directories = set()

        if os.path.isfile(self.configfile):
            try:
                with open(self.configfile) as f:
                    self._data = yaml.safe_load(f)
                # Loading empty yaml yields None, for no apparent reason...
                if self._data is None:
                    self._data = {}
            except Exception as e:
                self.error(e)

        if isinstance(self._data, dict):
            # The top-level dict always represents a directory, even if there
            # is no type key
            self._data['type'] = 'directory'

    def __str__(self):
        return 'generators'

    def _parse_command(self, key, state):
        command = state[key]
        name = os.path.basename(state['path'])
        random_salt = str(state['random_salt'])

        def err():
            self.error('Invalid %s key for path %s in generators.yaml' % (key, state['path']))

        if not isinstance(command, str):
            return err()

        seed = str(int(hashlib.sha512((random_salt + command).encode('utf-8')).hexdigest(), 16) % (2**31))

        parts = shlex.split(command)
        if not parts:
            return err()

        for i, part in enumerate(parts):
            new = ''
            for j, group in enumerate(part.split('{')):
                if group.count('}') != (0 if j == 0 else 1):
                    return err()
                if j == 0:
                    new += group
                else:
                    group, rest = group.split('}')
                    if group.startswith('seed'):
                        new += seed
                    elif group == 'name':
                        new += name
                    else:
                        return err()
                    new += rest
            parts[i] = new

        program, arguments = parts[0], parts[1:]
        if program not in self._generators:
            self._generators[program] = program

        return (program, arguments)

    def _parse_testcase(self, data, state):
        if state['input'] is None:
            self.error('Path %s in generators.yaml must contain an input key' % state['path'])
        for key in ['input', 'solution', 'visualizer']:
            if state[key] is not None:
                state[key] = self._parse_command(key, state)
        if state['input'] is not None:
            self._testcases.append(state)

    def _parse_directory(self, data, state):
        # TODO: Process includes

        if 'testdata.yaml' in data:
            content = data['testdata.yaml']
            if content is None:
                content = {}
            self._testdata_yaml['%s/%s' % (state['path'], 'testdata.yaml')] = content

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

    def _parse_element(self, data, state):
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

    def _resolve_path(self, path):
        base_path = self._problem.probdir
        if path.startswith('/'):
            path = path[1:]
        else:
            base_path = os.path.join(base_path, 'generators')
        return os.path.join(*([base_path] + path.split('/')))

    def _compile_generators(self):
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
                        self.error(e)
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

    def check(self, args):
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
                    self._data_directories.add(key)
                if not valid:
                    invalid.append(key)
            for key in invalid:
                del self._data['data'][key]

        # Run a depth-first search through generators.yaml and generate a
        # flattened list of testcases
        default_state = { key: None for key in Generators._TESTCASE_OPTIONS }
        default_state.update({
            'path': 'data',
            'manual': False,
            'random_salt': '',
        })

        self._parse_element(self._data, default_state)

        if 'compile_generators' not in args or args.compile_generators:
            self._compile_generators()

        return self._check_res


class ProblemStatement(ProblemAspect):
    def __init__(self, problem):
        self.debug('  Loading problem statement')
        self._problem = problem
        self.languages = []
        glob_path = os.path.join(problem.probdir, 'problem_statement', 'problem.')
        if glob.glob(glob_path + 'tex'):
            self.languages.append('')
        for f in glob.glob(glob_path + '[a-z][a-z].tex'):
            self.languages.append(re.search("problem.([a-z][a-z]).tex$", f).group(1))

    def check(self, args):
        if self._check_res is not None:
            return self._check_res
        self._check_res = True

        if not self.languages:
            self.error('No problem statements found (expected problem.tex or problem.[a-z][a-z].tex in problem_statement directory)')
        if '' in self.languages and 'en' in self.languages:
            self.error("Can't supply both problem.tex and problem.en.tex")
        pdfopt = problem2pdf.ConvertOptions()
        pdfopt.nopdf = True
        pdfopt.quiet = True
        htmlopt = problem2html.ConvertOptions()
        htmlopt.destdir = os.path.join(self._problem.tmpdir, 'html')
        htmlopt.quiet = True

        for lang in self.languages:
            pdfopt.language = lang
            htmlopt.language = lang
            try:
                if not problem2pdf.convert(self._problem.probdir, pdfopt):
                    langparam = ''
                    if lang != '':
                        langparam = '-l ' + lang
                    self.error(f'Could not compile problem statement for language "{lang}".  Run problem2pdf {langparam} on the problem to diagnose.')
            except Exception as e:
                self.error(f'Error raised when checking problem statement for language {lang}:\n{e}')
            try:
                problem2html.convert(self._problem.probdir, htmlopt)
            except Exception as e:
                langparam = ''
                if lang != '':
                    langparam = '-l ' + lang
                self.error(f'Could not convert problem statement to html for language "{lang}".  Run problem2html {langparam} on the problem to diagnose.')
        return self._check_res

    def __str__(self):
        return 'problem statement'

    def get_config(self):
        ret = {}
        for lang in self.languages:
            filename = f'problem.{lang}.tex' if lang != '' else 'problem.tex'
            stmt = open(os.path.join(self._problem.probdir, 'problem_statement', filename)).read()
            patterns = [(r'\\problemname{(.*)}', 'name'),
                        (r'^%%\s*plainproblemname:(.*)$', 'name')
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

    def __init__(self, problem):
        attachments_path = os.path.join(problem.probdir, 'attachments')
        if os.path.isdir(attachments_path):
            self.attachments = [os.path.join(attachments_path, attachment_name) for attachment_name in os.listdir(attachments_path)]
        else:
            self.attachments = []
        self.debug(f'Adding attachments {str(self.attachments)}')

    def check(self, args):
        if self._check_res is not None:
            return self._check_res
        self._check_res = True

        for attachment_path in self.attachments:
            if os.path.isdir(attachment_path):
                self.error(f'Directories are not allowed as attachments ({attachment_path} is a directory)')

        return self._check_res

    def get_attachment_paths(self):
        return self.attachments

    def __str__(self):
        return 'attachments'


_JUNK_CASES = [
    ('an empty file', b''),
    ('a binary file with byte values 0 up to 256', bytearray(x for x in range(256))),
    ('a text file with the ASCII characters 32 up to 127', bytearray(x for x in range(32, 127))),
    ('a random text file with printable ASCII characters', bytearray(random.choice(string.printable.encode('utf8')) for _ in range(200))),
]

def _build_junk_modifier(desc, pattern, repl):
    p = re.compile(pattern)
    return (desc, p.search, lambda text: p.sub(repl, text))

_JUNK_MODIFICATIONS = [
    _build_junk_modifier('spaces added where there already is whitespace', r'\s', lambda m: m.group(0) + ' ' * random.randint(1, 5)),
    _build_junk_modifier('newlines added where there already are newlines', '\n', lambda m: '\n' * random.randint(2, 5)),
    _build_junk_modifier('leading zeros added to integers', r'(^|[^.]\b)([0-9]+)\b', r'\g<1>0000000000\g<2>'),
    _build_junk_modifier('trailing zeros added to real number decimal portion', r'\.[0-9]+\b', r'\g<0>0000000000'),
    ('random junk added to the end of the file', lambda f: True, lambda f: f + ''.join(random.choice(string.printable) for _ in range(200))),
]

class InputFormatValidators(ProblemAspect):

    def __init__(self, problem):
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


    def __str__(self):
        return 'input format validators'


    def check(self, args):
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
                self.error(e)

        # Only sanity check input validators if they all actually compiled
        if self._check_res:
            all_flags = set()
            def collect_flags(group, flags):
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
                for flags in all_flags:
                    flags = flags.split()
                    for val in self._validators:
                        status, _ = val.run(file_name, args=flags)
                        if os.WEXITSTATUS(status) != 42:
                            break
                    else:
                        self.warning(f'No validator rejects {desc} with flags "{" ".join(flags)}"')

            def modified_input_validates(applicable, modifier):
                for testcase in self._problem.testdata.get_all_testcases():
                    with open(testcase.infile) as infile:
                        infile = infile.read()
                    if not applicable(infile):
                        continue

                    with open(file_name, "wb") as f:
                        f.write(modifier(infile).encode('utf8'))

                    for flags in all_flags:
                        flags = flags.split()
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


    def validate(self, testcase):
        flags = testcase.testcasegroup.config['input_validator_flags'].split()
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

    def __init__(self, problem):
        self._problem = problem
        self._graders = run.find_programs(os.path.join(problem.probdir, 'graders'),
                                          language_config=problem.language_config,
                                          work_dir=problem.tmpdir)

    def __str__(self):
        return 'graders'

    def check(self, args):
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

    def grade(self, sub_results, testcasegroup, shadow_result=False):

        if testcasegroup.config['grading'] == 'default':
            graders = [self._default_grader]
        else:
            graders = self._graders

        grader_input = ''.join([f'{r.verdict} {0 if r.score is None else r.score}\n' for r in sub_results])
        grader_output_re = r'^((AC)|(WA)|(TLE)|(RTE)|(JE))\s+-?[0-9.]+\s*$'
        verdict = 'AC'
        score = 0

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

                verdict, score = grader_output.split()
                score = float(score)
        # TODO: check that all graders give same result

        if not shadow_result:
            self.info(f'Grade on {testcasegroup} is {verdict} ({score})')

        return (verdict, score)


class OutputValidators(ProblemAspect):
    _default_validator = run.get_tool('default_validator')


    def __init__(self, problem):
        self._problem = problem
        self._validators = run.find_programs(os.path.join(problem.probdir,
                                                          'output_validators'),
                                             language_config=problem.language_config,
                                             work_dir=problem.tmpdir)


    def __str__(self):
        return 'output validators'


    def check(self, args):
        if self._check_res is not None:
            return self._check_res
        self._check_res = True

        recommended_output_validator_languages = {'c', 'cpp', 'python3'}

        for v in self._validators:
            if not isinstance(v, run.BuildRun) and v.language.lang_id not in recommended_output_validator_languages:
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
                self.error(e)

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
    def __get_feedback(feedback_dir):
        all_feedback = []
        for feedback_file in os.listdir(feedback_dir):
            feedback_path = os.path.join(feedback_dir, feedback_file)
            if os.path.getsize(feedback_path) == 0:
                continue
            all_feedback.append(f'=== {feedback_file}: ===')
            # FIXME handle feedback files containing non-text
            with open(feedback_path, 'r') as feedback:
                # Cap amount of feedback per file at some high-ish
                # size, so that a buggy validator spewing out lots of
                # data doesn't kill us.
                all_feedback.append(feedback.read(128*1024))
        if all_feedback:
            return '\n'.join(all_feedback)
        return None


    def _parse_validator_results(self, val, status, feedbackdir, testcase):
        custom_score = self._problem.config.get('grading')['custom_scoring']
        score = None
        # TODO: would be good to have some way of displaying the feedback for debugging uses
        score_file = os.path.join(feedbackdir, 'score.txt')
        if not custom_score and os.path.isfile(score_file):
            return SubmissionResult('JE', reason='validator produced "score.txt" but problem does not have custom scoring activated')

        if not os.WIFEXITED(status):
            return SubmissionResult('JE',
                                    reason=f'output validator {val} crashed, status {status}',
                                    additional_info=OutputValidators.__get_feedback(feedbackdir))
        ret = os.WEXITSTATUS(status)
        if ret not in [42, 43]:
            return SubmissionResult('JE',
                                    reason=f'output validator {val} exited with status {ret}',
                                    additional_info=OutputValidators.__get_feedback(feedbackdir))

        if ret == 43:
            return SubmissionResult('WA', additional_info=OutputValidators.__get_feedback(feedbackdir))

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


    def _actual_validators(self):
        vals = self._validators
        if self._problem.config.get('validation') == 'default':
            vals = [self._default_validator]
        return vals


    def validate_interactive(self, testcase, submission, timelim, errorhandler):
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
            if val is not None and val.compile()[0]:
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
                        val_status, _, sub_status, sub_runtime, first = interactive_output.split()
                        sub_status = int(sub_status)
                        sub_runtime = float(sub_runtime)
                        val_status = int(val_status)
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


    def validate(self, testcase, submission_output):
        res = SubmissionResult('JE')
        val_timelim = self._problem.config.get('limits')['validation_time']
        val_memlim = self._problem.config.get('limits')['validation_memory']
        flags = self._problem.config.get('validator_flags').split() + testcase.testcasegroup.config['output_validator_flags'].split()
        for val in self._actual_validators():
            if val is not None and val.compile()[0]:
                feedbackdir = tempfile.mkdtemp(prefix='feedback', dir=self._problem.tmpdir)
                status, runtime = val.run(submission_output,
                                          args=[testcase.infile, testcase.ansfile, feedbackdir] + flags,
                                          timelim=val_timelim, memlim=val_memlim)
                res = self._parse_validator_results(val, status, feedbackdir, testcase)
                shutil.rmtree(feedbackdir)
                if res.verdict != 'AC':
                    return res

        # TODO: check that all output validators give same result
        return res


class Submissions(ProblemAspect):
    _SUB_REGEXP = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.-]*[a-zA-Z0-9](\.c\+\+)?$')
    # (verdict, directory, required)
    _VERDICTS = [
        ['AC', 'accepted', True],
        ['PAC', 'partially_accepted', False],
        ['WA', 'wrong_answer', False],
        ['RTE', 'run_time_error', False],
        ['TLE', 'time_limit_exceeded', False],
    ]

    def __init__(self, problem):
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

    def __str__(self):
        return 'submissions'

    def check_submission(self, sub, args, expected_verdict, timelim, timelim_low, timelim_high):
        desc = f'{expected_verdict} submission {sub}'
        partial = False
        if expected_verdict == 'PAC':
            # For partially accepted solutions, use the low timelim instead of the real one,
            # to make sure we have margin in both directions.
            expected_verdict = 'AC'
            partial = True
        else:
            timelim_low = timelim

        result, result_low, result_high = self._problem.testdata.run_submission(sub, args, timelim, timelim_low, timelim_high)

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

    def full_score_finite(self):
        min_score, max_score = self._problem.testdata.get_score_range()
        if self._problem.config.get('grading')['objective'] == 'min':
            return min_score != -float('inf')
        else:
            return max_score != float('inf')

    def fully_accepted(self, result):
        min_score, max_score = self._problem.testdata.get_score_range()
        best_score = min_score if self._problem.config.get('grading')['objective'] == 'min' else max_score
        return result.verdict == 'AC' and (not self._problem.is_scoring or result.score == best_score)

    def check(self, args):
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
        if args.fixed_timelim is not None:
            timelim = args.fixed_timelim
            timelim_margin = int(round(timelim * safety_margin))

        for verdict in Submissions._VERDICTS:
            acr = verdict[0]
            if verdict[2] and not self._submissions[acr]:
                self.error(f'Require at least one "{verdict[1]}" submission')

            runtimes = []

            for sub in self._submissions[acr]:
                if args.submission_filter.search(os.path.join(verdict[1], sub.name)):
                    self.info(f'Check {acr} submission {sub}')

                    if sub.code_size() > 1024*limits['code']:
                        self.error(f'{acr} submission {sub} has size {sub.code_size() / 1024.0:.1f} kiB, exceeds code size limit of {limits["code"]} kiB')
                        continue

                    success, msg = sub.compile()
                    if not success:
                        self.error(f'Compile error for {acr} submission {sub}', additional_info=msg)
                        continue

                    res = self.check_submission(sub, args, acr, timelim, timelim_margin_lo, timelim_margin)
                    runtimes.append(res.runtime)

            if acr == 'AC':
                if len(runtimes) > 0:
                    max_runtime = max(runtimes)
                    exact_timelim = max_runtime * time_multiplier
                    max_runtime = f'{max_runtime:.3f}'
                    timelim = max(1, int(0.5 + exact_timelim))
                    timelim_margin_lo = max(1, min(int(0.5 + exact_timelim / safety_margin), timelim - 1))
                    timelim_margin = max(timelim + 1,
                                         int(0.5 + exact_timelim * safety_margin))
                else:
                    max_runtime = None
                if args.fixed_timelim is not None and args.fixed_timelim != timelim:
                    self.msg(f"   Solutions give timelim of {timelim} seconds, but will use provided fixed limit of {args.fixed_timelim} seconds instead")
                    timelim = args.fixed_timelim
                    timelim_margin = timelim * safety_margin

                self.msg(f"   Slowest AC runtime: {max_runtime}, setting timelim to {timelim} secs, safety margin to {timelim_margin} secs")
            limits['time'] = timelim

        return self._check_res

PROBLEM_PARTS = ['config', 'statement', 'validators', 'graders', 'generators', 'data', 'submissions']

class Problem(ProblemAspect):
    def __init__(self, probdir):
        self.probdir = os.path.realpath(probdir)
        self.shortname = os.path.basename(self.probdir)
        self.language_config = languages.load_language_config()

    def __enter__(self):
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
        self.input_format_validators = InputFormatValidators(self)
        self.output_validators = OutputValidators(self)
        self.graders = Graders(self)
        self.testcase_by_infile = {}
        self.testdata = TestCaseGroup(self, os.path.join(self.probdir, 'data'))
        self.submissions = Submissions(self)
        self.generators = Generators(self)
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        shutil.rmtree(self.tmpdir)

    def __str__(self):
        return self.shortname

    def check(self, args=None):
        if self.shortname is None:
            return [1, 0]
        if args is None:
            args = default_args()

        ProblemAspect.errors = 0
        ProblemAspect.warnings = 0
        ProblemAspect.bail_on_error = args.bail_on_error
        ProblemAspect.consider_warnings_errors = args.werror

        try:
            part_mapping = {'config': [self.config],
                            'statement': [self.statement, self.attachments],
                            'validators': [self.input_format_validators, self.output_validators],
                            'graders': [self.graders],
                            'data': [self.testdata],
                            'submissions': [self.submissions],
                            'generators': [self.generators]}

            if not re.match('^[a-z0-9]+$', self.shortname):
                self.error(f"Invalid shortname '{self.shortname}' (must be [a-z0-9]+)")

            run.limit.check_limit_capabilities(self)

            for part in args.parts:
                self.msg(f'Checking {part}')
                for item in part_mapping[part]:
                    item.check(args)
        except VerifyError:
            pass
        return [ProblemAspect.errors, ProblemAspect.warnings]


def re_argument(s):
    try:
        r = re.compile(s)
        return r
    except re.error:
        raise argparse.ArgumentTypeError(f'{s} is not a valid regex')


def part_argument(s):
    if s not in PROBLEM_PARTS:
        raise argparse.ArgumentTypeError(f"Invalid problem part specified: {s}")
    return s


def argparser_basic_arguments(parser):
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


def argparser():
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

    argparser_basic_arguments(parser)

    parser.add_argument('problemdir', nargs='+')
    return parser


def default_args():
    return argparser().parse_args([None])


def initialize_logging(args):
    ProblemAspect.max_additional_info = args.max_additional_info

    fmt = "%(levelname)s %(message)s"
    logging.basicConfig(stream=sys.stdout,
                        format=fmt,
                        level=eval(f"logging.{args.log_level.upper()}"))


def main():
    args = argparser().parse_args()

    initialize_logging(args)

    total_errors = 0
    for problemdir in args.problemdir:
        print(f'Loading problem {os.path.basename(os.path.realpath(problemdir))}')
        with Problem(problemdir) as prob:
            [errors, warnings] = prob.check(args)
            p = lambda x: '' if x == 1 else 's'
            print(f'{prob.shortname} tested: {errors} error{p(errors)}, {warnings} warning{p(warnings)}')
            total_errors += errors

    sys.exit(1 if total_errors > 0 else 0)

if __name__ == '__main__':
    main()
