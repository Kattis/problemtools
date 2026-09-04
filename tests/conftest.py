"""Shared pytest fixtures and test doubles."""

from pathlib import Path

import pytest

from problemtools.diagnostics import Diagnostics


def datadir() -> Path:
    """Root directory holding static test fixture data."""
    return (Path(__file__).parent / 'data').resolve()


def example_directory(problem_name: str) -> Path:
    """Path to one of the example problems shipped in the repo's top-level examples/ directory."""
    return (Path(__file__).parent.parent / 'examples' / problem_name).resolve()


class RecordingDiagnostics(Diagnostics):
    """A Diagnostics that records messages instead of emitting them, for asserting on in tests."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def error(self, msg: str, additional_info: str | None = None) -> None:
        self.messages.append(('error', msg))

    def warning(self, msg: str, additional_info: str | None = None) -> None:
        self.messages.append(('warning', msg))

    def info(self, msg: str) -> None:
        pass

    def debug(self, msg: str) -> None:
        pass

    def msg(self, msg: str) -> None:
        pass

    def ttymsg(self, msg: str) -> None:
        pass

    def child(self, name: str) -> Diagnostics:
        return self

    @property
    def errors(self) -> int:
        return len([m for m in self.messages if m[0] == 'error'])

    @property
    def warnings(self) -> int:
        return len([m for m in self.messages if m[0] == 'warning'])


@pytest.fixture
def diag() -> RecordingDiagnostics:
    return RecordingDiagnostics()
