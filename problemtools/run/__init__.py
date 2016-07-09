"""Package for managing execution of external programs in Kattis
Problemtools.
"""
import re
import os

from .buildrun import BuildRun
from .checktestdata import Checktestdata
from .errors import ProgramError
from .executable import Executable
from .program import Program
from .source import SourceCode
from .viva import Viva
from .tools import get_tool_path, get_tool
from . import rutil


def find_programs(path, pattern='.*', language_config=None, work_dir=None,
                  include_dir=None, allow_validation_script=False):
    """Find all programs in a directory.

    Args:
        path (str): directory in which to search for programs

        pattern (str): only files/subdirectories in path whose base
            name matches this regular expression will be included.

        language_config (problemtools.languages.Languages):
            language config, used for auto-detecting programming
            language of source code and providing info on how to
            compile and run the source code.

        work_dir (str): temp directory in which to compile programs etc

        include_dir (str): directory containing language-specific
            include files to use.  If a program is found with source
            code for language ID <foo> (e.g. <foo>="cpp"), then the
            files in include_dir/<foo>/ will be copied into the
            work_dir along with the source file(s).

        allow_validation_script (bool): if true, also looks for
            validation scripts in the Checktestdata and VIVA formats.

    Returns:
        list of Program instances, all programs found in path.

    """
    if not os.path.isdir(path):
        return []
    ret = []
    for name in sorted(os.listdir(path)):
        if re.match(pattern, name):
            fullpath = os.path.join(path, name)
            run = get_program(fullpath,
                              language_config=language_config,
                              work_dir=work_dir,
                              include_dir=include_dir,
                              allow_validation_script=allow_validation_script)
            if run is not None:
                ret.append(run)
    return ret


def get_program(path, language_config=None, work_dir=None, include_dir=None,
                allow_validation_script=False):
    """Get a Program object for a program

    Args:

        path (str): path of program.  Can be either a single file or a
            directory (in which case the program is considered to
            consist of all files and subdirectories in the path).

        language_config (problemtools.languages.Languages):
            language config, used for auto-detecting programming
            language of source code and providing info on how to
            compile and run the source code.

        work_dir (str): temp directory in which to compile programs etc

        include_dir (str): directory containing language-specific
            include files to use.  If a program is found with source
            code for language ID <foo> (e.g. <foo>="cpp"), then the
            files in include_dir/<foo>/ will be copied into the
            work_dir along with the source file(s).

        allow_validation_script (bool): if true, also looks for
            validation scripts in the Checktestdata and VIVA formats.

    Returns:
        a Program instance, or None if no program was found at
        the given path.
    """

    if os.path.isfile(path):
        if allow_validation_script:
            ext = os.path.splitext(path)[1]
            if ext == '.viva':
                return Viva(path)
            if ext == '.ctd':
                return Checktestdata(path)
        files = [path]
    else:
        build = os.path.join(path, 'build')
        if os.path.isfile(build) and os.access(path, os.X_OK):
            return BuildRun(path, work_dir)
        files = rutil.list_files_recursive(path)

    if language_config is not None:
        lang = language_config.detect_language(files)
        if lang is not None:
            return SourceCode(path, lang,
                              work_dir=work_dir, include_dir=include_dir)
    return None
