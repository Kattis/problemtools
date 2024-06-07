"""Abstract base class for programs.
"""
import os
from . import limit
import resource
import signal
import logging
import threading

from .errors import ProgramError

log = logging.getLogger(__name__)


class Program(object):
    """Abstract base class for programs.
    """

    def __init__(self) -> None:
        self.runtime = 0
        self._compile_lock = threading.Lock()
        self._compile_result: tuple[bool, str|None]|None = None

    def run(self, infile='/dev/null', outfile='/dev/null', errfile='/dev/null',
            args=None, timelim=1000, memlim=1024, set_work_dir=False):
        """Run the program.

        Args:
            infile (str): name of file to pass on stdin
            outfile (str): name of file to send stdout to
            errfile (str): name of file to send stderr ro
            args (list of str): additional command-line arguments to
                pass to the program
            timelim (int): CPU time limit in seconds
            memlim (int): memory limit in MB

        Returns:
            pair (status, runtime):
               status (int): exit status of the process
               runtime (float): user+sys runtime of the process, in seconds
        """
        runcmd = self.get_runcmd(memlim=memlim)
        if runcmd == []:
            raise ProgramError('Could not figure out how to run %s' % self)
        if args is None:
            args = []
        if self.should_skip_memory_rlimit():
            memlim = None

        status, runtime = self.__run_wait(runcmd + args,
                                          infile, outfile, errfile,
                                          timelim, memlim, self.path if set_work_dir else None)

        self.runtime = max(self.runtime, runtime)

        return status, runtime

    def compile(self) -> tuple[bool, str|None]:
        with self._compile_lock:
            if self._compile_result is None:
                self._compile_result = self.do_compile()
            return self._compile_result

    def do_compile(self) -> tuple[bool, str|None]:
        """Actually compile the program, if needed. Subclasses should override this method.
        Do not call this manually -- use compile() instead."""
        return (True, None)

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


    @staticmethod
    def __run_wait(argv, infile, outfile, errfile, timelim, memlim, working_directory=None):
        log.debug('run "%s < %s > %s 2> %s"',
                      ' '.join(argv), infile, outfile, errfile)
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
                if hasattr(signal, "SIGPIPE"):
                    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
                if hasattr(signal, "SIGXFZ"):
                    signal.signal(signal.SIGXFZ, signal.SIG_DFL)
                if hasattr(signal, "SIGXFSZ"):
                    signal.signal(signal.SIGXFSZ, signal.SIG_DFL)

                if timelim is not None:
                    limit.try_limit(resource.RLIMIT_CPU, timelim, timelim + 1)
                if memlim is not None:
                    limit.try_limit(resource.RLIMIT_AS, memlim * (1024**2), resource.RLIM_INFINITY)
                limit.try_limit(resource.RLIMIT_STACK,
                                resource.RLIM_INFINITY, resource.RLIM_INFINITY)

                Program.__setfd(0, infile, os.O_RDONLY)
                Program.__setfd(1, outfile,
                                os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
                Program.__setfd(2, errfile,
                                os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
                if working_directory is not None:
                    os.chdir(working_directory)
                os.execvp(argv[0], argv)
            except Exception as exc:
                print("Oops. Fatal error in child process:")
                print(exc)
                os.kill(os.getpid(), signal.SIGTERM)
            # Unreachable
            log.error("Unreachable part of run_wait reached")
            os.kill(os.getpid(), signal.SIGTERM)
        (pid, status, rusage) = os.wait4(pid, 0)
        return status, rusage.ru_utime + rusage.ru_stime


    @staticmethod
    def __setfd(fd, filename, flag):
        tmpfd = os.open(filename, flag)
        os.dup2(tmpfd, fd)
        os.close(tmpfd)
