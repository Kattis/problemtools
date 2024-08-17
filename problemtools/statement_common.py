import os
from typing import Optional
import html

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
        print("Please add problem name to problem.yaml when using markdown")
        return None
    names = config.get("name")
    # If there is only one language, per the spec that is the one we want
    if len(names) == 1:
        return next(iter(names.values()))

    if language not in names:
        raise Exception(f"No problem name defined for language {language or 'en'}")
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

