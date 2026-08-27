"""This module handles execution of scripts in the Checktestdata input
verification language (https://github.com/DOMjudge/checktestdata)
"""

import os
import sys
from pathlib import Path

from .executable import Executable
from .program import CompileResult


class Checktestdata(Executable):
    """Wrapper class for running Checktestdata scripts."""

    def __init__(self, path: str) -> None:
        """Create a Checktestdata wrapper.

        Args:
            path: path to .ctd source file
        """
        super().__init__(sys.executable, args=['-m', 'checktestdata', path], name=os.path.basename(path))

    def do_compile(self, work_dir: Path) -> CompileResult:
        """Syntax-check the Checktestdata script"""
        (status, _) = super().run()
        success = os.WIFEXITED(status) and os.WEXITSTATUS(status) in [0, 1]
        return CompileResult(success, None, self.path)

    def run(
        self,
        infile: str = '/dev/null',
        outfile: str = '/dev/null',
        errfile: str = '/dev/null',
        args: list[str] | None = None,
        timelim: int = 1000,
        memlim: int = 1024,
        work_dir: Path | None = None,
    ) -> tuple[int, float]:
        """Run the Checktestdata script to validate an input file.

        Args:
            infile: name of input file to validate
            outfile: file name to save stdout of Checktestdata in
            errfile: file name to save stderr of Checktestdata in
            args: additional command-line arguments to pass to Checktestdata
            timelim: time limit for the Checktestdata process in seconds

        Returns:
            tuple (status, runtime):
                status: exit status of the validator.
                    WEXITSTATUS(status) will be 42 if and only if
                    Checktestdata accepted the input file.
                runtime: runtime of the Checktestdata process in seconds
        """
        (status, runtime) = super().run(
            infile=infile, outfile=outfile, errfile=errfile, args=args, timelim=timelim, memlim=memlim, work_dir=work_dir
        )
        # This is ugly, switches the accept exit status and our accept
        # exit status 42.
        if os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0:
            return (42 << 8, runtime)
        if os.WIFEXITED(status) and os.WEXITSTATUS(status) == 42:
            return (0, runtime)
        return (status, runtime)
