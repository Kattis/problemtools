import os
import yaml
from dataclasses import dataclass


VERSION_LEGACY = "legacy"
VERSION_2023_07 = "2023-07"


@dataclass(frozen=True)
class FormatData:
    name: str
    statement_directory: str
    statement_extensions: list[str]


FORMAT_DATACLASSES = {
    VERSION_LEGACY: FormatData(name=VERSION_LEGACY, statement_directory="problem_statement", statement_extensions=["tex"]),
    VERSION_2023_07: FormatData(name=VERSION_2023_07, statement_directory="statement", statement_extensions=["md", "tex"])
}


"""
Returns the problem version value of problem.yaml or throws an error if it is unable to read the file.
"""
def detect_problem_version(path) -> str:
    config_path = os.path.join(path, 'problem.yaml')
    try:
        with open(config_path) as f:
            config: dict = yaml.safe_load(f) or {}
    except Exception as e:
        raise VersionError(f"Error reading problem.yaml: {e}")
    return config.get('problem_format_version', VERSION_LEGACY)


"""
Returns a dataclass containing the necessary data for a file format.
"""
def get_format_data(path):
    version = detect_problem_version(path)
    data = FORMAT_DATACLASSES[version]
    if not data:
        raise VersionError(f"No version found with name {version}")
    else:
        return data


"""
Returns a dataclass containing the necessary data for a file format given the format's name. 
"""
def get_format_data_by_name(name):
    data = FORMAT_DATACLASSES.get(name)
    if not data:
        raise VersionError(f"No version found with name {name}")
    else:
        return data


class VersionError(Exception):
    pass

