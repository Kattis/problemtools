from pathlib import Path

import pytest

from problemtools.statement_util import find_footnotes
from tests.test_xss import render, renderpdf

# TODO: add when guess is updated to 2023-07
# def test_pdf_render():
#     with tempfile.TemporaryDirectory() as temp_dir:
#         problem_path = Path(__file__).parent / '..' / 'examples' / 'guess'
#         args, _unknown = problem2pdf.get_parser().parse_known_args(
#                 ['--problem', str(problem_path.resolve()), '-l', 'sv', '--dest-dir', str(temp_dir)]
#             )
#         problem2pdf.convert(args)


def test_sample_escaping(diag):
    problem_path = Path(__file__).parent / 'problems' / 'specialcharacterssample'
    html = render(problem_path, diag)
    all_printable = r"""0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ!"#$%&'()*+,-./:;<=>?@[\]^_`{|}~"""
    # We escape &, < and >
    all_printable = all_printable.replace('&', '&amp;')
    all_printable = all_printable.replace('<', '&lt;')
    all_printable = all_printable.replace('>', '&gt;')
    assert all_printable in html


def test_footnotes(diag):
    # We always want footnotes to be at the bottom
    # When we insert samples, we need to insert them right above the first footnote
    # To do this, we search for a string (very fragile)
    problem_path = Path(__file__).parent / 'problems' / 'footnote'
    html = render(problem_path, diag)
    assert find_footnotes(html) is not None

    problem_path = Path(__file__).parent / 'problems' / 'twofootnotes'
    html = render(problem_path, diag)
    assert find_footnotes(html) is not None


def test_footnotes_href(diag):
    # We use allowlist-based id values for footnotes. Ensure they have not changed
    problem_path = Path(__file__).parent / 'problems' / 'footnote'
    html = render(problem_path, diag)
    assert 'fn1' in html and 'fnref1' in html


def test_invalid_image_throws(diag):
    # If images can point to img that doesn't exist, it's arbitrary web request
    for problem in ('imgrequest', 'imgrequest2'):
        problem_path = Path(__file__).parent / 'problems' / problem
        with pytest.raises(ValueError):
            render(problem_path, diag)

    # Pandoc won't make a web request for imgrequest2
    with pytest.raises(ValueError):
        renderpdf(Path(__file__).parent / 'problems' / 'imgrequest')
