"""
Implementation of programs provided by an executable file.
"""

import os
from pathlib import Path

from .errors import ProgramError
from .program import Program


class Executable(Program):
    """Class for executable files."""

    def __init__(self, path: str, args: list[str] | None = None, name: str | None = None) -> None:
        """Instantiate executable object.

        Args:
            path: path to the executable file.  Must be a file,
                and must be executable.
            args: list of additional command line arguments that
                should be passed to the program every time it is executed.
            name: name to use for the program.  Defaults to the basename of path.
        """
        if not os.path.isfile(path) or not os.access(path, os.X_OK):
            raise ProgramError(f'{path} is not an executable program')
        super().__init__(name=name if name is not None else os.path.basename(path), path=Path(path))
        self.args = args if args is not None else []

    def get_runcmd(self, cwd: str | None = None, memlim: int = 1024) -> list[str]:
        """Command to run the program."""
        return [str(self.path)] + self.args

    def should_skip_memory_rlimit(self) -> bool:
        """Ugly hack (see program.py for details)."""
        return True
