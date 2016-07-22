#! /usr/bin/env python2
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
import yaml
import tempfile
import sys
import copy
import random
from argparse import ArgumentParser, ArgumentTypeError
import problem2pdf
import problem2html

import languages
import run


def is_TLE(status, may_signal_with_usr1=False):
    return (os.WIFSIGNALED(status) and
            (os.WTERMSIG(status) == signal.SIGXCPU or
             (may_signal_with_usr1 and os.WTERMSIG(status) == signal.SIGUSR1)))


def is_RTE(status):
    return not os.WIFEXITED(status) or os.WEXITSTATUS(status)


class SubmissionResult:
    def __init__(self, verdict, score=None, testcase=None, reason=None):
        self.verdict = verdict
        self.score = score
        self.testcase = testcase
        self.reason = reason
        self.runtime = -1.0
        self.runtime_testcase = None
        self.ac_runtime = -1.0
        self.ac_runtime_testcase = None


    @staticmethod
    def aggregate_results(sub_results, policy, grade=None):
        res = SubmissionResult(None)

        for r in sub_results:
            if r.runtime > res.runtime:
                res.runtime = r.runtime
                res.runtime_testcase = r.runtime_testcase
            if r.ac_runtime > res.ac_runtime:
                res.ac_runtime = r.ac_runtime
                res.ac_runtime_testcase = r.ac_runtime_testcase

        verdict_value = {'JE': -1, 'CE': 0, 'TLE': 1, 'RTE': 2, 'WA': 3, 'AC': 4}

        rejection = next((r for r in sub_results if r.verdict == 'JE'), None)
        if rejection is None:
            if policy == 'first_error':
                rejection = next((r for r in sub_results if r.verdict != 'AC'), None)
            elif policy == 'worst_error':
                rejection = min(sub_results, key=lambda r: verdict_value[r.verdict])
            # else policy is 'grade' and we should grade the results

        if rejection is None:
            if grade is not None:
                (res.verdict, res.score) = grade(sub_results)
            else:
                res.verdict = 'AC'
        else:
            res.verdict = rejection.verdict
            res.reason = rejection.reason
            res.testcase = rejection.testcase

        return res



    def __str__(self):
        verdict = self.verdict
        details = []

        if verdict == 'AC' and self.score is not None:
            verdict += ' (%.0f)' % self.score

        if self.reason is not None:
            details.append(self.reason)
        if self.verdict != 'AC' and self.testcase is not None:
            details.append('test case: %s' % self.testcase)
        if self.runtime != -1:
            details.append('CPU: %.2fs @ %s' % (self.runtime, self.runtime_testcase))

        if len(details) == 0:
            return verdict
        return '%s [%s]' % (verdict, ', '.join(details))



class VerifyError(Exception):
    pass


class ProblemAspect:
    errors = 0
    warnings = 0
    bail_on_error = False
    _check_res = None

    def error(self, msg):
        self._check_res = False
        ProblemAspect.errors += 1
        logging.error('in %s: %s', self, msg)
        if ProblemAspect.bail_on_error:
            raise VerifyError(msg)

    def warning(self, msg):
        ProblemAspect.warnings += 1
        logging.warning('in %s: %s', self, msg)

    def msg(self, msg):
        print msg

    def info(self, msg):
        logging.info(': %s', msg)

    def debug(self, msg):
        logging.debug(': %s', msg)


