from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .paths import AbsolutePath, abspath, resolve


@dataclass(frozen=True)
class Attachments:
    """A problem's attachments: files found under the attachments/ directory."""

    paths: list[AbsolutePath] = field(default_factory=list)


def load_attachments(probdir: Path) -> Attachments:
    attachments_dir = resolve(probdir) / 'attachments'
    paths = [abspath(p) for p in attachments_dir.iterdir()] if attachments_dir.is_dir() else []
    return Attachments(paths=paths)
