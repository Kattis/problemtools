"""
Implementation of programs provided by source code.
"""

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from ..languages import CommandSubstitution, Language
from .errors import ProgramError
from .program import CompileResult, Program

if TYPE_CHECKING:
    from ..model import LanguageIncludes, ProgramFiles

log = logging.getLogger(__name__)


class SourceCode(Program):
    """Class representing a program provided by source code."""

    files: 'ProgramFiles'  # The program's own source files, not including any include files

    def __init__(self, name: str, files: 'ProgramFiles', language: Language, includes: 'LanguageIncludes') -> None:
        """Instantiate SourceCode object

        Args:
            name: name of the program.

            files: the source code files (see load_program_files).

            language: language definition for the programming
                language of the code.

            includes: include files to add alongside the source
                file(s), already resolved for this program's language
                (see Includes.get_includes_for_language). If it specifies
                a mainfile, that takes precedence over the one we would
                otherwise have detected.
        """
        super().__init__(name=name)
        self.language = language
        self.files = files
        self._includes = includes

    def code_size(self) -> int:
        return self.files.size()

    def do_compile(self, work_dir: Path) -> CompileResult:
        """Set up the compile work-space (writing source and includes into work_dir) and
        compile the source code."""
        name = self.name

        # Set up work-space
        run_path = work_dir / name
        if run_path.exists():
            run_path = Path(tempfile.mkdtemp(prefix=f'{name}-', dir=work_dir))
        else:
            run_path.mkdir(parents=True)
        self._path = run_path

        all_files = self.files.merged(self._includes.files)
        try:
            all_files.materialize(self.path)
        except OSError as e:
            return CompileResult(False, f'Failed to write program files: {e}', self.path)

        self.src = [self.path / f for f in self.language.get_source_files([f.path for f in all_files.files])]
        if len(self.src) == 0:
            raise ProgramError(f'No source files found for language {self.language.lang_id} in {self.name}')

        if self._includes.mainfile is not None:
            self.mainfile = self.path / self._includes.mainfile
        else:
            candidates = self.language.mainfile_candidates(self.src)
            self.mainfile = candidates[0] if candidates else self.src[0]

        self.mainclass = self.mainfile.stem
        self.Mainclass = self.mainclass[0].upper() + self.mainclass[1:]

        self.binary = self.path / 'run'

        not_installed = self.language.check_installed()
        if not_installed is not None:
            return CompileResult(False, not_installed, self.path)

        command = self.language.get_compile_command(self.__get_substitution())
        if command is None:
            return CompileResult(True, None, self.path)

        log.debug('compile command: %s', command)

        try:
            subprocess.check_output(command, stderr=subprocess.STDOUT)
            return CompileResult(True, None, self.path)
        except subprocess.CalledProcessError as err:
            return CompileResult(False, err.output.decode('utf8', 'replace'), self.path)

    def get_runcmd(self, cwd: Path | None = None, memlim: int = 1024) -> list[str]:
        """Run command for the program.

        Must not be called until compile() has been called.

        Args:
            cwd: if not None, the run command is provided
                relative to cwd (otherwise absolute paths are given).
            memlim: memory limit in MiB (only relevant for
                languages where memory limit is passed on command line)
        """
        subs = self.__get_substitution(memlim)
        if cwd is not None:
            subs.path = os.path.relpath(subs.path, cwd)
            subs.binary = os.path.relpath(subs.binary, cwd)
            subs.mainfile = os.path.relpath(subs.mainfile, cwd)
        return self.language.get_run_command(subs)

    def should_skip_memory_rlimit(self) -> bool:
        """Ugly hack (see program.py for details)."""
        return self.language.name in ['Java', 'Scala', 'Kotlin', 'Common Lisp']

    def __str__(self) -> str:
        """String representation"""
        return f'{self.name} ({self.language.name})'

    def __get_substitution(self, memlim: int = 1024) -> CommandSubstitution:
        return CommandSubstitution(
            path=str(self.path),
            files=' '.join(str(f) for f in self.src),
            memlim=memlim,
            mainfile=str(self.mainfile),
            mainclass=self.mainclass,
            Mainclass=self.Mainclass,
            binary=str(self.binary),
        )
