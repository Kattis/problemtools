"""The files and directories making up a problem package.

The package is represented as a logical tree: entries are keyed by the path at
which they appear in the package, with symlinks (to files or directories inside
the package) followed. E.g., if data/secret/group is a symlink to ../sample,
then data/secret/group/1.in is an entry.

Entries whose name starts with '.' are ignored (and not descended into).
Entries which can not be part of a valid package (see BadReason) are recorded,
but are not part of the tree.
"""

from __future__ import annotations

import errno
import os
import stat
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path

from .paths import AbsolutePath, abspath, resolve


class EntryKind(Enum):
    FILE = auto()
    DIR = auto()


class BadReason(Enum):
    ABSOLUTE_SYMLINK = auto()
    OUTSIDE_PACKAGE = auto()
    BROKEN_SYMLINK = auto()
    SYMLINK_LOOP = auto()
    IGNORED_TARGET = auto()  # symlink pointing at, or into, an ignored entry
    SPECIAL_FILE = auto()  # fifo, socket, device, ...


@dataclass(frozen=True)
class BadEntry:
    path: AbsolutePath
    reason: BadReason


@dataclass(frozen=True)
class Files:
    """All files and directories of a problem package.

    All paths are absolute logical paths (i.e., below root, with symlinks not
    resolved). Paths passed to the query methods must be absolute (asserted, but
    typed as Path for convenience), and are matched exactly.
    """

    root: AbsolutePath
    entries: dict[AbsolutePath, EntryKind] = field(default_factory=dict)
    ignored: list[AbsolutePath] = field(default_factory=list)
    bad: list[BadEntry] = field(default_factory=list)
    # Sorted children of root and of each directory in entries.
    _children: dict[AbsolutePath, list[AbsolutePath]] = field(default_factory=dict, repr=False)

    def is_file(self, path: Path) -> bool:
        return self.entries.get(abspath(path)) == EntryKind.FILE

    def is_dir(self, path: Path) -> bool:
        return abspath(path) in self._children

    def listdir(self, dir: Path, kind: EntryKind | None = None) -> list[AbsolutePath]:
        """Sorted entries directly in dir, optionally only those of the given kind.

        Empty if dir is not a directory in the package.
        """
        return [path for path in self._children.get(abspath(dir), []) if kind is None or self.entries[path] == kind]

    def walk(self, dir: Path, kind: EntryKind | None = EntryKind.FILE) -> list[AbsolutePath]:
        """Sorted entries anywhere below dir, optionally only those of the given kind.

        Empty if dir is not a directory in the package.
        """
        found: list[AbsolutePath] = []
        stack = list(self._children.get(abspath(dir), []))
        while stack:
            path = stack.pop()
            if kind is None or self.entries[path] == kind:
                found.append(path)
            stack.extend(self._children.get(path, []))
        return sorted(found)


def load_files(probdir: Path) -> Files:
    """Walk the problem package at probdir, following symlinks inside the package."""
    root = resolve(probdir)
    files = Files(root=root)
    _walk(files, root, root, frozenset([root]))
    return files


def _walk(files: Files, dir: AbsolutePath, real_dir: Path, ancestors: frozenset[Path]) -> None:
    """Add the contents of the directory at dir (which really is real_dir) to files.

    ancestors are the real paths of all directories from root down to (and including) real_dir.
    """
    children = files._children.setdefault(dir, [])
    for name in sorted(os.listdir(real_dir)):
        path = abspath(dir / name)
        if name.startswith('.'):
            files.ignored.append(path)
            continue

        real = real_dir / name
        st = os.lstat(real)
        if stat.S_ISLNK(st.st_mode):
            reason = _check_symlink(files.root, real)
            if reason is not None:
                files.bad.append(BadEntry(path, reason))
                continue
            real = Path(os.path.realpath(real))
            st = os.stat(real)

        if stat.S_ISDIR(st.st_mode):
            if real in ancestors:
                files.bad.append(BadEntry(path, BadReason.SYMLINK_LOOP))
                continue
            files.entries[path] = EntryKind.DIR
            children.append(path)
            _walk(files, path, real, ancestors | {real})
        elif stat.S_ISREG(st.st_mode):
            files.entries[path] = EntryKind.FILE
            children.append(path)
        else:
            files.bad.append(BadEntry(path, BadReason.SPECIAL_FILE))


def _check_symlink(root: Path, symlink: Path) -> BadReason | None:
    """Check whether symlink is bad, returning the reason if so."""
    if os.path.isabs(os.readlink(symlink)):
        return BadReason.ABSOLUTE_SYMLINK
    try:
        target = Path(os.path.realpath(symlink, strict=True))
    except OSError as e:
        return BadReason.SYMLINK_LOOP if e.errno == errno.ELOOP else BadReason.BROKEN_SYMLINK
    if not target.is_relative_to(root):
        return BadReason.OUTSIDE_PACKAGE
    if any(part.startswith('.') for part in target.relative_to(root).parts):
        return BadReason.IGNORED_TARGET
    return None
