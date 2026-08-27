"""This module handles execution of scripts in the VIVA input
verification language (http://viva.vanb.org/).
"""

import os
from pathlib import Path

from .errors import ProgramError
from .executable import Executable
from .program import CompileResult
from .tools import get_tool_path


class Viva(Executable):
    """Wrapper class for running VIVA scripts."""

    _VIVA_PATH = get_tool_path('viva.sh')

    def __init__(self, path: str) -> None:
        """Create a VIVA wrapper.

        Args:
            path: path to .viva source file
        """
        if Viva._VIVA_PATH is None:
            raise ProgramError(f'Could not locate the VIVA program to run {path}')
        super().__init__(Viva._VIVA_PATH, args=[path], name=os.path.basename(path))

    def do_compile(self, work_dir: Path) -> CompileResult:
        """Syntax-check the VIVA script"""
        (status, _) = super().run()
        success = os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
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
        """Run the VIVA script to validate an input file.

        Args:
            infile: name of input file to validate
            outfile: file name to save stdout of VIVA in
            errfile: file name to save stderr of VIVA in
            args: additional command-line arguments to pass to VIVA
            timelim: time limit for the VIVA process in seconds

        Returns:
            tuple (status, runtime):
                status: exit status of the validator.
                    WEXITSTATUS(status) will be 42 if and only if VIVA
                    accepted the input file.
                runtime: runtime of the VIVA process in seconds
        """
        if args is None:
            args = []
        # VIVA takes input as argument and not on stdin
        if infile != '/dev/null':
            args = args + [infile]

        (status, runtime) = super().run(
            outfile=outfile, errfile=errfile, args=args, timelim=timelim, memlim=memlim, work_dir=work_dir
        )
        # This is ugly, switches the accept exit status and our accept
        # exit status 42.
        if os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0:
            return (42 << 8, runtime)
        if os.WIFEXITED(status) and os.WEXITSTATUS(status) == 42:
            return (0, runtime)
        return (status, runtime)