class TestCase(ProblemAspect):
    def __init__(self, problem, base, testcasegroup):
        self._base = base
        self.infile = base + '.in'
        self.ansfile = base + '.ans'
        self._problem = problem
        self.testcasegroup = testcasegroup

    def check_newlines(self, filename):
        with open(filename, 'r') as f:
            data = f.read()
        if data.find('\r') != -1:
            self.warning('The file %s contains non-standard line breaks.'
                         % filename)
        if len(data) > 0 and data[-1] != '\n':
            self.warning("The file %s does not end with '\\n'." % filename)

    def strip_path_prefix(self, path):
        return os.path.relpath(path, os.path.join(self._problem.probdir, 'data'))

    def check(self, args):
        if self._check_res is not None:
            return self._check_res
        self._check_res = True
        self.check_newlines(self.infile)
        self.check_newlines(self.ansfile)
        self._problem.input_format_validators.validate(self)
        anssize = os.path.getsize(self.ansfile) / 1024.0 / 1024.0
        outputlim = self._problem.config.get('limits')['output']
        if anssize > outputlim:
            self.error('Answer file (%.1f Mb) is larger than output limit (%d Mb), you need to increase output limit' % (anssize, outputlim))
        elif 2 * anssize > outputlim:
            self.warning('Answer file (%.1f Mb) is within %.0f%% of output limit (%d Mb), you might want to increase output limit' % (anssize, 100.0*anssize/outputlim, outputlim))
        if not self._problem.is_interactive:
            val_res = self._problem.output_validators.validate(self, self.ansfile)
            if val_res.verdict != 'AC':
                if self.strip_path_prefix(self.infile)[0:6] == 'sample':
                    self.error('judge answer file got %s' % val_res)
                else:
                    self.warning('judge answer file got %s' % val_res)
        return self._check_res

    def __str__(self):
        return 'test case %s' % self.strip_path_prefix(self._base)

    def matches_filter(self, filter_re):
        return filter_re.search(self.strip_path_prefix(self._base)) is not None

    def run_submission(self, sub, args, timelim_low=1000, timelim_high=1000):
        outfile = os.path.join(self._problem.tmpdir, 'output')
        if sys.stdout.isatty():
            msg = 'Running %s on %s...' % (sub, self)
            sys.stdout.write('%s' % msg)
            sys.stdout.flush()

        if self._problem.is_interactive:
            res2 = self._problem.output_validators.validate_interactive(self, sub, timelim_high, self._problem.submissions)
        else:
            status, runtime = sub.run(self.infile, outfile, timelim=timelim_high+1)
            if is_TLE(status) or runtime > timelim_high:
                res2 = SubmissionResult('TLE', score=self._problem.config.get('grading')['reject_score'])
            elif is_RTE(status):
                res2 = SubmissionResult('RTE', score=self._problem.config.get('grading')['reject_score'])
            else:
                res2 = self._problem.output_validators.validate(self, outfile)
            res2.runtime = runtime
        if sys.stdout.isatty():
            sys.stdout.write('%s' % '\b' * (len(msg)))
        if res2.runtime <= timelim_low:
            res1 = res2
        else:
            res1 = SubmissionResult('TLE', score=self._problem.config.get('grading')['reject_score'])
        res1.testcase = res2.testcase = self
        res1.runtime_testcase = res2.runtime_testcase = self
        res1.runtime = res2.runtime
        if res1.verdict == 'AC':
            res1.ac_runtime = res1.runtime
            res1.ac_runtime_testcase = res1.runtime_testcase
        if res2.verdict == 'AC':
            res2.ac_runtime = res2.runtime
            res2.ac_runtime_testcase = res2.runtime_testcase
        self.info('Test file result: %s)' % (res1))
        return (res1, res2)

    def get_all_testcases(self):
        return [self]

    def all_datasets(self):
        return [self._base]


