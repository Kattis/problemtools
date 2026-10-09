import os
from pathlib import Path

from .executable import Executable
from .program import CompileResult, Program

_PACKAGE_DIR = Path(__file__).parent.parent


class Tool(Program):
    """One of problemtools' external tools. Compiling it fails if the tool was not found."""

    def __init__(self, name: str, binary: Path | None) -> None:
        """Instantiate tool object.

        Args:
            name: name of the tool.
            binary: path to the tool, or None if it was not found.
        """
        super().__init__(name=name)
        self._binary = binary

    def _do_compile(self, work_dir: Path) -> CompileResult:
        if self._binary is None:
            return CompileResult(errmsg=f'Could not locate {self.name}')
        return CompileResult(executable=Executable(self.name, self._binary, skip_memory_rlimit=True))


def get_tool_path(name: str) -> Path | None:
    """Find the path to one of problemtools' external tools.

    Args:
        name: which tool is wanted (one of [default_grader,
            default_validator, interactive, viva.sh])

    Returns:
        path to the tool, or None if the tool was not found.
    """
    return __locate_executable(
        [
            _PACKAGE_DIR / 'support' / name,
            _PACKAGE_DIR.parent / 'support' / Path(name).stem / name,
        ]
    )


def get_tool(name: str) -> Tool:
    """Get a Tool instance for one of problemtools' external tools.

    Args:
        name: same as for get_tool_path
    """
    return Tool(name, get_tool_path(name))


def __locate_executable(candidate_paths: list[Path]) -> Path | None:
    """Find executable among a set of paths.

    Args:
        candidate_paths: list of locations in which to look for an
            executable file.

    Returns:
        first entry of candidate_paths that is an executable file, or
        None if no such entry.
    """
    return next((p for p in candidate_paths if p.is_file() and os.access(p, os.X_OK)), None)
