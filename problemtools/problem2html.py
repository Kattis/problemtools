#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import re
import os.path
import sys
import string
import optparse
from .ProblemPlasTeX import ProblemRenderer
from .ProblemPlasTeX import ProblemsetMacros
import plasTeX.TeX
import plasTeX.Logging
import logging
import subprocess
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
        plasTeX.Logging.getLogger().setLevel(eval("logging." + options.loglevel.upper()))
        plasTeX.Logging.getLogger('status').setLevel(eval("logging." + options.loglevel.upper()))

    texfile = problem
    # Set up template if necessary
    with template.Template(problem, language=options.language, title=options.title) as templ:
        texfile = open(templ.get_file_name(), 'r')

        origcwd = os.getcwd()

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
         'only generate HTML body, no HTML headers.'],
        ['css', 'store_false', '-c', '--no-css',
         "don't copy CSS file to output directory."],
        ['headers', 'store_false', '-H', '--headers',
         "don't generate problem headers (title, problem id, time limit)"],
        ['tidy', 'store_false', '-m', '--messy',
         "don't run tidy to postprocess the HTML"],
        ['destdir', 'store', '-d', '--dest-dir',
         "output directory."],
        ['destfile', 'store', '-f', '--dest-file',
         "output file name."],
        ['language', 'store', '-l', '--language',
         'choose alternate language (2-letter code).'],
        ['title', 'store', '-T', '--title',
         'set title (only used when there is no pre-existing template and -h not set).'],
        ['loglevel', 'store', '-L', '--log-level',
         'set log level (debug, info, warning, error, critical).'],
        ['quiet', 'store_true', '-q', '--quiet',
         "quiet."],
        ]

    def __init__(self):
        self.bodyonly = False
        self.css = True
        self.headers = True
        self.tidy = True
        self.destdir = "${problem}_html"
        self.destfile = "index.html"
        self.language = ""
        self.title = "Problem Name"
        self.loglevel = "warning"
        self.imgbasedir = ''
        self.quiet = False


def main():
    options = ConvertOptions()
    parser = optparse.OptionParser(usage="usage: %prog [options] problem")
    for (dest, action, short, long, help) in ConvertOptions.available:
        if (action == 'store'):
            help += ' default: "%s"' % options.__dict__[dest]
        parser.add_option(short, long, dest=dest, help=help, action=action)

    (options, args) = parser.parse_args(values=options)

    if len(args) != 1:
        parser.print_help()
        sys.exit(1)

    texfile = args[0]
    convert(texfile, options)

if __name__ == '__main__':
    main()
