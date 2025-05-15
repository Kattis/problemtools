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


def convert(problem_root: Path, options: argparse.Namespace, statement_file: Path) -> bool:
    """Convert a Markdown statement to HTML

    Args:
        problem: path to problem directory
        options: command-line arguments. See problem2html.py
    """
    destfile = string.Template(options.destfile).safe_substitute(problem=problem_root.name)

    command = ['pandoc', str(statement_file), '-t', 'html', '--mathjax']
    statement_html = subprocess.run(command, capture_output=True, text=True, shell=False, check=True).stdout

    statement_html = sanitize_html(statement_file.parent, statement_html)

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

    problem_name = statement_util.get_yaml_problem_name(problem_root, options.language)
    substitution_params = {
        'statement_html': statement_html,
        'language': options.language,
        'title': html.escape(problem_name) if problem_name else 'Missing problem name',
        'problemid': html.escape(problem_root.name),
    }

    statement_html = template % substitution_params

    samples = statement_util.format_samples(problem_root)
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


def sanitize_html(statement_dir: Path, statement_html: str) -> str:
    # Allow footnote ids (the anchor points you jump to)
    def is_fn_id(s):
        pattern_id_top = r'^fn\d+$'
        pattern_id_bottom = r'^fnref\d+$'
        return bool(re.fullmatch(pattern_id_top, s)) or bool(re.fullmatch(pattern_id_bottom, s))

    allowed_classes = ('sample', 'problemheader', 'problembody', 'sampleinteractionwrite', 'sampleinteractionread')

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
            try:
                statement_util.assert_image_is_valid(statement_dir, value)
            except Exception as e:
                nonlocal image_fail_reason
                image_fail_reason = str(e)
                return None
            copy_image(statement_dir, value)
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


def copy_image(statement_dir: Path, img_src: str) -> None:
    """Copy image to output directory

    Args:
        statement_dir: the directory with problem statement files
        img_src: the image source as in the Markdown statement
    """

    if os.path.isfile(img_src):  # already copied
        return
    shutil.copyfile(statement_dir / img_src, img_src)
