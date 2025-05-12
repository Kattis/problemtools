#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import html
import os
from pathlib import Path
import re
import shutil
import string
import subprocess

import nh3

from . import statement_util


def convert(problem: str, options: argparse.Namespace) -> bool:
    """Convert a Markdown statement to HTML

    Args:
        problem: path to problem directory
        options: command-line arguments. See problem2html.py
    """
    problembase = os.path.splitext(os.path.basename(problem))[0]
    destfile = string.Template(options.destfile).safe_substitute(problem=problembase)

    statement_path = statement_util.find_statement(problem, extension='md', language=options.language)

    if statement_path is None:
        raise FileNotFoundError('No markdown statement found')

    if not os.path.isfile(statement_path):
        raise FileNotFoundError(f'Error! {statement_path} does not exist')

    command = ['pandoc', statement_path, '-t', 'html', '--mathjax']
    statement_html = subprocess.run(command, capture_output=True, text=True, shell=False, check=True).stdout

    statement_html = sanitize_html(problem, statement_html)

    templatepaths = [
        os.path.join(os.path.dirname(__file__), 'templates/markdown_html'),
        '/usr/lib/problemtools/templates/markdown_html',
    ]
    templatepath = next(
        (p for p in templatepaths if os.path.isdir(p) and os.path.isfile(os.path.join(p, 'default-layout.html'))), None
    )

    if templatepath is None:
        raise FileNotFoundError('Could not find directory with markdown templates')

    with open(Path(templatepath) / 'default-layout.html', 'r', encoding='utf-8') as template_file:
        template = template_file.read()

    problem_name = statement_util.get_yaml_problem_name(problem, options.language)
    substitution_params = {
        'statement_html': statement_html,
        'language': options.language,
        'title': html.escape(problem_name) if problem_name else 'Missing problem name',
        'problemid': html.escape(problembase),
    }

    statement_html = template % substitution_params

    samples = statement_util.format_samples(problem)
    # Insert samples at {{nextsample}} and {{remainingsamples}}
    statement_html, remaining_samples = statement_util.inject_samples(statement_html, samples)

    # Insert the remaining samples at the bottom
    # However, footnotes should be below samples
    sample_insertion_position = statement_util.find_footnotes(statement_html)
    if sample_insertion_position is None:
        # No footnotes, so insert at the end
        sample_insertion_position = statement_html.rfind('</body>')
    statement_html = (
        statement_html[:sample_insertion_position] + ''.join(remaining_samples) + statement_html[sample_insertion_position:]
    )

    with open(destfile, 'w', encoding='utf-8', errors='xmlcharrefreplace') as output_file:
        output_file.write(statement_html)

    if options.css:
        shutil.copyfile(os.path.join(templatepath, 'problem.css'), 'problem.css')

    return True


def sanitize_html(problem: str, statement_html: str):
    # Allow footnote ids (the anchor points you jump to)
    def is_fn_id(s):
        pattern_id_top = r'^fn\d+$'
        pattern_id_bottom = r'^fnref\d+$'
        return bool(re.fullmatch(pattern_id_top, s)) or bool(re.fullmatch(pattern_id_bottom, s))

    allowed_classes = ('sample', 'problemheader', 'problembody', 'sampleinteractionwrite', 'sampleinteractionread')

    def is_image_valid(problem_root: str, img_src: str) -> str | None:
        # Check that the image exists and uses an allowed extension
        extension = Path(img_src).suffix
        # TODO: fix svg sanitization and allow svg
        if extension not in statement_util.ALLOWED_IMAGE_EXTENSIONS:
            return f'Unsupported image extension {extension} for image {img_src}'

        source_file = Path(problem_root) / 'statement' / img_src
        if not source_file.exists():
            return f'Resource file {img_src} not found in statement'
        return None

    # Annoying: nh3 will ignore exceptions in attribute_filter
    image_fail_reason: str | None = None

    def attribute_filter(tag, attribute, value):
        if attribute == 'class' and value in allowed_classes:
            return value
        # Never versions of Pandoc will give class="footnotes footnotes-end-of-document"
        # We don't want to blindly allow any class with footnotes in it, so only allow footnotes
        if attribute == 'class' and 'footnotes' in value:
            return 'footnotes'
        if tag == 'a' and attribute == 'href':
            return value
        if tag in ('li', 'a') and attribute == 'id' and is_fn_id(value):
            return value
        if tag == 'img' and attribute == 'src':
            fail = is_image_valid(problem, value)
            if fail:
                nonlocal image_fail_reason
                image_fail_reason = fail
                return None
            copy_image(problem, value)
            return value
        return None

    statement_html = nh3.clean(
        statement_html,
        link_rel='noopener nofollow noreferrer',
        attribute_filter=attribute_filter,
        tags=nh3.ALLOWED_TAGS | {'img', 'a', 'section'},
        attributes={
            'table': {'class'},
            'aside': {'class'},
            'div': {'class'},
            'section': {'class'},
            'img': {'src'},
            'a': {'href', 'id'},
            'li': {'id'},
        },
    )

    if image_fail_reason:
        assert isinstance(image_fail_reason, str)
        if 'Unsupported' in image_fail_reason:
            raise ValueError(image_fail_reason)
        raise FileNotFoundError(image_fail_reason)

    return statement_html


def copy_image(problem_root: str, img_src: str) -> None:
    """Copy image to output directory

    Args:
        problem_root: the root of the problem directory
        img_src: the image source as in the Markdown statement
    """

    source_name = os.path.join(problem_root, 'statement', img_src)

    if os.path.isfile(img_src):  # already copied
        return
    shutil.copyfile(source_name, img_src)
