from problemtools.config_parser import Path

def test_parse():
    assert Path.parse("a/b/c") == Path("a", "b", "c")
    assert Path.parse("array[0]/key") == Path("array", 0, "key")
    assert Path.parse("nested/list[2]/item") == Path("nested", "list", 2, "item")

def test_combine():
    assert Path.combine("a", "b", "c") == Path("a", "b", "c")
    assert Path.combine("list[1]", "key") == Path("list", 1, "key")
    assert Path.combine(Path("x", "y"), "z") == Path("x", "y", "z")

def test_index():
    data = {"a": {"b": [1, 2, 3]}}
    assert Path("a", "b", 1).index(data) == 2
    assert Path("a", "c").index(data) is None
    assert Path("a", "b", 10).index(data) is None

def test_spec_path():
    assert Path("a", "b", 2).spec_path() == Path("properties", "a", "properties", "b", "content")
    assert Path("x", 3, "y").spec_path() == Path("properties", "x", "content", "properties", "y")

def test_data_paths():
    data = {"list": ["a", "b", "c"]}
    path = Path("properties", "list", "content")
    assert path.data_paths(data) == [Path("list", 0), Path("list", 1), Path("list", 2)]

def test_up():
    assert Path("a", "b", "c").up() == Path("a", "b")
    assert Path("x", "y", "z").up(2) == Path("x")

def test_last_name():
    assert Path("a", "b", "c").last_name() == "c"
    assert Path("list", 3).last_name() == 3

def test_str_repr():
    assert str(Path("a", "b", 2)) == "a/b[2]"
    assert repr(Path("x", "y")) == "Path(x/y)"

def test_equality_hash():
    p1 = Path("a", "b", 1)
    p2 = Path("a", "b", 1)
    p3 = Path("a", "b", 2)
    assert p1 == p2
    assert p1 != p3
    assert hash(p1) == hash(p2)
    assert hash(p1) != hash(p3)
