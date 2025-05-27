# -*- coding: utf-8 -*-
from pathlib import Path

import pytest

from pydantic import ValidationError
from problemtools import metadata
from problemtools.formatversion import FormatVersion

# A few quick tests of config parsing. pytest structure isn't great here, so code gets repetitive, but I wanted *something* basic in place at least.


def test_parse_empty_legacy():
    m = metadata.parse_metadata(FormatVersion.LEGACY, {})
    # Just check off a few random things
    assert not m.name
    assert not m.source
    assert not m.credits.authors


def test_parse_legacy_with_problem_names():
    m = metadata.parse_metadata(FormatVersion.LEGACY, {}, {'en': 'Hello World!'})
    assert m.name['en'] == 'Hello World!'


def test_parse_empty_2023_fails():
    with pytest.raises(ValidationError):
        metadata.parse_metadata(FormatVersion.V_2023_07, {}, {'en': 'Hello World!'})


@pytest.fixture
def minimal_2023_conf():
    return {
        'problem_format_version': '2023-07-draft',
        'uuid': '46fa942f-44c3-46c0-8ddc-22e02d2e5d2b',
        'name': {'en': 'Hello World!'},
    }


def test_parse_minimal_2023(minimal_2023_conf):
    m = metadata.parse_metadata(FormatVersion.V_2023_07, minimal_2023_conf, {'en': 'Hello World!'})
    assert m.name['en'] == 'Hello World!'
    assert not m.source
    assert not m.credits.authors


def test_parse_typo_fails(minimal_2023_conf):
    c = minimal_2023_conf
    c['limits'] = {'typo': 1}
    with pytest.raises(ValidationError):
        metadata.parse_metadata(FormatVersion.V_2023_07, c, {'en': 'Hello World!'})


def test_parse_single_author_2023(minimal_2023_conf):
    c = minimal_2023_conf
    c['credits'] = ' \t  Authy McAuth \t <authy@mcauth.example> \t\t  '  # Add some extra whitespace to check that we strip
    m = metadata.parse_metadata(FormatVersion.V_2023_07, c, {'en': 'Hello World!'})
    assert len(m.credits.authors) == 1
    assert m.credits.authors[0].name == 'Authy McAuth'
    assert m.credits.authors[0].email == 'authy@mcauth.example'


def test_parse_single_source_2023(minimal_2023_conf):
    c = minimal_2023_conf
    c['source'] = 'NWERC 2024'
    m = metadata.parse_metadata(FormatVersion.V_2023_07, c, {'en': 'Hello World!'})
    assert len(m.source) == 1
    assert m.source[0].name == 'NWERC 2024'
    assert m.source[0].url is None


def test_parse_multi_source(minimal_2023_conf):
    c = minimal_2023_conf
    c['source'] = [
        {'name': 'NWERC 2024', 'url': 'https://2024.nwerc.example/contest'},
        'SWERC 2024',
        {'name': 'SEERC 2024'},
    ]
    m = metadata.parse_metadata(FormatVersion.V_2023_07, c, {'en': 'Hello World!'})
    assert len(m.source) == 3
    assert m.source[0].name == 'NWERC 2024'
    assert m.source[0].url == 'https://2024.nwerc.example/contest'
    assert m.source[1].name == 'SWERC 2024'
    assert m.source[1].url is None
    assert m.source[2].name == 'SEERC 2024'
    assert m.source[2].url is None


def test_parse_complex_type(minimal_2023_conf):
    c = minimal_2023_conf
    c['type'] = ['scoring', 'multi-pass', 'interactive']
    m = metadata.parse_metadata(FormatVersion.V_2023_07, c, {'en': 'Hello World!'})
    assert len(m.type) == 3
    assert metadata.ProblemType.SCORING in m.type
    assert metadata.ProblemType.MULTI_PASS in m.type
    assert metadata.ProblemType.INTERACTIVE in m.type
    assert not m.is_pass_fail()
    assert m.is_scoring()
    assert m.is_interactive()
    assert m.is_multi_pass()
    assert not m.is_submit_answer()


def test_load_hello():
    m, _ = metadata.load_metadata(Path(__file__).parent / 'hello')
    assert m.name['en'] == 'Hello World!'
    assert m.name['sv'] == 'Hej Världen!'
    assert len(m.source) == 1
    assert m.source[0].name == 'Kattis'
    assert m.source[0].url is None
    assert m.license is metadata.License.PUBLIC_DOMAIN
    assert len(m.type) == 1
    assert m.type[0] is metadata.ProblemType.PASS_FAIL
    assert m.is_pass_fail()
    assert not m.is_scoring()
    assert not m.is_interactive()
    assert not m.is_multi_pass()
    assert not m.is_submit_answer()
