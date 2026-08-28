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
from . import rutil
from .errors import ProgramError
from .program import CompileResult, Program

if TYPE_CHECKING:
    from ..model import LanguageIncludes

log = logging.getLogger(__name__)


class SourceCode(Program):
    """Class representing a program provided by source code."""

    def __init__(self, path: str, language: Language, includes: 'LanguageIncludes') -> None:
        """Instantiate SourceCode object

        Args:
            path: path of source code.  Can be either a single
                file or a directory (in which case the program is
                considered to consist of all files and subdirectories
                in the path).

            language: language definition for the programming
                language of the code.

            includes: include files to add alongside the source
                file(s), already resolved for this program's language
                (see Includes.get_includes_for_language). If it specifies
                a mainfile, that takes precedence over the one we would
                otherwise have detected.
        """
        if path[-1] == '/':
            path = path[:-1]
        name = os.path.basename(path)
        super().__init__(name=name)
        self.language = language
        self._source_path = path
        self._includes = includes
        if os.path.isfile(path):
            self._code_size = os.path.getsize(path)
        else:
            self._code_size = sum(os.path.getsize(f) for f in rutil.list_files_recursive(path))

    def code_size(self) -> int:
        return self._code_size

    def do_compile(self, work_dir: Path) -> CompileResult:
        """Set up the compile work-space (copying source and includes into work_dir) and
        compile the source code."""
        name = self.name

        # Set up work-space
        run_path = work_dir / name
        if os.path.exists(run_path):
            run_path = Path(tempfile.mkdtemp(prefix=f'{name}-', dir=work_dir))
        else:
            os.makedirs(run_path)
        self._path = run_path

        # Copy all files
        rutil.add_files(self._source_path, self.path)
        for include_file in self._includes.files:
            dest = os.path.join(self.path, include_file.path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, 'wb') as f:
                f.write(include_file.data)

        self.src = sorted(self.language.get_source_files(rutil.list_files_recursive(self.path)))
        if len(self.src) == 0:
            raise ProgramError(f'No source files found for language {self.language.lang_id} in {self.name}')

        if self._includes.mainfile is not None:
            self.mainfile = os.path.join(self.path, self._includes.mainfile)
        else:
            candidates = self.language.mainfile_candidates(self.src)
            self.mainfile = str(candidates[0]) if candidates else self.src[0]

        self.mainclass = os.path.splitext(os.path.basename(self.mainfile))[0]
        self.Mainclass = self.mainclass[0].upper() + self.mainclass[1:]

        self.binary = os.path.join(self.path, 'run')

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

    def get_runcmd(self, cwd: str | None = None, memlim: int = 1024) -> list[str]:
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
            files=' '.join(self.src),
            memlim=memlim,
            mainfile=self.mainfile,
            mainclass=self.mainclass,
            Mainclass=self.Mainclass,
            binary=self.binary,
        )
