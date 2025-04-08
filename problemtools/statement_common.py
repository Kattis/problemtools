import os
from typing import Optional, List
import html
import json
import re
import subprocess
import tempfile
from pathlib import Path

import yaml

SUPPORTED_EXTENSIONS = ("tex", "md")

def find_statement(problem_root: str, extension: str, language: Optional[str]) -> Optional[str]:
    """Finds the "best" statement for given language and extension"""
    if language is None:
        statement_path = os.path.join(problem_root, f"statement/problem.en.{extension}")
        if os.path.isfile(statement_path):
            return statement_path
        statement_path = os.path.join(problem_root, f"statement/problem.{extension}")
        if os.path.isfile(statement_path):
            return statement_path
        return None
    statement_path = os.path.join(problem_root, f"statement/problem.{language}.{extension}")
    if os.path.isfile(statement_path):
        return statement_path
    return None


def find_statement_extension(problem_root: str, language: Optional[str]) -> str:
    """Given a language, find whether the extension is tex or md

    Args:
        problem_root: path to problem root
    """
    extensions = []
    for ext in SUPPORTED_EXTENSIONS:
        if find_statement(problem_root, ext, language) is not None:
            extensions.append(ext)
    # At most one extension per language to avoid arbitrary/hidden priorities
    if len(extensions) > 1:
        raise ValueError(f"""Found more than one type of statement ({' and '.join(extensions)})
                        for language {language or 'en'}""")
    if len(extensions) == 1:
        return extensions[0]
    raise FileNotFoundError(f"No statement found for language {language or 'en'}")


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
    # Find all images in the statement and call callback for each one
    command = ["pandoc", statement_path, "-t" , "json"]
    # Must create a working directory for pytest to work
    with tempfile.TemporaryDirectory() as dir:
        statement_json = subprocess.run(command, capture_output=True, text=True,
                                        shell=False, check=True, cwd=dir).stdout

    json_dfs(json.loads(statement_json), callback)

def is_image_valid(problem_root: str, img_src: str) -> str|None:
    # Check that the image exists and uses an allowed extension
    extension = Path(img_src).suffix
    # TODO: fix svg sanitization and allow svg
    if extension not in (".png", ".jpg", ".jpeg"): # ".svg"
        return f"Unsupported image extension {extension} for image {img_src}"

    source_file = Path(problem_root) / "statement" / img_src
    if not source_file.exists():
        return f"Resource file {img_src} not found in statement"
    return None

def assert_image_is_valid(problem_root: str, img_src: str) -> str|None:
    # Check that the image exists and uses an allowed extension
    extension = Path(img_src).suffix
    # TODO: fix svg sanitization and allow svg
    if extension not in (".png", ".jpg", ".jpeg"): # ".svg"
        raise ValueError(f"Unsupported image extension {extension} for image {img_src}")

    source_file = Path(problem_root) / "statement" / img_src
    if not source_file.exists():
        raise FileNotFoundError(f"Resource file {img_src} not found in statement")


def assert_images_are_valid_md(statement_path: str) -> None:
    # Find all images in the statement and assert that they exist and
    # use valid image extensions
    problem_root = os.path.dirname(statement_path)
    foreach_image(statement_path,
                lambda img_name: assert_image_is_valid(problem_root, img_name))

def get_yaml_problem_name(problem: str, language: Optional[str]) -> Optional[str]:

    # TODO: getting this should be done using verifyproblem
    # Wait until new config parsing system is in place
    config_file = Path(problem) / 'problem.yaml'

    if not config_file.is_file():
        raise FileNotFoundError("No problem.yaml found")

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        if config is None:
            config = {}
    except Exception as e:
        raise ValueError(f"Invalid problem.yaml: {e}") from e

    if 'name' in config and not isinstance(config['name'], dict):
        config['name'] = {'': config['name']}

    names = config.get("name")
    # If there is only one language, per the spec that is the one we want
    if len(names) == 1:
        return next(iter(names.values()))

    if language is None:
        language = "en"
    if language not in names:
        raise ValueError(f"No problem name defined for language {language or 'en'}")
    return names[language]


def inject_samples(statement_html, samples, sample_separator):
    """Injects samples at occurences of {{nextsample}} and {{remainingsamples}}
    Non-destructive, returns the new html and all left-over samples

    Returns:
        """

    while True:
        match = re.search(r'\{\{(nextsample|remainingsamples)\}\}', statement_html)
        if not match:
            break
        matched_text = match.group(1)
        if matched_text == "nextsample" and len(samples) == 0:
            raise ValueError("Error: called {{nextsample}} without any samples left")

        num_inject = 1 if matched_text == "nextsample" else len(samples)
        to_inject = sample_separator.join(samples[:num_inject])
        samples = samples[num_inject:]

        # Always inject, even if to_inject is empty
        # This will remove all occurences of {{nextsample}} and {{remainingsamples}}
        # (And also properly throw an error if {{nextsample}} is called with no samples left)
        statement_html = statement_html[:match.start()] + to_inject + statement_html[match.end():]

    return statement_html, samples


