from pathlib import Path
import re
import tempfile

from problemtools import problem2html, problem2pdf


def test_pdf_render_verifyproblem():
    # Same options as in verifyproblem
    options = problem2pdf.get_parser().parse_args([''])
    problem_path = Path(__file__).parent / '..' / 'examples' / 'guess'
    options.problem = str(problem_path.resolve())
    options.language = 'en'
    options.nopdf = True
    options.quiet = True
    if not problem2pdf.convert(options):
        assert False, 'PDF conversion failed'


def test_pdf_render_problem2pdf():
    # Same options as typical problem2pdf usage
    with tempfile.TemporaryDirectory() as temp_dir:
        problem_path = Path(__file__).parent / '..' / 'examples' / 'guess'
        temp_filename = Path(temp_dir) / 'guess.pdf'
        options = problem2pdf.get_parser().parse_args(['-o', str(temp_filename), '-l', 'en', '-q', str(problem_path.resolve())])
        if not problem2pdf.convert(options):
            assert False, 'PDF conversion failed'
        with open(temp_filename, 'rb') as temp_file:
            assert temp_file.read(5) == b'%PDF-', 'Output header does not look like a PDF.'


def test_html_render_different():
    # Same options as typical problem2html usage
    with tempfile.TemporaryDirectory() as temp_dir:
        problem_path = Path(__file__).parent / '..' / 'examples' / 'different'
        temp_dir = Path(temp_dir) / 'different_html'
        options = problem2html.get_parser().parse_args(['-d', str(temp_dir), '-l', 'en', '-q', str(problem_path.resolve())])
        problem2html.convert(options)
        with open(temp_dir / 'index.html', 'r') as temp_file:
            full_html = temp_file.read()
            assert re.search('<html>', full_html)
            assert re.search('A Different Problem', full_html)
            assert re.search('Problem ID: different', full_html)
            assert re.search('Write a program that computes', full_html)
            assert re.search('71293781758123 72784', full_html)  # part of sample


def test_html_render_guess():
    # Same options as typical problem2html usage
    with tempfile.TemporaryDirectory() as temp_dir:
        problem_path = Path(__file__).parent / '..' / 'examples' / 'guess'
        temp_dir = Path(temp_dir) / 'guess_html'
        options = problem2html.get_parser().parse_args(['-d', str(temp_dir), '-l', 'en', '-q', str(problem_path.resolve())])
        problem2html.convert(options)
        with open(temp_dir / 'index.html', 'r') as temp_file:
            full_html = temp_file.read()
            assert re.search('<html>', full_html)
            assert re.search('Guess the Number', full_html)
            assert re.search('Problem ID: guess', full_html)
            assert re.search('After each guess,', full_html)  # Short snippet from statement
            assert re.search('995', full_html)  # part of sample
