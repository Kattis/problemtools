"""Shared pytest fixtures and test doubles."""

import pytest

from problemtools.diagnostics import Diagnostics


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
