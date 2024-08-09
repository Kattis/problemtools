#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import html
import os.path
import string
import argparse
import re
from typing import Optional

import xml.etree.ElementTree as etree
import markdown
from markdown.treeprocessors import Treeprocessor
from markdown.inlinepatterns import InlineProcessor
from markdown.extensions import Extension

from . import verifyproblem
from . import problem2html


def convert(problem: str, options: argparse.Namespace) -> None:
    """Convert a Markdown statement to HTML
    
    Args:
        problem: path to problem directory
        options: command-line arguments. See problem2html.py
    """
    problembase = os.path.splitext(os.path.basename(problem))[0]
    destfile = string.Template(options.destfile).safe_substitute(problem=problembase)

    statement_path = problem2html._find_statement(problem, extension="md", language=options.language)

    if statement_path is None:
        raise Exception('No markdown statement found')

    seen_images = set()
    call_handle = lambda src: _handle_image(os.path.join(problem, "problem_statement", src), seen_images)
    with open(statement_path, "r", encoding="utf-8") as input_file:
        text = input_file.read()
        statement_html = markdown.markdown(text, extensions=[MathExtension(), AddClassExtension(), "tables",
                                                             FixImageLinksExtension(call_handle)])



    templatepaths = [os.path.join(os.path.dirname(__file__), 'templates/markdown'),
                     os.path.join(os.path.dirname(__file__), '../templates/markdown'),
                     '/usr/lib/problemtools/templates/markdown']
    templatepath = next((p for p in templatepaths
                              if os.path.isdir(p) and os.path.isfile(os.path.join(p, "default-layout.html"))),
                             None)

    if templatepath is None:
        raise Exception('Could not find directory with markdown templates')

    problem_name = _get_problem_name(problem)

    html_template = _substitute_template(templatepath, "default-layout.html",
           statement_html=statement_html,
           language=options.language,
           title=problem_name or "Missing problem name",
           problemid=problembase)

    html_template += _samples_to_html(problem)

    with open(destfile, "w", encoding="utf-8", errors="xmlcharrefreplace") as output_file:
        output_file.write(html_template)

    if options.css:
        with open("problem.css", "w") as output_file:
            with open(os.path.join(templatepath, "problem.css"), "r") as input_file:
                output_file.write(input_file.read())


def _handle_image(src, seen_images):
    if src in seen_images:
        return
    if not os.path.isfile(src):
        raise Exception(f"Could not find image {src} in problem_statement folder")
    file_name = os.path.basename(src)
    with open(src, "rb") as img:
        with open(file_name, "wb") as out:
            out.write(img.read())


def _substitute_template(templatepath: str, templatefile: str, **params) -> str:
    """Read the markdown template and substitute in things such as problem name,
    statement etc using python's format syntax.
    """
    with open(os.path.join(templatepath, templatefile), "r", encoding="utf-8") as template_file:
        html_template = template_file.read() % params
    return html_template


def _get_problem_name(problem: str, language: str = "en") -> Optional[str]:
    """Load problem.yaml to get problem name"""
    with verifyproblem.Problem(problem) as prob:
        config = verifyproblem.ProblemConfig(prob)
    if not config.check(None):
        print("Please add problem name to problem.yaml when using markdown")
        return None
    names = config.get("name")
    # If there is only one language, per the spec that is the one we want
    if len(names) == 1:
        return next(iter(names.values()))

    if language not in names:
        raise Exception(f"No problem name defined for language {language}")
    return names[language]


