from typing import Literal

#: A submission's (or testcase's) verdict, e.g. as expected by policy or produced by judging.
Verdict = Literal['AC', 'TLE', 'OLE', 'MLE', 'RTE', 'WA', 'PAC', 'JE']

from .includes import DEFAULT_LANGUAGE, IncludeFile, Includes, LanguageIncludes, load_includes
from .submissions import LegacyPolicy, Submission, Submissions, load_submissions
from .testdata import DEFAULT_CONFIG, SCORING_ONLY_KEYS, TestCase, TestDataGroup, load_testdata
from .validators import DEFAULT_VALIDATOR, InputValidators, OutputValidators, load_input_validators, load_output_validators

__all__ = [
    'DEFAULT_CONFIG',
    'DEFAULT_LANGUAGE',
    'DEFAULT_VALIDATOR',
    'SCORING_ONLY_KEYS',
    'IncludeFile',
    'Includes',
    'InputValidators',
    'LanguageIncludes',
    'LegacyPolicy',
    'OutputValidators',
    'Submission',
    'Submissions',
    'TestCase',
    'TestDataGroup',
    'Verdict',
    'load_includes',
    'load_input_validators',
    'load_output_validators',
    'load_submissions',
    'load_testdata',
]
