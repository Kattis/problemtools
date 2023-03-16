"""
Logging for problemtools.verifyproblem.

The logging hierarchy has depth two and uses different logger classes.
Every problem is at the top of a logging hierarchy, below which are the problem
aspects (which may be parts such # as "output validators" or test cases):

  verifyproblem: RootLogger
  |
  +- hello: ProblemLogger
  |     |
  |     +- submissions: AspectLogger
  |     +- test case secret/002-huge.in: AspectLogger
  |
  +- different: ProblemLogger
     |
     +- submissions: AspectLogger

Naming conventions follow the ideas laid out in Python's logging module, so that
child loggers are called "parent.child", such as "verifyproblem.hello.submissions"

Most of the work is done in the ProblemLogger class, which contains
custom handlers, filters, and formatters.  The behaviour of those is configured by passing
the command line arguments of verifyproblem to the config function.

All other loggers (say, different.submissions) are instances of AspectLogger
and have no custom configuration -- they mainly pass on their messages to the
problem logger. Each AspectLogger does have its own counter, but no handlers
or formatters.

TODO: Think about:
* Should every Submission have its own logger?
* Should every test case group have its own logger?
"""

import logging
import sys
import yaml
from . import verifyproblem


# ---------------------------------------------------------------------------
#  Custom handlers
# ---------------------------------------------------------------------------


class BailOnError(logging.StreamHandler):
    """
    Handler that raises VerifyError when it first handles an ERROR.
    """

    def emit(self, record: logging.LogRecord):
        super().emit(record)
        if record.levelno >= logging.ERROR:
            raise verifyproblem.VerifyError()


# ---------------------------------------------------------------------------
# Custom filters
# ---------------------------------------------------------------------------


class Counter(logging.Filter):
    """
    A stateful filter than counts the number of warnings and errors it has seen.
    """

    def __init__(self):
        super().__init__()
        self.errors: int = 0
        self.warnings: int = 0

    def __str__(self) -> str:
        def p(x):
            return "" if x == 1 else "s"

        return f"{self.errors} error{p(self.errors)}, {self.warnings} warning{p(self.warnings)}"

    def filter(self, record) -> bool:
        if record.levelno == logging.WARNING:
            self.warnings += 1
        if record.levelno == logging.ERROR:
            self.errors += 1
        return True


class TreatWarningsAsErrors(logging.Filter):
    """
    Escalate the level of a WARNING passing through this filter to ERROR.

    The interaction with the Counter filter depends on the order
    in which these two filters are added to their handler, you probably want
    this filter added first.
    """

    def filter(self, record: logging.LogRecord):
        if record.levelno == logging.WARNING:
            record.levelno = logging.ERROR
            record.levelname = logging.getLevelName(logging.ERROR)
        return True


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

FORMAT = yaml.safe_load(
    """
classic:
  ERROR: "%(levelname)s in %(shortname)s: %(message)s"
  WARNING: "%(levelname)s in %(shortname)s: %(message)s"
  default: "%(levelname)s : %(message)s"
vanilla:
  default: "%(levelname)s:%(name)s: %(message)s"
"""
)


class ProblemLogFormatter(logging.Formatter):
    """
    In addition to the attributes provided by logging.Formatter, provides

    %(problemname)s  Name of the underlying problem, i.e., "different"
    %(aspectname)s   Name of the problem part, i.e., "submissions" (None if not in a part)
    %(shortname)s    = %(problemname)s or %(aspectname)s

    Recall that the name of the logger itself, i.e., the value of
    logging.Formatter's field %(name)s is "verifyproblem.%(problemname)s.%(aspectname)s",
    such as "verifyproblem.different.submissions"

    The additional info is passed to the error or warning message in the extra dict,
    like so:
        log.error(f"Compile error for {val}", extra={"additional_info": msg})
    """

    def __init__(self, max_additional_info=15):
        super().__init__()
        self._max_additional_info = max_additional_info
        self._fmt = _args.log_format

    def __append_additional_info(self, msg: str, additional_info: str):
        if additional_info is None or self._max_additional_info <= 0:
            return msg
        additional_info = additional_info.rstrip()
        if not additional_info:
            return msg
        lines = additional_info.split("\n")
        if len(lines) == 1:
            return "%s (%s)" % (msg, lines[0])
        if len(lines) > self._max_additional_info:
            lines = lines[: self._max_additional_info] + [
                "[.....truncated to %d lines.....]" % self._max_additional_info
            ]
        return "%s:\n%s" % (msg, "\n".join(" " * 8 + line for line in lines))

    def format(self, record: logging.LogRecord):
        record.message = record.getMessage()

        name_tokens = record.name.split(".")
        record.problemname = name_tokens[1]
        record.aspectname = None if len(name_tokens) == 2 else name_tokens[2]
        record.shortname = record.aspectname or record.problemname

        level = record.levelname
        fmt = self._fmt[level] if level in self._fmt else self._fmt["default"]
        result = fmt % record.__dict__
        if hasattr(record, "additional_info"):
            self.__append_additional_info(result, record.additional_info)
        return result


