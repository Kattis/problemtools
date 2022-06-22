#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import re
import os.path
import string
import argparse
import logging
import subprocess

import plasTeX.TeX
import plasTeX.Logging

from .ProblemPlasTeX import ProblemRenderer
from .ProblemPlasTeX import ProblemsetMacros
from . import template

def convert(problem, options=None):
    problembase = os.path.splitext(os.path.basename(problem))[0]
    destdir = string.Template(options.destdir).safe_substitute(problem=problembase)
    destfile = string.Template(options.destfile).safe_substitute(problem=problembase)
    imgbasedir = string.Template(options.imgbasedir).safe_substitute(problem=problembase)

    if options.quiet:
        plasTeX.Logging.disableLogging()
    else:
        plasTeX.Logging.getLogger().setLevel(getattr(logging, options.loglevel.upper()))
        plasTeX.Logging.getLogger('status').setLevel(getattr(logging, options.loglevel.upper()))

    texfile = problem
    # Set up template if necessary
    with template.Template(problem, language=options.language, title=options.title) as templ:
        texfile = open(templ.get_file_name(), 'r')

        # Setup parser and renderer etc
        tex = plasTeX.TeX.TeX(myfile=texfile)

        ProblemsetMacros.init(tex)

        tex.ownerDocument.config['general']['copy-theme-extras'] = options.css
        if not options.headers:
            tex.ownerDocument.userdata['noheaders'] = True
        tex.ownerDocument.config['files']['filename'] = destfile
        tex.ownerDocument.config['images']['filenames'] = 'img-$num(4)'
        tex.ownerDocument.config['images']['enabled'] = False
        tex.ownerDocument.config['images']['imager'] = 'none'
        tex.ownerDocument.config['images']['base-url'] = imgbasedir

        renderer = ProblemRenderer()

        if not options.quiet:
            print('Parsing TeX source...')
        doc = tex.parse()
        texfile.close()

    # Go to destdir
    os.chdir(destdir)

    if not options.quiet:
        print('Rendering!')
    renderer.render(doc)

    # Annoying: I have not figured out any way of stopping the plasTeX
    # renderer from generating a .paux file
    if os.path.isfile('.paux'):
        os.remove('.paux')
