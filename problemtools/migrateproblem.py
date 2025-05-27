#! /usr/bin/env python3
# -*- coding: utf-8 -*-
from enum import IntFlag
import argparse
import io
import os
import re
import shutil
import sys
import tempfile
import uuid
import yaml
import yaml.parser

def dict_add_unless_none(dict, key, value):
    if value is not None:
        dict[key] = value

def parser_warning(msg):
    print(f'PARSER WARNING: {msg}', file=sys.stderr)

def parser_error(msg):
    sys.exit(f'PARSER ERROR: {msg}')

def parser_unimplemented(msg):
    sys.exit(f'PARSER NOT IMPLEMENTED: {msg}')

class ProblemFormatVersion(IntFlag):
    LEGACY_ICPC = 2
    LEGACY = 3
    V2023_07 = 4

class Validation(IntFlag):
    NONE = 0
    DEFAULT = 1
    CUSTOM = 2
    SCORE = 4
    INTERACTIVE = 8

class ProblemYaml:
    def __init__(self, in_version, out_version):
        # names without spaces and/or with special characters are suspicious
        self._suspicious_name = re.compile(r'^([^ ]*|.*[!"#$%&()*+,./0-9:;<=>?@[\\\]\^_{|}~].*)$')
        # split a string on the format "Full Name <adress>" or "Full Name"
        self._fullname_address = re.compile(r'^(|.*[^\s>])\s*(?:<([^<>]*)>)?\s*$')

        if in_version is None or in_version == 'legacy':
            self._in_version = ProblemFormatVersion.LEGACY
        else:
            parser_unimplemented(f'problem format version: {in_version}')
        self._out_version = out_version
        self._type = None
        self._name = None
        self._uuid = None
        self._version = None
        self._credits = None
        self._source = None
        self._license = None
        self._rights_owner = None
        self._limits = None
        self._validation = None
        self._validator_flags = None
        self._scoring = None
        self._keywords = None

    # present in all versions
    @property
    def problem_format_version(self):
        match self._out_version:
            case ProblemFormatVersion.LEGACY:
                return 'legacy'
            case ProblemFormatVersion.LEGACY_ICPC:
                return 'legacy-icpc'
            case ProblemFormatVersion.V2023_07:
                return '2023-07-draft'
            case _:
                parser_error('unexpected target problem format version')

    # not present in legacy-icpc
    @property
    def type(self):
        if self._out_version is ProblemFormatVersion.LEGACY_ICPC and self._type is not None:
            parser_error('legacy-icpc format doesn\'t support property "type"')
        if self._out_version is ProblemFormatVersion.LEGACY and self._type not in ['pass-fail', 'scoring']:
            parser_error(f'unsupported type property in legacy format: "{self._type}"')
        return self._type

    @type.setter
    def type(self, value):
        if value is None: return
        # todo: implement 2023-07-draft
        if not isinstance(value, str): parser_error(f'unexpected type of property "type": {type(value)}')
        if value not in ['pass-fail', 'scoring']:
            parser_error(f'unknown problem type: {value}')
        self._type = value

    # present in all versions
    @property
    def name(self):
        if self._out_version >= ProblemFormatVersion.V2023_07 and self._name is None:
            parser_error('the target format version requires the problem "name" property')
        return self._name

    @name.setter
    def name(self, value):
        if value is None: return
        # todo: implement 2023-07-draft
        if not isinstance(value, str): parser_error(f'unexpected type of property "name": {type(value)}')
        self._name = value

    # present in all versions
    @property
    def uuid(self):
        if self._out_version >= ProblemFormatVersion.V2023_07 and self._uuid is None:
            self._uuid = uuid.uuid4()
            parser_warning('generated a new UUID for the "uuid" property as the input didn\'t contain one')
        return str(self._uuid)

    @uuid.setter
    def uuid(self, value):
        if value is None: return
        self._uuid = uuid.UUID(value)

    # present since 2023-07-draft
    @property
    def version(self):
        if self._out_version & ProblemFormatVersion.LEGACY_ICPC and self._version is not None:
            parser_warning('dropping "version" property because of target problem format version')
        return self._version

    @version.setter
    def version(self, value):
        if value is None: return
        # todo: check format version
        self._version = value

    # not present since 2023-07-draft (see credits)
    @property
    def author(self):
        if self._out_version >= ProblemFormatVersion.V2023_07: return None
        if self._credits is None or 'authors' not in self._credits: return None
        return ', '.join([author.get('name', None) for author in self._credits['authors']])

    @author.setter
    def author(self, value):
        if value is None: return
        # check input version

        # adapted from kattisd/addproblem.py
        authors = re.split(',|\s+and\s+|\s+&\s+', value)
        authors = [x.strip(' \t\r\n') for x in authors]
        authors = [{ 'name': x } for x in authors if len(x) > 0]

        for author in authors:
            name = author['name']
            if self._suspicious_name.search(name):
                parser_warning(f'the author name "{name}" may have been incorrectly parsed')

        self._credits = { 'authors': authors }

    # present since 2023-07-draft (see author for older syntax)
    @property
    def credits(self):
        # todo: check if credits are dropped because of version downgrade
        if self._out_version & ProblemFormatVersion.LEGACY_ICPC: return None
        if self._credits is None: return None
        # todo: flatten if array is of length 1
        dict = {}
        if 'authors' in self._credits:
            dict['authors'] = [(f'{author["name"]} <{author["address"]}>' if 'address' in author else author['name']) for author in self._credits['authors']]
        return dict if dict else None

    @credits.setter
    def credits(self, value):
        if value is None: return
        parser_unimplemented('parsing of credits has not yet been implemented')

    # present in all versions
    @property
    def source(self):
        if self._out_version & ProblemFormatVersion.LEGACY_ICPC:
            if self._source is None or not self._source: return None
            return self._source[0].get('name', None)
        return self._source

    @source.setter
    def source(self, value):
        if value is None: return
        if self._in_version & ProblemFormatVersion.LEGACY_ICPC:
            if not isinstance(value, str): parser_error(f'unexpected type of property "source": {type(value)}')
            if self._source is None: self._source = [{}]
            self._source[0]['name'] = value
        else:
            # value could be
            # 1. a string
            # 2. an object of 'name' and possibly 'url'
            # 3. an array of strings and/or objects of 'name' and possibly 'url'
            # this code unifies 1 and 2 into 3
            if not isinstance(value, list):
                value = [value]
            for i, x in enumerate(value):
                if isinstance(x, str): value[i] = { 'name': x }
            self._source = value

    # not present since 2023-07-draft (see source)
    @property
    def source_url(self):
        if self._out_version & ProblemFormatVersion.LEGACY_ICPC:
            if self._source is None or not self._source: return None
            return self._source[0].get('url', None)
        return None

    @source_url.setter
    def source_url(self, value):
        if value is None: return
        if self._in_version & ProblemFormatVersion.LEGACY_ICPC:
            if not isinstance(value, str): parser_error(f'unexpected type of property "source_url": {type(value)}')
            if self._source is None: self._source = [{}]
            self._source[0]['url'] = value
        else:
            parser_error('property "source_url" is not allowed in this source problem format version')

    # present in all versions
    @property
    def license(self):
        return self._license

    @license.setter
    def license(self, value):
        if value is None: return
        if value not in ['unknown', 'public domain', 'cc0', 'cc by', 'cc by-sa', 'educational', 'permission']:
            parser_error(f'illegal license: {value}')
        self._license = value

    # present in all versions
    @property
    def rights_owner(self):
        if self._rights_owner is not None and self._license == 'public domain':
            parser_error('"rights_owner" given although license is "public domain"')
        if self._license is not None and self._license not in ['unknown', 'public domain'] and self._rights_owner is None and (self._credits is None or 'authors' not in self._credits) and self._source is None:
            parser_error(f'no owner can be identified although license is "{self._license}"')
        return self._rights_owner

    @rights_owner.setter
    def rights_owner(self, value):
        if value is None: return
        self._rights_owner = value

    # present in all versions
    @property
    def limits(self):
        return self._limits

    @limits.setter
    def limits(self, value):
        if value is None: return
        self._limits = value

    # not present since 2023-07-draft
    @property
    def validation(self):
        if self._validation is None: return None
        flags = []
        if self._validation & Validation.DEFAULT:
            flags.append('default')
        if self._validation & Validation.CUSTOM:
            flags.append('custom')
        if self._validation & Validation.SCORE:
            flags.append('score')
        if self._validation & Validation.INTERACTIVE:
            flags.append('interactive')
        return ' '.join(flags)

    @validation.setter
    def validation(self, value):
        if value is None: return

        flags = Validation.NONE
        for s in value.split():
            match s:
                case 'default':
                    flags |= Validation.DEFAULT
                case 'custom':
                    flags |= Validation.CUSTOM
                case 'score':
                    flags |= Validation.SCORE
                case 'interactive':
                    flags |= Validation.INTERACTIVE
                case _:
                    parser_error(f'unknown validation "{s}"')
        if flags & Validation.DEFAULT and flags & ~Validation.DEFAULT:
            parser_error(f'forbidden validation combination "{value}"')
        self._validation = flags

    # not present since 2023-07-draft
    @property
    def validator_flags(self):
        return self._validator_flags

    @validator_flags.setter
    def validator_flags(self, value):
        if value is None: return
        self._validator_flags = value

    # only present in legacy
    @property
    def scoring(self):
        return self._scoring

    @scoring.setter
    def scoring(self, value):
        if value is None: return
        self._scoring = value

    def grading(self, value):
        if value is None: return
        parser_warning('"grading" is deprecated, use "scoring" instead')
        self._scoring = value

    # present in all versions
    @property
    def keywords(self):
        return self._keywords

    @keywords.setter
    def keywords(self, value):
        if value is None: return
        self._keywords = value

    # todo: add languages (since 2023-07-draft)
    # todo: add constants (since 2023-07-draft)

    def generate_dict(self):
        dict = {
            "problem_format_version": self.problem_format_version,
        }
        dict_add_unless_none(dict, 'type', self.type)
        dict_add_unless_none(dict, 'name', self.name)
        dict_add_unless_none(dict, 'uuid', self.uuid)
        dict_add_unless_none(dict, 'version', self.version)
        dict_add_unless_none(dict, 'author', self.author)
        dict_add_unless_none(dict, 'credits', self.credits)
        dict_add_unless_none(dict, 'source', self.source)
        dict_add_unless_none(dict, 'source_url', self.source_url)
        dict_add_unless_none(dict, 'license', self.license)
        dict_add_unless_none(dict, 'rights_owner', self.rights_owner)
        dict_add_unless_none(dict, 'limits', self.limits)
        dict_add_unless_none(dict, 'validation', self.validation)
        dict_add_unless_none(dict, 'validator_flags', self.validator_flags)
        dict_add_unless_none(dict, 'scoring', self.scoring)
        dict_add_unless_none(dict, 'keywords', self.keywords)
        return dict

