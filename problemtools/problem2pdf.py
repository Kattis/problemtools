#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import os.path
import shutil
import string
import argparse
import subprocess
from . import template


def convert(args: list[str]|None = None) -> bool:
    options = parse_args(args)

    problem = os.path.realpath(options.problem)
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

def parse_args(args: list[str]|None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('-o', '--output', dest='destfile', help="output file name", default='${problem}.pdf')
    parser.add_argument('-q', '--quiet', dest='quiet', action='store_true', help="quiet", default=False)
    parser.add_argument('-l', '--language', dest='language', help='choose alternate language (2-letter code)', default=None)
    parser.add_argument('-n', '--no-pdf', dest='nopdf', action='store_true', help='run pdflatex in -draftmode', default=False)
    parser.add_argument('problem', help='the problem to convert')

    if args is not None:
        return parser.parse_args(args)

    return parser.parse_args()


def main() -> None:
    convert()


if __name__ == '__main__':
    main()
