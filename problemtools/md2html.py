#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import os.path
import string
import argparse
import json
import subprocess

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
                 lambda img_name: handle_image(os.path.join(problem, "problem_statement", img_name)))
    command = ["pandoc", statement_path, "-t" , "html"]
    statement_html = subprocess.run(command, capture_output=True, text=True,
                                    shell=False, check=True).stdout

    templatepaths = [os.path.join(os.path.dirname(__file__), 'templates/markdown'),
                     os.path.join(os.path.dirname(__file__), '../templates/markdown'),
                     '/usr/lib/problemtools/templates/markdown']
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

    samples = "".join(statement_common.format_samples(problem, to_pdf=False))

    html_template = inject_samples(html_template, samples)
    html_template = replace_hr_in_footnotes(html_template)

    with open(destfile, "w", encoding="utf-8", errors="xmlcharrefreplace") as output_file:
        output_file.write(html_template)

    if options.css:
        with open("problem.css", "w") as output_file:
            with open(os.path.join(templatepath, "problem.css"), "r") as input_file:
                output_file.write(input_file.read())
    
    return True


def handle_image(src: str) -> None:
    """This is called for every image in the statement
    Copies the image from the statement to the output directory

    Args:
        src: full file path to the image
    """
    file_name = os.path.basename(src)

    if not os.path.isfile(src):
        raise Exception(f"File {file_name} not found in problem_statement")
    if os.path.isfile(file_name):
        return
    with open(src, "rb") as img:
        with open(file_name, "wb") as out:
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
    command = ["pandoc", statement_path, "-t" , "json"]
    statement_json = subprocess.run(command, capture_output=True,
                                    text=True, shell=False, check=True).stdout
    json_dfs(json.loads(statement_json), callback)


def inject_samples(html, samples):
    if FOOTNOTES_STRING in html:
        pos = html.find(FOOTNOTES_STRING)
    else:
        pos = html.find("</body>")
    html = html[:pos] + samples + html[pos:]
    return html


def replace_hr_in_footnotes(html_content):
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