def format_samples(problem_root: str, to_pdf: bool = False) -> List[str]:
    """Read all samples from the problem directory and convert them to pandoc-valid markdown

    Args:
        problem_root: path to root of problem
        to_pdf: whether the outputted samples should be valid for for html or pdf

    Returns:
        List[str]: All samples, converted to a format appropriate to be pasted into
        a markdown file. Ordered lexicographically by file names
    """

    sample_path = os.path.join(problem_root, "data", "sample")
    if not os.path.isdir(sample_path):
        return []
    samples = []
    casenum = 1
    for sample in sorted(os.listdir(sample_path)):
        if sample.endswith(".interaction"):
            samples.append(format_interactive_sample(sample_path, sample, casenum, to_pdf))
            casenum += 1
            continue

        if not sample.endswith(".in"):
            continue
        sample_name = sample[:-3]
        outpath = os.path.join(sample_path, sample_name + ".ans")
        if not os.path.isfile(outpath):
            continue

        samples.append(format_normal_sample(sample_path, sample, casenum, to_pdf))
        casenum += 1

    return samples

def escape_latex_char(char: str) -> str:
    if len(char) != 1:
        raise ValueError("Input must be a single character.")

    replacements = {
        "\\": "\\textbackslash{}",
        "^": "\\textasciicircum{}",
        "~": "\\textasciitilde{}",
        "#": "\\#",
        "$": "\\$",
        "%": "\\%",
        "&": "\\&",
        "_": "\\_",
        "{": "\\{",
        "}": "\\}",
        "*": "\\*",
        "<": "\\textless{}",
        ">": "\\textgreater{}",
        "|": "\\textbar{}",
        "'": "\\textquotesingle{}",
        "`": "\\textasciigrave{}",
        "\"":"\\verb|\"|",
        ",": "\\verb|,|",
        "-": "\\verb|-|",
        "[": "\\verb|[|",
        "]": "\\verb|]|",
    }
    return replacements.get(char, char)  # Default: return unmodified char

def format_normal_sample(sample_root: str, sample: str, casenum: int, to_pdf: bool) -> str:
    """

    Args:
        sample_root: root of the sample folder
        sample: file name of the sample
        casenum: which sample is this? (1, 2, 3...)
        to_pdf: do we target pdf or html output

    Returns:
        str: the sample, ready to be pasted into a markdown doc and fed to pandoc
    """

    with open(os.path.join(sample_root, sample), "r", encoding="utf-8") as infile:
        sample_input = infile.read()
    sample_name = sample[:-3]
    outpath = os.path.join(sample_root, sample_name + ".ans")
    with open(outpath, "r", encoding="utf-8") as outfile:
        sample_output = outfile.read()

    if not to_pdf:
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
            </table>""" % ({"case": casenum, "input": html.escape(sample_input),
                            "output": html.escape(sample_output)})


    # Try to pack input and output into a Markdown table like this
    # Precompute characters widths in LaTeX, pack as much
    # as possible without causing overflow in the LaTeX table
    # Use an obscene number of columns so Markdown is not limiting
    """
    +---------------------------------+---------------------------------+
    | Sample Input 1                  | Sample Output 1                 |
    +=================================+=================================+
    |0123456789abcdefghijklmnopqrstuv-|Nice!                            |
    |wxyzABCDEFGHIJKLMNOPQRS-         |                                 |
    |TUVWXYZ!"#$%&'()*+,-./:;<=>?-    |                                 |
    |@[\]^_`{|}~                      |                                 |
    +---------------------------------+---------------------------------+
    """
    # Need to account for if we have >= 10 samples
    casenum_len = len(str(casenum))-1

    # If there are lots of ^, we use lots of \\textasciicircum{}, and they must all fit
    # Lower if debugging (or zoom out terminal veery far)
    table_cols = 1000
    row = f"|{' ' * (table_cols + 16)}|{' ' * (table_cols + 16)}|\n"
    ascii_char_widths = {' ': 3.33333, '!': 3.2, '"': 6.2, '#': 9.6, '$': 5.9, '%': 9.6, '&': 9.0, "'": 3.2, '(': 4.5, ')': 4.5, '*': 5.8, '+': 9.0, ',': 6.2, '-': 6.5, '.': 5, '/': 5.8, '0': 5.8, '1': 5.8, '2': 5.8, '3': 5.8, '4': 5.8, '5': 5.8, '6': 5.8, '7': 5.8, '8': 5.8, '9': 5.8, ':': 3.2, ';': 3.2, '<': 8.9, '=': 8.9, '>': 8.9, '?': 5.4, '@': 8.9, 'A': 7.50002, 'B': 7.08336, 'C': 7.22223, 'D': 7.6389, 'E': 6.80557, 'F': 6.5278, 'G': 7.84723, 'H': 7.50002, 'I': 3.61111, 'J': 5.1389, 'K': 8.5, 'L': 6.25002, 'M': 9.16669, 'N': 7.50002, 'O': 8.5, 'P': 6.80557, 'Q': 8.5, 'R': 7.36111, 'S': 5.55557, 'T': 7.22223, 'U': 7.50002, 'V': 7.50002, 'W': 10.2778, 'X': 7.50002, 'Y': 7.50002, 'Z': 6.11111, '[': 6.2, '\\': 6.0, ']': 6.2, '^': 6.5, '_': 8.6, '`': 5.8, 'a': 5.8, 'b': 5.55557, 'c': 4.44444, 'd': 5.55557, 'e': 4.44444, 'f': 3.05557, 'g': 5.8, 'h': 5.55557, 'i': 3.2, 'j': 3.05557, 'k': 5.2778, 'l': 3.2, 'm': 9.6, 'n': 5.55557, 'o': 5.8, 'p': 5.55557, 'q': 5.27779, 'r': 3.91667, 's': 3.94444, 't': 4.5, 'u': 5.55557, 'v': 5.2778, 'w': 7.22223, 'x': 5.2778, 'y': 5.2778, 'z': 4.44444, '{': 5.8, '|': 3.3, '}': 5.8, '~': 6.5}
    space_per_row = 160 # Number of LaTeX units of horizontal space available
    chars_per_row = (table_cols + 16)-1 # Save one space for -
    num_rows = 0
    table = list(f"""
+----------------{'-' * table_cols}+----------------{'-' * table_cols}+
| Sample Input {casenum} {' ' * (table_cols-casenum_len)}| Sample Output {casenum}{' ' * (table_cols-casenum_len)}|
+================{'=' * table_cols}+================{'=' * table_cols}+
""")
    base_table_offset = len(table)
    def insert_into_table(offset, text):
        nonlocal num_rows, table
        curr_row = -1
        for line in text.split("\n"):
            while len(line):
                curr_row += 1
                if curr_row >= num_rows:
                    num_rows+=1
                    table += list(row)
                    table += list(row)

                # Add stuff to write to this line while it fits
                curr_vspace = 0
                curr_line = ""
                # Must fit in both Markdown table and LaTeX table
                while len(line) and \
                    len(curr_line)+1<chars_per_row and \
                    curr_vspace + ascii_char_widths[line[0]] < space_per_row:

                    curr_vspace += ascii_char_widths[line[0]]
                    curr_line += line[0]
                    line = line[1:]

                if len(line):
                    curr_line += "-"

                base = 0
                for c in curr_line:
                    ind = base_table_offset+2*curr_row* len(row)+base + offset+1
                    num_c = len(escape_latex_char(c))
                    table[ind:ind+num_c] = escape_latex_char(c)
                    base += num_c
    insert_into_table(1, sample_input)
    insert_into_table(len(f"+================{'=' * table_cols}+"), sample_output)
    table = "".join(table)
    table += f"+----------------{'-' * table_cols}+----------------{'-' * table_cols}+\n"
    return table


