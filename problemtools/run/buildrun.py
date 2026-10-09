"""
Implementation of programs provided by a directory with build/run scripts.
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from .errors import ProgramError
from .program import CompileResult, Program

if TYPE_CHECKING:
    from ..model import ProgramFiles


class BuildRun(Program):
    """Class for build/run-script program."""

    files: 'ProgramFiles'  # The program's files, including the build script

    def __init__(self, name: str, files: 'ProgramFiles') -> None:
        """Instantiate BuildRun object.

        Args:
            name: name of the program.
            files: the program's files, including the build script (see load_program_files).
        """
        super().__init__(name=name)
        self.files = files

    def do_compile(self, work_dir: Path) -> CompileResult:
        """Set up the compile work-space (writing the build script and friends into
        work_dir) and run the build script."""
        name = self.name
        run_path = work_dir / name
        if run_path.exists():
            run_path = Path(tempfile.mkdtemp(prefix=f'{name}-', dir=work_dir))
        else:
            run_path.mkdir(parents=True)
        self._path = run_path

        try:
            self.files.materialize(self.path)
        except OSError as e:
            return CompileResult(False, f'Failed to write program files: {e}', self.path)

        build = self.path / 'build'
        if not build.is_file():
            raise ProgramError(f'{self.name} does not have a build script')
        if not os.access(build, os.X_OK):
            raise ProgramError(f'{self.name}/build is not executable')

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
