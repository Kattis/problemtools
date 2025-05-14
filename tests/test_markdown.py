from pathlib import Path
from tests.test_xss import render, renderpdf
from problemtools.statement_util import find_footnotes
import pytest


def test_sample_escaping():
    problem_path = Path(__file__).parent / 'problems' / 'specialcharacterssample'
    html = render(problem_path)
    all_printable = r"""0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ!"#$%&'()*+,-./:;<=>?@[\]^_`{|}~"""
    # We escape &, < and >
    all_printable = all_printable.replace('&', '&amp;')
    all_printable = all_printable.replace('<', '&lt;')
    all_printable = all_printable.replace('>', '&gt;')
    assert all_printable in html


def test_footnotes():
    # We always want footnotes to be at the bottom
    # When we insert samples, we need to insert them right above the first footnote
    # To do this, we search for a string (very fragile)
    problem_path = Path(__file__).parent / 'problems' / 'footnote'
    html = render(problem_path)
    assert find_footnotes(html) is not None

    problem_path = Path(__file__).parent / 'problems' / 'twofootnotes'
    html = render(problem_path)
    assert find_footnotes(html) is not None


def test_footnotes_href():
    # We use allowlist-based id values for footnotes. Ensure they have not changed
    problem_path = Path(__file__).parent / 'problems' / 'footnote'
    html = render(problem_path)
    assert 'fn1' in html and 'fnref1' in html


def test_invalid_image_throws():
    # If images can point to img that doesn't exist, it's arbitrary web request
    for problem in ('imgrequest', 'imgrequest2'):
        problem_path = Path(__file__).parent / 'problems' / problem
        with pytest.raises(ValueError):
            render(problem_path)

    # Pandoc won't make a web request for imgrequest2
    with pytest.raises(ValueError):
        renderpdf(Path(__file__).parent / 'problems' / 'imgrequest')
