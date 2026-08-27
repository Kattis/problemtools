from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Attachments:
    """A problem's attachments: files found under the attachments/ directory."""

    paths: list[Path] = field(default_factory=list)


def load_attachments(probdir: Path) -> Attachments:
    attachments_dir = probdir / 'attachments'
    paths = list(attachments_dir.iterdir()) if attachments_dir.is_dir() else []
    return Attachments(paths=paths)
