from typing import Literal

#: A submission's (or testcase's) verdict, e.g. as expected by policy or produced by judging.
Verdict = Literal['AC', 'TLE', 'OLE', 'MLE', 'RTE', 'WA', 'PAC', 'JE']

from .includes import DEFAULT_LANGUAGE, IncludeFile, Includes, LanguageIncludes, load_includes
from .submissions import LegacyPolicy, Submission, Submissions, load_submissions
from .testdata import TestCase, TestDataGroup, load_testdata

__all__ = [
    'DEFAULT_LANGUAGE',
    'IncludeFile',
    'Includes',
    'LanguageIncludes',
    'LegacyPolicy',
    'Submission',
    'Submissions',
    'TestCase',
    'TestDataGroup',
    'Verdict',
    'load_includes',
    'load_submissions',
    'load_testdata',
]
