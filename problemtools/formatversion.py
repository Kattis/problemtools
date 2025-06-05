import yaml
from enum import StrEnum
from pathlib import Path


class FormatVersion(StrEnum):
    LEGACY = 'legacy'
    V_2023_07 = '2023-07-draft'  # When 2023-07 is finalized, replace this and update _missing_

    @property
    def statement_directory(self) -> str:
        match self:
            case FormatVersion.LEGACY:
                return 'problem_statement'
            case FormatVersion.V_2023_07:
                return 'statement'

    @property
    def statement_extensions(self) -> list[str]:
        match self:
            case FormatVersion.LEGACY:
                return ['tex']
            case FormatVersion.V_2023_07:
                return ['md', 'tex']

    @property
    def output_validator_directory(self) -> str:
        match self:
            case FormatVersion.LEGACY:
                return 'output_validators'
            case FormatVersion.V_2023_07:
                return 'output_validator'

    # Support 2023-07 and 2023-07-draft strings.
    # This method should be replaced with an alias once we require python 3.13
    @classmethod
    def _missing_(cls, value):
        if value == '2023-07':
            return cls.V_2023_07
        return None


def get_format_version(problem_root: Path) -> FormatVersion:
    """Loads the version from the problem in problem_root"""
    with open(problem_root / 'problem.yaml') as f:
        config: dict = yaml.safe_load(f) or {}
    return FormatVersion(config.get('problem_format_version', FormatVersion.LEGACY))
