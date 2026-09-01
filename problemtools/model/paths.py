"""Type-level distinction between absolute and relative paths.

`AbsolutePath`/`RelativePath` are used to communicate which paths
in our models are absolute, and which are relative, with type
system enforcement. For relative paths, the model should document
what they are relative to."""

from pathlib import Path
from typing import NewType

AbsolutePath = NewType('AbsolutePath', Path)
RelativePath = NewType('RelativePath', Path)


def abspath(path: Path) -> AbsolutePath:
    """Assert that `path` is already absolute."""
    assert path.is_absolute(), f'expected an absolute path, got {path}'
    return AbsolutePath(path)


def relpath(path: Path) -> RelativePath:
    """Assert that `path` is relative."""
    assert not path.is_absolute(), f'expected a relative path, got {path}'
    return RelativePath(path)


def resolve(path: Path) -> AbsolutePath:
    """Canonicalize `path` to an `AbsolutePath`."""
    return AbsolutePath(path.resolve())