class TestdataYaml:
    def __init__(self, in_version, out_version):
        if in_version is None or in_version == 'legacy':
            self._in_version = ProblemFormatVersion.LEGACY
        else:
            parser_unimplemented(f'problem format version: {in_version}')

    # only present in legacy
    @property
    def on_reject(self):
        return self._on_reject

    @on_reject.setter
    def on_reject(self, value):
        if value is None: return
        if value not in ['break', 'continue']:
            parser_error(f'illegal on_reject: {value}')
        self._on_reject = value

    # only present since 2023-07-draft
    @property
    def scoring(self):
        return self._scoring

    @scoring.setter
    def scoring(self, value):
        if value is None: return
        self._scoring = value

    # only present in legacy
    @property
    def grading(self):
        return self._grading

    @grading.setter
    def grading(self, value):
        if value is None: return
        if value not in ['default', 'custom']:
            parser_error(f'illegal grading: {value}')
        self._grading = value

    # only present in legacy
    @property
    def grader_flags(self):
        return self._grader_flags

    @grader_flags.setter
    def grader_flags(self, value):
        if value is None: return
        self._grader_flags = value

    # only present in legacy
    @property
    def input_validator_flags(self):
        return self._input_validator_args

    @input_validator_flags.setter
    def input_validator_flags(self, value):
        if value is None: return
        self._input_validator_args = value

    # only present since 2023-07-draft
    @property
    def input_validator_args(self):
        return self._input_validator_args

    @input_validator_args.setter
    def input_validator_args(self, value):
        if value is None: return
        self._input_validator_args = value

    # only present since 2023-07-draft
    @property
    def static_validation(self):
        return self._static_validation

    @static_validation.setter
    def static_validation(self, value):
        if value is None: return
        self._static_validation = value

    # only present since 2023-07-draft
    @property
    def full_feedback(self):
        return self._full_feedback

    @full_feedback.setter
    def full_feedback(self, value):
        if value is None: return
        self._full_feedback = value

    # only present in legacy
    # todo: should this really be a string as specified?
    @property
    def accept_score(self):
        return self._accept_score

    @accept_score.setter
    def accept_score(self, value):
        if value is None: return
        self._accept_score = value

    # only present in legacy
    # todo: should this really be a string as specified?
    @property
    def reject_score(self):
        return self._reject_score

    @reject_score.setter
    def reject_score(self, value):
        if value is None: return
        self._reject_score = value

    # only present in legacy
    @property
    def range(self):
        return self._range

    @range.setter
    def range(self, value):
        if value is None: return
        self._range = value

