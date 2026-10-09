"""A compiled program, ready to be run."""

import logging
import os
import resource
import signal
from pathlib import Path

from . import limit
from .errors import ProgramError

log = logging.getLogger(__name__)

DEV_NULL = Path(os.devnull)


class Executable:
    """Something that can be run: the result of compiling a Program."""

    name: str  # Human-readable name of the program
    build_dir: Path | None  # Directory the program was built in, if any

    def __init__(
        self,
        name: str,
        binary: Path,
        args: list[str] | None = None,
        build_dir: Path | None = None,
        skip_memory_rlimit: bool = False,
        swap_exit_codes: bool = False,
        infile_as_arg: bool = False,
    ) -> None:
        """Instantiate executable object.

        Args:
            name: human-readable name of the program.
            binary: path to the file to execute.
            args: additional command line arguments passed to the program
                every time it is executed.
            build_dir: directory the program was built in, if any.
            skip_memory_rlimit: do not apply a memory rlimit when running
                the program. Ugly workaround to accommodate Java -- the JVM
                will crash and burn if there is a memory rlimit applied and
                this will probably not change anytime soon [time of writing
                this: 2017-02-05], see e.g.:
                https://bugs.openjdk.java.net/browse/JDK-8071445
                2019-02-22: Turns out sbcl for Common Lisp also wants to roam
                free and becomes sad when reined in by a memory rlimit.
            swap_exit_codes: swap exit codes 0 and 42, for programs which
                exit with 0 on accept (e.g. Checktestdata and VIVA).
            infile_as_arg: pass infile as the last command line argument
                instead of on stdin.
        """
        self.name = name
        self.build_dir = build_dir
        self._binary = binary
        self._args = args if args is not None else []
        self._skip_memory_rlimit = skip_memory_rlimit
        self._swap_exit_codes = swap_exit_codes
        self._infile_as_arg = infile_as_arg

    def __str__(self) -> str:
        return self.name

    def get_runcmd(self, cwd: Path | None = None, memlim: int = 1024) -> list[str]:
        """Command to run the program.

        Args:
            cwd: if not None, the run command is provided
                relative to cwd (otherwise absolute paths are given).
                Only properly supported for programs compiled from
                SourceCode or BuildRun, with cwd a parent of build_dir:
                paths in args (e.g. a Checktestdata script) are not made
                relative.
            memlim: memory limit in MiB (only relevant for
                programs where memory limit is passed on command line)
        """
        binary = self._binary if cwd is None else Path(os.path.relpath(self._binary, cwd))
        return [str(binary)] + self._args

    def run(
        self,
        infile: Path = DEV_NULL,
        outfile: Path = DEV_NULL,
        errfile: Path = DEV_NULL,
        args: list[str] | None = None,
        timelim: int = 1000,
        memlim: int = 1024,
        work_dir: Path | None = None,
    ) -> tuple[int, float]:
        """Run the program.

        Args:
            infile: file to pass on stdin
            outfile: file to send stdout to
            errfile: file to send stderr to
            args: additional command-line arguments to pass to the program
            timelim: CPU time limit in seconds
            memlim: memory limit in MiB
            work_dir: directory to run the program in

        Returns:
            pair (status, runtime):
               status: exit status of the process
               runtime: user+sys runtime of the process, in seconds
        """
        runcmd = self.get_runcmd(memlim=memlim)
        if runcmd == []:
            raise ProgramError(f'Could not figure out how to run {self}')
        argv = runcmd + (args if args is not None else [])
        if self._infile_as_arg:
            if infile != DEV_NULL:
                argv.append(str(infile))
            infile = DEV_NULL

        status, runtime = self.__run_wait(argv, infile, outfile, errfile, timelim, memlim, work_dir)

        if self._swap_exit_codes and os.WIFEXITED(status):
            if os.WEXITSTATUS(status) == 0:
                status = 42 << 8
            elif os.WEXITSTATUS(status) == 42:
                status = 0
        return status, runtime

    def __run_wait(
        self,
        argv: list[str],
        infile: Path,
        outfile: Path,
        errfile: Path,
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
                if not self._skip_memory_rlimit:
                    limit.try_limit(resource.RLIMIT_AS, memlim * (1024**2), resource.RLIM_INFINITY)
                limit.try_limit(resource.RLIMIT_STACK, resource.RLIM_INFINITY, resource.RLIM_INFINITY)

                Executable.__setfd(0, infile, os.O_RDONLY)
                Executable.__setfd(1, outfile, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
                Executable.__setfd(2, errfile, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
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
    def __setfd(fd: int, filename: Path, flag: int) -> None:
        tmpfd = os.open(filename, flag)
        os.dup2(tmpfd, fd)
        os.close(tmpfd)
