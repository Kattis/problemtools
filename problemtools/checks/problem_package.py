"""Checks for the structure of a problem package (file/directory names, symlinks)."""

from __future__ import annotations

import difflib
import os
import re
from pathlib import Path

from ..diagnostics import Diagnostics
from ..formatversion import FormatVersion

_NAME_REGEX = re.compile(r'^[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,254}$')


def check_problem_package(probdir: Path, format_version: FormatVersion, diag: Diagnostics) -> None:
    """Run all checks on the structure of a problem package."""
    _check_symlinks(probdir, diag)
    _check_file_and_directory_names(probdir, diag)
    _check_root_directory_names(probdir, format_version, diag)


def _check_symlinks(probdir: Path, diag: Diagnostics) -> None:
    """Check that all symlinks point to something existing within the problem package"""
    real_probdir = os.path.realpath(probdir)
    for root, dirs, files in os.walk(real_probdir):
        for file in dirs + files:
            filename = os.path.join(root, file)
            if os.path.islink(filename):
                target = os.path.realpath(filename)
                # relfile is the filename of the symlink, relative to the problem root (only used for nicer error messages)
                relfile = os.path.relpath(filename, probdir)
                # reltarget is what the symlink points to (absolute, or relative to where the symlink is)
                reltarget = os.readlink(filename)
                if not os.path.exists(target):
                    diag.error(f'Symlink {relfile} links to {reltarget} which does not exist')
                if os.path.commonpath([real_probdir, target]) != real_probdir:
                    diag.error(f'Symlink {relfile} links to {reltarget} which is outside of problem package')
                if os.path.isabs(reltarget):
                    diag.error(f'Symlink {relfile} links to {reltarget} which is an absolute path. Symlinks must be relative.')


def _check_file_and_directory_names(probdir: Path, diag: Diagnostics) -> None:
    def _special_case_allowed_files(file: str, reldir: str) -> bool:
        return file == '.gitignore' or (file == '.timelimit' and reldir == probdir.name)

    def _special_case_allowed_dirs(directory: str, reldir: str) -> bool:
        return directory == '.git' and reldir == probdir.name

    for root, dirs, files in os.walk(probdir):
        # Path of the directory we're in, starting with problem shortname. Only used for nicer error messages.
        reldir = os.path.relpath(root, probdir.parent)
        for file in files:
            if not _NAME_REGEX.match(file) and not _special_case_allowed_files(file, reldir):
                diag.error(f"Invalid file name '{file}' in {reldir}, should match {_NAME_REGEX.pattern}")
        for directory in dirs:
            if not _NAME_REGEX.match(directory) and not _special_case_allowed_dirs(directory, reldir):
                diag.error(f"Invalid directory name '{directory}' in {reldir}, should match {_NAME_REGEX.pattern}")


def _warn_renamed_directory(found_name: str, format_version: FormatVersion, diag: Diagnostics) -> bool:
    """If found_name is what some other format version calls a directory that was renamed
    across format versions, warn that it's been renamed and return True."""
    for prop in ('statement_directory', 'output_validator_directory'):
        good_dir = getattr(format_version, prop)
        bad_dirs = {getattr(version, prop) for version in FormatVersion} - {good_dir}
        if found_name in bad_dirs:
            diag.warning(f'Found directory "{found_name}". Version {format_version} looks for this as "{good_dir}"')
            return True
    return False


def _check_root_directory_names(probdir: Path, format_version: FormatVersion, diag: Diagnostics) -> None:
    """Warn about unrecognized directories at the problem root: deprecated names,
    directories renamed between format versions, directories belonging to other
    format versions, and likely typos."""
    known = format_version.root_directories
    other_known = {directory for version in FormatVersion for directory in version.root_directories} - known

    for entry in probdir.iterdir():
        name = entry.name
        if not entry.is_dir() or name in known or name == '.git':
            continue
        if not _NAME_REGEX.match(name):
            # Already flagged as an invalid name by _check_file_and_directory_names.
            continue

        if name == 'input_format_validators':
            diag.warning('input_format_validators is a deprecated name; please use input_validators instead')
        elif _warn_renamed_directory(name, format_version, diag):
            pass
        elif name in other_known:
            diag.warning(f'Directory "{name}" is not part of format version {format_version}')
        else:
            closest, similarity = max(
                ((d, difflib.SequenceMatcher(None, name, d).ratio()) for d in known),
                key=lambda x: x[1],
            )
            if similarity >= 0.75:
                diag.warning(f'Potential typo: directory "{name}" is similar to "{closest}"')
            else:
                diag.warning(f'Unrecognized directory "{name}" at problem root')
