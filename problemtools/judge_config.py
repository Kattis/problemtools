"""Configuration describing what the judge system problems are verified against supports.

Loaded from judge.yaml, with the same override paths as languages.yaml. All fields
are optional and permissive by default, so a config only needs to list what it restricts.
"""

from pathlib import Path

import pydantic
from pydantic import BaseModel, ConfigDict

from . import config


class LimitMaxima(BaseModel):
    """Maximum values for problem.yaml limits. Same keys and units as there. None means unchecked."""

    memory: int | None = None
    output: int | None = None
    code: int | None = None
    compilation_time: int | None = None
    compilation_memory: int | None = None
    validation_time: int | None = None
    validation_memory: int | None = None
    validation_output: int | None = None

    model_config = ConfigDict(extra='forbid')


class JudgeConfig(BaseModel):
    enabled: bool = True
    name: str = 'your judge system'
    limits: LimitMaxima = LimitMaxima()
    max_shortname_length: int | None = None  # length of the problem package directory name
    max_file_size: int | None = None  # MiB, any file in the package
    max_testdata_size: int | None = None  # MiB, de-duplicated test data .in and .ans files
    integer_time_limit: bool = False
    allow_minimization: bool = True
    allow_negative_scores: bool = True

    model_config = ConfigDict(extra='forbid')


def load_judge_config(probdir_parent: Path) -> JudgeConfig:
    """Load judge configuration.

    :raises config.ConfigError: if the configuration is invalid.
    """
    data = config.load_config('judge.yaml', [probdir_parent])
    try:
        return JudgeConfig.model_validate(data)
    except pydantic.ValidationError as e:
        raise config.ConfigError(f'Invalid judge configuration (judge.yaml): {e}') from e
