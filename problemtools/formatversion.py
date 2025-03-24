import os
import yaml


"""
The data specific to any given format version.
"""
FORMAT_DATA = {
    "legacy": {
        "name": "legacy",
        "statement_directory": "problem_statement",
        "statement_extensions": ["tex"]
    },
    "2023-07": {
        "name": "2023-07",
        "statement_directory": "statement",
        "statement_extensions": ["md", "tex"],
    }
}

VERSION_LEGACY = "legacy"
VERSION_2023_07 = "2023-07"


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
    return config.get('problem_format_version', 'legacy')


"""
Returns a dictionary containing the necessary data for a file format.
"""
def get_format_data(path):
    version = detect_problem_version(path)
    data = FORMAT_DATA.get(version)
    if not data:
        raise VersionError(f"No version found with name {version}")
    else:
        return data


"""
Returns a dictionary containing the necessary data for a file format given the format's name. 
"""
def get_format_data_by_name(name):
    data = FORMAT_DATA.get(name)
    if not data:
        raise VersionError(f"No version found with name {name}")
    else:
        return data

class VersionError(Exception):
    pass

