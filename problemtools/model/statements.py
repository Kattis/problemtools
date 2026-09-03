from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .. import statement_util
from ..formatversion import FormatVersion
from .paths import AbsolutePath, abspath, resolve


@dataclass(frozen=True)
class Statements:
    """A problem's statements, keyed by language code.

    Well-formed packages have exactly one statement per language; this keeps every
    file found (rather than just the first) so checks can report duplicates."""

    by_language: dict[str, list[AbsolutePath]] = field(default_factory=dict)


def load_statements(probdir: Path, format_version: FormatVersion) -> Statements:
    probdir = resolve(probdir)
    found = statement_util.find_statements(probdir, format_version)
    return Statements(by_language={lang: [abspath(p) for p in paths] for lang, paths in found.items()})
