import os
from pathlib import Path
from problemtools.problem2html import convert, get_parser
import tempfile

def render(problem_path):
    with tempfile.TemporaryDirectory() as temp_dir:
        args, _unknown = get_parser().parse_known_args(['--problem', str(problem_path.resolve()), '--dest-dir', str(temp_dir)])
        convert(args)
        with open(f"{temp_dir}/index.html", "r") as f:
            html = f.read()
            return html

def test_no_xss_statement():
    problem_path = Path(__file__).parent / "problems" / "statementxss"
    html = render(problem_path)
    assert "alert" not in html

def test_no_xss_problemname():
    problem_path = Path(__file__).parent / "problems" / "problemnamexss"
    html = render(problem_path)
    assert "<script>" not in html
   
def test_no_xss_sample():
    problem_path = Path(__file__).parent / "problems" / "samplexss"
    html = render(problem_path)
    assert "<script>" not in html

# TODO: I can't even pass the path properly kinda??
# def test_no_xss_problem_id():
#     problem_path = Path(__file__).parent / "problems" / '<img src=x onerror=alert(1)>'
#     html = render(problem_path)
#     assert "alert" not in html