class TestCaseGroup(ProblemAspect):
    _DEFAULT_CONFIG = {'grading': 'default',
                       'grader_flags': '',
                       'input_validator_flags': '',
                       'output_validator_flags': ''}

    def __init__(self, problem, datadir, parent=None):
        self._parent = parent
        self._problem = problem
        self._datadir = datadir
        self.debug('  Loading test data group %s' % datadir)
        configfile = os.path.join(self._datadir, 'testdata.yaml')
        if os.path.isfile(configfile):
            try:
                self.config = yaml.safe_load(file(configfile))
            except Exception as e:
                self.error(e)
                self.config = {}
        elif parent is not None:
            self.config = parent.config.copy()
        else:
            self.config = {}

        for field, default in TestCaseGroup._DEFAULT_CONFIG.iteritems():
            if not field in self.config:
                self.config[field] = default

        self._items = []
        if os.path.isdir(datadir):
            for f in sorted(os.listdir(datadir)):
                f = os.path.join(datadir, f)
                if os.path.isdir(f):
                    self._items.append(TestCaseGroup(problem, f, self))
                else:
                    base, ext = os.path.splitext(f)
                    if ext == '.ans' and os.path.isfile(base + '.in'):
                        self._items.append(TestCase(problem, base, self))


    def __str__(self):
        return 'test case group %s' % os.path.relpath(self._datadir, os.path.join(self._problem.probdir))


    def matches_filter(self, filter_re):
        return True


    def get_all_testcases(self):
        res = []
        for subdata in self._items:
            res += subdata.get_all_testcases()
        return res


    def get_testcases(self):
        return [sub for sub in self._items if isinstance(sub, TestCase)]


    def get_subgroups(self):
        return [sub for sub in self._items if isinstance(sub, TestCaseGroup)]


    def get_subgroup(self, name):
        return next((sub for sub in self._items if isinstance(sub, TestCaseGroup) and os.path.basename(sub._datadir) == name), None)


    def check(self, args):
        if self._check_res is not None:
            return self._check_res
        self._check_res = True

        if self.config['grading'] not in ['default', 'custom']:
            self.error("Invalid grading policy in testdata.yaml")

        if self.config['grading'] == 'custom' and len(self._problem.graders._graders) == 0:
            self._problem.graders.error('%s has custom grading but no custom graders provided' % self)
        if self.config['grading'] == 'default' and Graders._default_grader is None:
            self._problem.graders.error('%s has default grading but I could not find default grader' % self)

        for field in self.config.keys():
            if field not in TestCaseGroup._DEFAULT_CONFIG.keys():
                self.warning("Unknown key '%s' in '%s'" % (field, os.path.join(self._datadir, 'testdata.yaml')))

        infiles = glob.glob(os.path.join(self._datadir, '*.in'))
        ansfiles = glob.glob(os.path.join(self._datadir, '*.ans'))

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
                    if filename[-3:] == ".in":
                        md5 = hashlib.md5()
                        with open(os.path.join(root, filename), 'rb') as f:
                            for buf in iter(lambda: f.read(1024), b''):
                                md5.update(buf)
                        filehash = md5.digest()
                        filepath = os.path.join(root, filename)
                        hashes[filehash].append(os.path.relpath(filepath, self._problem.probdir))
            for _, files in hashes.iteritems():
                if len(files) > 1:
                    self.warning("Identical input files: '%s'" % str(files))

        for f in infiles:
            if not f[:-3] + '.ans' in ansfiles:
                self.error("No matching answer file for input '%s'" % f)
        for f in ansfiles:
            if not f[:-4] + '.in' in infiles:
                self.error("No matching input file for answer '%s'" % f)

        for subdata in self._items:
            if subdata.matches_filter(args.data_filter):
                subdata.check(args)

        return self._check_res


    def compute_result(self, sub_results, probtype, on_reject, shadow_result=False):
        grade = None
        if probtype == 'scoring':
            grade = lambda x: self._problem.graders.grade(x, self, shadow_result)
        return SubmissionResult.aggregate_results(sub_results, on_reject, grade=grade)


    def run_submission(self, sub, args, timelim_low, timelim_high):
        self.info('Running on %s' % self)
        subres1 = []
        subres2 = []
        probtype = self._problem.config.get('type')
        on_reject = self._problem.config.get('grading')['on_reject']
        for subdata in self._items:
            if not subdata.matches_filter(args.data_filter):
                continue
            (r1, r2) = subdata.run_submission(sub, args, timelim_low, timelim_high)
            subres1.append(r1)
            subres2.append(r2)
            if on_reject == 'first_error' and r2.verdict != 'AC':
                break
        return (self.compute_result(subres1, probtype, on_reject),
                self.compute_result(subres2, probtype, on_reject, shadow_result=True))

    def all_datasets(self):
        res = []
        for subdata in self._items:
            res += subdata.all_datasets()
        return res


