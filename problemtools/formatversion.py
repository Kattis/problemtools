import os
import yaml
from dataclasses import dataclass


VERSION_LEGACY = "legacy"
VERSION_2023_07 = "2023-07"


@dataclass(frozen=True)
class FormatData:
    """
    A class containing data specific to the format version.
    name: the version name.
    statement_directory: the directory where the statements should be found.
    """
    name: str
    statement_directory: str


FORMAT_DATACLASSES = {
    VERSION_LEGACY: FormatData(name=VERSION_LEGACY, statement_directory="problem_statement"),
    VERSION_2023_07: FormatData(name=VERSION_2023_07, statement_directory="statement")
}


def detect_problem_version(path) -> str:
    """
    Returns the problem version value of problem.yaml or throws an error if it is unable to read the file.
    Args:
        path: the problem path

    Returns:
        the version name as a String

    """
    config_path = os.path.join(path, 'problem.yaml')
    try:
        with open(config_path) as f:
            config: dict = yaml.safe_load(f) or {}
    except Exception as e:
        raise VersionError(f"Error reading problem.yaml: {e}")
    return config.get('problem_format_version', VERSION_LEGACY)


def get_format_data(path):
    """
    Gets the dataclass object containing the necessary data for a problem format.
    Args:
        path: the problem path

    Returns:
        the dataclass object containing the necessary data for a problem format

    """
    return get_format_data_by_name(detect_problem_version(path))


def get_format_data_by_name(name):
    """
    Gets the dataclass object containing the necessary data for a problem format given the format name.
    Args:
        name: the format name

    Returns:
        the dataclass object containing the necessary data for a problem format

    """
    data = FORMAT_DATACLASSES.get(name)
    if not data:
        raise VersionError(f"No version found with name {name}")
    else:
        return data


class VersionError(Exception):
    pass

