"""Some utility functions for the run module."""

import os
import stat
from pathlib import Path


def list_files_recursive(root: Path) -> list[Path]:
    """List files in a directory with subdirectories.

    Returns:
        paths of all files contained in a directory and its
        subdirectories.
    """
    ret: list[Path] = []
    for path, _, files in os.walk(root):
        ret.extend(Path(path) / filename for filename in files)
    return ret


def check_build_dir(build_dir: Path) -> str | None:
    """Check that a build only produced regular files and directories.

    Symlinks are not followed.

    Returns:
        an error message listing everything else (symlinks, fifos, sockets,
        devices, ...) found in build_dir, or None if there is nothing else.
    """
    special = []
    for path, dirnames, filenames in os.walk(build_dir):
        for name in dirnames + filenames:
            entry = Path(path) / name
            mode = entry.lstat().st_mode
            if not stat.S_ISREG(mode) and not stat.S_ISDIR(mode):
                special.append(entry.relative_to(build_dir))
    if not special:
        return None
    names = ', '.join(str(path) for path in sorted(special))
    return f'Build produced something other than regular files and directories: {names}'
