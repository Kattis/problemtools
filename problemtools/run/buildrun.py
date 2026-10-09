"""
Implementation of programs provided by a directory with build/run scripts.
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from .executable import Executable
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

    def _do_compile(self, work_dir: Path) -> CompileResult:
        """Set up the compile work-space (writing the build script and friends into
        work_dir) and run the build script."""
        name = self.name
        build_dir = work_dir / name
        if build_dir.exists():
            build_dir = Path(tempfile.mkdtemp(prefix=f'{name}-', dir=work_dir))
        else:
            build_dir.mkdir(parents=True)

        try:
            self.files.materialize(build_dir)
        except OSError as e:
            return CompileResult(errmsg=f'Failed to write program files: {e}')

        build = build_dir / 'build'
        if not build.is_file():
            return CompileResult(errmsg='no build script')
        if not os.access(build, os.X_OK):
            return CompileResult(errmsg='build script is not executable')

        try:
            subprocess.check_output(['./build'], stderr=subprocess.STDOUT, cwd=build_dir)
        except subprocess.CalledProcessError as err:
            return CompileResult(errmsg=err.output.decode('utf8', 'replace'))

        run = build_dir / 'run'
        if not run.is_file() or not os.access(run, os.X_OK):
            return CompileResult(errmsg='build script did not produce an executable called "run"')
        return CompileResult(executable=Executable(self.name, run, build_dir=build_dir, skip_memory_rlimit=True))
