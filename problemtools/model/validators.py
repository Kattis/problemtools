from __future__ import annotations

from dataclasses import dataclass, field

from ..formatversion import FormatVersion
from ..languages import Languages
from ..metadata import Metadata
from ..run import BuildRun, Program, SourceCode, get_tool
from .files import Files
from .programs import as_source_or_buildrun, find_programs

#: The problemtools-provided validator used when a problem doesn't ship a custom output validator.
DEFAULT_VALIDATOR = get_tool('default_validator')


@dataclass(frozen=True)
class InputValidators:
    """A problem's input format validators."""

    validators: list[Program] = field(default_factory=list)


def load_input_validators(files: Files, language_config: Languages) -> InputValidators:
    # input_format_validators is a deprecated name for input_validators. We just load
    # from both and let _check_root_directory_names warn about the deprecated directory
    validators = [
        program
        for directory in ('input_format_validators', 'input_validators')
        for program in find_programs(files, files.root / directory, language_config=language_config, allow_validation_script=True)
    ]
    return InputValidators(validators=validators)


@dataclass(frozen=True)
class OutputValidators:
    """A problem's output validators: custom validator programs found on disk, if any."""

    validators: list[SourceCode | BuildRun] = field(default_factory=list)

    def uses_default(self, format_version: FormatVersion, metadata: Metadata) -> bool:
        """Whether the default validator is used, rather than a custom one."""
        if format_version is FormatVersion.LEGACY:
            return metadata.legacy_validation == 'default'
        return not self.validators

    def select(self, format_version: FormatVersion, metadata: Metadata) -> Program:
        """The output validator that will actually be used."""
        if self.uses_default(format_version, metadata) or not self.validators:
            return DEFAULT_VALIDATOR
        return self.validators[0]


def load_output_validators(files: Files, format_version: FormatVersion, language_config: Languages) -> OutputValidators:
    validators = as_source_or_buildrun(
        find_programs(files, files.root / format_version.output_validator_directory, language_config=language_config)
    )
    return OutputValidators(validators=validators)
