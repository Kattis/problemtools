"""This module handles execution of scripts in the Checktestdata input
verification language (https://github.com/DOMjudge/checktestdata)
"""

import os
from .executable import Executable
from .errors import ProgramError
from .tools import get_tool_path


class Checktestdata(Executable):
    """Wrapper class for running Checktestdata scripts.
    """
    _CTD_PATH = get_tool_path('checktestdata')

    def __init__(self, path):
        """Create a Checktestdata wrapper.

        Args:
            path (str): path to .ctd source file
        """
        if Checktestdata._CTD_PATH is None:
            raise ProgramError(
                'Could not locate the Checktestdata program to run %s' % path)
        super().__init__(Checktestdata._CTD_PATH, args=[path])


    def __str__(self) -> str:
        """String representation"""
        return '%s' % (self.args[0])


    def do_compile(self) -> tuple[bool, str|None]:
        """Syntax-check the Checktestdata script

        Returns:
            (False, None) if the Checktestdata script has syntax errors and
            (True, None) otherwise
        """
        (status, _) = super().run()
        return ((os.WIFEXITED(status) and os.WEXITSTATUS(status) in [0, 1]), None)


    def run(self, infile='/dev/null', outfile='/dev/null',
            errfile='/dev/null', args=None, timelim=1000):
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
        (status, runtime) = super(Checktestdata, self).run(infile=infile,
                                                           outfile=outfile,
                                                           errfile=errfile,
                                                           args=args,
                                                           timelim=timelim)
        # This is ugly, switches the accept exit status and our accept
        # exit status 42.
        if os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0:
            return (42<<8, runtime)
        if os.WIFEXITED(status) and os.WEXITSTATUS(status) == 42:
            return (0, runtime)
        return (status, runtime)
