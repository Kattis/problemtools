import os
from typing import Optional, List, Tuple
import html
import json
import re
import subprocess
import tempfile
from pathlib import Path

from . import formatversion
from . import verifyproblem

ALLOWED_IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg')  # ".svg"
FOOTNOTES_STRINGS = ['<section class="footnotes">', '<aside class="footnotes">']


def find_statement(problem_root: str, extension: str, language: Optional[str]) -> Optional[str]:
    """Finds the "best" statement for given language and extension"""
    statement_dir = Path(problem_root) / formatversion.get_format_data(problem_root).statement_directory

    candidates = []
    if language is None:
        candidates = [
            statement_dir / f'problem.en.{extension}',
            statement_dir / f'problem.{extension}',
        ]
    else:
        candidates = [statement_dir / f'problem.{language}.{extension}']

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    return None


def find_statement_extension(problem_root: str, language: Optional[str]) -> str:
    """Given a language, find whether the extension is tex or md

    Args:
        problem_root: path to problem root
    """
    extensions = []
    for ext in formatversion.get_format_data(problem_root).statement_extensions:
        if find_statement(problem_root, ext, language) is not None:
            extensions.append(ext)
    # At most one extension per language to avoid arbitrary/hidden priorities
    if len(extensions) > 1:
        raise ValueError(f"""Found more than one type of statement ({' and '.join(extensions)})
                        for language {language or 'en'}""")
    if len(extensions) == 1:
        return extensions[0]
    raise FileNotFoundError(f'No statement found for language {language or "en"}')


def get_yaml_problem_name(problem: str, language: Optional[str]) -> str:
    """Finds the problem name from the problem.yaml file"""

    # Minimal setup to get the problem name
    problem_obj = verifyproblem.Problem(problem)
    statement_obj = verifyproblem.ProblemStatement(problem_obj)
    problem_obj._data[statement_obj.PART_NAME] = statement_obj.setup()
    verifyproblem.ProblemConfig(problem_obj).setup()

    names = problem_obj.getMetadata().name
    # If there is only one language, per the spec that is the one we want
    if len(names) == 1:
        return next(iter(names.values()))

    if language is None:
        language = 'en'
    if language not in names:
        raise ValueError(f'No problem name defined for language {language or "en"}')
    return names[language]


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


def foreach_image(statement_path, callback):
    """Find all images in the statement and call callback for each one"""
    command = ['pandoc', statement_path, '-t', 'json']
    # Must create a working directory for pytest to work
    with tempfile.TemporaryDirectory() as work_dir:
        statement_json = subprocess.run(command, capture_output=True, text=True, shell=False, check=True, cwd=work_dir).stdout

    json_dfs(json.loads(statement_json), callback)


def assert_image_is_valid(problem_root: str, img_src: str) -> None:
    """Check that the image exists and uses an allowed extension"""
    extension = Path(img_src).suffix
    # TODO: fix svg sanitization and allow svg
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError(f'Unsupported image extension {extension} for image {img_src}')

    source_file = Path(problem_root) / img_src
    if not source_file.exists():
        raise FileNotFoundError(f'Resource file {img_src} not found in statement')


def assert_images_are_valid_md(statement_path: str) -> None:
    """Find all images in the statement and assert that they exist and
    use valid image extensions

    """
    problem_root = os.path.dirname(statement_path)
    foreach_image(statement_path, lambda img_name: assert_image_is_valid(problem_root, img_name))


def find_footnotes(statement_html: str) -> Optional[int]:
    """Find the position of the footnotes in the statement and return it or None"""
    for footnote_string in FOOTNOTES_STRINGS:
        if footnote_string in statement_html:
            return statement_html.find(footnote_string)
    return None


