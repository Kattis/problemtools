import collections
import html
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, List, Tuple

from . import formatversion
from . import metadata

ALLOWED_IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg')  # ".svg"
FOOTNOTES_STRINGS = ['<section class="footnotes">', '<aside class="footnotes">']


def find_statements(problem_root: Path, version: formatversion.FormatData) -> dict[str, list[Path]]:
    """Returns a dict mapping language code to a list of paths to statements (relative to problem_root)

    Note that in well-formed problem packages, there should only be a single
    statement for each language, but this function returns all found
    statements, to let the caller inform the user of errors.
    """

    directory = problem_root / version.statement_directory
    ret = collections.defaultdict(list)
    if directory.is_dir():
        filename_re = re.compile(r'^problem(\.([a-z]{2,3}|[a-z]{2}-[A-Z]{2}))?\.(%s)$' % ('|'.join(version.statement_extensions)))
        for file in directory.iterdir():
            if m := filename_re.search(file.name):
                if m.group(2) is None:  # problem.tex is allowed and assumed to be 'en' in legacy. We ignore it in newer formats.
                    if version.name == formatversion.VERSION_LEGACY:
                        ret['en'].append(file)
                else:
                    ret[m.group(2)].append(file)
    return dict(ret)


def load_names_from_statements(problem_root: Path, version: formatversion.FormatData) -> dict[str, str]:
    """Returns a dict mapping language code => problem name"""

    assert version.name == formatversion.VERSION_LEGACY, 'load_names_from_statements only makes sense for legacy format'
    ret: dict[str, str] = {}
    for lang, files in find_statements(problem_root, version).items():
        hit = re.search(r'\\problemname{(.*)}', files[0].read_text(), re.MULTILINE)
        if hit:
            ret[lang] = hit.group(1).strip()
    return ret


def find_statement(problem_root: Path, language: str) -> Path:
    """Finds the statement in a given language.

    Raises
        ValueError: if there are multiple statements in language.
        FileNotFoundError: if there are no statements in language.
    """
    candidates = find_statements(problem_root, formatversion.get_format_data(str(problem_root)))
    if language not in candidates:
        raise FileNotFoundError(f'No statement found in language {language}. Found languages: {", ".join(candidates)}')
    elif len(candidates[language]) > 1:
        raise ValueError(f'Multiple statements in language {language}: {", ".join((file.name for file in candidates[language]))}')
    else:
        return candidates[language][0]


def get_yaml_problem_name(problem_root: Path, language: str) -> str:
    """Finds the problem name from the problem.yaml file"""

    problem_metadata, _ = metadata.load_metadata(problem_root)
    names = problem_metadata.name
    # If there is only one language, per the spec that is the one we want
    if len(names) == 1:
        return next(iter(names.values()))

    if language not in names:
        raise ValueError(f'No problem name defined for language {language}')
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


def foreach_image(statement_path: Path, callback):
    """Find all images in the statement and call callback for each one"""
    command = ['pandoc', str(statement_path), '-t', 'json']
    # Must create a working directory for pytest to work
    with tempfile.TemporaryDirectory() as work_dir:
        statement_json = subprocess.run(command, capture_output=True, text=True, shell=False, check=True, cwd=work_dir).stdout

    json_dfs(json.loads(statement_json), callback)


def assert_image_is_valid(statement_dir: Path, img_src: str) -> None:
    """Check that the image exists and uses an allowed extension"""
    extension = Path(img_src).suffix
    # TODO: fix svg sanitization and allow svg
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError(f'Unsupported image extension {extension} for image {img_src}')

    source_file = statement_dir / img_src
    if not source_file.exists():
        raise FileNotFoundError(f'Resource file {img_src} not found in statement')


def assert_images_are_valid_md(statement_path: Path) -> None:
    """Find all images in the statement and assert that they exist and
    use valid image extensions"""
    statement_dir = statement_path.parent
    foreach_image(statement_path, lambda img_name: assert_image_is_valid(statement_dir, img_name))


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


def format_samples(problem_root: Path) -> List[str]:
    """Read all samples from the problem directory and convert them to pandoc-valid markdown

    Args:
        problem_root: path to root of problem

    Returns:
        List[str]: All samples, converted to a format appropriate to be pasted into
        a markdown file. Ordered lexicographically by file names
    """

    sample_path = os.path.join(str(problem_root), 'data', 'sample')
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
        lines.append(f"""<div class="{line_type}"><pre>{data}</pre></div>""")

    return line + ''.join(lines)
