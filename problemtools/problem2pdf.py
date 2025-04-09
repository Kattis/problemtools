#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import os.path
import shutil
import string
import argparse
from pathlib import Path
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

    fake_tex = Path(statement_path).parent / "problem.tex"
    print(f"{fake_tex=} {statement_path=}")
    command = ["pandoc", statement_path, "-o", fake_tex]
    try:
        subprocess.run(command, capture_output=True,
            text=True, shell=False, check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Error compiling Markdown to pdf: {e.stderr}")
        return False
    
    with open(fake_tex, "r") as f:
        tex = f.read()
    with open(fake_tex, "w") as f:
        f.write('\\problemname{asd}\n'+tex)

    try:
        latex2pdf(options)
    finally:
        fake_tex.unlink()
    return False

    templatepaths = [os.path.join(os.path.dirname(__file__), 'templates/markdown_pdf'),
                    '/usr/lib/problemtools/templates/markdown_pdf']
    templatepath = next((p for p in templatepaths
                            if os.path.isdir(p) and os.path.isfile(os.path.join(p, "fix_tables.md"))),
                            None)
    table_fix_path = os.path.join(templatepath, "fix_tables.md")
    if not os.path.isfile(table_fix_path):
        raise FileNotFoundError("Could not find markdown pdf template")

    with open(table_fix_path, "r", encoding="utf-8") as file:
        table_fix = file.read()

    statement_dir = os.path.join(problem_root, "statement")
    with open(statement_path, "r", encoding="utf-8") as file:
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

    print("Rendering!")
    command = ["pandoc", "-f", "markdown", "-o", destfile, f"--resource-path={statement_dir}"]
    try:
        subprocess.run(command, input=statement_md, capture_output=True,
            text=True, shell=False, check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Error compiling Markdown to pdf: {e.stderr}")
        return False

    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as f:
        command = ["gs", "-q", "-dBATCH", "-sDEVICE=pdfwrite", "-dNOPAUSE",
                   "-dCompatibilityLevel=1.7", f"-sOutputFile={f.name}", destfile]
        subprocess.run(command, capture_output=True,
            text=True, shell=False, check=True
        )
        shutil.copy(f.name, destfile)

    return True

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
    parser.add_argument('problem', help='the problem to convert')

    return parser


def main() -> None:
    parser = get_parser()
    options = parser.parse_args()
    convert(options)


if __name__ == '__main__':
    main()
