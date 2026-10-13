"""Discovery of the programs (submissions, validators, graders) in a problem package."""

from __future__ import annotations

import os
from pathlib import Path

from ..languages import Languages
from ..run import BuildRun, Checktestdata, Program, SourceCode, Viva
from .files import Files
from .includes import Includes
from .program_files import load_program_files


def find_programs(
    files: Files,
    dir: Path,
    language_config: Languages,
    allow_validation_script: bool = False,
) -> list[Program]:
    """Find all programs in a directory.

    Args:
        files: the files of the problem package.

        dir: directory in which to search for programs

        language_config: language config, used for auto-detecting
            programming language of source code and providing info
            on how to compile and run the source code.

        allow_validation_script: if true, also looks for
            validation scripts in the Checktestdata and VIVA formats.

    Returns:
        list of Program instances, all programs found in dir.
    """
    ret = []
    for path in files.listdir(dir):
        program = get_program(files, path, language_config=language_config, allow_validation_script=allow_validation_script)
        if program is not None:
            ret.append(program)
    return ret


def get_program(
    files: Files,
    path: Path,
    language_config: Languages,
    allow_validation_script: bool = False,
) -> Program | None:
    """Get a Program object for a program

    Args:
        files: the files of the problem package.

        path: path of program.  Can be either a single file or a
            directory (in which case the program is considered to
            consist of all files and subdirectories in the path).

        language_config, allow_validation_script: see find_programs.

    Returns:
        a Program instance, or None if no program was found at
        the given path.
    """
    if files.is_file(path):
        if allow_validation_script:
            if path.suffix == '.viva':
                return Viva(path)
            if path.suffix == '.ctd':
                return Checktestdata(path)
    else:
        build = path / 'build'
        if files.is_file(build) and os.access(build, os.X_OK):
            return BuildRun(path.name, load_program_files(files, path))

    return get_source_program(files, path, language_config)


def find_source_programs(files: Files, dir: Path, language_config: Languages, includes: Includes) -> list[SourceCode]:
    """Find all programs provided as source code in a directory.

    Like find_programs, but never gives a BuildRun: a directory with a build
    script is treated like any other source code directory.
    """
    ret = []
    for path in files.listdir(dir):
        program = get_source_program(files, path, language_config=language_config, includes=includes)
        if program is not None:
            ret.append(program)
    return ret


def get_source_program(
    files: Files, path: Path, language_config: Languages, includes: Includes | None = None
) -> SourceCode | None:
    """Get a SourceCode object for a program.

    Args:
        files, path, language_config: see get_program.

        includes: include files to add to the program, resolved per
            the program's detected language (see
            Includes.get_includes_for_language). Defaults to no includes.

    Returns:
        a SourceCode instance, or None if no source code in a known
        language was found at the given path.
    """
    if includes is None:
        includes = Includes()

    lang = language_config.detect_language([path] if files.is_file(path) else files.walk(path))
    if lang is None:
        return None
    return SourceCode(path.name, load_program_files(files, path), lang, includes=includes.get_includes_for_language(lang.lang_id))


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
