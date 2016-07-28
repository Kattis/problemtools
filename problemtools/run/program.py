"""Abstract base class for programs.
"""
import os
import limit
import resource
import signal
import logging

from .errors import ProgramError

class Program(object):
    """Abstract base class for programs.
    """
    runtime = 0

    def run(self, infile='/dev/null', outfile='/dev/null', errfile='/dev/null',
            args=None, timelim=1000):
        """Run the program.

        Args:
            infile (str): name of file to pass on stdin
            outfile (str): name of file to send stdout to
            errfile (str): name of file to send stderr ro
            args (list of str): additional command-line arguments to
                pass to the program
            timelim (int): CPU time limit in seconds

        Returns:
            pair (status, runtime):
               status (int): exit status of the process
               runtime (float): user+sys runtime of the process, in seconds
        """
        runcmd = self.get_runcmd()
        if runcmd == []:
            raise ProgramError('Could not figure out how to run %s' % self)
        if args is None:
            args = []

        status, runtime = self.__run_wait(runcmd + args,
                                          infile, outfile, errfile, timelim)

        self.runtime = max(self.runtime, runtime)

        return status, runtime


    @staticmethod
    def __run_wait(argv, infile='/dev/null', outfile='/dev/null',
                   errfile='/dev/null', timelim=1000):
        logging.debug('run "%s < %s > %s 2> %s"',
                      ' '.join(argv), infile, outfile, errfile)
        pid = os.fork()
        if pid == 0:  # child
            try:
                limit.try_limit(resource.RLIMIT_STACK,
                                resource.RLIM_INFINITY, resource.RLIM_INFINITY)
                limit.try_limit(resource.RLIMIT_CPU, timelim, timelim + 1)
                Program.__setfd(0, infile, os.O_RDONLY)
                Program.__setfd(1, outfile,
                                os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
                Program.__setfd(2, errfile,
                                os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
                os.execvp(argv[0], argv)
            except Exception as exc:
                print "Oops. Fatal error in child process:"
                print exc
                os.kill(os.getpid(), signal.SIGTERM)
            #Unreachable
            logging.error("Unreachable part of run_wait reached")
            os.kill(os.getpid(), signal.SIGTERM)
        (pid, status, rusage) = os.wait4(pid, 0)
        return status, rusage.ru_utime + rusage.ru_stime


    @staticmethod
    def __setfd(fd, filename, flag):
        tmpfd = os.open(filename, flag)
        os.dup2(tmpfd, fd)
        os.close(tmpfd)
