"""
Implementation of programs provided by a directory with build/run scripts.
"""

import os
import subprocess
import tempfile

from . import rutil
from .errors import ProgramError
from .program import Program


class BuildRun(Program):
    """Class for build/run-script program."""

    def __init__(self, path: str, work_dir: str) -> None:
        """Instantiate BuildRun object.

        Args:
            path: directory containing the build script.
            work_dir: name of temp directory in which to run the scripts.
        """
        if not os.path.isdir(path):
            raise ProgramError(f'{path} is not a directory')

        if path[-1] == '/':
            path = path[:-1]
        name = os.path.basename(path)
        run_path = os.path.join(work_dir, name)
        if os.path.exists(run_path):
            run_path = tempfile.mkdtemp(prefix=f'{name}-', dir=work_dir)
        else:
            os.makedirs(run_path)
        super().__init__(path=run_path, name=name)

        rutil.add_files(path, self.path)

        build = os.path.join(self.path, 'build')
        if not os.path.isfile(build):
            raise ProgramError(f'{path} does not have a build script')
        if not os.access(build, os.X_OK):
            raise ProgramError(f'{path}/build is not executable')

    def do_compile(self) -> tuple[bool, str | None]:
        """Run the build script."""
        try:
            subprocess.check_output(['./build'], stderr=subprocess.STDOUT, cwd=self.path)
        except subprocess.CalledProcessError as err:
            return (False, err.output.decode('utf8', 'replace'))

        run = os.path.join(self.path, 'run')
        if not os.path.isfile(run) or not os.access(run, os.X_OK):
            return (False, 'build script did not produce an executable called "run"')
        return (True, None)

    def get_runcmd(self, cwd: str | None = None, memlim: int = 1024) -> list[str]:
        """Run command for the program.

        Args:
            cwd: if not None, the run command is provided
                relative to cwd (otherwise absolute paths are given).
        """
        path = self.path if cwd is None else os.path.relpath(self.path, cwd)
        return [os.path.join(path, 'run')]

    def should_skip_memory_rlimit(self) -> bool:
        """Ugly hack (see program.py for details)."""
        return True
