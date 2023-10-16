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
    problem = os.path.realpath(problem)

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
    with template.Template(problem, language=options.language) as templ:
        texfile = open(templ.get_file_name(), 'r')

        origcwd = os.getcwd()

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

    # Go to destdir
    if destdir:
        if not os.path.isdir(destdir):
            os.makedirs(destdir)
        os.chdir(destdir)

    try:
        if not options.quiet:
            print('Rendering!')
        renderer.render(doc)

        # Annoying: I have not figured out any way of stopping the plasTeX
        # renderer from generating a .paux file
        if os.path.isfile('.paux'):
            os.remove('.paux')

        if options.tidy:
            with open(os.devnull, 'w') as devnull:
                try:
                    subprocess.call(['tidy', '-utf8', '-i', '-q', '-m', destfile], stderr=devnull)
                except OSError:
                    if not options.quiet:
                        print("Warning: Command 'tidy' not found. Install tidy or run with --messy")

        # identify any large generated files (especially images)
        if not options.quiet:
            for path, dirs, files in os.walk('.'):
                for f in files:
                    file_size_kib = os.stat(os.path.join(path, f)).st_size // 1024
                    if file_size_kib > 1024:
                        print(f"WARNING: FILE {f} HAS SIZE {file_size_kib} KiB; CONSIDER REDUCING IT")
                    elif file_size_kib > 300:
                        print(f"Warning: file {f} has size {file_size_kib} KiB; consider reducing it")

        if options.bodyonly:
            content = open(destfile).read()
            body = re.search('<body>(.*)</body>', content, re.DOTALL)
            assert body
            open(destfile, 'w').write(body.group(1))
    finally:
        # restore cwd
        os.chdir(origcwd)

    return True


class ConvertOptions:
    available = [
        ['bodyonly', 'store_true', '-b', '--body-only',
         'only generate HTML body, no HTML headers', False],
        ['css', 'store_false', '-c', '--no-css',
         "don't copy CSS file to output directory", True],
        ['headers', 'store_false', '-H', '--headers',
         "don't generate problem headers (title, problem id, time limit)", True],
        ['tidy', 'store_false', '-m', '--messy',
         "don't run tidy to postprocess the HTML", True],
        ['destdir', 'store', '-d', '--dest-dir',
         "output directory", '${problem}_html'],
        ['destfile', 'store', '-f', '--dest-file',
         "output file name", 'index.html'],
        ['language', 'store', '-l', '--language',
         'choose alternate language (2-letter code)', None],
        ['loglevel', 'store', '-L', '--log-level',
         'set log level (debug, info, warning, error, critical)', 'warning'],
        ['quiet', 'store_true', '-q', '--quiet',
         "quiet", False],
        ]

    def __init__(self):
        for (dest, _, _, _, _, default) in ConvertOptions.available:
            setattr(self, dest, default)
        self.imgbasedir = ''


def main():
    options = ConvertOptions()
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    for (dest, action, short, _long, _help, default) in ConvertOptions.available:
        parser.add_argument(short, _long, dest=dest, help=_help, action=action, default=default)
    parser.add_argument('problem', help='the problem to convert')

    options = parser.parse_args(namespace=options)
    convert(options.problem, options)


if __name__ == '__main__':
    main()
