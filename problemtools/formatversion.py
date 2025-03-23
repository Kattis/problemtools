import os

import yaml


def detect_problem_version(path) -> str:
    config_path = os.path.join(path, 'problem.yaml')
    try:
        with open(config_path) as f:
            config: dict = yaml.safe_load(f) or {}
    except Exception as e:
        raise VersionError(f"Error reading problem.yaml: {e}")
    return config.get('problem_format_version', 'legacy')


class FormatVersionData:
    STATEMENT_DIRECTORY = ""
    STATEMENT_EXTENSIONS = []

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

    @staticmethod
    def get_statement_data(path):
        version = detect_problem_version(path)
        if version == "legacy":
            return StatementLegacyData
        elif version == "2023-07":
            return Statement2023_07Data


class StatementLegacyData(FormatVersionData):
    EXTENSIONS = ['tex']
    STATEMENT_DIRECTORY = "problem_statement"
    FORMAT_VERSION = "legacy"
    

class Statement2023_07Data(FormatVersionData):
    EXTENSIONS = ['md', 'tex']
    DIR_END = "statement"
    FORMAT_VERSION = "2023-07"


class VersionError(Exception):
    pass

