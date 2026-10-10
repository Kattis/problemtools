"""
Implementation of programs provided by source code.
"""

import dataclasses
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from ..languages import CommandSubstitution, Language
from . import rutil
from .executable import Executable
from .program import CompileResult, Program

if TYPE_CHECKING:
    from ..model import LanguageIncludes, ProgramFiles

log = logging.getLogger(__name__)


class SourceCode(Program):
    """Class representing a program provided by source code."""

    files: 'ProgramFiles'  # The program's own source files, not including any include files
    language: Language  # The programming language of the code

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
        """Total size of the program's own source files, not including any include files."""
        return self.files.size()

    def _do_compile(self, work_dir: Path) -> CompileResult:
        """Set up the compile work-space (writing source and includes into work_dir) and
        compile the source code."""
        name = self.name

        # Set up work-space
        build_dir = work_dir / name
        if build_dir.exists():
            build_dir = Path(tempfile.mkdtemp(prefix=f'{name}-', dir=work_dir))
        else:
            build_dir.mkdir(parents=True)

        all_files = self.files.merged(self._includes.files)
        try:
            all_files.materialize(build_dir)
        except OSError as e:
            return CompileResult(errmsg=f'Failed to write program files: {e}')

        src = self.language.get_source_files([f.path for f in all_files.files])
        if len(src) == 0:
            return CompileResult(errmsg=f'No source files found for language {self.language.lang_id}')

        if self._includes.mainfile is not None:
            mainfile: Path = self._includes.mainfile
        else:
            candidates = self.language.mainfile_candidates(src)
            mainfile = candidates[0] if candidates else src[0]

        mainclass = mainfile.stem
        subs = CommandSubstitution(
            path=str(build_dir),
            files=' '.join(str(build_dir / f) for f in src),
            binary=str(build_dir / 'run'),
            mainfile=str(build_dir / mainfile),
            mainclass=mainclass,
            Mainclass=mainclass[0].upper() + mainclass[1:],
        )

        not_installed = self.language.check_installed()
        if not_installed is not None:
            return CompileResult(errmsg=not_installed)

        executable = SourceExecutable(str(self), self.language, subs)
        command = self.language.get_compile_command(subs)
        if command is None:
            return CompileResult(executable=executable)

        log.debug('compile command: %s', command)

        try:
            subprocess.check_output(command, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as err:
            return CompileResult(errmsg=err.output.decode('utf8', 'replace'))

        if (errmsg := rutil.check_build_dir(build_dir)) is not None:
            return CompileResult(errmsg=errmsg)
        return CompileResult(executable=executable)

    def __str__(self) -> str:
        """String representation"""
        return f'{self.name} ({self.language.name})'


class SourceExecutable(Executable):
    """A compiled SourceCode program, run using its language's run command."""

    def __init__(self, name: str, language: Language, subs: CommandSubstitution) -> None:
        """Instantiate SourceExecutable object

        Args:
            name: name of the program.
            language: language definition for the programming language of the code.
            subs: values to substitute into the language's run command (memlim
                is overridden when running).
        """
        super().__init__(
            name,
            Path(subs.binary),
            build_dir=Path(subs.path),
            skip_memory_rlimit=language.name in ['Java', 'Scala', 'Kotlin', 'Common Lisp'],
        )
        self._language = language
        self._subs = subs

    def get_runcmd(self, cwd: Path | None = None, memlim: int = 1024) -> list[str]:
        """Run command for the program.

        Args:
            cwd: if not None, the run command is provided
                relative to cwd (otherwise absolute paths are given).
            memlim: memory limit in MiB (only relevant for
                languages where memory limit is passed on command line)
        """
        subs = dataclasses.replace(self._subs, memlim=memlim)
        if cwd is not None:
            subs.path = os.path.relpath(subs.path, cwd)
            subs.binary = os.path.relpath(subs.binary, cwd)
            subs.mainfile = os.path.relpath(subs.mainfile, cwd)
        return self._language.get_run_command(subs)
