import os
import logging
import string
import argparse

from . import template


def convert(problem: str, options: argparse.Namespace) -> None:
    # PlasTeX.Logging statically overwrites logging and formatting, so delay loading
    import plasTeX.TeX
    import plasTeX.Logging
    from .ProblemPlasTeX import ProblemRenderer
    from .ProblemPlasTeX import ProblemsetMacros

    problembase = os.path.splitext(os.path.basename(problem))[0]
    if options.quiet:
        plasTeX.Logging.disableLogging()
    else:
        plasTeX.Logging.getLogger().setLevel(getattr(logging, options.loglevel.upper()))
        plasTeX.Logging.getLogger('status').setLevel(getattr(logging, options.loglevel.upper()))

    destfile = string.Template(options.destfile).safe_substitute(problem=problembase)
    imgbasedir = string.Template(options.imgbasedir).safe_substitute(problem=problembase)

    texfile = problem
    # Set up template if necessary
    with template.Template(problem, language=options.language) as templ:
        texfile = open(templ.get_file_name(), 'r')

        # Setup parser and renderer etc

        # plasTeX version 3 changed the name of this argument (and guarding against this
        # by checking plasTeX.__version__ fails on plastex v3.0 which failed to update
        # __version__)
        try:
            tex = plasTeX.TeX.TeX(myfile=texfile)
        except Exception:
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
