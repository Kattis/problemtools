"""
Implementation of programs provided by source code.
"""

import logging
import os
import shlex
import subprocess
import tempfile

from ..languages import Language
from ..model import LanguageIncludes
from . import rutil
from .errors import ProgramError
from .program import Program

log = logging.getLogger(__name__)


class SourceCode(Program):
    """Class representing a program provided by source code."""

    def __init__(self, path: str, language: Language, work_dir: str, includes: LanguageIncludes):
        """Instantiate SourceCode object

        Args:
            path: path of source code.  Can be either a single
                file or a directory (in which case the program is
                considered to consist of all files and subdirectories
                in the path).

            language: language definition for the programming
                language of the code.

            work_dir: temp directory in which to compile programs etc

            includes: include files to add alongside the source
                file(s), already resolved for this program's language
                (see Includes.get_includes_for_language). If it specifies
                a mainfile, that takes precedence over the one we would
                otherwise have detected.
        """
        super().__init__()

        if path[-1] == '/':
            path = path[:-1]
        self.name = os.path.basename(path)
        self.language = language

        # Set up work-space
        self.path = os.path.join(work_dir, self.name)
        if os.path.exists(self.path):
            self.path = tempfile.mkdtemp(prefix='%s-' % self.name, dir=work_dir)
        else:
            os.makedirs(self.path)

        # Copy all files
        rutil.add_files(path, self.path)
        self._code_size = sum(os.path.getsize(f) for f in rutil.list_files_recursive(self.path))
        for include_file in includes.files:
            dest = os.path.join(self.path, include_file.path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, 'wb') as f:
                f.write(include_file.data)

        self.src = sorted(self.language.get_source_files(rutil.list_files_recursive(self.path)))
        if len(self.src) == 0:
            raise ProgramError('No source files found for language %s in %s' % (self.language.lang_id, self.name))

        if includes.mainfile is not None:
            self.mainfile = os.path.join(self.path, includes.mainfile)
        else:
            candidates = self.language.mainfile_candidates(self.src)
            self.mainfile = str(candidates[0]) if candidates else self.src[0]

        self.mainclass = os.path.splitext(os.path.basename(self.mainfile))[0]
        self.Mainclass = self.mainclass[0].upper() + self.mainclass[1:]

        self.binary = os.path.join(self.path, 'run')

    def code_size(self) -> int:
        return self._code_size

    def do_compile(self) -> tuple[bool, str | None]:
        """Compile the source code.

        Returns tuple:
            (True, None) if compilation succeeded
            (False, errmsg) otherwise
        """
        if self.language.compile is None:
            return (True, None)

        command = self.get_compilecmd()
        compiler = command[0]

        if not os.path.isfile(compiler) or not os.access(compiler, os.X_OK):
            return (False, '%s does not seem to be installed, expected to find compiler at %s' % (self.language.name, compiler))

        log.debug('compile command: %s', command)

        try:
            subprocess.check_output(command, stderr=subprocess.STDOUT)
            return (True, None)
        except subprocess.CalledProcessError as err:
            return (False, err.output.decode('utf8', 'replace'))

    def get_compilecmd(self) -> list[str]:
        assert self.language.compile is not None, 'get_compilecmd called for a language with no compile command'
        return shlex.split(self.language.compile.format(**self.__get_substitution()))

    def get_runcmd(self, cwd=None, memlim=1024):
        """Run command for the program.

        Args:
            cwd (str): if not None, the run command is provided
                relative to cwd (otherwise absolute paths are given).
            memlim (int): if not None, memory limit in MiB (only
                relevant for languages where memory limit is passed on
                command line)
        """
        self.compile()
        subs = self.__get_substitution(memlim)
        if cwd is not None:
            subs['path'] = os.path.relpath(subs['path'], cwd)
            subs['binary'] = os.path.relpath(subs['binary'], cwd)
            subs['mainfile'] = os.path.relpath(subs['mainfile'], cwd)
        return shlex.split(self.language.run.format(**subs))

    def should_skip_memory_rlimit(self) -> bool:
        """Ugly hack (see program.py for details)."""
        return self.language.name in ['Java', 'Scala', 'Kotlin', 'Common Lisp']

    def __str__(self) -> str:
        """String representation"""
        return '%s (%s)' % (self.name, self.language.name)

    def __get_substitution(self, memlim=1024):
        return {
            'path': self.path,
            'files': ' '.join(self.src),
            'memlim': memlim,
            'mainfile': self.mainfile,
            'mainclass': self.mainclass,
            'Mainclass': self.Mainclass,
            'binary': self.binary,
        }
