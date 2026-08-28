from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..formatversion import FormatVersion
from ..languages import Languages
from ..metadata import Metadata
from ..run import Program, find_programs, get_tool

#: The problemtools-provided validator used when a problem doesn't ship a custom output validator.
DEFAULT_VALIDATOR = get_tool('default_validator')


@dataclass(frozen=True)
class InputValidators:
    """A problem's input format validators."""

    validators: list[Program] = field(default_factory=list)
    uses_old_path: bool = False


def load_input_validators(probdir: Path, language_config: Languages) -> InputValidators:
    old_path = probdir / 'input_format_validators'
    uses_old_path = old_path.is_dir()
    validators_path = old_path if uses_old_path else probdir / 'input_validators'
    validators = find_programs(str(validators_path), language_config=language_config, allow_validation_script=True)
    return InputValidators(validators=validators, uses_old_path=uses_old_path)


@dataclass(frozen=True)
class OutputValidators:
    """A problem's output validators: custom validator programs found on disk, if any."""

    validators: list[Program] = field(default_factory=list)

    def uses_default(self, format_version: FormatVersion, metadata: Metadata) -> bool:
        """Whether the default validator is used, rather than a custom one."""
        if format_version is FormatVersion.LEGACY:
            return metadata.legacy_validation == 'default'
        return not self.validators

    def select(self, format_version: FormatVersion, metadata: Metadata) -> Program | None:
        """The output validator that will actually be used, or None if the default validator
        is required but not available on this problemtools install."""
        if self.uses_default(format_version, metadata) or not self.validators:
            return DEFAULT_VALIDATOR
        return self.validators[0]


def load_output_validators(probdir: Path, format_version: FormatVersion, language_config: Languages) -> OutputValidators:
    validators = find_programs(str(probdir / format_version.output_validator_directory), language_config=language_config)
    return OutputValidators(validators=validators)
