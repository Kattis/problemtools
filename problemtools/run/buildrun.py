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

    def __init__(self, path: Path) -> None:
        """Instantiate BuildRun object.

        Args:
            path: directory containing the build script.
        """
        if not path.is_dir():
            raise ProgramError(f'{path} is not a directory')

        super().__init__(name=path.name)
        self._source_path = path

    def do_compile(self, work_dir: Path) -> CompileResult:
        """Set up the compile work-space (copying the build script and friends into
        work_dir) and run the build script."""
        name = self.name
        run_path = work_dir / name
        if run_path.exists():
            run_path = Path(tempfile.mkdtemp(prefix=f'{name}-', dir=work_dir))
        else:
            run_path.mkdir(parents=True)
        self._path = run_path

        rutil.add_files(self._source_path, self.path)

        build = self.path / 'build'
        if not build.is_file():
            raise ProgramError(f'{self._source_path} does not have a build script')
        if not os.access(build, os.X_OK):
            raise ProgramError(f'{self._source_path}/build is not executable')

        try:
            subprocess.check_output(['./build'], stderr=subprocess.STDOUT, cwd=self.path)
        except subprocess.CalledProcessError as err:
            return CompileResult(False, err.output.decode('utf8', 'replace'), self.path)

        run = self.path / 'run'
        if not run.is_file() or not os.access(run, os.X_OK):
            return CompileResult(False, 'build script did not produce an executable called "run"', self.path)
        return CompileResult(True, None, self.path)

    def get_runcmd(self, cwd: Path | None = None, memlim: int = 1024) -> list[str]:
        """Run command for the program.

        Must not be called until compile() has been called.

        Args:
            cwd: if not None, the run command is provided
                relative to cwd (otherwise absolute paths are given).
        """
        path = self.path if cwd is None else Path(os.path.relpath(self.path, cwd))
        return [str(path / 'run')]

    def should_skip_memory_rlimit(self) -> bool:
        """Ugly hack (see program.py for details)."""
        return True
