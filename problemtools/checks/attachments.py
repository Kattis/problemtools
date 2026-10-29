"""Checks for a problem package's attachments."""

from __future__ import annotations

from ..diagnostics import Diagnostics, pluralize
from ..formatversion import FormatVersion
from ..languages import Languages
from ..metadata import Metadata
from ..model import TEMPLATES_DIRECTORY, Attachments, EntryKind, Files


def check_attachments(
    attachments: Attachments, files: Files, metadata: Metadata, language_config: Languages, diag: Diagnostics
) -> None:
    """Run all checks on a problem's attachments."""
    for attachment_path in attachments.paths:
        if attachment_path.is_dir():
            diag.error(f'Directories are not allowed as attachments ({attachment_path} is a directory)')
    _check_templates(attachments, files, metadata, language_config, diag)


def _check_templates(
    attachments: Attachments, files: Files, metadata: Metadata, language_config: Languages, diag: Diagnostics
) -> None:
    templates_dir = files.root / 'attachments' / TEMPLATES_DIRECTORY
    if attachments.templates:
        diag.msg(f'Checking code templates for {pluralize(len(attachments.templates), "language")}')
        if metadata.problem_format_version is FormatVersion.LEGACY:
            diag.warning('Code templates are not part of the legacy problem format')
    for path in files.listdir(templates_dir, EntryKind.FILE):
        diag.error(f'Code templates must be in a directory per language, found file {path}')
    for lang_id, program_files in attachments.templates.items():
        if language_config.get(lang_id) is None:
            diag.error(f'Code templates found for unknown language "{lang_id}"')
        elif metadata.languages != 'all' and lang_id not in metadata.languages:
            diag.warning(f'Code templates found for language "{lang_id}", which is not allowed by problem.yaml')
        if not program_files.files:
            diag.error(f'Code templates directory for language "{lang_id}" is empty')
