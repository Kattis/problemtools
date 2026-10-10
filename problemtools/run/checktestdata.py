"""This module handles execution of scripts in the Checktestdata input
verification language (https://github.com/DOMjudge/checktestdata)
"""

import os
import sys
from pathlib import Path

from .executable import Executable
from .program import CompileResult, Program


class Checktestdata(Program):
    """Wrapper class for running Checktestdata scripts."""

    def __init__(self, path: Path) -> None:
        """Create a Checktestdata wrapper.

        Args:
            path: path to .ctd source file
        """
        super().__init__(name=path.name)
        # Checktestdata exits with 0 on accept, so swap that with our accept exit status 42.
        self._executable = Executable(
            path.name,
            Path(sys.executable),
            args=['-m', 'checktestdata', str(path)],
            skip_memory_rlimit=True,
            swap_exit_codes=True,
        )

    def _do_compile(self, work_dir: Path) -> CompileResult:
        """Syntax-check the Checktestdata script"""
        (status, _) = self._executable.run()
        # Checktestdata accepting (42 after swapping) or rejecting (1) the empty input both mean the syntax is fine.
        if os.WIFEXITED(status) and os.WEXITSTATUS(status) in [42, 1]:
            return CompileResult(executable=self._executable)
        return CompileResult(errmsg='Checktestdata syntax check failed')
