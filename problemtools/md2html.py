#! /usr/bin/env python3
# -*- coding: utf-8 -*-
import html
import os.path
import string
import argparse
import re
import json
from typing import Optional

from . import verifyproblem
from . import problem2html


FOOTNOTES_STRING = '<section class="footnotes" role="doc-endnotes">'

def convert(problem: str, options: argparse.Namespace) -> None:
    """Convert a Markdown statement to HTML
    
    Args:
        problem: path to problem directory
        options: command-line arguments. See problem2html.py
    """
    problembase = os.path.splitext(os.path.basename(problem))[0]
    destfile = string.Template(options.destfile).safe_substitute(problem=problembase)

    statement_path = problem2html.find_statement(problem, extension="md", language=options.language)

    if statement_path is None:
        raise Exception('No markdown statement found')

    if not os.path.isfile(statement_path):
        raise Exception(f"Error! {statement_path} is not a file")


    _copy_images(statement_path,
                 lambda img_name: handle_image(os.path.join(problem, "problem_statement", img_name)))
    statement_html = os.popen(f"pandoc {statement_path} -t html").read()

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

    samples = _samples_to_html(problem)

    html_template = inject_samples(html_template, samples)
    html_template = replace_hr_in_footnotes(html_template)

    with open(destfile, "w", encoding="utf-8", errors="xmlcharrefreplace") as output_file:
        output_file.write(html_template)

    if options.css:
        with open("problem.css", "w") as output_file:
            with open(os.path.join(templatepath, "problem.css"), "r") as input_file:
                output_file.write(input_file.read())


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
    if isinstance(data, dict):
        for key, value in data.items():
            # Markdown-style images
            if key == 't' and value == 'Image':
                callback(data['c'][2][0])
            else:
                json_dfs(value, callback)

            # HTML-style images
            if key == "t" and value == "RawInline":
                image_string = data["c"][1]
                src = re.search(r'src=["\'](.*?)["\']', image_string)
                if src:
                    callback(src.group(1))
    
    elif isinstance(data, list):
        for item in data:
            json_dfs(item, callback)


def _copy_images(statement_path, callback):
    statement_json = os.popen(f"pandoc {statement_path} -t json").read()
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

