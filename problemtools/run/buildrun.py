"""
Implementation of programs provided by a directory with build/run scripts.
"""

import os
import tempfile

import logging

from .errors import ProgramError
from .program import Program
from . import rutil


class BuildRun(Program):
    """Class for build/run-script program.
    """

    def __init__(self, path, work_dir=None):
        """Instantiate BuildRun object.

        Args:
            path (str): directory containing the build script.
            work_dir (str): name of temp directory in which to run the
                scripts (if None, will make new temp directory).
        """
        if not os.path.isdir(path):
            raise ProgramError('%s is not a directory' % path)

        build = os.path.join(path, 'build')
        if not os.path.isfile(build):
            raise ProgramError('%s does not have a build script' % path)
        if not os.access(build, os.X_OK):
            raise ProgramError('%s/build is not executable' % path)

        if work_dir is None:
            work_dir = tempfile.mkdtemp()

        if path[-1] == '/':
            path = path[:-1]
        self.name = os.path.basename(path)
        self.path = os.path.join(work_dir, self.name)
        if os.path.exists(self.path):
            self.path = tempfile.mkdtemp(prefix='%s-' % self.name, dir=work_dir)
        else:
            os.makedirs(self.path)

        rutil.add_files(path, self.path)


    def __str__(self):
        """String representation"""
        return '%s/' % (self.path)


    _compile_result = None
    def compile(self):
        """Run the build script."""
        if self._compile_result is not None:
            return self._compile_result

        command = 'cd "%s" && ./build > /dev/null 2> /dev/null' % self.path
        status = os.system(command)

        if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
            logging.debug('Build script failed (status %d) when compiling %s\n        Command used:\n%s', status, self.name, command)
            self._compile_result = False
            return False

        run = os.path.join(self.path, 'run')
        if not os.path.isfile(run) or not os.access(run, os.X_OK):
            logging.error('build script for directory %s did not produce an executable called "run"', self.name)
            self._compile_result = False
            return False

        self._compile_result = True
        return True


    def get_runcmd(self, cwd=None):
        """Run command for the program.

        Args:
            cwd (str): if not None, the run command is provided
                relative to cwd (otherwise absolute paths are given).
        """
        path = self.path if cwd is None else os.path.relpath(self.path, cwd)
        return [os.path.join(path, 'run')]
