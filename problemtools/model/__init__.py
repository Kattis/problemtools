from typing import Literal

#: A submission's (or testcase's) verdict, e.g. as expected by policy or produced by judging.
Verdict = Literal['AC', 'TLE', 'OLE', 'MLE', 'RTE', 'WA', 'PAC', 'JE']

from .attachments import Attachments, load_attachments
from .graders import DEFAULT_GRADER, Graders, load_graders
from .includes import DEFAULT_LANGUAGE, IncludeFile, Includes, LanguageIncludes, load_includes
from .problem import Problem, load_problem
from .statements import Statements, load_statements
from .submissions import LegacyPolicy, Submission, Submissions, load_submissions
from .testdata import DEFAULT_CONFIG, SCORING_ONLY_KEYS, TestCase, TestDataGroup, load_testdata
from .validators import DEFAULT_VALIDATOR, InputValidators, OutputValidators, load_input_validators, load_output_validators

__all__ = [
    'DEFAULT_CONFIG',
    'DEFAULT_GRADER',
    'DEFAULT_LANGUAGE',
    'DEFAULT_VALIDATOR',
    'SCORING_ONLY_KEYS',
    'Attachments',
    'Graders',
    'IncludeFile',
    'Includes',
    'InputValidators',
    'LanguageIncludes',
    'LegacyPolicy',
    'OutputValidators',
    'Problem',
    'Statements',
    'Submission',
    'Submissions',
    'TestCase',
    'TestDataGroup',
    'Verdict',
    'load_attachments',
    'load_graders',
    'load_includes',
    'load_input_validators',
    'load_output_validators',
    'load_problem',
    'load_statements',
    'load_submissions',
    'load_testdata',
]
