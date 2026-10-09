"""In-memory snapshot of the files making up a program (e.g. a submission or validator)."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from .paths import RelativePath, relpath


@dataclass(frozen=True)
class ProgramFile:
    """A single file of a program.

    `path` is relative to the program's root, e.g. for
    submissions/accepted/hello/src/main.cpp, path is src/main.cpp.
    """

    path: RelativePath
    data: bytes
    executable: bool


@dataclass(frozen=True)
class ProgramFiles:
    """All files of a program, sorted by path."""

    files: list[ProgramFile] = field(default_factory=list)

    def merged(self, other: 'ProgramFiles') -> 'ProgramFiles':
        """Files from both self and other; where paths coincide, the file from other wins."""
        by_path = {file.path: file for file in self.files} | {file.path: file for file in other.files}
        return ProgramFiles(files=sorted(by_path.values(), key=lambda file: file.path))

    def materialize(self, dest: Path) -> None:
        """Write the files into dest, creating subdirectories as needed.

        Existing files are overwritten. Files are written with mode 0755 if
        executable, 0644 otherwise.
        """
        for file in self.files:
            target = dest / file.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(file.data)
            target.chmod(0o755 if file.executable else 0o644)

    def size(self) -> int:
        """Total size of the files, in bytes."""
        return sum(len(file.data) for file in self.files)


def load_program_files(path: Path) -> ProgramFiles:
    """Load the files of the program at path.

    path is either a single file (giving a program with that one file), or a
    directory, which is read recursively, following symlinks. A file counts as
    executable if any of its execute bits are set.
    """
    if path.is_file():
        return ProgramFiles(files=[_load_file(path, relpath(Path(path.name)))])

    files = []
    for root, _, filenames in os.walk(path, followlinks=True):
        for filename in filenames:
            file_path = Path(root) / filename
            files.append(_load_file(file_path, relpath(file_path.relative_to(path))))
    return ProgramFiles(files=sorted(files, key=lambda file: file.path))


def _load_file(path: Path, relative: RelativePath) -> ProgramFile:
    return ProgramFile(path=relative, data=path.read_bytes(), executable=bool(path.stat().st_mode & 0o111))
