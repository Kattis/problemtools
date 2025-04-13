#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import os.path
import re
import shutil
import string
import subprocess
import tempfile
from pathlib import Path

from . import template
from . import statement_util


def convert(options: argparse.Namespace) -> bool:
    problem_root = os.path.realpath(options.problem)

    if statement_util.find_statement_extension(problem_root, language=options.language) == "md":
        return md2pdf(options)
    else:
        return latex2pdf(options)


def md2pdf(options: argparse.Namespace) -> bool:
    problem_root = os.path.realpath(options.problem)
    statement_path = statement_util.find_statement(problem_root, extension="md", language=options.language)

    if not statement_path or not os.path.isfile(statement_path):
        raise FileNotFoundError(f"Error! {statement_path} does not exist")

    statement_util.assert_images_are_valid_md(statement_path)

    language = options.language
    if not language:
        language = "en"
    temp_tex_file = Path(statement_path).parent / f"problem.{language}.tex"
    command = ["pandoc", statement_path, "-o", str(temp_tex_file)]
    try:
        subprocess.run(command, capture_output=True,
                       text=True, shell=False, check=True
                       )
    except subprocess.CalledProcessError as e:
        print(f"Error compiling Markdown to pdf: {e.stderr}")
        return False

    try:
        with open(temp_tex_file, "r", encoding="utf-8") as f:
            tex = f.read()

        def format_latex_tables(latex_doc):
            # Match table environments produced by pandoc
            pattern = r'''
                (\\begin\{longtable\}\[\]\{@\{\})
                ([a-z])
                ([a-z]*)
                (@\{\}\})
            '''

            def replacer(match):
                prefix = match.group(1)[:-3]
                first_col = match.group(2)
                other_cols = match.group(3)
                suffix = match.group(4)[3:]

                # Combine columns with | separators
                cols = [first_col] + list(other_cols)
                return f'{prefix}|{"|".join(cols)}|{suffix} \\hline'

            return re.sub(pattern, replacer, latex_doc, flags=re.VERBOSE)

        # Add solid outline to tables
        tex = format_latex_tables(tex)
        tex = tex.replace(r"\toprule", "")
        tex = tex.replace(r"\midrule", "")
        tex = tex.replace(r"\endhead", "")
        tex = tex.replace(r"\bottomrule", "")
        tex = tex.replace(r"\tabularnewline", r"\\ \hline")

        # Fix sample inclusions commands
        # Currently does not work, as normal problemtools tex -> pdf does not support it
        tex = tex.replace(r"\{\{nextsample\}\}", r"\nextsample")
        tex = tex.replace(r"\{\{remainingsamples\}\}", r"\remainingsamples")

        problem_name = statement_util.get_yaml_problem_name(problem_root, options.language)
        tex = r'\problemname{' + problem_name + '}\n' + tex
        with open(temp_tex_file, "w", encoding="utf-8") as f:
            f.write(tex)

        status = latex2pdf(options)
        if status != 0:
            return False
    finally:
        temp_tex_file.unlink()

    return status == 0


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
    parser.add_argument('-v', '--format-version', dest='format_version', help='choose format version', default="automatic")
    parser.add_argument('problem', help='the problem to convert')

    return parser


def main() -> None:
    parser = get_parser()
    options = parser.parse_args()
    convert(options)


if __name__ == '__main__':
    main()
