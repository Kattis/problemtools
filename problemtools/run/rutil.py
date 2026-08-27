"""Some utility functions for the run module."""

import errno
import os
import shutil
from pathlib import Path

from .errors import ProgramError


def add_files(src: str | Path, dstdir: str | Path) -> None:
    """Copy src to dstdir.

    Args:
        src: path of file(s) to copy.
            If path is a file, that file will simply be copied to
            dstdir.
            If path is a directory, then every entry (both files and
            subdirectories) in that directory will be copied to
            dstdir.
        dstdir: directory into which to copy src.  Must be an
            existing directory.
    """
    try:
        if os.path.isfile(src):
            shutil.copy(src, dstdir)
        else:
            for name in os.listdir(src):
                srcfile = os.path.join(src, name)
                destfile = os.path.join(dstdir, name)
                if os.path.isdir(srcfile):
                    shutil.copytree(srcfile, destfile, dirs_exist_ok=True)
                else:
                    shutil.copy(srcfile, destfile)
    except OSError as exc:
        # FIXME why is this specific error special-cased
        if exc.errno == errno.ENOENT:
            raise ProgramError(f'File not found when copying program:\n {exc.filename}')
        raise


def list_files_recursive(root: str | Path) -> list[str]:
    """List files in a directory with subdirectories.

    Returns:
        all file names for all files contained in a directory and its
        subdirectories.
    """
    ret = []
    for path, _, files in os.walk(root):
        ret.extend([os.path.join(root, path, filename) for filename in files])
    return ret