class ProblemConfig(ProblemAspect):
    _MANDATORY_CONFIG = ['name']
    _OPTIONAL_CONFIG = {
        'uuid': '',
        'type': 'pass-fail',
        'author': '',
        'source': '',
        'source_url': '',
        'license': 'unknown',
        'rights_owner': '',
        'keywords': '',
        'limits': {'time_multiplier': 5,
                   'time_safety_margin': 2,
                   'memory': 1024,
                   'output': 8,
                   'compilation_time': 60,
                   'validation_time': 60,
                   'validation_memory': 1024,
                   'validation_output': 8},
        'validation': 'default',
        'validator_flags': '',
        'grading': {'on_reject': 'first_error',
                    'accept_score': 1.0,
                    'reject_score': 0.0,
                    'objective': 'max',
                    'range': '-inf +inf'},
        'libraries': '',
        'languages': ''
        }
    _VALID_LICENSES = ['unknown', 'public domain', 'cc0', 'cc by', 'cc by-sa', 'educational', 'permission']

    def __init__(self, problem):
        self.debug('  Loading problem config')
        self._problem = problem
        self.configfile = os.path.join(problem.probdir, 'problem.yaml')
        self._data = {}

        if os.path.isfile(self.configfile):
            try:
                self._data = yaml.safe_load(file(self.configfile))
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
        if 'name' in self._data and not type(self._data['name']) is dict:
            self._data['name'] = {'': self._data['name']}

        for field, default in copy.deepcopy(ProblemConfig._OPTIONAL_CONFIG).iteritems():
            if not field in self._data:
                self._data[field] = default
            elif type(default) is dict and type(self._data[field]) is dict:
                self._data[field] = dict(default.items() + self._data[field].items())

        self._origdata = copy.deepcopy(self._data)

        val = self._data['validation'].split()
        self._data['validation-type'] = val[0]
        self._data['validation-params'] = val[1:]

        if self._data['type'] == 'pass-fail':
            self._data['grading']['accept_score'] = None
            self._data['grading']['reject_score'] = None

        self._data['grading']['custom_scoring'] = False
        for param in self._data['validation-params']:
            if param == 'score':
                self._data['grading']['custom_scoring'] = True
            elif param == 'interactive':
                pass

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
            self.error("No config file %s found" % self.configfile)

        for field in ProblemConfig._MANDATORY_CONFIG:
            if not field in self._data:
                self.error("Mandatory field '%s' not provided" % field)

        for field, value in self._origdata.iteritems():
            if field not in ProblemConfig._OPTIONAL_CONFIG.keys() and field not in ProblemConfig._MANDATORY_CONFIG:
                self.warning("Unknown field '%s' provided in problem.yaml" % field)
            if value is None:
                self.error("Field '%s' provided in problem.yaml but is empty" % field)
                self._data[field] = ProblemConfig._OPTIONAL_CONFIG.get(field, '')

        # Check type
        if not self._data['type'] in ['pass-fail', 'scoring']:
            self.error("Invalid value '%s' for type" % self._data['type'])

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
            self.error("Invalid value for license: %s.\n  Valid licenses are %s" % (self._data['license'], ProblemConfig._VALID_LICENSES))
        elif self._data['license'] == 'unknown':
            self.warning("License is 'unknown'")

        if not self._data['grading']['on_reject'] in ['first_error', 'worst_error', 'grade']:
            self.error("Invalid value '%s' for on_reject policy" % self._data['grading']['on_reject'])

        if self._data['type'] == 'pass-fail' and self._data['grading']['on_reject'] == 'grade':
            self.error("Invalid on_reject policy '%s' for problem type '%s'" % (self._data['grading']['on_reject'], self._data['type']))

        if not self._data['validation-type'] in ['default', 'custom']:
            self.error("Invalid value '%s' for validation, first word must be 'default' or 'custom'" % self._data['validation'])

        if self._data['validation-type'] == 'default' and len(self._data['validation-params']) > 0:
            self.error("Invalid value '%s' for validation" % (self._data['validation']))

        if self._data['validation-type'] == 'custom':
            for param in self._data['validation-params']:
                if param not in['score', 'interactive']:
                    self.error("Invalid parameter '%s' for custom validation" % param)

        # Check limits
        if type(self._data['limits']) is not dict:
            self.error('Limits key in problem.yaml must specify a dict')
            self._data['limits'] = ProblemConfig._OPTIONAL_CONFIG['limits']

        # Check grading
        try:
            score_range = self._data['grading']['range']
            (min_score, max_score) = map(float, score_range.split())
            if min_score >= max_score:
                self.error("Invalid score range '%s': minimum score must be smaller than maximum score" % score_range)
        except VerifyError:
            raise
        except:
            self.error("Invalid format '%s' for grading.range: must be exactly two floats" % score_range)

        # Some things not yet implemented
        if self._data['grading']['on_reject'] == 'worst_error':
            self.error("'on_reject: worst_error' not yet supported")
        if self._data['libraries'] != '':
            self.error("Libraries not yet supported")
        if self._data['languages'] != '':
            self.error("Languages not yet supported")

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
            pdf_ok = True
            try:
                if not problem2pdf.convert(self._problem.probdir, pdfopt):
                    langparam = ''
                    if lang != '':
                        langparam = '-l ' + lang
                    self.error('Could not compile problem statement for language "%s".  Run problem2pdf %s on the problem to diagnose.' % (lang, langparam))
            except Exception as e:
                self.error('Error raised when checking problem statement for language %s:\n%s' % (lang, e))
            if not pdf_ok:
                continue
            try:
                problem2html.convert(self._problem.probdir, htmlopt)
            except Exception as e:
                langparam = ''
                if lang != '':
                    langparam = '-l ' + lang
                self.error('Could not convert problem statement to html for language "%s".  Run problem2html %s on the problem to diagnose.' % (lang, langparam))
        return self._check_res

    def __str__(self):
        return 'problem statement'

    def get_config(self):
        ret = {}
        for lang in self.languages:
            filename = ('problem.%s.tex' % lang) if lang != '' else 'problem.tex'
            stmt = open(os.path.join(self._problem.probdir, 'problem_statement', filename)).read()
            patterns = [('\\problemname{(.*)}', 'name'),
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


_JUNK_CASES = [
    ('an empty file', ''),
    ('a binary file with byte values 0 up to 256', ''.join(chr(x) for x in range(256))),
    ('a text file with the ascii characters 32 up to 127', ''.join(chr(x) for x in range(32, 127))),
    ('a random text file with printable characters', ''.join(random.choice(string.printable) for _ in range(200))),
]


class InputFormatValidators(ProblemAspect):

    def __init__(self, problem):
        self._problem = problem
        self._validators = run.find_programs(os.path.join(problem.probdir,
                                                          'input_format_validators'),
                                             language_config=problem.language_config,
                                             allow_validation_script=True,
                                             work_dir=problem.tmpdir)


    def __str__(self):
        return 'input format validators'


    def check(self, args):
        if self._check_res is not None:
            return self._check_res
        self._check_res = True
        if len(self._validators) == 0:
            self.error('No input format validators found')

        for val in self._validators:
            try:
                if not val.compile():
                    self.error('Compile error for %s' % val)
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
                        self.warning('No validator rejects %s with flags "%s"' % (desc, ' '.join(flags)))
            os.unlink(file_name)

        return self._check_res


    def validate(self, testcase):
        flags = testcase.testcasegroup.config['input_validator_flags'].split()
        self.check(None)
        for val in self._validators:
            status, _ = val.run(testcase.infile, args=flags)
            if not os.WIFEXITED(status):
                testcase.error('Input format validator %s crashed on input %s' % (val, testcase.infile))
            if os.WEXITSTATUS(status) != 42:
                testcase.error('Input format validator %s did not accept input %s, exit code: %d' % (val, testcase.infile, os.WEXITSTATUS(status)))


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
            if not grader.compile():
                self.error('Compile error for %s' % grader)
        return self._check_res

    def grade(self, sub_results, testcasegroup, shadow_result=False):

        if testcasegroup.config['grading'] == 'default':
            graders = [self._default_grader]
        else:
            graders = self._graders

        grader_input = ''.join(['%s %s\n' % (r.verdict, r.score) for r in sub_results])
        grader_output_re = r'^((AC)|(WA)|(TLE)|(RTE))\s+[0-9.]+\s*$'
        verdict = 'AC'
        score = 0

        self.debug('Grading %d results:\n%s' % (len(sub_results), grader_input))
        self.debug('Grader flags: %s' % (testcasegroup.config.get('grader_flags')))

        for grader in graders:
            if grader is not None and grader.compile():
                fd, infile = tempfile.mkstemp()
                os.close(fd)
                fd, outfile = tempfile.mkstemp()
                os.close(fd)

                open(infile, 'w').write(grader_input)

                status, runtime = grader.run(infile, outfile,
                                             args=testcasegroup.config.get('grader_flags').split())

                grader_output = open(outfile, 'r').read()
                os.remove(infile)
                os.remove(outfile)
                if not os.WIFEXITED(status):
                    self.error('Judge error: %s crashed' % grader)
                    self.debug('Grader input:\n%s' % grader_input)
                    return SubmissionResult('JE', score=0.0)
#                ret = os.WEXITSTATUS(status)
#                if ret != 42:
#                    self.error('Judge error: exit code %d for grader %s' % (ret, grader))
#                    self.debug('Grader input: %s\n' % grader_input)
#                    return SubmissionResult('JE', 0.0)

                if not re.match(grader_output_re, grader_output):
                    self.error('Judge error: invalid format of grader output')
                    self.debug('Output must match: "%s"' % grader_output_re)
                    self.debug('Output was: "%s"' % grader_output)
                    return SubmissionResult('JE', score=0.0)

                verdict, score = grader_output.split()
                score = float(score)
        # TODO: check that all graders give same result

        if not shadow_result:
            self.info('Grade on %s is %s (%s)' % (testcasegroup, verdict, score))

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

        if self._problem.config.get('validation') == 'default' and self._validators:
            self.error('There are validator programs but problem.yaml has validation = "default"')
        elif self._problem.config.get('validation') != 'default' and not self._validators:
            self.error('problem.yaml specifies custom validator but no validator programs found')

        if self._problem.config.get('validation') == 'default' and self._default_validator is None:
            self.error('Unable to locate default validator')

        for val in self._validators:
            if not val.compile():
                self.error('Compile error for output validator %s' % val)


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
                        self.error('%s as output, and output validator flags "%s" gave %s' % (desc, ' '.join(flags), result))
                        break
                if not rejected:
                    self.warning('%s gets AC' % (desc))
            os.unlink(file_name)

        return self._check_res


    def _parse_validator_results(self, val, status, feedbackdir):
        custom_score = self._problem.config.get('grading')['custom_scoring']
        score = None
        # TODO: would be good to have some way of displaying the feedback for debugging uses
        score_file = os.path.join(feedbackdir, 'score.txt')
        if not custom_score and os.path.isfile(score_file):
            return SubmissionResult('JE', reason='validator produced "score.txt" but problem does not have custom scoring activated')
        if custom_score:
            if os.path.isfile(score_file):
                try:
                    score_str = open(score_file).read()
                    score = float(score_str)
                except Exception as e:
                    return SubmissionResult('JE', reason='failed to parse validator score: %s' % e)
            else:
                return SubmissionResult('JE', reason='problem has custom scoring but validator did not produce "score.txt"')

        if not os.WIFEXITED(status):
            return SubmissionResult('JE', reason='output validator %s crashed, status %d' % (val, status))
        ret = os.WEXITSTATUS(status)
        if ret not in [42, 43]:
            return SubmissionResult('JE', reason='exit code %d for output validator %s' % (ret, val))

        if ret == 43:
            if score is None:
                score = self._problem.config.get('grading')['reject_score']
            return SubmissionResult('WA', score=score)
        if score is None:
            score = self._problem.config.get('grading')['accept_score']
        return SubmissionResult('AC', score=score)


    def _actual_validators(self):
        vals = self._validators
        if self._problem.config.get('validation') == 'default':
            vals = [self._default_validator]
        return vals


    def validate_interactive(self, testcase, submission, timelim, errorhandler):
        interactive_output_re = r'\d+ \d+\.\d+ \d+ \d+\.\d+'
        res = SubmissionResult('JE')
        interactive = run.get_tool('interactive')
        if interactive is None:
            errorhandler.error('Could not locate interactive runner')
            return res
        # file descriptor, wall time lim
        initargs = ['1', str(2 * timelim)]
        validator_args = [testcase.infile, testcase.ansfile, '<feedbackdir>']
        submission_args = submission.get_runcmd()
        for val in self._actual_validators():
            if val is not None and val.compile():
                feedbackdir = tempfile.mkdtemp(prefix='feedback', dir=self._problem.tmpdir)
                validator_args[2] = feedbackdir + os.sep
                f = tempfile.NamedTemporaryFile(delete=False)
                interactive_out = f.name
                f.close()
                i_status, _ = interactive.run(outfile=interactive_out,
                                                      args=initargs + val.get_runcmd() + validator_args + [';'] + submission_args)
                if is_RTE(i_status):
                    errorhandler.error('Interactive crashed, status %d' % i_status)
                else:
                    interactive_output = open(interactive_out).read()
                    errorhandler.debug('Interactive output: "%s"' % interactive_output)
                    if not re.match(interactive_output_re, interactive_output):
                        errorhandler.error('Output from interactive does not follow expected format, got output "%s"' % interactive_output)
                    else:
                        val_status, _, sub_status, sub_runtime = interactive_output.split()
                        sub_status = int(sub_status)
                        sub_runtime = float(sub_runtime)
                        val_status = int(val_status)

                        if is_TLE(sub_status, True):
                            res = SubmissionResult('TLE', score=self._problem.config.get('grading')['reject_score'])
                        elif is_RTE(sub_status):
                            res = SubmissionResult('RTE', score=self._problem.config.get('grading')['reject_score'])
                        else:
                            res = self._parse_validator_results(val, val_status, feedbackdir)

                        res.runtime = sub_runtime

                os.unlink(interactive_out)
                shutil.rmtree(feedbackdir)
                if res.verdict != 'AC':
                    return res
        # TODO: check that all output validators give same result
        return res


    def validate(self, testcase, submission_output):
        res = SubmissionResult('JE')
        for val in self._actual_validators():
            if val is not None and val.compile():
                feedbackdir = tempfile.mkdtemp(prefix='feedback', dir=self._problem.tmpdir)
                status, runtime = val.run(submission_output,
                                          args=[testcase.infile, testcase.ansfile, feedbackdir] + self._problem.config.get('validator_flags').split() + testcase.testcasegroup.config['output_validator_flags'].split())

                res = self._parse_validator_results(val, status, feedbackdir)
                shutil.rmtree(feedbackdir)
                if res.verdict != 'AC':
                    return res

        # TODO: check that all output validators give same result
        return res


class Submissions(ProblemAspect):
    _SUB_REGEXP = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.-]*[a-zA-Z0-9](\.c\+\+)?$')
    _VERDICTS = [
        ['AC', 'accepted', True],
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

    def check_submission(self, sub, args, expected_verdict, timelim_low, timelim_high):
        (result1, result2) = self._problem.testdata.run_submission(sub, args, timelim_low, timelim_high)

        if result1.verdict != result2.verdict:
            self.warning('%s submission %s sensitive to time limit: limit of %s secs -> %s, limit of %s secs -> %s' % (expected_verdict, sub, timelim_low, result1.verdict, timelim_high, result2.verdict))

        if result1.verdict == expected_verdict:
            self.msg('   %s submission %s OK: %s' % (expected_verdict, sub, result1))
        elif result2.verdict == expected_verdict:
            self.msg('   %s submission %s OK with extra time: %s' % (expected_verdict, sub, result2))
        else:
            self.error('%s submission %s got %s' % (expected_verdict, sub, result1))
        return result1

    def check(self, args):
        if self._check_res is not None:
            return self._check_res
        self._check_res = True

        timelim_margin = 300  # 5 minutes
        timelim = 300
        if 'time_for_AC_submissions' in self._problem.config.get('limits'):
            timelim = timelim_margin = self._problem.config.get('limits')['time_for_AC_submissions']
        if args.fixed_timelim is not None:
            timelim = args.fixed_timelim
            timelim_margin = timelim * self._problem.config.get('limits')['time_safety_margin']

        for verdict in Submissions._VERDICTS:
            acr = verdict[0]
            if verdict[2] and not self._submissions[acr]:
                self.error('Require at least one "%s" submission' % verdict[1])

            runtimes = []

            for sub in self._submissions[acr]:
                if args.submission_filter.search(os.path.join(verdict[1], sub.name)):
                    self.info('Check %s submission %s' % (acr, sub))

                    if not sub.compile():
                        self.error('Compile error for %s submission %s' % (acr, sub))
                        continue

                    res = self.check_submission(sub, args, acr, timelim, timelim_margin)
                    runtimes.append(res.runtime)

            if acr == 'AC':
                if len(runtimes) > 0:
                    max_runtime = max(runtimes)
                    exact_timelim = max_runtime * self._problem.config.get('limits')['time_multiplier']
                    max_runtime = '%.3f' % max_runtime
                    timelim = max(1, int(0.5 + exact_timelim))
                    timelim_margin = max(timelim + 1,
                                         int(0.5 + exact_timelim * self._problem.config.get('limits')['time_safety_margin']))
                else:
                    max_runtime = None
                if args.fixed_timelim is not None and args.fixed_timelim != timelim:
                    self.msg("   Solutions give timelim of %d seconds, but will use provided fixed limit of %d seconds instead" % (timelim, args.fixed_timelim))
                    timelim = args.fixed_timelim
                    timelim_margin = timelim * self._problem.config.get('limits')['time_safety_margin']

                self.msg("   Slowest AC runtime: %s, setting timelim to %d secs, safety margin to %d secs" % (max_runtime, timelim, timelim_margin))
            self._problem.config.get('limits')['time'] = timelim

        return self._check_res


PROBLEM_PARTS = ['config', 'statement', 'validators', 'graders', 'data', 'submissions']

class Problem(ProblemAspect):
    def __init__(self, probdir):
        self.probdir = os.path.realpath(probdir)
        self.shortname = os.path.basename(self.probdir)
        self.language_config = languages.load_language_config_default_paths()

    def __enter__(self):
        self.tmpdir = tempfile.mkdtemp(prefix='verify-%s-'%self.shortname)
        if not os.path.isdir(self.probdir):
            self.error("Problem directory '%s' not found" % self.probdir)
            self.shortname = None
            return self

        self.statement = ProblemStatement(self)
        self.config = ProblemConfig(self)
        self.is_interactive = 'interactive' in self.config.get('validation-params')
        self.input_format_validators = InputFormatValidators(self)
        self.output_validators = OutputValidators(self)
        self.graders = Graders(self)
        self.testdata = TestCaseGroup(self, os.path.join(self.probdir, 'data'))
        self.submissions = Submissions(self)
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

        try:
            part_mapping = {'config': [self.config],
                            'statement': [self.statement],
                            'validators': [self.input_format_validators, self.output_validators],
                            'graders': [self.graders],
                            'data': [self.testdata],
                            'submissions': [self.submissions]}

            if not re.match('^[a-z0-9]+$', self.shortname):
                self.error("Invalid shortname '%s' (must be [a-z0-9]+)" % self.shortname)

            run.limit.check_limit_capabilities(self)

            for part in args.parts:
                self.msg('Checking %s' % part)
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
        raise ArgumentTypeError('%s is not a valid regex' % s)


def part_argument(s):
    if s not in PROBLEM_PARTS:
        raise ArgumentTypeError("Invalid problem part specified: %s" % s)
    return s


def argparser():
    parser = ArgumentParser(description="Validate a problem package in the Kattis problem format.")
    parser.add_argument("-s", "--submission_filter", metavar='SUBMISSIONS', help="run only submissions whose name contains this regex.  The name includes category (accepted, wrong_answer, etc), e.g. 'accepted/hello.java' (for a single file submission) or 'wrong_answer/hello' (for a directory submission)", type=re_argument, default=re.compile('.*'))
    parser.add_argument("-d", "--data_filter", metavar='DATA', help="use only data files whose name contains this regex.  The name includes path relative to the data directory but not the extension, e.g. 'sample/hello' for a sample data file", type=re_argument, default=re.compile('.*'))
    parser.add_argument("-t", "--fixed_timelim", help="use this fixed time limit (useful in combination with -d and/or -s when all AC submissions might not be run on all data)", type=int)
    parser.add_argument("-p", "--parts", help="only test the indicated parts of the problem.  Each PROBLEM_PART can be one of %s." % PROBLEM_PARTS, metavar='PROBLEM_PART', type=part_argument, nargs='+', default=PROBLEM_PARTS)
    parser.add_argument("-b", "--bail_on_error", help="bail verification on first error", action='store_true')
    parser.add_argument("-l", "--log-level", dest="loglevel", help="set log level (debug, info, warning, error, critical)", default="warning")
    parser.add_argument('problemdir')
    return parser


def default_args():
    return argparser().parse_args([None])


def main():
    args = argparser().parse_args()
    fmt = "%(levelname)s %(message)s"
    logging.basicConfig(stream=sys.stdout,
                        format=fmt,
                        level=eval("logging." + args.loglevel.upper()))

    print 'Loading problem %s' % os.path.basename(os.path.realpath(args.problemdir))
    with Problem(args.problemdir) as prob:
        [errors, warnings] = prob.check(args)
        print "%s tested: %d errors, %d warnings" % (prob.shortname, errors, warnings)


if __name__ == '__main__':
    main()
