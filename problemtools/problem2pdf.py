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

    if statement_common.find_statement_extension(problem_root, language=options.language) == "md":
        return md2pdf(options)
    else:
        return latex2pdf(options)


def md2pdf(options: argparse.Namespace) -> bool:
    problem_root = os.path.realpath(options.problem)
    problembase = os.path.splitext(os.path.basename(problem_root))[0]
    destfile = string.Template(options.destfile).safe_substitute(problem=problembase)

    statement_path = statement_common.find_statement(problem_root, extension="md", language=options.language)

    if not os.path.isfile(statement_path):
        raise Exception(f"Error! {statement_path} is not a file")

    statement_common.assert_images_are_valid_md(statement_path)

    templatepaths = [os.path.join(os.path.dirname(__file__), 'templates/markdown_pdf'),
                    '/usr/lib/problemtools/templates/markdown_pdf']
    templatepath = next((p for p in templatepaths
                            if os.path.isdir(p) and os.path.isfile(os.path.join(p, "fix_tables.md"))),
                            None)
    table_fix_path = os.path.join(templatepath, "fix_tables.md")
    if not os.path.isfile(table_fix_path):
        raise Exception("Could not find markdown pdf template")

    with open(table_fix_path, "r") as file:
        table_fix = file.read()

    statement_dir = os.path.join(problem_root, "problem_statement")
    with open(statement_path, "r") as file:
        statement_md = file.read()
    
    problem_name = statement_common.get_yaml_problem_name(problem_root, options.language)

    # Add problem name and id to the top
    problem_id = os.path.basename(problem_root)
    statement_md = r'\centerline{\large %s}' % f"Problem id: {problem_id}" + statement_md
    statement_md = r'\centerline{\huge %s}' % problem_name + statement_md
    # Add code that adds vertical and horizontal lines to all tables
    statement_md = table_fix + statement_md

    samples = statement_common.format_samples(problem_root, to_pdf=True)

    statement_md, remaining_samples = statement_common.inject_samples(statement_md, samples, "\n")
    # If we don't add newline, the topmost table might get attached to a footnote
    statement_md += "\n" + "\n".join(remaining_samples)

    with tempfile.NamedTemporaryFile(mode='w', suffix=".md") as temp_file:
        temp_file.write(statement_md)
        temp_file.flush()
        command = ["pandoc", temp_file.name, "-o", destfile, f"--resource-path={statement_dir}"]
        try:
            return subprocess.run(command, capture_output=True, text=True, shell=False, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error compiling Markdown to pdf: {e.stderr}")
            return False


def latex2pdf(options: argparse.Namespace) -> bool:
    problem_root = os.path.realpath(options.problem)
    problembase = os.path.splitext(os.path.basename(problem_root))[0]
    destfile = string.Template(options.destfile).safe_substitute(problem=problembase)

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
