"""
Implementation of programs provided by an executable file.
"""

import os

from .errors import ProgramError
from .program import Program


class Executable(Program):
    """Class for executable files."""

    def __init__(self, path: str, args: list[str] | None = None):
        """Instantiate executable object.

        Args:
            path: path to the executable file.  Must be a file,
                and must be executable.
            args: list of additional command line arguments that
                should be passed to the program every time it is executed.
        """
        super().__init__()

        if not os.path.isfile(path) or not os.access(path, os.X_OK):
            raise ProgramError('%s is not an executable program' % path)
        self.path = path
        self.args = args if args is not None else []

    def __str__(self):
        """String representation"""
        return '%s' % (self.path)

    def get_runcmd(self, cwd=None, memlim=None):
        """Command to run the program."""
        return [self.path] + self.args

    def should_skip_memory_rlimit(self):
        """Ugly hack (see program.py for details)."""
        return True