def format_interactive_sample(sample_root: str, sample: str, casenum: int, to_pdf: bool) -> str:
    """

    Args:
        sample_root: root of the sample folder
        sample: file name of the sample
        casenum: which sample is this? (1, 2, 3...)
        to_pdf: do we target pdf or html output

    Returns:
        str: the sample, ready to be pasted into a markdown doc and fed to pandoc
    """
    if to_pdf:
        line = r"""\begin{tabular}{p{0.3\textwidth} p{0.5\textwidth} p{0.0\textwidth}}
\textbf{Read} & \textbf{Sample Interaction %i} & \textbf{Write} \\
\end{tabular}""" % casenum
    else:
        line = f"""
            <table class="sample" summary="sample data">
                <tr>
                    <th style="text-align:left; width:33%;">Read</th>
                    <th style="text-align:center; width:33%;">Sample Interaction {casenum}</th>
                    <th style="text-align:right; width:33%;">Write</th>
                </tr>
            </table>"""

    with open(os.path.join(sample_root, sample), "r", encoding="utf-8") as infile:
        sample_interaction = infile.readlines()
    lines = []
    for interaction in sample_interaction:
        data = html.escape(interaction[1:])
        if to_pdf:
            if interaction[0] == '>':
                left = True
            elif interaction[0] == '<':
                left = False
            else:
                left = True
                print(f"Warning: Interaction had unknown prefix {interaction[0]}")
            lines.append(r"""
                            \begin{table}[H]
                            %(justify)s\begin{tabular}{|p{0.6\textwidth}|}
                                \hline
                                %(text)s \\
                                \hline
                            \end{tabular}
                        \end{table}""" % {"justify": "" if left else "\\hspace*{\\fill}\n",
                                            "text": html.escape(data)})
        else:
            line_type = ""
            if interaction[0] == '>':
                line_type = "sampleinteractionwrite"
            elif interaction[0] == '<':
                line_type = "sampleinteractionread"
            else:
                print(f"Warning: Interaction had unknown prefix {interaction[0]}")
            lines.append(f"""<div class="{line_type}"><pre>{html.escape(data)}</pre></div>""")

    if to_pdf:
        return line + '\\vspace{-15pt}'.join(lines)

    return line + ''.join(lines)
