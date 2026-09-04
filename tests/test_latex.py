import re
import tempfile
from pathlib import Path

from problemtools import problem2html, problem2pdf
from problemtools.diagnostics import Diagnostics
from tests.conftest import example_directory


def test_pdf_render_verifyproblem() -> None:
    # Same options as in verifyproblem
    options = problem2pdf.get_parser().parse_args([''])
    problem_path = example_directory('guess')
    options.problem = str(problem_path)
    options.language = 'en'
    options.nopdf = True
    options.quiet = True
    if not problem2pdf.convert(options):
        assert False, 'PDF conversion failed'


def test_pdf_render_problem2pdf() -> None:
    # Same options as typical problem2pdf usage
    with tempfile.TemporaryDirectory() as temp_dir:
        problem_path = example_directory('guess')
        temp_filename = Path(temp_dir) / 'guess.pdf'
        options = problem2pdf.get_parser().parse_args(['-o', str(temp_filename), '-l', 'en', '-q', str(problem_path)])
        if not problem2pdf.convert(options):
            assert False, 'PDF conversion failed'
        with open(temp_filename, 'rb') as temp_file:
            assert temp_file.read(5) == b'%PDF-', 'Output header does not look like a PDF.'


def test_html_render_different(diag: Diagnostics) -> None:
    # Same options as typical problem2html usage
    with tempfile.TemporaryDirectory() as temp_dir:
        problem_path = example_directory('different')
        out_dir = Path(temp_dir) / 'different_html'
        options = problem2html.get_parser().parse_args(['-d', str(out_dir), '-l', 'en', '-q', str(problem_path)])
        problem2html.convert(options, diag)
        with open(out_dir / 'index.html', 'r') as temp_file:
            full_html = temp_file.read()
            assert re.search('<html>', full_html)
            assert re.search('A Different Problem', full_html)
            assert re.search('Problem ID: different', full_html)
            assert re.search('Write a program that computes', full_html)
            assert re.search('71293781758123 72784', full_html)  # part of sample


def test_html_render_guess(diag: Diagnostics) -> None:
    # Same options as typical problem2html usage
    with tempfile.TemporaryDirectory() as temp_dir:
        problem_path = example_directory('guess')
        out_dir = Path(temp_dir) / 'guess_html'
        options = problem2html.get_parser().parse_args(['-d', str(out_dir), '-l', 'en', '-q', str(problem_path)])
        problem2html.convert(options, diag)
        with open(out_dir / 'index.html', 'r') as temp_file:
            full_html = temp_file.read()
            assert re.search('<html>', full_html)
            assert re.search('Guess the Number', full_html)
            assert re.search('Problem ID: guess', full_html)
            assert re.search('After each guess,', full_html)  # Short snippet from statement
            assert re.search('995', full_html)  # part of sample
