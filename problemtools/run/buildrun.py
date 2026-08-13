"""
Implementation of programs provided by a directory with build/run scripts.
"""

import logging
import os
import subprocess
import tempfile

from . import rutil
from .errors import ProgramError
from .program import Program

log = logging.getLogger(__file__)


class BuildRun(Program):
    """Class for build/run-script program."""

    def __init__(self, path: str, work_dir: str):
        """Instantiate BuildRun object.

        Args:
            path: directory containing the build script.
            work_dir: name of temp directory in which to run the scripts.
        """
        super().__init__()

        if not os.path.isdir(path):
            raise ProgramError('%s is not a directory' % path)

        if path[-1] == '/':
            path = path[:-1]
        self.name = os.path.basename(path)
        self.path = os.path.join(work_dir, self.name)
        if os.path.exists(self.path):
            self.path = tempfile.mkdtemp(prefix='%s-' % self.name, dir=work_dir)
        else:
            os.makedirs(self.path)

        rutil.add_files(path, self.path)

        build = os.path.join(self.path, 'build')
        if not os.path.isfile(build):
            raise ProgramError('%s does not have a build script' % path)
        if not os.access(build, os.X_OK):
            raise ProgramError('%s/build is not executable' % path)

    def __str__(self) -> str:
        """String representation"""
        return '%s/' % (self.path)

    def do_compile(self) -> tuple[bool, str | None]:
        """Run the build script."""
        with open(os.devnull, 'w') as devnull:
            status = subprocess.call(['./build'], stdout=devnull, stderr=devnull, cwd=self.path)
        run = os.path.join(self.path, 'run')

        if status:
            logging.debug('Build script failed (status %d) when compiling %s\n', status, self.name)
            return (False, 'build script failed with exit code %d' % (status))
        elif not os.path.isfile(run) or not os.access(run, os.X_OK):
            return (False, 'build script did not produce an executable called "run"')
        else:
            return (True, None)

    def get_runcmd(self, cwd=None, memlim=None) -> list[str]:
        """Run command for the program.

        Args:
            cwd (str): if not None, the run command is provided
                relative to cwd (otherwise absolute paths are given).
        """
        path = self.path if cwd is None else os.path.relpath(self.path, cwd)
        return [os.path.join(path, 'run')]

    def should_skip_memory_rlimit(self) -> bool:
        """Ugly hack (see program.py for details)."""
        return True
