from typing import Literal

#: A submission's (or testcase's) verdict, e.g. as expected by policy or produced by judging.
Verdict = Literal['AC', 'TLE', 'OLE', 'MLE', 'RTE', 'WA', 'PAC', 'JE']

from .attachments import TEMPLATES_DIRECTORY, Attachments, load_attachments
from .files import BadEntry, BadReason, EntryKind, Files, load_files
from .graders import DEFAULT_GRADER, Graders, load_graders
from .includes import DEFAULT_LANGUAGE, Includes, LanguageIncludes, load_includes
from .problem import Problem, load_problem
from .program_files import ProgramFile, ProgramFiles, load_program_files
from .statements import Statements, load_statements
from .submissions import Submission, Submissions, load_submissions
from .submissions_policy import SubmissionsEntry, SubmissionsPolicy, TimeLimitBound, parse_submissions_yaml
from .testdata import DEFAULT_CONFIG, SCORING_ONLY_KEYS, TestCase, TestDataGroup, load_testdata
from .validators import DEFAULT_VALIDATOR, InputValidators, OutputValidators, load_input_validators, load_output_validators

__all__ = [
    'DEFAULT_CONFIG',
    'DEFAULT_GRADER',
    'DEFAULT_LANGUAGE',
    'DEFAULT_VALIDATOR',
    'SCORING_ONLY_KEYS',
    'TEMPLATES_DIRECTORY',
    'Attachments',
    'BadEntry',
    'BadReason',
    'EntryKind',
    'Files',
    'Graders',
    'Includes',
    'InputValidators',
    'LanguageIncludes',
    'OutputValidators',
    'Problem',
    'ProgramFile',
    'ProgramFiles',
    'Statements',
    'Submission',
    'Submissions',
    'SubmissionsEntry',
    'SubmissionsPolicy',
    'TestCase',
    'TestDataGroup',
    'TimeLimitBound',
    'Verdict',
    'load_attachments',
    'load_files',
    'load_graders',
    'load_includes',
    'load_input_validators',
    'load_output_validators',
    'load_problem',
    'load_program_files',
    'load_statements',
    'load_submissions',
    'load_testdata',
    'parse_submissions_yaml',
]
