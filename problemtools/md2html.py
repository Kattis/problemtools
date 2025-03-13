#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import os.path
import string
import argparse
import subprocess
import re
import tempfile

from . import statement_common


FOOTNOTES_STRING = '<section class="footnotes" role="doc-endnotes">'

def convert(problem: str, options: argparse.Namespace) -> bool:
    """Convert a Markdown statement to HTML

    Args:
        problem: path to problem directory
        options: command-line arguments. See problem2html.py
    """
    problembase = os.path.splitext(os.path.basename(problem))[0]
    destfile = string.Template(options.destfile).safe_substitute(problem=problembase)

    statement_path = statement_common.find_statement(problem, extension="md", language=options.language)

    if statement_path is None:
        raise Exception('No markdown statement found')

    if not os.path.isfile(statement_path):
        raise Exception(f"Error! {statement_path} is not a file")


    statement_common.assert_images_are_valid_md(statement_path)
    statement_common.foreach_image(statement_path,
                 lambda img_name: copy_image(problem, img_name))
    
    command = ["pandoc", statement_path, "-t" , "html", "-f", "markdown-raw_html", "--mathjax"]
    statement_html = subprocess.run(command, capture_output=True, text=True,
        shell=False, check=True).stdout


    templatepaths = [os.path.join(os.path.dirname(__file__), 'templates/markdown_html'),
                     os.path.join(os.path.dirname(__file__), '../templates/markdown_html'),
                     '/usr/lib/problemtools/templates/markdown_html']
    templatepath = next((p for p in templatepaths
                              if os.path.isdir(p) and os.path.isfile(os.path.join(p, "default-layout.html"))),
                             None)

    if templatepath is None:
        raise Exception('Could not find directory with markdown templates')

    problem_name = statement_common.get_problem_name(problem, options.language)

    html_template = _substitute_template(templatepath, "default-layout.html",
           statement_html=statement_html,
           language=options.language,
           title=problem_name or "Missing problem name",
           problemid=problembase)

    samples = statement_common.format_samples(problem, to_pdf=False)

    # Insert samples at {{nextsample}} and {{remainingsamples}}
    html_template, remaining_samples = statement_common.inject_samples(html_template, samples, "")

    # Insert the remaining samples at the bottom
    if FOOTNOTES_STRING in html_template:
        pos = html_template.find(FOOTNOTES_STRING)
    else:
        pos = html_template.find("</body>")
    html_template = html_template[:pos] + "".join(remaining_samples) + html_template[pos:]

    html_template = replace_hr_in_footnotes(html_template)

    with open(destfile, "w", encoding="utf-8", errors="xmlcharrefreplace") as output_file:
        output_file.write(html_template)

    if options.css:
        with open("problem.css", "w") as output_file:
            with open(os.path.join(templatepath, "problem.css"), "r") as input_file:
                output_file.write(input_file.read())

    return True


def copy_image(problem_root: str, img_src: str) -> None:
    """Copy image to output directory

    Args:
        problem_root: the root of the problem directory
        img_src: the image source as in the Markdown statement
    """

    source_name = os.path.join(problem_root, "problem_statement", img_src)

    if os.path.isfile(img_src): # already copied
        return
    with open(source_name, "rb") as img:
        with open(img_src, "wb") as out:
            out.write(img.read())


def replace_hr_in_footnotes(html_content):
    # Remove <hr /> tag that pandoc automatically creates after the footnotes
    if not FOOTNOTES_STRING in html_content:
        return html_content
    footnotes = html_content.find(FOOTNOTES_STRING)
    hr_pos = html_content.find("<hr />", footnotes)
    return html_content[:hr_pos] + """
<p>
    <b>Footnotes</b>
</p>
""" + html_content[6 + hr_pos:]


def _substitute_template(templatepath: str, templatefile: str, **params) -> str:
    """Read the markdown template and substitute in things such as problem name,
    statement etc using python's format syntax.
    """
    with open(os.path.join(templatepath, templatefile), "r", encoding="utf-8") as template_file:
        html_template = template_file.read() % params
    return html_template
