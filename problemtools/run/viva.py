"""This module handles execution of scripts in the VIVA input
verification language (http://viva.vanb.org/).
"""

import os
from .executable import Executable
from .errors import ProgramError
from .tools import get_tool_path


class Viva(Executable):
    """Wrapper class for running VIVA scripts.
    """
    _VIVA_PATH = get_tool_path('viva.sh')

    def __init__(self, path):
        """Create a VIVA wrapper.

        Args:
            path (str): path to .viva source file
        """
        if Viva._VIVA_PATH is None:
            raise ProgramError(
                'Could not locate the VIVA program to run %s' % path)
        super().__init__(Viva._VIVA_PATH, args=[path])


    def __str__(self):
        """String representation"""
        return '%s' % (self.args[0])


    def do_compile(self) -> tuple[bool, str|None]:
        """Syntax-check the VIVA script

        Returns:
            (False, None) if the VIVA script has syntax errors and (True, None) otherwise
        """
        (status, _) = super().run()
        return ((os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0), None)


    def run(self, infile='/dev/null', outfile='/dev/null',
            errfile='/dev/null', args=None, timelim=1000):
        """Run the VIVA script to validate an input file.

        Args:
            infile (str): name of input file to validate
            outfile (str): file name to save stdout of VIVA in
            errfile (str): file name to save stderr of VIVA in
            args (list of str): additional command-line arguments to
                pass to VIVA
            timelim (int): time limit for the VIVA process in seconds

        Returns:
            tuple (status, runtime):
                status (int): exit status of the validator.
                    WEXITSTATUS(status) will be 42 if and only if VIVA
                    accepted the input file.
                runtime (float): runtime of the VIVA process in seconds
        """
        if args is None:
            args = []
        # VIVA takes input as argument and not on stdin
        if infile != '/dev/null':
            args = args + [infile]

        (status, runtime) = super(Viva, self).run(outfile=outfile,
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
