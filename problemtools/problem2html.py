#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import re
import os.path
import string
import argparse
import subprocess

from . import tex2html
from . import md2html
from . import statement_util


def convert(options: argparse.Namespace) -> None:
    problem = os.path.realpath(options.problem)

    if not os.path.isdir(problem):
        raise Exception(f"Problem does not exist: {problem}")

    problembase = os.path.splitext(os.path.basename(problem))[0]
    destdir = string.Template(options.destdir).safe_substitute(problem=problembase)
    destfile = string.Template(options.destfile).safe_substitute(problem=problembase)

    # Go to destdir
    if destdir:
        if not os.path.isdir(destdir):
            os.makedirs(destdir)
        os.chdir(destdir)

    try:
        if not options.quiet:
            print('Rendering!')

        origcwd = os.getcwd()

        if statement_util.find_statement_extension(problem, options.language) == "tex":
            tex2html.convert(problem, options)
        else:
            md2html.convert(problem, options)

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
                        print(f'WARNING: FILE {f} HAS SIZE {file_size_kib} KiB; CONSIDER REDUCING IT')
                    elif file_size_kib > 300:
                        print(f'Warning: file {f} has size {file_size_kib} KiB; consider reducing it')

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

    parser.add_argument(
        '-b', '--body-only', dest='bodyonly', action='store_true', help='only generate HTML body, no HTML headers', default=False
    )
    parser.add_argument(
        '-c', '--no-css', dest='css', action='store_false', help="don't copy CSS file to output directory", default=True
    )
    parser.add_argument(
        '-H',
        '--headers',
        dest='headers',
        action='store_false',
        help="don't generate problem headers (title, problem id, time limit)",
        default=True,
    )
    parser.add_argument(
        '-m', '--messy', dest='tidy', action='store_false', help="don't run tidy to postprocess the HTML", default=True
    )
    parser.add_argument('-d', '--dest-dir', dest='destdir', help='output directory', default='${problem}_html')
    parser.add_argument('-f', '--dest-file', dest='destfile', help='output file name', default='index.html')
    parser.add_argument('-l', '--language', dest='language', help='choose alternate language (2-letter code)', default=None)
    parser.add_argument(
        '-L', '--log-level', dest='loglevel', help='set log level (debug, info, warning, error, critical)', default='warning'
    )
    parser.add_argument('-q', '--quiet', dest='quiet', action='store_true', help='quiet', default=False)
    parser.add_argument('-i', '--imgbasedir', dest='imgbasedir', default='')
    parser.add_argument('-v', '--format-version', dest='format_version', help='choose format version', default='automatic')
    parser.add_argument('problem', help='the problem to convert')

    return parser


def main() -> None:
    parser = get_parser()
    options = parser.parse_args()
    convert(options)


if __name__ == '__main__':
    main()
