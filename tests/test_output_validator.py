import random
import pathlib
import string
import tempfile

from problemtools.judge.validate import _get_feedback


def test_output_validator_feedback():
    r = random.Random(0)
    with tempfile.TemporaryDirectory() as directory:
        feedback = pathlib.Path(directory) / 'feedback.txt'
        text = ''.join(r.choices(string.printable))
        feedback.write_text(text)
        data = _get_feedback(pathlib.Path(directory))
        assert data is not None and text in data


def test_output_validator_feedback_non_unicode():
    r = random.Random(0)
    with tempfile.TemporaryDirectory() as directory:
        feedback = pathlib.Path(directory) / 'feedback.txt'
        feedback.write_bytes(r.randbytes(1024))
        # Just test that this does not throw an error
        _get_feedback(pathlib.Path(directory))