def arg_inputdir(path):
    if not os.path.isdir(path):
        raise argparse.ArgumentTypeError(f'inputdir: {path} is not a valid path')
    return path

def arg_outputdir(path):
    #if os.path.lexists(path):
    #    raise argparse.ArgumentTypeError(f'outputdir: {path} already exists')
    canonical = os.path.realpath(path)
    parent, _ = os.path.split(canonical)
    try:
        os.makedirs(parent, exist_ok=True)
    except OSError as error:
        raise argparse.ArgumentTypeError(f'outputdir: could not create: {error}')
    return canonical

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Evaluate (and optionally perform) problem package migration from legacy to current format.')
    parser.add_argument('inputdir', type=arg_inputdir, help='the path to a problem package in legacy format')
    parser.add_argument('-o', '--outputdir', type=arg_outputdir, help='folder of the output package (to be created)')
    parser.add_argument('-f', '--format', choices=['legacy', 'legacy-icpc', '2023-07-draft'], default='2023-07-draft', help='problem version format of the target')
    options = parser.parse_args()

    match options.format:
        case 'legacy':
            target_format = ProblemFormatVersion.LEGACY
        case 'legacy-icpc':
            target_format = ProblemFormatVersion.LEGACY_ICPC
        case '2023-07-draft':
            target_format = ProblemFormatVersion.V2023_07
        case _:
            sys.exit(f'unexpected target problem format version: {options.format}')

    if options.outputdir is None:
        parent = None
    else:
        parent, _ = os.path.split(options.outputdir)

    tempdir = tempfile.mkdtemp(prefix='migrateproblem-', dir=parent)
    print(tempdir)
    shutil.copytree(options.inputdir, tempdir, dirs_exist_ok=True)

    try:
        problem_yaml_path = os.path.join(options.inputdir, 'problem.yaml')
        problem_yaml_stream = io.open(problem_yaml_path, 'r')
    except FileNotFoundError:
        parser_error(f'problem metadata not found in inputdir ({problem_yaml_path})')

    with problem_yaml_stream:
        try:
            problem_yaml_object = yaml.safe_load(problem_yaml_stream)
        except yaml.parser.ParserError as error:
            parser_error(f'problem metadata parsing failed: {error}')

    problem_yaml = ProblemYaml(problem_yaml_object.pop('problem_format_version', None), target_format)
    problem_yaml.type = problem_yaml_object.pop('type', None)
    problem_yaml.name = problem_yaml_object.pop('name', None)
    problem_yaml.uuid = problem_yaml_object.pop('uuid', None)
    problem_yaml.version = problem_yaml_object.pop('version', None)
    problem_yaml.author = problem_yaml_object.pop('author', None)
    problem_yaml.credits = problem_yaml_object.pop('credits', None)
    problem_yaml.source = problem_yaml_object.pop('source', None)
    problem_yaml.source_url = problem_yaml_object.pop('source_url', None)
    problem_yaml.license = problem_yaml_object.pop('license', None)
    problem_yaml.rights_owner = problem_yaml_object.pop('rights_owner', None)
    problem_yaml.limits = problem_yaml_object.pop('limits', None)
    problem_yaml.validation = problem_yaml_object.pop('validation', None)
    problem_yaml.validator_flags = problem_yaml_object.pop('validator_flags', None)
    problem_yaml.scoring = problem_yaml_object.pop('scoring', None)
    problem_yaml.grading(problem_yaml_object.pop('grading', None))
    problem_yaml.keywords = problem_yaml_object.pop('keywords', None)

    if bool(problem_yaml_object):
        parser_warning(f'superfluous keys in "problem.yaml": {problem_yaml_object}')

    print(f'{problem_yaml.generate_dict()}')

    print(problem_yaml_object)
    # key_grader_flags = problem_yaml_object.pop('grader_flags', None)
    # match key_grader_flags:
    #     case None:
    #         pass
    #     case 'min' | 'sum':
    #         problem_yaml_object['aggregation'] = key_grader_flags
    #     case 'accept_if_any_accepted' | 'always_accept' | 'first_error' | 'ignore_sample' | 'max' | 'worst_error':
    #         parser_unimplemented(f'grader_flags value "{key_grader_flags}"')
    #     case 'avg':
    #         parser_error(f'unsupported grader_flags value "{key_grader_flags}" - this package cannot be migrated')
    #     case _:
    #         parser_error(f'unknown grader_flags value "{key_grader_flags}"')

    print(type(problem_yaml_object))
    print(problem_yaml_object)
