#! /usr/bin/env python2
# -*- coding: utf-8 -*-
import re
import os.path
import sys
import string
from string import Template
from optparse import OptionParser
from ProblemPlasTeX import ProblemRenderer
from ProblemPlasTeX import ProblemsetMacros
from plasTeX.TeX import TeX
from plasTeX.Logging import getLogger, disableLogging
import logging
import template


def convert(problem, options=None):
    problem = os.path.realpath(problem)

    problembase = os.path.splitext(os.path.basename(problem))[0]
    destdir = Template(options.destdir).safe_substitute(problem=problembase)
    destfile = Template(options.destfile).safe_substitute(problem=problembase)
    imgbasedir = Template(options.imgbasedir).safe_substitute(problem=problembase)

    if options.quiet:
        disableLogging()
    else:
        getLogger().setLevel(eval("logging." + options.loglevel.upper()))
        getLogger('status').setLevel(eval("logging." + options.loglevel.upper()))

    texfile = problem
    # Set up template if necessary
    templ = None
    if os.path.isdir(problem):
        templ = template.Template(problem, language=options.language, title=options.title)
        texfile = templ.get_file_name()

    origcwd = os.getcwd()

    # Setup parser and renderer etc
    tex = TeX(file=texfile)

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
        print 'Parsing TeX source...'
    doc = tex.parse()

    # Go to destdir
    if destdir:
        if not os.path.isdir(destdir):
            os.makedirs(destdir)
        os.chdir(destdir)

    try:
        if not options.quiet:
            print 'Rendering!'
        renderer.render(doc)

        # Annoying: I have not figured out any way of stopping the plasTeX
        # renderer from generating a .paux file
        if os.path.isfile('.paux'):
            os.remove('.paux')

        if options.tidy:
            os.system('tidy -utf8 -i -q -m %s 2> /dev/null' % destfile)

        if options.bodyonly:
            content = open(destfile).read()
            body = re.search('<body>(.*)</body>', content, re.DOTALL)
            assert body
            open(destfile, 'w').write(body.group(1))
    finally:
        # restore cwd
        os.chdir(origcwd)
        if templ:
            templ.cleanup()

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
    optparse = OptionParser(usage="usage: %prog [options] problem")
    for (dest, action, short, long, help) in ConvertOptions.available:
        if (action == 'store'):
            help += ' default: "%s"' % options.__dict__[dest]
        optparse.add_option(short, long, dest=dest, help=help, action=action)

    (options, args) = optparse.parse_args(values=options)

    if len(args) != 1:
        optparse.print_help()
        sys.exit(1)

    texfile = args[0]
    convert(texfile, options)

if __name__ == '__main__':
    main()
