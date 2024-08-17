#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import os.path
import shutil
import string
import argparse
import subprocess
import tempfile

from . import template
from . import statement_common

def convert(options: argparse.Namespace) -> bool:
    problem_root = os.path.realpath(options.problem)
    problembase = os.path.splitext(os.path.basename(problem_root))[0]
    destfile = string.Template(options.destfile).safe_substitute(problem=problembase)

    if statement_common.find_statement_extension(problem_root, language=options.language) == "md":
        statement_path = statement_common.find_statement(problem_root, extension="md", language=options.language)

        if not os.path.isfile(statement_path):
            raise Exception(f"Error! {statement_path} is not a file")
        
        statement_dir = os.path.join(problem_root, "problem_statement")
        with open(statement_path, "r") as f:
            statement_md = f.read()
        
        # Hacky: html samples -> md. Then we append to the markdown document
        samples = statement_common._samples_to_html(problem_root)
        with tempfile.NamedTemporaryFile(mode='w', suffix=".html") as temp_file:
            temp_file.write(samples)
            temp_file.flush()
            samples_md = os.popen(f"pandoc {temp_file.name} -t markdown").read()

        statement_md += samples_md
        with tempfile.NamedTemporaryFile(mode='w', suffix=".md") as temp_file:
            temp_file.write(statement_md)
            temp_file.flush()
            # Do .read so that the file isn't deleted until pandoc is done
            os.popen(f"pandoc {temp_file.name} -o {problembase}.pdf --resource-path={statement_dir}").read()

    else:
        # Set up template if necessary
        with template.Template(problem_root, language=options.language) as templ:
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

def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('-o', '--output', dest='destfile', help="output file name", default='${problem}.pdf')
    parser.add_argument('-q', '--quiet', dest='quiet', action='store_true', help="quiet", default=False)
    parser.add_argument('-l', '--language', dest='language', help='choose alternate language (2-letter code)', default=None)
    parser.add_argument('-n', '--no-pdf', dest='nopdf', action='store_true', help='run pdflatex in -draftmode', default=False)
    parser.add_argument('problem', help='the problem to convert')

    return parser


def main() -> None:
    parser = get_parser()
    options = parser.parse_args()
    convert(options)


if __name__ == '__main__':
    main()
