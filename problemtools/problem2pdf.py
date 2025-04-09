#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import os.path
import shutil
import string
import argparse
from pathlib import Path
import re
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
        raise FileNotFoundError(f"Error! {statement_path} does not exist")

    #statement_common.assert_images_are_valid_md(statement_path)

    # TODO: fix nextsample and remainingsamples
    # TODO: better language code
    fake_tex = Path(statement_path).parent / "problem.en.tex"
    print(f"{fake_tex=} {statement_path=}")
    command = ["pandoc", statement_path, "-o", fake_tex]
    try:
        subprocess.run(command, capture_output=True,
            text=True, shell=False, check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Error compiling Markdown to pdf: {e.stderr}")
        return False
    
    try:
        with open(fake_tex, "r") as f:
            tex = f.read()

        def format_latex_tables(latex_doc):
            # Match table environments with column specs between @{...@{}}
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
                return f'{prefix}|{"|".join(cols)}|{suffix} \hline'
            
            return re.sub(pattern, replacer, latex_doc, flags=re.VERBOSE)

        tex = format_latex_tables(tex)
        tex = tex.replace(r"\toprule", "")
        tex = tex.replace(r"\midrule", "")
        tex = tex.replace(r"\endhead", "")
        tex = tex.replace(r"\bottomrule", "")
        tex = tex.replace(r"\tabularnewline", r"\\ \hline")
        
        problem_name = statement_common.get_yaml_problem_name(problem_root, options.language)
        tex = '\\problemname{' + problem_name + '}\n' + tex
        with open(fake_tex, "w") as f:
            f.write(tex)
        with open("SOGS.tex", "w") as f:
            f.write(tex)
        print("RENDERING!!")
        latex2pdf(options)
    except Exception as e:
        print(f"{e}")
    finally:
        fake_tex.unlink()

    # with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as f:
    #         command = ["gs", "-q", "-dBATCH", "-sDEVICE=pdfwrite", "-dNOPAUSE",
    #                 "-dCompatibilityLevel=1.7", f"-sOutputFile={f.name}", destfile]
    #         subprocess.run(command, capture_output=True,
    #             text=True, shell=False, check=True
    #         )
    #         shutil.copy(f.name, destfile)

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
        print(texfile)

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
