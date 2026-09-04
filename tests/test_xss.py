import os
import tempfile
from pathlib import Path

from problemtools import problem2html, problem2pdf
from problemtools.diagnostics import Diagnostics
from tests.conftest import datadir


def render(problem_path: Path, diag: Diagnostics) -> str:
    with tempfile.TemporaryDirectory() as temp_dir:
        args, _unknown = problem2html.get_parser().parse_known_args(
            ['--problem', str(problem_path.resolve()), '--dest-dir', str(temp_dir)]
        )
        problem2html.convert(args, diag)
        with open(f'{temp_dir}/index.html', 'r') as f:
            html = f.read()
            return html


def renderpdf(problem_path: Path) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        outpath = os.path.join(temp_dir, 'out.pdf')
        args, _unknown = problem2pdf.get_parser().parse_known_args(['--problem', str(problem_path.resolve()), '--o', outpath])
        problem2pdf.convert(args)


def test_no_xss_statement(diag: Diagnostics) -> None:
    problem_path = datadir() / 'problems' / 'statementxss'
    html = render(problem_path, diag)
    assert 'alert' not in html


def test_no_xss_problemname(diag: Diagnostics) -> None:
    problem_path = datadir() / 'problems' / 'problemnamexss'
    html = render(problem_path, diag)
    assert '<script>' not in html


def test_no_xss_sample(diag: Diagnostics) -> None:
    problem_path = datadir() / 'problems' / 'samplexss'
    html = render(problem_path, diag)
    assert '<script>' not in html
