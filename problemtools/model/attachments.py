from __future__ import annotations

from dataclasses import dataclass, field

from .files import EntryKind, Files
from .paths import AbsolutePath
from .program_files import ProgramFiles, load_program_files

TEMPLATES_DIRECTORY = 'templates'


@dataclass(frozen=True)
class Attachments:
    """A problem's attachments: files found under the attachments/ directory."""

    paths: list[AbsolutePath] = field(default_factory=list)
    templates: dict[str, ProgramFiles] = field(default_factory=dict)


def load_attachments(files: Files) -> Attachments:
    attachments_dir = files.root / 'attachments'
    templates_dir = attachments_dir / TEMPLATES_DIRECTORY
    return Attachments(
        paths=[path for path in files.listdir(attachments_dir) if path != templates_dir],
        templates={
            lang_dir.name: load_program_files(files, lang_dir) for lang_dir in files.listdir(templates_dir, EntryKind.DIR)
        },
    )
