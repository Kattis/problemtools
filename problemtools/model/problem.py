"""Model for a whole problem package: the aggregate of all its parts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..diagnostics import Diagnostics, VerifyError
from ..formatversion import FormatVersion
from ..languages import Languages, load_language_config
from ..metadata import Metadata, load_metadata
from .attachments import Attachments, load_attachments
from .graders import Graders, load_graders
from .includes import Includes, load_includes
from .statements import Statements, load_statements
from .submissions import Submissions, load_submissions
from .testdata import TestDataGroup, load_testdata
from .validators import InputValidators, OutputValidators, load_input_validators, load_output_validators


@dataclass(frozen=True)
class Problem:
    """A statically loaded problem package.

    Loading is static parsing with very little verification (it does not, e.g.,
    compile validators or run submissions) -- see the `checks` package for the
    checks that should be run on top of a loaded Problem.
    """

    probdir: Path
    language_config: Languages
    metadata: Metadata
    statements: Statements
    attachments: Attachments
    input_validators: InputValidators
    output_validators: OutputValidators
    graders: Graders
    testdata: TestDataGroup
    includes: Includes
    submissions: Submissions

    @property
    def shortname(self) -> str:
        return self.probdir.name

    @property
    def format_version(self) -> FormatVersion:
        return self.metadata.problem_format_version


def load_problem(probdir: Path, diag: Diagnostics) -> Problem:
    """Loads a problem package from probdir.

    On failure, reports errors via `diag` and raises VerifyError.
    """
    try:
        language_config = load_language_config(probdir.parent)
        problem_metadata = load_metadata(probdir)
        format_version = problem_metadata.problem_format_version

        includes = load_includes(probdir, language_config)
        return Problem(
            probdir=probdir,
            language_config=language_config,
            metadata=problem_metadata,
            statements=load_statements(probdir, format_version),
            attachments=load_attachments(probdir),
            input_validators=load_input_validators(probdir, language_config),
            output_validators=load_output_validators(probdir, format_version, language_config),
            graders=load_graders(probdir, language_config),
            testdata=load_testdata(probdir, problem_metadata),
            includes=includes,
            # Submissions need includes, so includes must be loaded first.
            submissions=load_submissions(probdir, language_config, includes),
        )
    except VerifyError:
        # A loader already reported its own diagnostic; don't double-report.
        raise
    except Exception as e:
        diag.fatal(f'Failed to load problem: {e}')
