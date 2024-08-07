#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import html
import os.path
import string
import argparse
from typing import Optional

import markdown
from markdown.inlinepatterns import InlineProcessor
from markdown.extensions import Extension
import xml.etree.ElementTree as etree

from . import verifyproblem
from . import problem2html

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

        samples.append(f"""
            <tr>
                <th>Sample Input %(case)d</th>
                <th>Sample Output %(case)d</th>
            </tr>
            <tr>
            <td><pre>%(input)s</pre></td>
            <td><pre>%(output)s</pre></td>
            </tr>""" % ({"case": casenum, "input": html.escape(sample_input), "output": html.escape(sample_output)}))
        casenum += 1

    if interactive_samples:
        samples_html += ''.join(interactive_samples)
    if samples:
        samples_html += """
        <table class="sample" summary="sample data">
          <tbody>
          %(samples)s
          </tbody>
        </table>
        """ % {"samples": ''.join(samples)}
    return samples_html


def convert(problem: str, options: argparse.Namespace) -> None:
    problembase = os.path.splitext(os.path.basename(problem))[0]
    destfile = string.Template(options.destfile).safe_substitute(problem=problembase)

    statement_path = problem2html._find_statement(problem, extension="md", language=options.language)

    if statement_path is None:
        raise Exception('No markdown statement found')

    with open(statement_path, "r", encoding="utf-8") as input_file:
        text = input_file.read()
        statement_html = markdown.markdown(text, extensions=[MathExtension(), "tables"])

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


class InlineMathProcessor(InlineProcessor):
    def handleMatch(self, m, data):
        el = etree.Element('span')
        el.attrib['class'] = 'tex2jax_process'
        el.text = "$" + m.group(1) + "$"
        return el, m.start(0), m.end(0)

class DisplayMathProcessor(InlineProcessor):
    def handleMatch(self, m, data):
        el = etree.Element('div')
        el.attrib['class'] = 'tex2jax_process'
        el.text = "$$" + m.group(1) + "$$"
        return el, m.start(0), m.end(0)

class MathExtension(Extension):
    def extendMarkdown(self, md):
        # Regex magic so that both $ $ and $$ $$ can coexist
        INLINE_MATH_PATTERN = r'(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)'  # $1 + 2$
        DISPLAY_MATH_PATTERN = r'\$\$(.+?)\$\$'  # $$E = mc^2$$

        md.inlinePatterns.register(DisplayMathProcessor(DISPLAY_MATH_PATTERN, md), 'display-math', 200)
        md.inlinePatterns.register(InlineMathProcessor(INLINE_MATH_PATTERN, md), 'inline-math', 201)
