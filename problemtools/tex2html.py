import os
import logging
import string
import argparse
from pathlib import Path

from . import template


def convert(problem_root: Path, options: argparse.Namespace, statement_file: Path) -> None:
    # PlasTeX.Logging statically overwrites logging and formatting, so delay loading
    import plasTeX.TeX
    import plasTeX.Logging
    from .ProblemPlasTeX import ProblemRenderer
    from .ProblemPlasTeX import ProblemsetMacros

    if options.quiet:
        plasTeX.Logging.disableLogging()
    else:
        plasTeX.Logging.getLogger().setLevel(getattr(logging, options.loglevel.upper()))
        plasTeX.Logging.getLogger('status').setLevel(getattr(logging, options.loglevel.upper()))

    destfile = string.Template(options.destfile).safe_substitute(problem=problem_root.name)
    imgbasedir = string.Template(options.imgbasedir).safe_substitute(problem=problem_root.name)

    # Set up template if necessary
    with template.Template(problem_root, statement_file, options.language) as templ:
        texfile = open(templ.get_file_name(), 'r')

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

        renderer = ProblemRenderer()

        if not options.quiet:
            print('Parsing TeX source...')
        doc = tex.parse()
        texfile.close()

    renderer.render(doc)

    # Annoying: I have not figured out any way of stopping the plasTeX
    # renderer from generating a .paux file
    if os.path.isfile('.paux'):
        os.remove('.paux')
