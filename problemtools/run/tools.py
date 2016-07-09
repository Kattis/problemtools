import os
from .executable import Executable

def get_tool_path(name):
    """Find the path to one of problemtools' external tools.

    Args:
        name (str): which tool is wanted (one of [default_grader,
            default_validator, interactive, checktestdata, viva.sh])

    Returns:
        str, path to the tool, or None if the tool was not found.
    """
    return __locate_executable([os.path.join(os.path.dirname(__file__),
                                             '..', 'support', name),
                                os.path.join(os.path.dirname(__file__),
                                             '..', '..', 'support',
                                             os.path.splitext(name)[0], name)])


def get_tool(name):
    """Get an Executable instance for one of problemtools' external tools.

    Args:
        name(str): same as for get_tool_path

    Returns:
        problemtools.run.Executable object for the tool, or None if
        the tool was not found.
    """
    path = get_tool_path(name)
    return Executable(path) if path is not None else None


def __locate_executable(candidate_paths):
    """Find executable among a set of paths.

    Args:
        candidate_paths (list of str): list of locations in which to
            look for an executable file.

    Returns:
        str, first entry of candidate_paths that is an executable
            file, or None if no such entry.
    """
    return next((p for p in candidate_paths
                 if os.path.isfile(p) and os.access(p, os.X_OK)), None)