def _samples_to_html(problem: str) -> str:
    """Read all samples from the problem directory and convert them to HTML"""
    samples_html = ""
    sample_path = os.path.join(problem, "data", "sample")
    interactive_samples = []
    samples = []
    casenum = 1
    for sample in sorted(os.listdir(sample_path)):
        if sample.endswith(".interaction"):
            lines = [f"""<table class="sample" summary="sample data">
                       <tr>
                          <th style="text-align:left; width:33%;">Read</th>
                          <th style="text-align:center; width:33%;">Sample Interaction {casenum}</th>
                          <th style="text-align:right; width:33%;">Write</th>
                       </tr>
                    </table>"""]
            with open(os.path.join(sample_path, sample), "r", encoding="utf-8") as infile:
                sample_interaction = infile.readlines()
            for interaction in sample_interaction:
                data = interaction[1:]
                line_type = ""
                if interaction[0] == '>':
                    line_type = "sampleinteractionwrite"
                elif interaction[0] == '<':
                    line_type = "sampleinteractionread"
                else:
                    print(f"Warning: Interaction had unknown prefix {interaction[0]}")
                lines.append(f"""<div class="{line_type}"><pre>{data}</pre></div>""")

            interactive_samples.append(''.join(lines))
            casenum += 1
            continue
        if not sample.endswith(".in"):
            continue
        sample_name = sample[:-3]
        outpath = os.path.join(sample_path, sample_name + ".ans")
        if not os.path.isfile(outpath):
            continue
        with open(os.path.join(sample_path, sample), "r", encoding="utf-8") as infile:
            sample_input = infile.read()
        with open(outpath, "r", encoding="utf-8") as outfile:
            sample_output = outfile.read()

        samples.append("""
            <tr>
                <th>Sample Input %(case)d</th>
                <th>Sample Output %(case)d</th>
            </tr>
            <tr>
            <td><pre>%(input)s</pre></td>
            <td><pre>%(output)s</pre></td>
            </tr>"""
            % ({"case": casenum, "input": html.escape(sample_input), "output": html.escape(sample_output)}))
        casenum += 1

    if interactive_samples:
        samples_html += ''.join(interactive_samples)
    if samples:
        samples_html += f"""
        <table class="sample" summary="sample data">
          <tbody>
          {''.join(samples)}
          </tbody>
        </table>
        """
    return samples_html


class InlineMathProcessor(InlineProcessor):
    """Tell mathjax to process all $a+b$"""
    def handleMatch(self, m, data):
        el = etree.Element('span')
        el.attrib['class'] = 'tex2jax_process'
        el.text = "$" + m.group(1) + "$"
        return el, m.start(0), m.end(0)


class DisplayMathProcessor(InlineProcessor):
    """Tell mathjax to process all $$a+b$$"""
    def handleMatch(self, m, data):
        el = etree.Element('div')
        el.attrib['class'] = 'tex2jax_process'
        el.text = "$$" + m.group(1) + "$$"
        return el, m.start(0), m.end(0)


class MathExtension(Extension):
    """Add $a+b$ and $$a+b$$"""
    def extendMarkdown(self, md):
        # Regex magic so that both $ $ and $$ $$ can coexist. Written by a wizard (ChatGPT)
        inline_math_pattern = r'(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)'  # $1 + 2$
        display_math_pattern = r'\$\$(.+?)\$\$'  # $$E = mc^2$$

        md.inlinePatterns.register(DisplayMathProcessor(display_math_pattern, md), 'display-math', 200)
        md.inlinePatterns.register(InlineMathProcessor(inline_math_pattern, md), 'inline-math', 201)


class AddClassTreeprocessor(Treeprocessor):
    """Add class "markdown-table" to all tables.
    Makes it easier to only style user-generated, and not sample tables
    """
    def run(self, root):
        for table in root.findall(".//table"):
            if 'class' not in table.attrib:
                table.set('class', 'markdown-table')


class AddClassExtension(Extension):
    """Just add AddClassTreeprocessor extension"""
    def extendMarkdown(self, md):
        md.treeprocessors.register(AddClassTreeprocessor(md), 'add_class', 15)


class FixImageLinks(Treeprocessor):
    """Find all reasonable images and run a callback with their image source
    If your image name is image.jpg, we consider the following to be reasonable
    ![Alt](image.jpg)
    <img src="image.jpg">
    
    Implementation details: python-markdown seems to put both of these inside
    html nodes' text, not as their own nodes. Therefore, we do a dfs and
    use regex to extract them.
    
    """
    def __init__(self, md, callback):
        super().__init__(md)
        self.callback = callback

    def find_images(self, text: str) -> None:
        """Find all images in a string and call the callback on each"""
        if not text:
            return
        
        # Find html-style images
        html_img_pattern = re.compile(r'<img\s+([^>]*?)>', re.IGNORECASE)

        html_src_pattern = re.compile(r'src\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
        for match in html_img_pattern.finditer(text):
            img_attrs = match.group(1)
            
            src_match = html_src_pattern.search(img_attrs)
            if src_match:
                src_value = src_match.group(1)
                self.callback(src_value)
        
        # Find markdown-style images
        markdown_pattern = re.compile(r'!\[(.*?)\]\((.*?)\s*(?:"(.*?)")?\)')

        for match in markdown_pattern.finditer(text):
            alt_text, src, title = match.groups()
            self.callback(src)

    def dfs(self, element):
        """Visit every html node and find any images contained in it"""
        self.find_images(element.text)
        for child in element:
            self.dfs(child)

    def run(self, root):
        self.dfs(root)

class FixImageLinksExtension(Extension):
    """Add FixImageLinks extension"""
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def extendMarkdown(self, md):
        md.treeprocessors.register(FixImageLinks(md, self.callback), 'find_images', 200)