# -------------------------------------------------------------------------------
# Custom Loggers
# -------------------------------------------------------------------------------

_args = None


def config(args):
    """
    Configure logging for all problems from command line arguments to verifyproblem.

    This should be called exactly once.
    """
    global _args
    _args = args
    _args.log_format = FORMAT[
        "classic"
    ]  # should eventually become an option to verifyproblem


class AspectLogger(logging.Logger):
    """
    Logger for a problem aspect, such as "hello.submissions" or
    "hello.test case secret/002-huge.in".

    The logger's count attribute gives access to the Counter filter associated
    with its default handler. For instance,
        logger.count.errors
    contains the number or errors that were handled by this logger.

    Never instantiate this class yourself; instead create new ProblemLoggers
    using
       logger.get(f"{problemname}.{aspectename}").
    After creation, you can access it as logging.getLogger(f"{problemname}.{aspectename}").
    However, objects in verifyproblem typically mantain their logger as an attribute
       self.log
    """

    def __init__(self, name, *args, **kwargs):
        logging.Logger.__init__(self, name, *args, **kwargs)

        self.propagate = True
        self.setLevel(_args.log_level.upper())

        self.count = Counter()
        self.addFilter(self.count)


def get(name) -> AspectLogger:
    """
    Return the logger with the given name, creating
    it if necessary.

    After creation, the logger can be accessed as both
       logger.get(name)
       logging.getLogger(name)
    """

    saved_class = logging.getLoggerClass()
    try:
        logging.setLoggerClass(AspectLogger)
        return logging.getLogger("verifyproblem." + name)
    finally:
        logging.setLoggerClass(saved_class)


class ProblemLogger(logging.Logger):
    """
    Logger for the given problem, such as "hello" adding necessary handlers, filters,
    and formatters.

    The problem logger's count attribute gives access to the Counter filter associated
    with its default handler. For instance,
        problemlogger.count.errors
    contains the number or errors that were handled by this logger.

    Never instantiate this class yourself; instead create new ProblemLoggers
    using
       logger.get_problem_logger(problemname).
    After creation, you can also access it as logging.getLogger(problemname).
    """

    def __init__(self, name, *args, **kwargs):
        logging.Logger.__init__(self, name, *args, **kwargs)

        self.propagate = True
        self.setLevel(_args.log_level.upper())

        problem_handler = logging.StreamHandler(sys.stdout)
        problem_handler.setFormatter(ProblemLogFormatter())
        if _args.werror:
            problem_handler.addFilter(TreatWarningsAsErrors())
        self.count = Counter()
        problem_handler.addFilter(self.count)
        self.addHandler(problem_handler)
        if _args.bail_on_error:
            self.addHandler(BailOnError())


def get_problem_logger(name: str) -> ProblemLogger:
    """Return the ProblemLogger for this problem, creating
    it if necessary. get_problem_logger("hello") creates a logger ProblemLogger
    called "verifyproblem.hello"
    """
    saved_class = logging.getLoggerClass()
    try:
        logging.setLoggerClass(ProblemLogger)
        return logging.getLogger("verifyproblem." + name)
    finally:
        logging.setLoggerClass(saved_class)


# -----
# Root logger for verifyproblem
# -----


class RootLogger(logging.Logger):
    """Root logger called "verifyproblem". Maintains a Counter filter,
    which effectively counts all the errror and warnings encountered
    by any other logger below it.
    """

    def __init__(self, name, *args, **kwargs):
        logging.Logger.__init__(self, name, *args, **kwargs)

        self.propagate = False
        handler = logging.StreamHandler(sys.stdout)
        self.count = Counter()
        handler.addFilter(self.count)
        self.addHandler(handler)


saved_class = logging.getLoggerClass()
logging.setLoggerClass(RootLogger)
root = logging.getLogger("verifyproblem")
logging.setLoggerClass(saved_class)
