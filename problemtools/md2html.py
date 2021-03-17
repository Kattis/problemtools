#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import html
import re
import os.path
import string
import argparse
import logging
import subprocess

import markdown
from markdown.inlinepatterns import InlineProcessor
from markdown.extensions import Extension
import xml.etree.ElementTree as etree


def _substitute_template(templatepath, templatefile, **params):
    with open(os.path.join(templatepath, templatefile), "r", encoding="utf-8") as template_file:
        html_template = template_file.read() % params
    return html_template


def _escape(text):
    return html.escape(text)


def get_markdown_statement(problem, language):
    if language == '':
        statement_path = os.path.join(problem, "problem_statement/problem.en.md".format(language))
        if os.path.isfile(statement_path):
            return statement_path
        return None
    statement_path = os.path.join(problem, "problem_statement/problem.{}.md".format(language))
    if os.path.isfile(statement_path):
        return statement_path
    return None


def convert(problem, options=None):
    problembase = os.path.splitext(os.path.basename(problem))[0]
    destdir = string.Template(options.destdir).safe_substitute(problem=problembase)
    destfile = string.Template(options.destfile).safe_substitute(problem=problembase)
    imgbasedir = string.Template(options.imgbasedir).safe_substitute(problem=problembase)

    statement_path = get_markdown_statement(problem, options.language)

    with open(statement_path, "r", encoding="utf-8") as input_file:
        text = input_file.read()
        html = markdown.markdown(text, extensions=[InlineMathExtension(), "tables"])

    templatepaths = [os.path.join(os.path.dirname(__file__), 'templates/markdown'),
                     os.path.join(os.path.dirname(__file__), '../templates/markdown'),
                     '/usr/lib/problemtools/templates/markdown']
    templatepath = next((p for p in templatepaths
                              if os.path.isdir(p) and os.path.isfile(os.path.join(p, "default-layout.html"))),
                             None)
    if templatepath is None:
        raise Exception('Could not find directory with markdown templates')

    html_template = _substitute_template(templatepath, "default-layout.html",
            statement_html=html,
            language=options.language,
            title=options.title or "Problem Title",
            problemid=problembase)


    sample_path = os.path.join(problem, "data", "sample")
    interactive_samples = []
    samples = []
    casenum = 1
    for sample in sorted(os.listdir(sample_path)):
        if sample.endswith(".interaction"):
            lines = ["""<table class="sample" summary="sample data">
                       <tr>
                          <th style="text-align:left; width:33%;">Read</th>
                          <th style="text-align:center; width:33%;">Sample Interaction {}</th>
                          <th style="text-align:right; width:33%;">Write</th>
                       </tr>
                    </table>""".format(casenum)]
            with open(os.path.join(sample_path, sample), "r", encoding="utf-8") as infile:
                sample_interaction = infile.readlines()
            for interaction in sample_interaction:
                data = interaction[1:]
                if interaction[0] == '>':
                    lines.append("""<div class="sampleinteractionwrite"><pre>%s</pre></div>""" % _escape(data))
                elif interaction[0] == '<':
                    lines.append("""<div class="sampleinteractionread"><pre>%s</pre></div>""" % _escape(data))
                else:
                    print("Warning: Interaction had unknown prefix " + interaction[0])
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
            samples.append((sample_input, sample_output))

        samples.append(r"""
            <tr>
                <th>Sample Input %(case)d</th>
                <th>Sample Output %(case)d</th>
            </tr>
            <tr>
            <td><pre>%(input)s</pre></td>
            <td><pre>%(output)s</pre></td>
            </tr>""" % ({"case": casenum, "input": _escape(sample_input), "output": _escape(sample_output)}))
        casenum += 1

    if interactive_samples:
        html_template = html_template + ''.join(interactive_samples)
    if samples:
        html_template = html_template + """
        <table class="sample" summary="sample data">
          <tbody>
          %(samples)s
          </tbody>
        </table>
        """ % {"samples": ''.join(samples)}

    with open(os.path.join(destdir, destfile), "w", encoding="utf-8", errors="xmlcharrefreplace") as output_file:
        output_file.write(html_template)

    if options.css:
        with open(os.path.join(destdir, "problem.css"), "w") as output_file:
            with open(os.path.join(templatepath, "problem.css"), "r") as input_file:
                output_file.write(input_file.read())


class InlineMathProcessor(InlineProcessor):
    def handleMatch(self, m, data):
        el = etree.Element('span')
        el.attrib['class'] = 'tex2jax_process'
        el.text = "\\\(" + m.group(1) + "\\\)"
        return el, m.start(0), m.end(0)

class InlineMathExtension(Extension):
    def extendMarkdown(self, md):
        MATH_PATTERN = r'\\\((.*?)\\\)'  # like \( 1 + 2 \)
        md.inlinePatterns.register(InlineMathProcessor(MATH_PATTERN, md), 'inline-math', 200)

