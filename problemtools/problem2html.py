#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import re
import os.path
import string
import argparse
import logging
import subprocess

from . import tex2html
from . import md2html


SUPPORTED_EXTENSIONS = ("tex", "md")


def convert(problem, options=None):
    problem = os.path.realpath(problem)
    origcwd = os.getcwd()
    try:
        problembase = os.path.splitext(os.path.basename(problem))[0]
        destdir = string.Template(options.destdir).safe_substitute(problem=problembase)
        if destdir:
            if not os.path.isdir(destdir):
                os.makedirs(destdir)

        if md2html.get_markdown_statement(problem, options.language):
            md2html.convert(problem, options)
        else:
            tex2html.convert(problem, options)

        destfile = os.path.join(destdir, string.Template(options.destfile).safe_substitute(problem=problembase))
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
         'choose alternate language (2-letter code)', ''],
        ['title', 'store', '-T', '--title',
         'set title (only used when there is no pre-existing template and -h not set)',
         'Problem Name'],
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
