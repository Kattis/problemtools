#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import re
import os.path
import string
import argparse
import logging
import subprocess

from . import template

def convert(options: argparse.Namespace) -> None:
    # PlasTeX.Logging statically overwrites logging and formatting, so delay loading
    import plasTeX.TeX
    import plasTeX.Logging
    from .ProblemPlasTeX import ProblemRenderer
    from .ProblemPlasTeX import ProblemsetMacros

    problem = os.path.realpath(options.problem)

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
            for path, _dirs, files in os.walk('.'):
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


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('-b', '--body-only', dest='bodyonly', action='store_true', help='only generate HTML body, no HTML headers', default=False)
    parser.add_argument('-c', '--no-css', dest='css', action='store_false', help="don't copy CSS file to output directory", default=True)
    parser.add_argument('-H', '--headers', dest='headers', action='store_false', help="don't generate problem headers (title, problem id, time limit)", default=True)
    parser.add_argument('-m', '--messy', dest='tidy', action='store_false', help="don't run tidy to postprocess the HTML", default=True)
    parser.add_argument('-d', '--dest-dir', dest='destdir', help="output directory", default='${problem}_html')
    parser.add_argument('-f', '--dest-file', dest='destfile', help="output file name", default='index.html')
    parser.add_argument('-l', '--language', dest='language', help='choose alternate language (2-letter code)', default=None)
    parser.add_argument('-L', '--log-level', dest='loglevel', help='set log level (debug, info, warning, error, critical)', default='warning')
    parser.add_argument('-q', '--quiet', dest='quiet', action='store_true', help="quiet", default=False)
    parser.add_argument('-i', '--imgbasedir', dest='imgbasedir', default='')
    parser.add_argument('problem', help='the problem to convert')

    return parser

def main() -> None:
    parser = get_parser()
    options = parser.parse_args()
    convert(options)


if __name__ == '__main__':
    main()
