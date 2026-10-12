"""Checks for the structure of a problem package (file/directory names, symlinks)."""

from __future__ import annotations

import difflib
import os
import re
from pathlib import Path

from ..diagnostics import Diagnostics, pluralize
from ..formatversion import FormatVersion
from ..model import BadReason, EntryKind, Files

_NAME_REGEX = re.compile(r'^[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,254}$')

_SYMLINK_PROBLEMS = {
    BadReason.ABSOLUTE_SYMLINK: 'which is an absolute path. Symlinks must be relative.',
    BadReason.OUTSIDE_PACKAGE: 'which is outside of problem package',
    BadReason.BROKEN_SYMLINK: 'which does not exist',
    BadReason.SYMLINK_LOOP: 'which creates a symlink loop',
    BadReason.IGNORED_TARGET: "which is ignored (its name, or the name of a directory it is in, starts with '.')",
}


def check_problem_package(files: Files, format_version: FormatVersion, diag: Diagnostics) -> None:
    """Run all checks on the structure of a problem package."""
    num_files = len(files.walk(files.root, EntryKind.FILE))
    num_dirs = len(files.walk(files.root, EntryKind.DIR))
    msg = f'Checking package structure: {pluralize(num_files, "file")}, {pluralize(num_dirs, "directory", "directories")}'
    extra = [f'{len(files.ignored)} ignored'] if files.ignored else []
    extra += [f'{len(files.bad)} invalid'] if files.bad else []
    if extra:
        msg += f' ({", ".join(extra)})'
    diag.msg(msg)

    _check_bad_entries(files, diag)
    _check_empty_directories(files, diag)
    _check_file_and_directory_names(files, diag)
    _check_root_directory_names(files, format_version, diag)


def _display_path(files: Files, path: Path) -> Path:
    """path, starting with the problem shortname. Only used for nicer error messages."""
    return path.relative_to(files.root.parent)


def _check_bad_entries(files: Files, diag: Diagnostics) -> None:
    """Report entries which can not be part of a valid package: bad symlinks and special files."""
    for entry in files.bad:
        if entry.reason is BadReason.SPECIAL_FILE:
            diag.error(f'{_display_path(files, entry.path)} is not a regular file, directory or symlink')
        else:
            target = os.readlink(entry.path)
            diag.error(f'Symlink {_display_path(files, entry.path)} links to {target} {_SYMLINK_PROBLEMS[entry.reason]}')


def _check_empty_directories(files: Files, diag: Diagnostics) -> None:
    for directory in files.walk(files.root, EntryKind.DIR):
        if not files.listdir(directory):
            diag.warning(f'Empty directory {_display_path(files, directory)}')


def _check_file_and_directory_names(files: Files, diag: Diagnostics) -> None:
    for path, kind in files.entries.items():
        if not _NAME_REGEX.match(path.name):
            what = 'file' if kind is EntryKind.FILE else 'directory'
            diag.error(
                f"Invalid {what} name '{path.name}' in {_display_path(files, path.parent)}, should match {_NAME_REGEX.pattern}"
            )


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


def _check_root_directory_names(files: Files, format_version: FormatVersion, diag: Diagnostics) -> None:
    """Warn about unrecognized directories at the problem root: deprecated names,
    directories renamed between format versions, directories belonging to other
    format versions, and likely typos."""
    known = format_version.root_directories
    other_known = {directory for version in FormatVersion for directory in version.root_directories} - known
    existing_dirs = {path.name for path in files.listdir(files.root, EntryKind.DIR)}
    typo_candidates = known - existing_dirs

    for name in sorted(existing_dirs - known):
        if not _NAME_REGEX.match(name):
            # Already flagged as an invalid name by _check_file_and_directory_names.
            continue

        if name == 'input_format_validators':
            diag.warning('input_format_validators is a deprecated name; please use input_validators instead')
        elif _warn_renamed_directory(name, format_version, diag):
            pass
        elif name in other_known:
            diag.warning(f'Directory "{name}" is not part of format version {format_version}')
        elif typo_candidates:
            closest, similarity = max(
                ((d, difflib.SequenceMatcher(None, name, d).ratio()) for d in typo_candidates),
                key=lambda x: x[1],
            )
            if similarity >= 0.75:
                diag.warning(f'Potential typo: directory "{name}" is similar to "{closest}"')
