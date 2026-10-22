"""Glob patterns as used in submissions.yaml, matching submission and test data paths.

The syntax is deliberately small: `*` matches any number of characters within a single path
component (never `/`), and `{a,b}` matches either alternative (braces may nest). Everything else
is a literal. `**` and character classes (`[xyz]`) are not supported, and are rejected.
"""

import re
from pathlib import Path


class Glob:
    """A glob pattern on relative paths. Raises ValueError if the pattern is invalid.

    The empty pattern is special: it exactly matches only the root (Path('.')), but covers every
    path. Non-empty patterns never match the root."""

    def __init__(self, pattern: str) -> None:
        self.pattern = pattern
        self._regex = re.compile(_translate(pattern), re.DOTALL)

    def matches(self, path: Path) -> bool:
        """Whether the pattern matches exactly `path`."""
        if path == Path('.'):
            return self.pattern == ''
        return self.pattern != '' and self._regex.fullmatch(path.as_posix()) is not None

    def covers(self, path: Path) -> bool:
        """Whether the pattern matches `path`, or any of its parents."""
        return self.pattern == '' or any(self.matches(p) for p in [path, *path.parents])

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Glob) and self.pattern == other.pattern

    def __hash__(self) -> int:
        return hash(self.pattern)

    def __repr__(self) -> str:
        return f'Glob({self.pattern!r})'

    def __str__(self) -> str:
        return self.pattern


def _translate(pattern: str) -> str:
    """Translate `pattern` into an (unanchored) regex, or raise ValueError if it's invalid."""
    if '**' in pattern:
        raise ValueError(f"Invalid glob pattern '{pattern}': '**' is not supported")
    if '[' in pattern or ']' in pattern:
        raise ValueError(f"Invalid glob pattern '{pattern}': character classes ('[...]') are not supported")
    if pattern != '' and '' in pattern.split('/'):
        raise ValueError(f"Invalid glob pattern '{pattern}': empty path component (leading, trailing, or double '/')")

    parts = []
    depth = 0
    for c in pattern:
        if c == '{':
            depth += 1
            parts.append('(?:')
        elif c == '}':
            if depth == 0:
                raise ValueError(f"Invalid glob pattern '{pattern}': unmatched '}}'")
            depth -= 1
            parts.append(')')
        elif c == ',' and depth > 0:
            parts.append('|')
        elif c == '*':
            parts.append('[^/]*')
        else:
            parts.append(re.escape(c))
    if depth > 0:
        raise ValueError(f"Invalid glob pattern '{pattern}': unmatched '{{'")
    return ''.join(parts)
