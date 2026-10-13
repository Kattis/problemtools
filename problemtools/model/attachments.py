from __future__ import annotations

from dataclasses import dataclass, field

from .files import Files
from .paths import AbsolutePath


@dataclass(frozen=True)
class Attachments:
    """A problem's attachments: files found under the attachments/ directory."""

    paths: list[AbsolutePath] = field(default_factory=list)


def load_attachments(files: Files) -> Attachments:
    return Attachments(paths=files.listdir(files.root / 'attachments'))
