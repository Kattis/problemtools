"""Some utility functions for the run module."""

import os
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
