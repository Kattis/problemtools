import os
from pathlib import Path
from problemtools import problem2html
from problemtools import problem2pdf
import tempfile

def render(problem_path):
    with tempfile.TemporaryDirectory() as temp_dir:
        args, _unknown = problem2html.get_parser().parse_known_args(['--problem', str(problem_path.resolve()), '--dest-dir', str(temp_dir)])
        problem2html.convert(args)
        with open(f"{temp_dir}/index.html", "r") as f:
            html = f.read()
            return html

def renderpdf(problem_path):
    with tempfile.TemporaryDirectory() as temp_dir:
        outpath = os.path.join(temp_dir, "out.pdf")
        args, _unknown = problem2pdf.get_parser().parse_known_args(['--problem', str(problem_path.resolve()), '--o', outpath])
        problem2pdf.convert(args)

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
