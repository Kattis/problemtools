import glob
import os
import signal
import resource
import logging
import re


class Program:
    # TODO: make language settings more configurable
    _SUFFIXES = {'.c': 'C',
                 '.cc': 'C++',
                 '.cpp': 'C++',
                 '.cxx': 'C++',
                 '.c++': 'C++',
                 '.C': 'C++',
                 '.java': 'Java',
                 '.pl': 'Prolog',
                 '.py': 'Python',
                 '.cs': 'C#',
                 '.c#': 'C#',
                 '.go': 'Go',
                 '.hs': 'Haskell'
                 }
    _COMPILE = {
        'C': 'gcc -O2 -static -std=gnu99 -o "%(exec)s" %(src)s -lm',
        'C++': 'g++ -O2 -static -std=gnu++0x -o "%(exec)s" %(src)s',
        'Java': 'javac -d %(execdir)s %(src)s',
        'Prolog': 'swipl -O -q -g main -t halt -o "%(exec)s" -c %(src)s',
        'Python': None,
        'C#': 'dmcs -optimize+ -r:System.Numerics "-out:%(exec)s.exe" %(src)s',
        'Go': 'gccgo -g -static-libgcc -o "%(exec)s" %(src)s',
        'Haskell': 'ghc -O2 -ferror-spans -threaded -rtsopts -o "%(exec)s" %(src)s',
        'dir': 'cd "%(path)s" && ./build',
        'executable': None
        }
    _RUN = {
        'C': ['%(exec)s'],
        'C++': ['%(exec)s'],
        'Java': ['java', '-Xmx2048m', '-Xss8m', '-cp', '%(execdir)s', '%(execbase)s'],
        'Prolog': ['%(exec)s'],
        'Python': ['python2', '%(mainfile)s'],
        'C#': ['%(exec)s.exe'],
        'Go': ['%(exec)s'],
        'Haskell': ['%(exec)s'],
        'dir': ['%(path)s/run'],
        'executable': ['%(path)s']
        }
    _INCLUDE_FILES = {
        'C': 'c/*.c',
        'C++': 'cpp/*.{cc,cpp,c++}',
        'Java': 'java/*.java',
        'Prolog': 'prolog/*.pl',
        'Python': 'python/*.py',
        'C#': 'cs/*.{cs,c#}',
        'Go': 'go/*.go',
        'Haskell': 'haskell/*.hs',
        'dir': '',
        'executable': '',
        }

    def __init__(self, path, allowExecutable=False, includedir=None):
        ext = os.path.splitext(path)[1]
        self.path = path
        if self.path[-1] == '/':
            self.path = self.path[:-1]
        self.name = os.path.basename(self.path)
        self.lang = None
        self.includedir = includedir
        if os.path.isdir(self.path):
            if os.access(os.path.join(self.path, 'build'), os.X_OK):
                # we have a build script
                self.src = [os.path.join(self.path, x) for x in os.listdir(self.path)]
                self.lang = 'dir'
            else:
                # no build script; try to find some source files
                for suff in Program._SUFFIXES:
                    f = sorted(glob.glob(os.path.join(path, '*' + suff)))
                    if f:
                        self.src = f
                        self.lang = Program._SUFFIXES[suff]
                        break
        elif allowExecutable and os.access(path, os.X_OK):
            self.src = [path]
            self.lang = 'executable'
        elif ext in Program._SUFFIXES:
            self.src = [path]
            self.lang = Program._SUFFIXES[ext]

        if self.lang == None:
            raise Exception("Could not instantiate program from %s" % path)

    runcmd = None
    _compile_result = None

    def compile(self, logger=None):
        if self._compile_result != None:
            return self._compile_result

        compiler = Program._COMPILE[self.lang]
        mainfile = next((x for x in self.src if re.match('^[Mm]ain\.', os.path.basename(x))), self.src[0])
        executable = os.path.splitext(mainfile)[0]
        args = {'path': self.path,
                'mainfile': mainfile,
                'src': ' '.join(self.src),
                'exec': executable,
                'execbase': os.path.basename(executable),
                'execdir': os.path.dirname(executable)
                }
        if self.includedir:
            includefiles = glob.glob(os.path.join(self.includedir, Program._INCLUDE_FILES[self.lang]))
            args['src'] += ' ' + ' '.join(includefiles)
            if self.lang == 'Java' and sum([x.endswith('Main.java') for x in includefiles]):
                args['execbase'] = 'Main'
            elif self.lang == 'Python' and sum([x.endswith('main.py') for x in includefiles]):
                args['mainfile'] = 'main'

        self.runcmd = []
        if compiler != None:
            compiler = (compiler + ' > /dev/null 2> /dev/null') % args
            logging.debug('compile: %s', compiler)
            status = os.system(compiler)

            if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
                if logger != None:
                    logger.error('Compiler failed (status %d) when compiling %s\n        Command used: %s' % (status, self.name, compiler % args))
                self._compile_result = False
                return False

        self._compile_result = True
        self.runcmd = [x % args for x in Program._RUN[self.lang]]
        return self._compile_result

    runtime = 0

    def get_runcmd(self, logger=None):
        self.compile(logger)
        return self.runcmd

    def run(self, infile='/dev/null', outfile='/dev/null', errfile='/dev/null', args=None, timelim=1000, logger=None):
        runcmd = self.get_runcmd(logger)
        if runcmd == []:
            if logger != None:
                logger.error('Could not run %s' % (self.name))
            return -1
        if args == None:
            args = []  # Damn you Python

        status, runtime = self._run_wait(runcmd + args, infile, outfile, errfile, timelim)

        self.runtime = max(self.runtime, runtime)

        return status, runtime

    def _run_wait(self, argv, infile="/dev/null", outfile="/dev/null", errfile="/dev/null", timelim=1000):
        logging.debug('run "%s < %s > %s 2> %s"', ' '.join(argv), infile, outfile, errfile)
        pid = os.fork()
        if pid == 0:  # child
            try:
                resource.setrlimit(resource.RLIMIT_CPU, (timelim, timelim + 1))
                self._setfd(0, infile, os.O_RDONLY)
                self._setfd(1, outfile, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
                self._setfd(2, errfile, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
                os.execvp(argv[0], argv)
            except Exception as e:
                print "Error"
                print e
                os.kill(os.getpid(), signal.SIGTERM)
            #Unreachable
            logging.error("Unreachable part of run_wait reached")
            os.kill(os.getpid(), signal.SIGTERM)
        (pid, status, rusage) = os.wait4(pid, 0)
        return status, rusage.ru_utime + rusage.ru_stime

    def _setfd(self, fd, filename, flag):
        tmpfd = os.open(filename, flag)
        os.dup2(tmpfd, fd)
        os.close(tmpfd)

    def __str__(self):
        return 'Program(%s)' % (self.name,)
