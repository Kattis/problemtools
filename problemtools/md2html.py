#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import html
import os
import re
import shutil
import string
import subprocess

import nh3

from . import statement_common


FOOTNOTES_STRING = '<section class="footnotes">'

def convert(problem: str, options: argparse.Namespace) -> bool:
    """Convert a Markdown statement to HTML

    Args:
        problem: path to problem directory
        options: command-line arguments. See problem2html.py
    """
    problembase = os.path.splitext(os.path.basename(problem))[0]
    destfile = string.Template(options.destfile).safe_substitute(problem=problembase)

    statement_path = statement_common.find_statement(problem, extension="md",
                                                     language=options.language)

    if statement_path is None:
        raise FileNotFoundError('No markdown statement found')

    if not os.path.isfile(statement_path):
        raise FileNotFoundError(f"Error! {statement_path} is not a file")


    command = ["pandoc", statement_path, "-t" , "html", "--mathjax"]
    statement_html = subprocess.run(command, capture_output=True, text=True,
        shell=False, check=True).stdout

    statement_html = sanitize_html(problem, statement_html)

    templatepaths = [os.path.join(os.path.dirname(__file__), 'templates/markdown_html'),
                     '/usr/lib/problemtools/templates/markdown_html']
    templatepath = next((p for p in templatepaths
        if os.path.isdir(p) and os.path.isfile(os.path.join(p, "default-layout.html"))),
        None)

    if templatepath is None:
        raise FileNotFoundError('Could not find directory with markdown templates')

    problem_name = statement_common.get_yaml_problem_name(problem, options.language)

    statement_html = _substitute_template(templatepath, "default-layout.html",
           statement_html=statement_html,
           language=options.language,
           title=html.escape(problem_name) if problem_name else "Missing problem name",
           problemid=html.escape(problembase))

    samples = statement_common.format_samples(problem, to_pdf=False)

    # Insert samples at {{nextsample}} and {{remainingsamples}}
    statement_html, remaining_samples = statement_common.inject_samples(statement_html, samples, "")

    # Insert the remaining samples at the bottom
    # However, footnotes should be below samples
    if FOOTNOTES_STRING in statement_html:
        pos = statement_html.find(FOOTNOTES_STRING)
    else:
        pos = statement_html.rfind("</body>")
    statement_html = statement_html[:pos] + "".join(remaining_samples) + statement_html[pos:]

    with open(destfile, "w", encoding="utf-8", errors="xmlcharrefreplace") as output_file:
        output_file.write(statement_html)

    if options.css:
        shutil.copyfile(os.path.join(templatepath, "problem.css"), "problem.css")

    return True

def sanitize_html(problem: str, statement_html: str):
    # Allow footnote ids (the anchor points you jump to)
    def is_fn_id(s):
        pattern_id_top = r'^fn\d+$'
        pattern_id_bottom = r'^fnref\d+$'
        return bool(re.fullmatch(pattern_id_top, s)) or bool(re.fullmatch(pattern_id_bottom, s))

    allowed_classes = ("sample", "problemheader", "problembody",
                    "sampleinteractionwrite", "sampleinteractionread",
                    "footnotes")

    # Annoying: nh3 will ignore exceptions in attribute_filter
    image_fail_reason = None
    def attribute_filter(tag, attribute, value):
        if attribute == "class" and value in allowed_classes:
            return value
        if tag == "a" and attribute == "href":
            return value
        if tag in ("li", "a") and attribute == "id" and is_fn_id(value):
            return value
        if tag == "img" and attribute == "src":
            fail = statement_common.is_image_valid(problem, value)
            if fail:
                nonlocal image_fail_reason
                image_fail_reason = fail
                return None
            copy_image(problem, value)
            return value
        return None

    statement_html = nh3.clean(statement_html,
        link_rel="noopener nofollow noreferrer",
        attribute_filter=attribute_filter,
        tags=nh3.ALLOWED_TAGS | {"img", "a", "section"},
        attributes={"table": {"class"}, "div": {"class"}, "section": {"class"}, "img": {"src"},
                    "a": {"href", "id"}, "li": {"id"}},
    )

    if image_fail_reason:
        raise Exception(image_fail_reason)

    return statement_html

def copy_image(problem_root: str, img_src: str) -> None:
    """Copy image to output directory

    Args:
        problem_root: the root of the problem directory
        img_src: the image source as in the Markdown statement
    """

    source_name = os.path.join(problem_root, "problem_statement", img_src)

    if os.path.isfile(img_src): # already copied
        return
    shutil.copyfile(source_name, img_src)

def _substitute_template(templatepath: str, templatefile: str, **params) -> str:
    """Read the markdown template and substitute in things such as problem name,
    statement etc using python's format syntax.
    """
    with open(os.path.join(templatepath, templatefile), "r", encoding="utf-8") as template_file:
        html_template = template_file.read() % params
    return html_template
