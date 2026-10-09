"""Package for managing execution of external programs in Kattis
Problemtools.
"""

import os
from pathlib import Path
from typing import TYPE_CHECKING

from ..languages import Languages
from . import rutil
from .buildrun import BuildRun
from .checktestdata import Checktestdata
from .executable import Executable as Executable
from .program import CompileResult as CompileResult
from .program import Program
from .source import SourceCode
from .tools import Tool as Tool
from .tools import get_tool as get_tool
from .tools import get_tool_path as get_tool_path
from .viva import Viva

if TYPE_CHECKING:
    from ..model import Includes


def find_programs(
    path: Path,
    language_config: Languages,
    allow_validation_script: bool = False,
) -> list[Program]:
    """Find all programs in a directory.

    Args:
        path: directory in which to search for programs

        language_config: language config, used for auto-detecting
            programming language of source code and providing info
            on how to compile and run the source code.

        allow_validation_script: if true, also looks for
            validation scripts in the Checktestdata and VIVA formats.

    Returns:
        list of Program instances, all programs found in path.

    """
    if not path.is_dir():
        return []
    ret = []
    for fullpath in sorted(path.iterdir()):
        run = get_program(
            fullpath,
            language_config=language_config,
            allow_validation_script=allow_validation_script,
        )
        if run is not None:
            ret.append(run)
    return ret


def get_program(
    path: Path,
    language_config: Languages,
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

        allow_validation_script: if true, also looks for
            validation scripts in the Checktestdata and VIVA formats.

    Returns:
        a Program instance, or None if no program was found at
        the given path.
    """
    # Imported lazily (rather than at module scope) since `model` depends on `run`
    # (e.g. for `run.find_programs`), so importing it here avoids a circular import.
    from ..model import load_program_files

    if path.is_file():
        if allow_validation_script:
            if path.suffix == '.viva':
                return Viva(path)
            if path.suffix == '.ctd':
                return Checktestdata(path)
    else:
        build = path / 'build'
        if build.is_file() and os.access(build, os.X_OK):
            return BuildRun(path.name, load_program_files(path))

    return get_source_program(path, language_config)


def find_source_programs(path: Path, language_config: Languages, includes: 'Includes') -> list[SourceCode]:
    """Find all programs provided as source code in a directory.

    Like find_programs, but never gives a BuildRun: a directory with a build
    script is treated like any other source code directory.
    """
    if not path.is_dir():
        return []
    ret = []
    for fullpath in sorted(path.iterdir()):
        program = get_source_program(fullpath, language_config=language_config, includes=includes)
        if program is not None:
            ret.append(program)
    return ret


def get_source_program(path: Path, language_config: Languages, includes: 'Includes | None' = None) -> SourceCode | None:
    """Get a SourceCode object for a program.

    Args:
        path, language_config: see get_program.

        includes: include files to add to the program, resolved per
            the program's detected language (see
            Includes.get_includes_for_language). Defaults to no includes.

    Returns:
        a SourceCode instance, or None if no source code in a known
        language was found at the given path.
    """
    # Imported lazily, see get_program
    from ..model import Includes, load_program_files

    if includes is None:
        includes = Includes()

    files = [path] if path.is_file() else rutil.list_files_recursive(path)
    lang = language_config.detect_language(files)
    if lang is None:
        return None
    return SourceCode(path.name, load_program_files(path), lang, includes=includes.get_includes_for_language(lang.lang_id))


def as_source_or_buildrun(programs: list[Program]) -> list[SourceCode | BuildRun]:
    """Narrow a list of Programs to SourceCode | BuildRun.

    Use on the result of find_programs(allow_validation_script=False) (the default) if
    you need to narrow the type."""
    result: list[SourceCode | BuildRun] = []
    for program in programs:
        assert isinstance(program, SourceCode | BuildRun), (
            f'{program} is a {type(program).__name__}, expected SourceCode or BuildRun'
        )
        result.append(program)
    return result
