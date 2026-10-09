"""Abstract base class for programs."""

import dataclasses
import threading
from abc import ABC, abstractmethod
from pathlib import Path

from .executable import Executable


@dataclasses.dataclass(frozen=True)
class CompileResult:
    """Result of compiling a Program.

    Exactly one of `executable` (on success) and `errmsg` (on failure) is set."""

    executable: Executable | None = None
    errmsg: str | None = None

    def __post_init__(self) -> None:
        assert (self.executable is None) != (self.errmsg is None), 'CompileResult needs exactly one of executable and errmsg'

    @property
    def success(self) -> bool:
        return self.executable is not None


class Program(ABC):
    """Abstract base class for programs."""

    name: str  # Human-readable name of the program

    def __init__(self, name: str) -> None:
        """Instantiate program object.

        Args:
            name: human-readable name of the program.
        """
        self.name = name
        self._compile_lock = threading.Lock()
        self._compile_results: dict[Path, CompileResult] = {}

    def __str__(self) -> str:
        return self.name

    def compile(self, work_dir: Path) -> CompileResult:
        """Compile the program, if needed, and return the result.

        Results are cached per work_dir, so compiling to a work_dir the
        program has already been compiled to returns the earlier result.
        work_dir is only used by subclasses that need a place to set up a
        compile workspace (i.e. source code); others ignore it.
        """
        key = work_dir.resolve()
        with self._compile_lock:
            if key not in self._compile_results:
                self._compile_results[key] = self._do_compile(work_dir)
            return self._compile_results[key]

    @abstractmethod
    def _do_compile(self, work_dir: Path) -> CompileResult:
        """Actually compile the program. Subclasses implement this, callers use compile()."""
