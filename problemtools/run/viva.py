"""This module handles execution of scripts in the VIVA input
verification language (http://viva.vanb.org/).
"""

import os
from pathlib import Path

from .errors import ProgramError
from .executable import Executable
from .program import CompileResult, Program
from .tools import get_tool_path


class Viva(Program):
    """Wrapper class for running VIVA scripts."""

    _VIVA_PATH = get_tool_path('viva.sh')

    def __init__(self, path: Path) -> None:
        """Create a VIVA wrapper.

        Args:
            path: path to .viva source file
        """
        if Viva._VIVA_PATH is None:
            raise ProgramError(f'Could not locate the VIVA program to run {path}')
        super().__init__(name=path.name)
        # VIVA takes input as argument and not on stdin, and exits with 0 on
        # accept, so swap that with our accept exit status 42.
        self._executable = Executable(
            path.name,
            Viva._VIVA_PATH,
            args=[str(path)],
            skip_memory_rlimit=True,
            swap_exit_codes=True,
            infile_as_arg=True,
        )

    def _do_compile(self, work_dir: Path) -> CompileResult:
        """Syntax-check the VIVA script"""
        (status, _) = self._executable.run()
        # Without an input file, VIVA only checks the script, and accepts (42 after swapping) if the syntax is fine.
        if os.WIFEXITED(status) and os.WEXITSTATUS(status) == 42:
            return CompileResult(executable=self._executable)
        return CompileResult(errmsg='VIVA syntax check failed')
