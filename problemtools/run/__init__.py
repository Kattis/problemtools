"""Package for managing execution of external programs in Kattis
Problemtools.
"""

import os

from ..languages import Languages
from ..model import Includes
from . import rutil
from .buildrun import BuildRun
from .checktestdata import Checktestdata
from .errors import ProgramError as ProgramError
from .program import Program
from .source import SourceCode
from .tools import get_tool as get_tool
from .tools import get_tool_path as get_tool_path
from .viva import Viva


def find_programs(
    path: str,
    language_config: Languages,
    work_dir: str,
    includes: Includes = Includes(),
    allow_validation_script: bool = False,
) -> list[Program]:
    """Find all programs in a directory.

    Args:
        path: directory in which to search for programs

        language_config: language config, used for auto-detecting
            programming language of source code and providing info
            on how to compile and run the source code.

        work_dir: temp directory in which to compile programs etc

        includes: include files to add to programs found, resolved
            per-program based on its detected language (see
            Includes.get_includes_for_language).

        allow_validation_script: if true, also looks for
            validation scripts in the Checktestdata and VIVA formats.

    Returns:
        list of Program instances, all programs found in path.

    """
    if not os.path.isdir(path):
        return []
    ret = []
    for name in sorted(os.listdir(path)):
        fullpath = os.path.join(path, name)
        run = get_program(
            fullpath,
            language_config=language_config,
            work_dir=work_dir,
            includes=includes,
            allow_validation_script=allow_validation_script,
        )
        if run is not None:
            ret.append(run)
    return ret


def get_program(
    path: str,
    language_config: Languages,
    work_dir: str,
    includes: Includes = Includes(),
    allow_validation_script: bool = False,
) -> Program | None:
    """Get a Program object for a program

    Args:
        path: path of program.  Can be either a single file or a
            directory (in which case the program is considered to
            consist of all files and subdirectories in the path).

        language_config: language config, used for auto-detecting
            programming language of source code and providing info
            on how to compile and run the source code.

        work_dir: temp directory in which to compile programs etc

        includes: include files to add to the program, resolved per
            the program's detected language (see
            Includes.get_includes_for_language).

        allow_validation_script: if true, also looks for
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
        if os.path.isfile(build) and os.access(build, os.X_OK):
            return BuildRun(path, work_dir)
        files = rutil.list_files_recursive(path)

    lang = language_config.detect_language(files)
    if lang is not None:
        return SourceCode(path, lang, work_dir=work_dir, includes=includes.get_includes_for_language(lang.lang_id))
    return None
