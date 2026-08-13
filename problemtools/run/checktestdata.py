"""This module handles execution of scripts in the Checktestdata input
verification language (https://github.com/DOMjudge/checktestdata)
"""

import os
import sys

from .executable import Executable


class Checktestdata(Executable):
    """Wrapper class for running Checktestdata scripts."""

    def __init__(self, path: str):
        """Create a Checktestdata wrapper.

        Args:
            path: path to .ctd source file
        """
        super().__init__(sys.executable, args=['-m', 'checktestdata', path])

    def __str__(self) -> str:
        """String representation"""
        return '%s' % (self.args[-1])

    def do_compile(self) -> tuple[bool, str | None]:
        """Syntax-check the Checktestdata script

        Returns:
            (False, None) if the Checktestdata script has syntax errors and
            (True, None) otherwise
        """
        (status, _) = super().run()
        return ((os.WIFEXITED(status) and os.WEXITSTATUS(status) in [0, 1]), None)

    def run(
        self, infile='/dev/null', outfile='/dev/null', errfile='/dev/null', args=None, timelim=1000, memlim=1024, work_dir=None
    ):
        """Run the Checktestdata script to validate an input file.

        Args:
            infile (str): name of input file to validate
            outfile (str): file name to save stdout of Checktestdata in
            errfile (str): file name to save stderr of Checktestdata in
            args (list of str): additional command-line arguments to
                pass to Checktestdata
            timelim (int): time limit for the Checktestdata process in
                seconds

        Returns:
            tuple (status, runtime):
                status (int): exit status of the validator.
                    WEXITSTATUS(status) will be 42 if and only if
                    Checktestdata accepted the input file.
                runtime (float): runtime of the Checktestdata process
                    in seconds
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
