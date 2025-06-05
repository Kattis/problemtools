from pathlib import Path
import tempfile

from problemtools import problem2pdf


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
