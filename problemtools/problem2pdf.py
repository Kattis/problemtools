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
        
        templatepaths = [os.path.join(os.path.dirname(__file__), 'templates/markdown_pdf'),
                     os.path.join(os.path.dirname(__file__), '../templates/markdown_pdf'),
                     '/usr/lib/problemtools/templates/markdown_pdf']
        templatepath = next((p for p in templatepaths
                              if os.path.isdir(p) and os.path.isfile(os.path.join(p, "fix_tables.md"))),
                             None)
        table_fix_path = os.path.join(templatepath, "fix_tables.md")
        if not os.path.isfile(table_fix_path):
            raise Exception("Could not find markdown pdf template")
        
        with open(table_fix_path, "r") as f:
            table_fix = f.read()

        statement_dir = os.path.join(problem_root, "problem_statement")
        with open(statement_path, "r") as f:
            statement_md = f.read()
        
        problem_name = statement_common.get_problem_name(problem_root, options.language)

        # Add code that adds vertical and horizontal lines to all tables
        statement_md = r'\centerline{\huge %s}' % problem_name + statement_md
        statement_md = table_fix + statement_md
        
        # Hacky: html samples -> md. Then we append to the markdown document
        samples = "\n".join(statement_common.format_samples(problem_root, to_pdf=True))

        # If we don't add newline, the table might get attached to a footnote
        statement_md += "\n" + samples

        with tempfile.NamedTemporaryFile(mode='w', suffix=".md") as temp_file:
            temp_file.write(statement_md)
            temp_file.flush()
            # Do .read so that the temp file isn't deleted until pandoc is done
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
