from problemtools.config_parser.matcher import AlternativeMatch, BoolMatch, StringMatch, IntMatch, FloatMatch
from problemtools.config_parser.general import SpecificationError
from itertools import chain

import pytest

def test_bool_match():
    for matcher in (BoolMatch(True), BoolMatch("true"), BoolMatch("tRuE")):
        assert matcher.check(True) is True
        assert matcher.check(False) is False
        assert str(matcher) == "True"
    for matcher in (BoolMatch(False), BoolMatch("false"), BoolMatch("FaLsE")):
        assert matcher.check(True) is False
        assert matcher.check(False) is True
        assert str(matcher) == "False"   
    for junk in ("asdsad", 123, "foobar", 0.0):
        with pytest.raises(SpecificationError):
            BoolMatch(junk) 

def test_string_match():
    matcher = StringMatch("f[ou][ou]")
    for s in ("foo", "fuu", "fou"):
        assert matcher.check(s) is True
    for s in ("bar", "fooo", "fo", "bfoo"):
        assert matcher.check(s) is False
    for s in ("xyz", "[aA][bB]", r"#([a-fA-F0-9]{3}|[a-fA-F0-9]{6})\b"):
        assert str(StringMatch(s)) == s
    for junk in (1.2, 123, True):
        assert matcher.check(junk) is False
        with pytest.raises(SpecificationError):
            StringMatch(junk) 

def test_int_match():
    matcher = IntMatch("0:")
    for i in range(-10, 0):
        assert matcher.check(i) is False
    for i in range(0, 10):
        assert matcher.check(i) is True
    assert str(matcher) == "0:"
        
    matcher = IntMatch(":13")
    for i in range(3, 14):
        assert matcher.check(i) is True
    for i in range(14, 24):
        assert matcher.check(i) is False
    assert str(matcher) == ":13"
        
    matcher = IntMatch("10:20")
    for i in range(10, 21):
        assert matcher.check(i) is True
    for i in chain(range(0, 10), range(21, 30)):
        assert matcher.check(i) is False
    assert str(matcher) == "10:20"
        
    matcher = IntMatch(":")
    for i in (-100, 1000000, 23, 101010, 0):
        assert matcher.check(i) is True
    for i in ("foo", 0.0, True, 3.5):
        assert matcher.check(i) is False
    assert str(matcher) == ":"
    
    for v in (13, "13"):
        matcher = IntMatch(v)
        for i in chain(range(5, 13), range(14, 20)):
            assert matcher.check(i) is False
        assert matcher.check(13) is True
        assert str(matcher) == "13"
    
    for junk in (1.2, "foo", True, "13:13:13"):
        assert matcher.check(junk) is False
        with pytest.raises(SpecificationError):
            IntMatch(junk)
    

def test_float_match():
    for v in ("0.0:", "0:"):
        matcher = FloatMatch(v)
        for i in range(-10, 0):
            assert matcher.check(i * 0.5) is False
        for i in range(1, 10):
            assert matcher.check(i * 0.5) is True
    
    for v in (":13", ":13.0", ":1.3e1"):
        matcher = FloatMatch(":13")
        for i in range(10, 25):
            assert matcher.check(i * 0.5) is True
        for i in range(27, 30):
            assert matcher.check(i * 0.5) is False
        
    matcher = FloatMatch("1.0:2.0")
    for i in range(11, 20):
        assert matcher.check(i * 0.1) is True
    for i in chain(range(0, 10), range(21, 30)):
        assert matcher.check(i * 0.1) is False
        
    matcher = FloatMatch(":")
    for i in (-100, 1000000, 23, 101010, 0):
        assert matcher.check(i * 1.0) is True
    for i in ("foo", 0, True, 35):
        assert matcher.check(i) is False
    
    for junk in (1.2, "foo", True, 13, "13", "13:13:13"):
        print(junk)
        with pytest.raises(SpecificationError):
            FloatMatch(junk)

def test_match_factory():
    for junk in (1.2, "foo", True, 13, "13", "13:13:13"):
        with pytest.raises(SpecificationError):
            AlternativeMatch.get_matcher(junk, "123")
    assert type(AlternativeMatch.get_matcher("string", "abc123")) is StringMatch
    assert type(AlternativeMatch.get_matcher("float", "0.0:1.0")) is FloatMatch
    assert type(AlternativeMatch.get_matcher("int", "13:25")) is IntMatch
    assert type(AlternativeMatch.get_matcher("bool", "True")) is BoolMatch