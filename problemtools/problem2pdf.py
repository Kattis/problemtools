#! /usr/bin/env python2
# -*- coding: utf-8 -*-
import re
import os.path
import shutil
import sys
import string
from string import Template
from optparse import OptionParser
import logging
import subprocess
from . import template


def convert(problem, options=None):
    if options == None:
        options = ConvertOptions()

    problem = os.path.realpath(problem)
    problembase = os.path.splitext(os.path.basename(problem))[0]
    destfile = Template(options.destfile).safe_substitute(problem=problembase)

    texfile = problem
    # Set up template if necessary
    with template.Template(problem, language=options.language,
                           title=options.title) as templ:
        texfile = templ.get_file_name()

        origcwd = os.getcwd()

        os.chdir(os.path.dirname(texfile))
        params = ['pdflatex', '-interaction=nonstopmode']
        output = None
        if options.quiet:
            output = open(os.devnull, 'w')
        if options.nopdf:
            params.append('-draftmode')

        params.append(texfile)

        status = subprocess.call(params, stdout=output)
        if status == 0:
            status = subprocess.call(params, stdout=output)

        if output is not None:
            output.close()

        os.chdir(origcwd)

        if not options.nopdf:
            shutil.move(os.path.splitext(texfile)[0] + '.pdf', destfile)

    return status == 0


class ConvertOptions:
    available = [
        ['destfile', 'store', '-o', '--output',
         "output file name."],
        ['quiet', 'store_true', '-q', '--quiet',
         "quiet."],
        ['title', 'store', '-T', '--title',
         'set title (only used when there is no pre-existing template and -h not set).'],
        ['language', 'store', '-l', '--language',
         'choose alternate language (2-letter code).'],
        ['nopdf', 'store_true', '-n', '--no-pdf',
         'run pdflatex in -draftmode'],
        ]

    def __init__(self):
        self.destfile = "${problem}.pdf"
        self.title = "Problem Name"
        self.quiet = False
        self.language = ""
        self.nopdf = False


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
