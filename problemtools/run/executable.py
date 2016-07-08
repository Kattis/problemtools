"""
Implementation of programs provided by an executable file.
"""
import os
from program import Program
from errors import ProgramError

class Executable(Program):
    """Class for executable files.
    """
    def __init__(self, path, args=None):
        """Instantiate executable object.

        Args:
            path (str): path to the executable file.  Must be a file,
                and must be executable.
            args: list of additional command line arguments that
                should be passed to the program every time it is executed.
        """
        if not os.path.isfile(path) or not os.access(path, os.X_OK):
            raise ProgramError('%s is not an executable program' % path)
        self.path = path
        self.args = args if args is not None else []

    def __str__(self):
        """String representation"""
        return 'Executable(%s)' % (self.path)

    def compile(self):
        """Dummy implementation of the compile method -- nothing to check!
        """
        return True

    def get_runcmd(self):
        """Command to run the program.
        """
        return [self.path] + self.args


def locate_executable(candidate_paths):
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