def inject_samples(statement_html: str, samples: List[str]) -> Tuple[str, List[str]]:
    """Injects samples at occurences of {{nextsample}} and {{remainingsamples}}
    Non-destructive

    Returns:
        Statement with samples inject and left-over samples.
    """

    while True:
        match = re.search(r'\{\{(nextsample|remainingsamples)\}\}', statement_html)
        if not match:
            break
        matched_text = match.group(1)
        if matched_text == 'nextsample' and len(samples) == 0:
            raise ValueError('Error: called {{nextsample}} without any samples left')

        num_inject = 1 if matched_text == 'nextsample' else len(samples)
        to_inject = ''.join(samples[:num_inject])
        samples = samples[num_inject:]

        # Always inject, even if to_inject is empty
        # This will remove all occurences of {{nextsample}} and {{remainingsamples}}
        # (And also properly throw an error if {{nextsample}} is called with no samples left)
        statement_html = statement_html[: match.start()] + to_inject + statement_html[match.end() :]

    return statement_html, samples


def format_samples(problem_root: str) -> List[str]:
    """Read all samples from the problem directory and convert them to pandoc-valid markdown

    Args:
        problem_root: path to root of problem

    Returns:
        List[str]: All samples, converted to a format appropriate to be pasted into
        a markdown file. Ordered lexicographically by file names
    """

    sample_path = os.path.join(problem_root, 'data', 'sample')
    if not os.path.isdir(sample_path):
        return []
    samples = []
    casenum = 1
    for sample in sorted(os.listdir(sample_path)):
        if sample.endswith('.interaction'):
            samples.append(format_interactive_sample(sample_path, sample, casenum))
            casenum += 1
            continue

        if not sample.endswith('.in'):
            continue
        sample_name = sample[:-3]
        outpath = os.path.join(sample_path, sample_name + '.ans')
        if not os.path.isfile(outpath):
            continue

        samples.append(format_normal_sample(sample_path, sample, casenum))
        casenum += 1

    return samples


def format_normal_sample(sample_root: str, sample: str, casenum: int) -> str:
    """

    Args:
        sample_root: root of the sample folder
        sample: file name of the sample
        casenum: which sample is this? (1, 2, 3...)

    Returns:
        str: the sample, ready to be pasted into a markdown doc and fed to pandoc
    """

    with open(os.path.join(sample_root, sample), 'r', encoding='utf-8') as infile:
        sample_input = infile.read()
    sample_name = sample[:-3]
    outpath = os.path.join(sample_root, sample_name + '.ans')
    with open(outpath, 'r', encoding='utf-8') as outfile:
        sample_output = outfile.read()

    return """
        <table class="sample" summary="sample data">
        <tbody>
            <tr>
                <th>Sample Input %(case)d</th>
                <th>Sample Output %(case)d</th>
            </tr>
            <tr>
                <td><pre>%(input)s</pre></td>
                <td><pre>%(output)s</pre></td>
            </tr>
        </tbody>
        </table>""" % ({'case': casenum, 'input': html.escape(sample_input), 'output': html.escape(sample_output)})


def format_interactive_sample(sample_root: str, sample: str, casenum: int) -> str:
    """

    Args:
        sample_root: root of the sample folder
        sample: file name of the sample
        casenum: which sample is this? (1, 2, 3...)

    Returns:
        str: the sample, ready to be pasted into a markdown doc and fed to pandoc
    """

    line = f"""
        <table class="sample" summary="sample data">
            <tr>
                <th style="text-align:left; width:33%;">Read</th>
                <th style="text-align:center; width:33%;">Sample Interaction {casenum}</th>
                <th style="text-align:right; width:33%;">Write</th>
            </tr>
        </table>"""

    with open(os.path.join(sample_root, sample), 'r', encoding='utf-8') as infile:
        sample_interaction = infile.readlines()
    lines = []
    for interaction in sample_interaction:
        data = html.escape(interaction[1:])
        line_type = ''
        if interaction[0] == '>':
            line_type = 'sampleinteractionwrite'
        elif interaction[0] == '<':
            line_type = 'sampleinteractionread'
        else:
            print(f'Warning: Interaction had unknown prefix {interaction[0]}')
        lines.append(f"""<div class="{line_type}"><pre>{html.escape(data)}</pre></div>""")

    return line + ''.join(lines)
