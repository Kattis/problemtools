from pathlib import Path
from problemtools.tests.test_xss import render

def test_sample_escaping():
    problem_path = Path(__file__).parent / "problems" / "specialcharacterssample"
    html = render(problem_path)
    all_printable = r"0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ!"#$%&'()*+,-./:;<=>?@[\]^_`{|}~"
    assert all_printable in html
