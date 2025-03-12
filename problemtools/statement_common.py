import os
from typing import Optional, List
import html
import tempfile
import subprocess

from . import verifyproblem

SUPPORTED_EXTENSIONS = ("tex", "md")

def find_statement(problem_root: str, extension: str, language: Optional[str]) -> Optional[str]:
    """Finds the "best" statement for given language and extension"""
    if language is None:
        statement_path = os.path.join(problem_root, f"problem_statement/problem.en.{extension}")
        if os.path.isfile(statement_path):
            return statement_path
        statement_path = os.path.join(problem_root, f"problem_statement/problem.{extension}")
        if os.path.isfile(statement_path):
            return statement_path
        return None
    statement_path = os.path.join(problem_root, f"problem_statement/problem.{language}.{extension}")
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
        raise Exception(f"""Found more than one type of statement ({' and '.join(extensions)})
                        for language {language or 'en'}""")
    if len(extensions) == 1:
        return extensions[0]
    raise Exception(f"No statement found for language {language or 'en'}")



def get_problem_name(problem: str, language: Optional[str]) -> Optional[str]:
    """Load problem.yaml to get problem name"""
    if language is None:
        language = "en"
    with verifyproblem.Problem(problem) as prob:
        config = verifyproblem.ProblemConfig(prob)
    if not config.check(None):
        raise Exception("Invalid problem.yaml")
    names = config.get("name")
    # If there is only one language, per the spec that is the one we want
    if len(names) == 1:
        return next(iter(names.values()))

    if language not in names:
        raise Exception(f"No problem name defined for language {language or 'en'}")
    return names[language]


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

    sample = """
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

    if to_pdf:
        # If pdf, convert to markdown
        with tempfile.NamedTemporaryFile(mode='w', suffix=".html") as temp_file:
            temp_file.write(sample)
            temp_file.flush()
            command = ["pandoc", temp_file.name, "-t" , "markdown", "-f", "markdown-raw_html"]
            return subprocess.run(command, capture_output=True, text=True,
                                  shell=False, check=True).stdout
    else:
        return sample


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
        data = interaction[1:]
        if to_pdf:
            if interaction[0] == '>':
                left = True
            elif interaction[0] == '<':
                left = False
            else:
                print(f"Warning: Interaction had unknown prefix {interaction[0]}")
            lines.append(r"""
                            \begin{table}[H]
                            %(justify)s\begin{tabular}{|p{0.6\textwidth}|}
                                \hline
                                %(text)s \\
                                \hline
                            \end{tabular}
                        \end{table}""" % {"justify": "" if left else "\\hspace*{\\fill}\n",
                                            "text": data})
        else:
            line_type = ""
            if interaction[0] == '>':
                line_type = "sampleinteractionwrite"
            elif interaction[0] == '<':
                line_type = "sampleinteractionread"
            else:
                print(f"Warning: Interaction had unknown prefix {interaction[0]}")
            lines.append(f"""<div class="{line_type}"><pre>{data}</pre></div>""")

    if to_pdf:
        return line + '\\vspace{-15pt}'.join(lines)
    else:
        return line + ''.join(lines)
