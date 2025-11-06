import argparse

from .formatversion import FormatVersion


def add_version_arg(parser: argparse.ArgumentParser) -> None:
    """Adds the --version argument to the parser"""
    # setuptools-scm drops a _version file in our package, so read version from there.
    # Fall back to "unknown", e.g., on a dev machine or in CI pipelines where setuptools
    # has not been run
    try:
        from . import _version  # type: ignore

        version = _version.version
    except (ImportError, ModuleNotFoundError, AttributeError):
        version = 'unknown'

    parser.add_argument(
        '--version',
        action='version',
        version=f'%(prog)s {version}. Supports problem format {FormatVersion.LEGACY}, and partial (experimental) support for {FormatVersion.V_2023_07}',
    )
