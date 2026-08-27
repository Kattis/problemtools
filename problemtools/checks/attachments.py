"""Checks for a problem package's attachments."""

from __future__ import annotations

from ..diagnostics import Diagnostics
from ..model import Attachments


def check_attachments(attachments: Attachments, diag: Diagnostics) -> None:
    """Run all checks on a problem's attachments."""
    for attachment_path in attachments.paths:
        if attachment_path.is_dir():
            diag.error(f'Directories are not allowed as attachments ({attachment_path} is a directory)')
