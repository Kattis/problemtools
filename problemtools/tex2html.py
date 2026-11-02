import argparse
import logging
import os
import string
from pathlib import Path

from . import template
from .diagnostics import Diagnostics


class _DiagnosticsHandler(logging.Handler):
    """Forwards plasTeX log records to a Diagnostics instance"""

    def __init__(self, diag: Diagnostics) -> None:
        super().__init__()
        self._diag = diag

    def emit(self, record: logging.LogRecord) -> None:
        msg = f'plasTeX: {record.getMessage().strip()}'
        if record.levelno >= logging.ERROR:
            self._diag.error(msg)
        elif record.levelno >= logging.WARNING:
            self._diag.warning(msg)
        elif record.levelno >= logging.INFO:
            self._diag.info(msg)
        else:
            self._diag.debug(msg)


def convert(problem_root: Path, options: argparse.Namespace, statement_file: Path, diag: Diagnostics) -> None:
    # PlasTeX.Logging statically overwrites logging and formatting, so delay loading
    import plasTeX.Logging

    plastex_log = plasTeX.Logging.getLogger()
    plastex_log.setLevel(getattr(logging, options.loglevel.upper()))
    plasTeX.Logging.getLogger('status').setLevel(getattr(logging, options.loglevel.upper()))

    # Route plasTeX's main logger through diag instead of its own stream handler, so
    # that problems in the statement are counted as warnings and errors in verifyproblem.
    saved_handlers = plastex_log.handlers[:]
    for handler in saved_handlers:
        plastex_log.removeHandler(handler)
    diag_handler = _DiagnosticsHandler(diag)
    plastex_log.addHandler(diag_handler)
    try:
        _convert(problem_root, options, statement_file, diag)
    finally:
        plastex_log.removeHandler(diag_handler)
        for handler in saved_handlers:
            plastex_log.addHandler(handler)


def _convert(problem_root: Path, options: argparse.Namespace, statement_file: Path, diag: Diagnostics) -> None:
    import plasTeX.TeX

    from .ProblemPlasTeX import ProblemRenderer, ProblemsetMacros

    destfile = string.Template(options.destfile).safe_substitute(problem=problem_root.name)
    imgbasedir = string.Template(options.imgbasedir).safe_substitute(problem=problem_root.name)

    # Set up template if necessary
    with (
        template.Template(problem_root, statement_file, options.language) as templ,
        open(templ.get_file_name(), 'r') as texfile,
    ):
        # Setup parser and renderer etc
        tex = plasTeX.TeX.TeX(file=texfile)

        ProblemsetMacros.init(tex)

        tex.ownerDocument.config['general']['copy-theme-extras'] = options.css
        if not options.headers:
            tex.ownerDocument.userdata['noheaders'] = True
        tex.ownerDocument.config['files']['filename'] = destfile
        tex.ownerDocument.config['images']['filenames'] = 'img-$num(4)'
        tex.ownerDocument.config['images']['enabled'] = False
        tex.ownerDocument.config['images']['imager'] = 'none'
        tex.ownerDocument.config['images']['base-url'] = imgbasedir
        # tell plasTeX where to search for problemtools' built-in packages
        tex.ownerDocument.config['general']['packages-dirs'] = [os.path.join(os.path.dirname(__file__), 'ProblemPlasTeX')]

        renderer = ProblemRenderer(diag)

        doc = tex.parse()

    renderer.render(doc)

    # Clean up the logger class plasTeX registers, and reset to the default
    logging.setLoggerClass(logging.Logger)

    # Annoying: I have not figured out any way of stopping the plasTeX
    # renderer from generating a .paux file
    if os.path.isfile('.paux'):
        os.remove('.paux')
