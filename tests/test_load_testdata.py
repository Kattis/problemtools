from pathlib import Path

from problemtools.metadata import load_metadata
from problemtools.model import load_files, load_testdata
from problemtools.model.testdata import TestCase, TestDataGroup

# Not test classes -- just named that way by the model. Tell pytest not to collect them.
TestCase.__test__ = False  # type: ignore[attr-defined]
TestDataGroup.__test__ = False  # type: ignore[attr-defined]


def test_items_are_ordered_by_base_name(tmp_path: Path) -> None:
    (tmp_path / 'problem.yaml').write_text('name: Test\n')
    secret = tmp_path / 'data' / 'secret'
    for name in ['foo', 'foo-bar', 'foo-baz/1', 'foo.a/1']:
        (secret / name).parent.mkdir(parents=True, exist_ok=True)
        (secret / f'{name}.in').write_text('')
        (secret / f'{name}.ans').write_text('')

    testdata = load_testdata(load_files(tmp_path), load_metadata(tmp_path))

    secret_group = testdata.items[0]
    assert isinstance(secret_group, TestDataGroup)
    assert [str(item.path) for item in secret_group.items] == [
        'secret/foo',
        'secret/foo-bar',
        'secret/foo-baz',
        'secret/foo.a',
    ]
    assert [str(case.path) for case in testdata.get_all_testcases()] == [
        'secret/foo',
        'secret/foo-bar',
        'secret/foo-baz/1',
        'secret/foo.a/1',
    ]
