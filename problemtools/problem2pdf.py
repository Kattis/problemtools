#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import os.path
import shutil
import string
import argparse
import subprocess
from . import template


def convert(problem, options=None):
    if options is None:
        options = ConvertOptions()

    problem = os.path.realpath(problem)
    problembase = os.path.splitext(os.path.basename(problem))[0]
    destfile = string.Template(options.destfile).safe_substitute(problem=problembase)

    texfile = problem
    # Set up template if necessary
    with template.Template(problem, language=options.language) as templ:
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

        if status == 0 and not options.nopdf:
            shutil.move(os.path.splitext(texfile)[0] + '.pdf', destfile)

    return status == 0


class ConvertOptions:
    available = [
        ['destfile', 'store', '-o', '--output',
         "output file name", '${problem}.pdf'],
        ['quiet', 'store_true', '-q', '--quiet',
         "quiet", False],
        ['language', 'store', '-l', '--language',
         'choose alternate language (2-letter code)', None],
        ['nopdf', 'store_true', '-n', '--no-pdf',
         'run pdflatex in -draftmode', False],
        ]

    def __init__(self):
        for (dest, _, _, _, _, default) in ConvertOptions.available:
            setattr(self, dest, default)


def main():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    for (dest, action, short, _long, _help, default) in ConvertOptions.available:
        parser.add_argument(short, _long, dest=dest, help=_help, action=action, default=default)
    parser.add_argument('problem', help='the problem to convert')

    options = parser.parse_args()
    convert(options.problem, options)


if __name__ == '__main__':
    main()
