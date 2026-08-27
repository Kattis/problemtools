"""Checks for the structure of a problem package (file/directory names, symlinks)."""

from __future__ import annotations

import difflib
import os
import re
from pathlib import Path

from ..diagnostics import Diagnostics
from ..formatversion import FormatVersion


def check_problem_package(probdir: Path, format: FormatVersion, diag: Diagnostics) -> None:
    """Run all checks on the structure of a problem package."""
    _check_symlinks(probdir, diag)
    _check_file_and_directory_names(probdir, diag)
    _check_submission_directory_names(probdir, format, diag)


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
    regex = re.compile(r'^[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,254}$')

    def _special_case_allowed_files(file: str, reldir: str) -> bool:
        return file == '.gitignore' or (file == '.timelimit' and reldir == probdir.name)

    def _special_case_allowed_dirs(directory: str, reldir: str) -> bool:
        return directory == '.git' and reldir == probdir.name

    for root, dirs, files in os.walk(probdir):
        # Path of the directory we're in, starting with problem shortname. Only used for nicer error messages.
        reldir = os.path.relpath(root, probdir.parent)
        for file in files:
            if not regex.match(file) and not _special_case_allowed_files(file, reldir):
                diag.error(f"Invalid file name '{file}' in {reldir}, should match {regex.pattern}")
        for directory in dirs:
            if not regex.match(directory) and not _special_case_allowed_dirs(directory, reldir):
                diag.error(f"Invalid directory name '{directory}' in {reldir}, should match {regex.pattern}")


def _check_submission_directory_names(probdir: Path, format: FormatVersion, diag: Diagnostics) -> None:
    """Heuristically check if submissions contain any directories that will be ignored because of typos or format mismatches"""
    submission_directories = [p.name for p in (probdir / 'submissions').glob('*') if p.is_dir()]
    if len(submission_directories) == 0:
        return

    def most_similar(present_dir: str, format_version: FormatVersion) -> tuple[str, float]:
        similarities = [
            (spec_dir, difflib.SequenceMatcher(None, present_dir, spec_dir).ratio())
            for spec_dir in format_version.submission_directories
        ]
        return max(similarities, key=lambda x: x[1])

    for present_dir in submission_directories:
        most_similar_dir, max_similarity = most_similar(present_dir, format)

        if max_similarity == 1:
            # Exact match, no typo
            continue

        if 0.75 <= max_similarity:
            diag.warning(f'Potential typo: directory submissions/{present_dir} is similar to {most_similar_dir}')
        else:
            for other_version in [v for v in FormatVersion if v != format]:
                _, max_similarity = most_similar(present_dir, other_version)
                if max_similarity == 1:
                    diag.warning(
                        f'Directory submissions/{present_dir} is not part of format version {format}, but part of {other_version}'
                    )
                    break
