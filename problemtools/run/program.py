"""Abstract base class for programs."""

import dataclasses
import logging
import os
import resource
import signal
import threading
from abc import ABC, abstractmethod
from pathlib import Path

from . import limit
from .errors import ProgramError

log = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class CompileResult:
    """Result of compiling a Program.

    `path` is always set (even on a failed compile): it's the resolved path to
    the program, established as a side effect of compiling. It's the only
    reliable way to learn a program's path -- `Program.path` raises if read
    before compile() has been called."""

    success: bool
    errmsg: str | None
    path: Path


class Program(ABC):
    """Abstract base class for programs."""

    def __init__(self, name: str, path: Path | None = None) -> None:
        """Instantiate program object.

        Args:
            name: human-readable name of the program.
            path: full path to the program, if already known (possibly in a
                temporary directory). Subclasses for which the path isn't known
                until compile time (e.g. source code that gets copied into a
                work directory) should leave this unset and assign `self._path`
                as part of `do_compile()`.
        """
        self._path = path
        self.name = name
        self._compile_lock = threading.Lock()
        self._compile_result: CompileResult | None = None

    @property
    def path(self) -> Path:
        if self._path is None:
            raise ProgramError(f'{self} has not been compiled yet')
        return self._path

    def __str__(self) -> str:
        return self.name

    @abstractmethod
    def get_runcmd(self, cwd: str | None = None, memlim: int = 1024) -> list[str]:
        pass

    def run(
        self,
        infile: str = '/dev/null',
        outfile: str = '/dev/null',
        errfile: str = '/dev/null',
        args: list[str] | None = None,
        timelim: int = 1000,
        memlim: int = 1024,
        work_dir: Path | None = None,
    ) -> tuple[int, float]:
        """Run the program.

        Args:
            infile: name of file to pass on stdin
            outfile: name of file to send stdout to
            errfile: name of file to send stderr to
            args: additional command-line arguments to pass to the program
            timelim: CPU time limit in seconds
            memlim: memory limit in MiB

        Returns:
            pair (status, runtime):
               status: exit status of the process
               runtime: user+sys runtime of the process, in seconds
        """
        runcmd = self.get_runcmd(memlim=memlim)
        if runcmd == []:
            raise ProgramError(f'Could not figure out how to run {self}')
        if args is None:
            args = []

        status, runtime = self.__run_wait(runcmd + args, infile, outfile, errfile, timelim, memlim, work_dir)

        return status, runtime

    def compile(self, work_dir: Path) -> CompileResult:
        """Compile the program, if needed, and return the result.

        Only the first call actually compiles; later calls (even with a different
        work_dir) return the cached result. work_dir is only used by subclasses that
        need a place to set up a compile workspace (i.e. source code); others ignore it.
        """
        with self._compile_lock:
            if self._compile_result is None:
                self._compile_result = self.do_compile(work_dir)
            return self._compile_result

    def do_compile(self, work_dir: Path) -> CompileResult:
        """Actually compile the program, if needed. Subclasses should override this method.
        Do not call this manually -- use compile() instead."""
        return CompileResult(True, None, self.path)

    def code_size(self) -> int:
        """Subclasses should override this method with the total size of the
        source code."""
        return 0

    def should_skip_memory_rlimit(self) -> bool:
        """Ugly workaround to accommodate Java -- the JVM will crash and burn
        if there is a memory rlimit applied and this will probably not
        change anytime soon [time of writing this: 2017-02-05], see
        e.g.: https://bugs.openjdk.java.net/browse/JDK-8071445

        Subclasses of Program where the associated program is (or may
        be) a Java program need to override this method and return
        True (which will cause the memory rlimit to not be applied).

        2019-02-22: Turns out sbcl for Common Lisp also wants to roam
        free and becomes sad when reined in by a memory rlimit.
        """
        return False

    def __run_wait(
        self,
        argv: list[str],
        infile: str,
        outfile: str,
        errfile: str,
        timelim: int,
        memlim: int,
        work_dir: Path | None,
    ) -> tuple[int, float]:
        log.debug('run "%s < %s > %s 2> %s"', ' '.join(argv), infile, outfile, errfile)
        pid = os.fork()
        if pid == 0:  # child
            try:
                # The Python interpreter internally sets some signal dispositions
                # to SIG_IGN (notably SIGPIPE), and unless we reset them manually
                # this leaks through to the program we exec. That can has some
                # funny side effects, like programs not crashing as expected when
                # trying to write to an interactive validator that has terminated
                # and closed the read end of a pipe.
                #
                # This *shouldn't* cause any verdict changes given the setup for
                # interactive problems, but reset them anyway, for sanity.
                if hasattr(signal, 'SIGPIPE'):
                    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
                if hasattr(signal, 'SIGXFZ'):
                    signal.signal(signal.SIGXFZ, signal.SIG_DFL)
                if hasattr(signal, 'SIGXFSZ'):
                    signal.signal(signal.SIGXFSZ, signal.SIG_DFL)

                limit.try_limit(resource.RLIMIT_CPU, timelim, timelim + 1)
                if not self.should_skip_memory_rlimit():
                    limit.try_limit(resource.RLIMIT_AS, memlim * (1024**2), resource.RLIM_INFINITY)
                limit.try_limit(resource.RLIMIT_STACK, resource.RLIM_INFINITY, resource.RLIM_INFINITY)

                Program.__setfd(0, infile, os.O_RDONLY)
                Program.__setfd(1, outfile, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
                Program.__setfd(2, errfile, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
                if work_dir is not None:
                    os.chdir(work_dir)
                os.execvp(argv[0], argv)
            except Exception as exc:
                print('Oops. Fatal error in child process:')
                print(exc)
                os.kill(os.getpid(), signal.SIGTERM)
            # Unreachable
            log.error('Unreachable part of run_wait reached')
            os.kill(os.getpid(), signal.SIGTERM)
        (pid, status, rusage) = os.wait4(pid, 0)
        return status, rusage.ru_utime + rusage.ru_stime

    @staticmethod
    def __setfd(fd: int, filename: str, flag: int) -> None:
        tmpfd = os.open(filename, flag)
        os.dup2(tmpfd, fd)
        os.close(tmpfd)
