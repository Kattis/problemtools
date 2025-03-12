#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import os.path
import string
import argparse
import json
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


    _copy_images(statement_path,
                 lambda img_name: handle_image(problem, img_name))
    
    with open (statement_path, "r") as source:
        statement_md = source.read()
        # Replace \nextsample with \\nextsample to avoid pandoc interpreting it as a newline
        statement_md = statement_md.replace('\\nextsample', '\\\\nextsample')
        statement_md = statement_md.replace('\\remainingsamples', '\\\\remainingsamples')
        with tempfile.NamedTemporaryFile(mode='w', suffix=".md") as temp_file:
            temp_file.write(statement_md)
            temp_file.flush()

            command = ["pandoc", temp_file.name, "-t" , "html", "-f", "markdown-raw_html", "--mathjax"]
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

    # Insert samples at \nextsample and \remainingsamples
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


def handle_image(problem_root: str, img_src: str) -> None:
    """This is called for every image in the statement
    First, check if we actually allow this image
    Then, copies the image from the statement to the output directory

    Args:
        problem_root: the root of the problem directory
        img_src: the image source as in the Markdown statement
    """

    src_pattern = r'^[a-zA-Z0-9._]+\.(png|jpg|jpeg)$'

    if not re.match(src_pattern, img_src):
        raise Exception(f"Image source must match regex {src_pattern}")

    source_name = os.path.join(problem_root, "problem_statement", img_src)

    if not os.path.isfile(source_name):
        raise Exception(f"File {source_name} not found in problem_statement")
    if os.path.isfile(img_src): # already copied
        return
    with open(source_name, "rb") as img:
        with open(img_src, "wb") as out:
            out.write(img.read())


def json_dfs(data, callback) -> None:
    """Traverse all items in a JSON tree, find all images, and call callback for each one"""
    if isinstance(data, dict):
        for key, value in data.items():
            # Markdown-style images
            if key == 't' and value == 'Image':
                callback(data['c'][2][0])
            else:
                json_dfs(value, callback)

    elif isinstance(data, list):
        for item in data:
            json_dfs(item, callback)


def _copy_images(statement_path, callback):
    command = ["pandoc", statement_path, "-t" , "json", "-f", "markdown-raw_html"]
    statement_json = subprocess.run(command, capture_output=True,
                                    text=True, shell=False, check=True).stdout
    json_dfs(json.loads(statement_json), callback)


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
