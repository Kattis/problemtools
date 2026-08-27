"""
Implementation of programs provided by a directory with build/run scripts.
"""

import os
import subprocess
import tempfile
from pathlib import Path

from . import rutil
from .errors import ProgramError
from .program import CompileResult, Program


class BuildRun(Program):
    """Class for build/run-script program."""

    def __init__(self, path: str) -> None:
        """Instantiate BuildRun object.

        Args:
            path: directory containing the build script.
        """
        if not os.path.isdir(path):
            raise ProgramError(f'{path} is not a directory')

        if path[-1] == '/':
            path = path[:-1]
        name = os.path.basename(path)
        super().__init__(name=name)
        self._source_path = path

    def do_compile(self, work_dir: Path) -> CompileResult:
        """Set up the compile work-space (copying the build script and friends into
        work_dir) and run the build script."""
        name = self.name
        run_path = work_dir / name
        if os.path.exists(run_path):
            run_path = Path(tempfile.mkdtemp(prefix=f'{name}-', dir=work_dir))
        else:
            os.makedirs(run_path)
        self._path = run_path

        rutil.add_files(self._source_path, self.path)

        build = os.path.join(self.path, 'build')
        if not os.path.isfile(build):
            raise ProgramError(f'{self._source_path} does not have a build script')
        if not os.access(build, os.X_OK):
            raise ProgramError(f'{self._source_path}/build is not executable')

        try:
            subprocess.check_output(['./build'], stderr=subprocess.STDOUT, cwd=self.path)
        except subprocess.CalledProcessError as err:
            return CompileResult(False, err.output.decode('utf8', 'replace'), self.path)

        run = os.path.join(self.path, 'run')
        if not os.path.isfile(run) or not os.access(run, os.X_OK):
            return CompileResult(False, 'build script did not produce an executable called "run"', self.path)
        return CompileResult(True, None, self.path)

    def get_runcmd(self, cwd: str | None = None, memlim: int = 1024) -> list[str]:
        """Run command for the program.

        Must not be called until compile() has been called.

        Args:
            cwd: if not None, the run command is provided
                relative to cwd (otherwise absolute paths are given).
        """
        path = self.path if cwd is None else os.path.relpath(self.path, cwd)
        return [os.path.join(path, 'run')]

    def should_skip_memory_rlimit(self) -> bool:
        """Ugly hack (see program.py for details)."""
        return True
