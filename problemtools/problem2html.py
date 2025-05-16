#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import os.path
import re
import string
import subprocess
import sys
from pathlib import Path

from . import tex2html
from . import md2html
from . import statement_util


def convert(options: argparse.Namespace, force_statement_file: Path | None = None) -> None:
    problem_root = Path(options.problem).resolve(strict=True)

    if force_statement_file:  # Used by verifyproblem to test rendering even if there are multiple statements in a language
        statement_file = force_statement_file
    else:
        statement_file = statement_util.find_statement(problem_root, options.language)

    destdir = string.Template(options.destdir).safe_substitute(problem=problem_root.name)
    destfile = string.Template(options.destfile).safe_substitute(problem=problem_root.name)
    origcwd = os.getcwd()

    # Go to destdir
    if destdir:
        if not os.path.isdir(destdir):
            os.makedirs(destdir)
        os.chdir(destdir)

    try:
        if not options.quiet:
            print('Rendering!')
        match statement_file.suffix:
            case '.md':
                md2html.convert(problem_root, options, statement_file)
            case '.tex':
                tex2html.convert(problem_root, options, statement_file)
            case _:
                raise NotImplementedError('Unsupported file type, expected md or tex: {statement_file.name}')

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
    parser.add_argument('-l', '--language', dest='language', help='choose language (2-letter code)', default='en')
    parser.add_argument(
        '-L', '--log-level', dest='loglevel', help='set log level (debug, info, warning, error, critical)', default='warning'
    )
    parser.add_argument('-q', '--quiet', dest='quiet', action='store_true', help='quiet', default=False)
    parser.add_argument('-i', '--imgbasedir', dest='imgbasedir', default='')
    parser.add_argument('problem', help='the problem to convert')

    return parser


def main() -> None:
    parser = get_parser()
    options = parser.parse_args()
    try:
        convert(options)
    except Exception as e:
        print(e)
        sys.exit(1)


if __name__ == '__main__':
    main()
