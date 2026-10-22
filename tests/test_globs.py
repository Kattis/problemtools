from pathlib import Path

import pytest

from problemtools.globs import Glob


@pytest.mark.parametrize(
    'pattern, path, expected',
    [
        ('accepted', 'accepted', True),
        ('accepted', 'accepted/sol.py', False),
        ('accepted', 'accept', False),
        ('accepted/sol.py', 'accepted/sol.py', True),
        # * matches within a component, including the empty string, but never /
        ('accepted/*', 'accepted/sol.py', True),
        ('accepted/*', 'accepted/sol', True),
        ('accepted/*', 'accepted', False),
        ('accepted/*', 'accepted/sol/main.py', False),
        ('*', 'accepted', True),
        ('*', 'accepted/sol.py', False),
        ('*.py', 'sol.py', True),
        ('*.py', '.py', True),
        ('*.py', 'sol.pyc', False),
        ('secret/*-easy', 'secret/1-easy', True),
        ('secret/*-easy', 'secret/1-hard', False),
        ('*/sol.py', 'accepted/sol.py', True),
        ('s*t/*', 'secret/a', True),
        # Braces
        ('{simple,complex}.py', 'simple.py', True),
        ('{simple,complex}.py', 'complex.py', True),
        ('{simple,complex}.py', 'other.py', False),
        ('{simple,complex}.py', '{simple,complex}.py', False),
        ('author.{py,cpp}', 'author.cpp', True),
        ('author.{py,cpp}', 'author.java', False),
        ('{a,b{c,d}}', 'a', True),
        ('{a,b{c,d}}', 'bd', True),
        ('{a,b{c,d}}', 'b', False),
        ('{a,}x', 'x', True),
        ('{a,}x', 'ax', True),
        ('{a,b/c}', 'b/c', True),
        ('{a,*}', 'anything', True),
        ('{a,*}', 'any/thing', False),
        # Outside braces, commas are literal
        ('a,b', 'a,b', True),
        ('a,b', 'a', False),
        # Regex metacharacters are literals
        ('a.py', 'aXpy', False),
        ('a+b(c)?$^|', 'a+b(c)?$^|', True),
        ('a?', 'ab', False),
        # Case sensitive
        ('Accepted', 'accepted', False),
        # The empty pattern only matches the empty path
        ('', '.', True),
        ('', '', True),
        ('', 'secret', False),
        ('*', '.', False),
        ('{a,}', '.', False),
    ],
)
def test_matches(pattern: str, path: str, expected: bool) -> None:
    assert Glob(pattern).matches(Path(path)) == expected


@pytest.mark.parametrize(
    'pattern, path, expected',
    [
        ('secret', 'secret', True),
        ('secret', 'secret/group1', True),
        ('secret', 'secret/group1/1', True),
        ('secret', 'secretive', False),
        ('secret', 'secretive/1', False),
        ('secret', 'sample/1', False),
        ('secret/group1', 'secret', False),
        ('secret/*', 'secret/group1/1', True),
        ('secret/*', 'secret', False),
        ('secret/*-easy', 'secret/1-easy', True),
        ('secret/*-easy', 'secret/1-easy/x', True),
        ('secret/*-easy', 'secret/1-hard', False),
        ('{sample,secret/group1}', 'sample/1', True),
        ('{sample,secret/group1}', 'secret/group1/1', True),
        ('{sample,secret/group1}', 'secret/group2/1', False),
        ('accepted/*', 'accepted/sol/main.py', True),
        # The empty pattern covers everything
        ('', '.', True),
        ('', 'secret', True),
        ('', 'secret/group1/1', True),
        ('*', '.', False),
    ],
)
def test_covers(pattern: str, path: str, expected: bool) -> None:
    assert Glob(pattern).covers(Path(path)) == expected


@pytest.mark.parametrize(
    'pattern, message',
    [
        ('**', r"'\*\*' is not supported"),
        ('secret/**/1', r"'\*\*' is not supported"),
        ('***', r"'\*\*' is not supported"),
        ('[ab].py', 'character classes'),
        ('a].py', 'character classes'),
        ('/accepted', 'empty path component'),
        ('accepted/', 'empty path component'),
        ('accepted//sol.py', 'empty path component'),
        ('/', 'empty path component'),
        ('{a,b', "unmatched '{'"),
        ('{a,{b}', "unmatched '{'"),
        ('a,b}', "unmatched '}'"),
        ('}{', "unmatched '}'"),
    ],
)
def test_invalid(pattern: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        Glob(pattern)


def test_equality_and_str() -> None:
    assert Glob('accepted/*') == Glob('accepted/*')
    assert Glob('accepted/*') != Glob('accepted')
    assert hash(Glob('accepted/*')) == hash(Glob('accepted/*'))
    assert str(Glob('{a,b}.py')) == '{a,b}.py'
