import os
from pathlib import Path

from .executable import Executable

_PACKAGE_DIR = Path(__file__).parent.parent


def get_tool_path(name: str) -> Path | None:
    """Find the path to one of problemtools' external tools.

    Args:
        name: which tool is wanted (one of [default_grader,
            default_validator, interactive, checktestdata, viva.sh])

    Returns:
        path to the tool, or None if the tool was not found.
    """
    return __locate_executable(
        [
            _PACKAGE_DIR / 'support' / name,
            _PACKAGE_DIR.parent / 'support' / Path(name).stem / name,
        ]
    )


def get_tool(name: str) -> Executable | None:
    """Get an Executable instance for one of problemtools' external tools.

    Args:
        name: same as for get_tool_path

    Returns:
        problemtools.run.Executable object for the tool, or None if
        the tool was not found.
    """
    path = get_tool_path(name)
    return Executable(path) if path is not None else None


def __locate_executable(candidate_paths: list[Path]) -> Path | None:
    """Find executable among a set of paths.

    Args:
        candidate_paths: list of locations in which to look for an
            executable file.

    Returns:
        first entry of candidate_paths that is an executable file, or
        None if no such entry.
    """
    return next((p for p in candidate_paths if p.is_file() and os.access(p, os.X_OK)), None)
