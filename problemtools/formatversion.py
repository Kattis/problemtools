import os
import yaml


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
Returns a FormatVersionData object based on the format version found in problem.yaml
"""

def get_format_version_data_by_dir(path):
    version = detect_problem_version(path)
    return get_format_version_data_by_name(version)


"""
Returns a FormatVersionData object based on the format version found in problem.yaml
"""

def get_format_version_data_by_name(version_name):
    if version_name == "legacy":
        return DataLegacy()
    elif version_name == "2023-07":
        return Data2023_07()
    else:
        raise VersionError(f"Unknown version {version_name}")


"""
A superclass for all the format version-specific variables and information
"""
class FormatVersionData:
    FORMAT_VERSION = ""
    STATEMENT_DIRECTORY = ""
    STATEMENT_EXTENSIONS = []

    def get_format_version(self):
        if self.FORMAT_VERSION == "":
            raise NotImplementedError()
        else:
            return self.FORMAT_VERSION

    def get_statement_directory(self):
        if self.STATEMENT_DIRECTORY == "":
            raise NotImplementedError()
        else:
            return self.STATEMENT_DIRECTORY

    def get_statement_extensions(self):
        if not self.STATEMENT_EXTENSIONS:
            raise NotImplementedError()
        else:
            return self.STATEMENT_EXTENSIONS


class DataLegacy(FormatVersionData):
    FORMAT_VERSION = "legacy"
    STATEMENT_DIRECTORY = "problem_statement"
    STATEMENT_EXTENSIONS = ['tex']


class Data2023_07(FormatVersionData):
    FORMAT_VERSION = "2023-07"
    STATEMENT_DIRECTORY = "statement"
    STATEMENT_EXTENSIONS = ['md', 'tex']


class VersionError(Exception):
    pass

