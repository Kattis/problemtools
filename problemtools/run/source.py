"""
Implementation of programs provided by source code.
"""
import re
import os
import shlex
import tempfile
import logging

from .errors import ProgramError
from .program import Program
from . import rutil

class SourceCode(Program):
    """Class representing a program provided by source code.
    """
    def __init__(self, path, language, work_dir=None, include_dir=None):
        """Instantiate SourceCode object

        Args:
            path (str): path of source code.  Can be either a single
                file or a directory (in which case the program is
                considered to consist of all files and subdirectories
                in the path).

            language (problemtools.Language): language definition for
                the programming language of the code.

            work_dir (str): temp directory in which to compile programs
                etc

            include_dir (str): directory containing language-specific
                include files to use.  If a program is found with
                source code for language ID <foo> (e.g. <foo>="cpp"),
                then the files in include_dir/<foo>/ will be copied
                into the work_dir along with the source file(s).
        """

        if path[-1] == '/':
            path = path[:-1]
        self.name = os.path.basename(path)
        self.language = language

        # Set up work-space
        if work_dir is None:
            work_dir = tempfile.mkdtemp()
        self.path = os.path.join(work_dir, self.name)
        if os.path.exists(self.path):
            self.path = tempfile.mkdtemp(prefix='%s-' % self.name, dir=work_dir)
        else:
            os.makedirs(self.path)

        # Copy all files
        rutil.add_files(path, self.path)
        if include_dir is not None:
            include_dir = os.path.join(include_dir, self.language.lang_id)
            if os.path.isdir(include_dir):
                rutil.add_files(include_dir, self.path)

        self.src = sorted(self.language.get_source_files(
            rutil.list_files_recursive(self.path)
        ))
        if len(self.src) == 0:
            raise ProgramError('No source files found for language %s in %s'
                               % (self.language.lang_id, self.name))

        self.mainfile = next((x for x in self.src
                              if re.match(r'^main\.', os.path.basename(x),
                                          re.IGNORECASE)), None)
        if self.mainfile is None:
            self.mainfile = self.src[0]

        self.mainclass = os.path.splitext(os.path.basename(self.mainfile))[0]
        if self.language.name == 'Kotlin':
          self.mainclass = self.mainclass.capitalize() + 'Kt'

        self.binary = os.path.join(self.path, 'run')


    _compile_result = None


    def compile(self):
        """Compile the source code.

        Returns:
            True if compilation succeeded, False otherwise
        """
        if self._compile_result is not None:
            return self._compile_result

        if self.language.compile is None:
            self._compile_result = True
            return True

        command = self.language.compile.format(**self.__get_substitution())

        logging.debug('compile command: %s', command)
        status = os.system(command + ' > /dev/null 2> /dev/null')

        if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
            logging.info('Compiler failed (status %d) when compiling %s\n        Command used:\n%s', status, self.name, command)
            self._compile_result = False
        else:
            self._compile_result = True
        return self._compile_result


    def get_runcmd(self, cwd=None, memlim=1024):
        """Run command for the program.

        Args:
            cwd (str): if not None, the run command is provided
                relative to cwd (otherwise absolute paths are given).
            memlim (int): if not None, memory limit in MB (only
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


    def should_skip_memory_rlimit(self):
        """Ugly hack (see program.py for details)."""
        return self.language.name in ['Java', 'Scala', 'Kotlin']


    def __str__(self):
        """String representation"""
        return '%s (%s)' % (self.name, self.language.name)


    def __get_substitution(self, memlim=1024):
        return {
            'path': self.path,
            'files': ' '.join(self.src),
            'memlim': memlim,
            'mainfile': self.mainfile,
            'mainclass': self.mainclass,
            'binary': self.binary
        }
