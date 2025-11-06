#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import os
import re
import shutil
import string
import subprocess
import sys
import tempfile
from pathlib import Path

from . import template
from . import statement_util
from .version import add_version_arg


def convert(options: argparse.Namespace, force_statement_file: Path | None = None) -> bool:
    problem_root = Path(options.problem).resolve(strict=True)

    if force_statement_file:  # Used by verifyproblem to test rendering even if there are multiple statements in a language
        statement_file = force_statement_file
    else:
        statement_file = statement_util.find_statement(problem_root, options.language)

    match statement_file.suffix:
        case '.md':
            return md2pdf(options, statement_file)
        case '.tex':
            return latex2pdf(options, statement_file)
        case _:
            raise NotImplementedError('Unsupported file type, expected md or tex: {statement_file.name}')


def md2pdf(options: argparse.Namespace, statement_file: Path) -> bool:
    """Renders a Markdown document to pdf. Uses pandoc md -> tex, then
    reuses the normal tex -> pdf pipeline
    """
    problem_root = Path(options.problem).resolve(strict=True)

    statement_util.assert_images_are_valid_md(statement_file)

    command = ['pandoc', str(statement_file), '-t', 'latex']
    try:
        tex = subprocess.run(command, capture_output=True, text=True, shell=False, check=True).stdout
    except subprocess.CalledProcessError as e:
        print(f'Error compiling Markdown to pdf: {e.stderr}')
        return False

    def format_latex_tables(latex_doc):
        # Match table environments produced by pandoc
        pattern = r"""
            (\\begin\{longtable\}\[\]\{@\{\})
            ([a-z])
            ([a-z]*)
            (@\{\}\})
        """

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
    tex = tex.replace(r'\toprule', '')
    tex = tex.replace(r'\midrule', '')
    tex = tex.replace(r'\endhead', '')
    tex = tex.replace(r'\bottomrule', '')
    tex = tex.replace(r'\tabularnewline', r'\\ \hline')

    # Fix sample inclusions commands
    # Currently does not work, as normal problemtools tex -> pdf does not support it
    tex = tex.replace(r'\{\{nextsample\}\}', r'\nextsample')
    tex = tex.replace(r'\{\{remainingsamples\}\}', r'\remainingsamples')

    problem_name = statement_util.get_yaml_problem_name(problem_root, options.language)
    tex = r'\problemname{' + problem_name + '}\n' + tex
    with tempfile.NamedTemporaryFile(mode='w', suffix='.tex', dir=statement_file.parent) as temp_tex_file:
        temp_tex_file.write(tex)
        temp_tex_file.flush()
        return latex2pdf(options, Path(temp_tex_file.name))

    return False


def latex2pdf(options: argparse.Namespace, statement_file: Path) -> bool:
    problem_root = Path(options.problem).resolve(strict=True)
    destfile = string.Template(options.destfile).safe_substitute(problem=problem_root.name)

    # Set up template if necessary
    with template.Template(problem_root, statement_file, options.language) as templ:
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

    if status:
        return False

    # We only sanitize if a PDF was created
    if not options.nopdf:
        try:
            with tempfile.NamedTemporaryFile(suffix='.pdf') as f:
                command = [
                    'gs',
                    '-q',
                    '-dBATCH',
                    '-sDEVICE=pdfwrite',
                    '-dNOPAUSE',
                    '-dCompatibilityLevel=1.7',
                    f'-sOutputFile={f.name}',
                    destfile,
                ]
                gs_status = subprocess.run(command, capture_output=True, text=True, shell=False, check=True)
                if gs_status.returncode != 0:
                    return False
                shutil.copy(f.name, destfile)
        except subprocess.CalledProcessError as e:
            print(f'Error sanitizing PDF: {e} {e.stderr}')
            raise

    return True


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('-o', '--output', dest='destfile', help='output file name', default='${problem}.pdf')
    parser.add_argument('-q', '--quiet', dest='quiet', action='store_true', help='quiet', default=False)
    parser.add_argument('-l', '--language', dest='language', help='choose language (2-letter code)', default='en')
    parser.add_argument('-n', '--no-pdf', dest='nopdf', action='store_true', help='run pdflatex in -draftmode', default=False)
    parser.add_argument('problem', help='the problem to convert')
    add_version_arg(parser)

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
