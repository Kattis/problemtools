from __future__ import annotations

import dataclasses
import logging
import sys
from abc import ABC, abstractmethod
from typing import NoReturn

import colorlog


class VerifyError(Exception):
    pass


class Diagnostics(ABC):
    """Interface for emitting and recording verification diagnostics."""

    @abstractmethod
    def error(self, msg: str, additional_info: str | None = None) -> None: ...

    @abstractmethod
    def warning(self, msg: str, additional_info: str | None = None) -> None: ...

    @abstractmethod
    def info(self, msg: str) -> None: ...

    @abstractmethod
    def debug(self, msg: str) -> None: ...

    @abstractmethod
    def child(self, name: str) -> Diagnostics:
        """Return a Diagnostics scoped to a named sub-component."""
        ...

    @property
    @abstractmethod
    def errors(self) -> int: ...

    @property
    @abstractmethod
    def warnings(self) -> int: ...

    def fatal(self, msg: str, additional_info: str | None = None) -> NoReturn:
        """Report a fatal error and unconditionally stop verification."""
        self.error(msg, additional_info)
        raise VerifyError(msg)


@dataclasses.dataclass
class _Counts:
    errors: int = 0
    warnings: int = 0


class LoggingDiagnostics(Diagnostics):
    """Diagnostics implementation that emits messages via Python's logging module."""

    def __init__(
        self,
        logger: logging.Logger,
        counts: _Counts,
        bail_on_error: bool,
        warnings_as_errors: bool,
        max_additional_info: int,
    ) -> None:
        self._log = logger
        self._counts = counts
        self._bail_on_error = bail_on_error
        self._warnings_as_errors = warnings_as_errors
        self._max_additional_info = max_additional_info

    @classmethod
    def create(
        cls,
        name: str,
        log_level: int = logging.WARNING,
        bail_on_error: bool = False,
        warnings_as_errors: bool = False,
        max_additional_info: int = 15,
    ) -> LoggingDiagnostics:
        """Create a root LoggingDiagnostics instance.

        Args:
            name: Logger name; becomes the root of the child logger hierarchy.
            log_level: A logging level constant (e.g. logging.DEBUG, logging.WARNING).
            bail_on_error: Raise VerifyError on the first error, rather than continuing.
            warnings_as_errors: Treat warnings as errors.
            max_additional_info: Maximum number of lines of additional context (e.g.
                compiler output or validator feedback) to include when reporting an error
                or warning. Set to 0 to suppress additional info entirely.
        """
        colorlog.basicConfig(
            stream=sys.stdout,
            format='%(log_color)s%(levelname)s %(message)s',
            level=log_level,
        )
        return cls(
            logger=logging.getLogger(name),
            counts=_Counts(),
            bail_on_error=bail_on_error,
            warnings_as_errors=warnings_as_errors,
            max_additional_info=max_additional_info,
        )

    def child(self, name: str) -> LoggingDiagnostics:
        return LoggingDiagnostics(
            logger=self._log.getChild(name),
            counts=self._counts,
            bail_on_error=self._bail_on_error,
            warnings_as_errors=self._warnings_as_errors,
            max_additional_info=self._max_additional_info,
        )

    @property
    def errors(self) -> int:
        return self._counts.errors

    @property
    def warnings(self) -> int:
        return self._counts.warnings

    def _format(self, msg: str, additional_info: str | None) -> str:
        if additional_info is None or self._max_additional_info <= 0:
            return msg
        additional_info = additional_info.rstrip()
        if not additional_info:
            return msg
        lines = additional_info.split('\n')
        if len(lines) == 1:
            return f'{msg} ({lines[0]})'
        if len(lines) > self._max_additional_info:
            lines = lines[: self._max_additional_info] + [f'[.....truncated to {self._max_additional_info} lines.....]']
        return f'{msg}:\n' + '\n'.join(' ' * 8 + line for line in lines)

    def error(self, msg: str, additional_info: str | None = None) -> None:
        self._counts.errors += 1
        self._log.error(self._format(msg, additional_info))
        if self._bail_on_error:
            raise VerifyError(msg)

    def warning(self, msg: str, additional_info: str | None = None) -> None:
        if self._warnings_as_errors:
            self.error(msg, additional_info)
            return
        self._counts.warnings += 1
        self._log.warning(self._format(msg, additional_info))

    def info(self, msg: str) -> None:
        self._log.info(msg)

    def debug(self, msg: str) -> None:
        self._log.debug(msg)
