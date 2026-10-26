from pathlib import Path

from problemtools.languages import load_language_config
from problemtools.metadata import load_metadata
from problemtools.model import load_files, load_testdata
from problemtools.model.includes import load_includes
from problemtools.model.submissions import Submission, Submissions, load_submissions

LEGACY = 'name: Test\n'
V_2023_07 = 'problem_format_version: 2023-07-draft\nname: Test\nuuid: 025dfeea-eb85-4532-94d1-3108ec03c80f\n'


def load(
    probdir: Path,
    problem_yaml: str,
    submission_files: list[str],
    submissions_yaml: str | bytes | None = None,
    include_files: list[str] | None = None,
) -> Submissions:
    """Create a problem in `probdir` with the given submission files (relative to submissions/) and
    include files (relative to include/), and load its submissions."""
    (probdir / 'data' / 'secret').mkdir(parents=True)
    (probdir / 'problem.yaml').write_text(problem_yaml)
    (probdir / 'data' / 'secret' / '1.in').write_text('')
    (probdir / 'data' / 'secret' / '1.ans').write_text('')
    paths = [probdir / 'submissions' / name for name in submission_files]
    paths += [probdir / 'include' / name for name in include_files or []]
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('')
    if isinstance(submissions_yaml, bytes):
        (probdir / 'submissions' / 'submissions.yaml').write_bytes(submissions_yaml)
    elif submissions_yaml is not None:
        (probdir / 'submissions' / 'submissions.yaml').write_text(submissions_yaml)

    files = load_files(probdir)
    language_config = load_language_config(probdir.parent)
    metadata = load_metadata(probdir)
    testdata = load_testdata(files, metadata)
    return load_submissions(files, language_config, load_includes(files, language_config), testdata, metadata)


def by_path(submissions: Submissions) -> dict[str, Submission]:
    return {str(sub.path): sub for sub in submissions.submissions}


def test_default_entries_depend_on_format_version(tmp_path: Path) -> None:
    files = ['accepted/a.py', 'brute_force/b.py']
    legacy = by_path(load(tmp_path / 'legacy', LEGACY, files))
    assert legacy['accepted/a.py'].rules
    assert [bound.direction for bound in legacy['accepted/a.py'].time_limit_bounds] == ['lower']
    # brute_force is not a default directory in legacy
    assert legacy['brute_force/b.py'].rules == ()

    new = by_path(load(tmp_path / 'new', V_2023_07, files))
    assert new['accepted/a.py'].rules
    assert new['brute_force/b.py'].rules


def test_submissions_yaml_adds_to_defaults(tmp_path: Path) -> None:
    files = ['accepted/a.py', 'accepted/b.py', 'other/c.py']
    defaults = by_path(load(tmp_path / 'defaults', V_2023_07, files))
    yaml = 'accepted/a.py:\n  secret:\n    required: [AC]\nother:\n  permitted: [AC]\n  use_for_time_limit: upper\n'
    loaded = load(tmp_path / 'yaml', V_2023_07, files, yaml)
    assert loaded.policy.parse_errors == []
    subs = by_path(loaded)
    assert len(subs['accepted/a.py'].rules) == len(defaults['accepted/a.py'].rules) + 1
    assert subs['accepted/b.py'].rules == defaults['accepted/b.py'].rules
    assert len(subs['other/c.py'].rules) == 1
    assert [bound.direction for bound in subs['other/c.py'].time_limit_bounds] == ['upper']


def test_invalid_submissions_yaml(tmp_path: Path) -> None:
    loaded = load(tmp_path, V_2023_07, ['accepted/a.py'], 'accepted: [')
    assert len(loaded.policy.parse_errors) == 1
    # The defaults still apply
    assert by_path(loaded)['accepted/a.py'].rules


def test_non_utf8_submissions_yaml(tmp_path: Path) -> None:
    loaded = load(tmp_path, V_2023_07, ['accepted/a.py'], b'accepted:\n  author: \xff\n')
    assert len(loaded.policy.parse_errors) == 1
    assert all(entry.is_default for entry in loaded.policy.entries)


def test_no_submissions_yaml(tmp_path: Path) -> None:
    loaded = load(tmp_path, V_2023_07, ['accepted/a.py'])
    assert loaded.policy.parse_errors == []
    assert all(entry.is_default for entry in loaded.policy.entries)


def test_language_is_detected(tmp_path: Path) -> None:
    subs = by_path(load(tmp_path, V_2023_07, ['accepted/a.py', 'accepted/a.cpp', 'accepted/notes.txt']))
    assert subs['accepted/a.py'].program.language.lang_id == 'python3'
    assert subs['accepted/a.cpp'].program.language.lang_id == 'cpp'
    # Files in no known language aren't submissions
    assert 'accepted/notes.txt' not in subs


def test_language_from_submissions_yaml(tmp_path: Path) -> None:
    files = ['accepted/a.py', 'accepted/sol.txt']
    yaml = 'accepted/a.py:\n  language: python2\naccepted/sol.txt:\n  language: python3\n'
    subs = by_path(load(tmp_path, V_2023_07, files, yaml))
    assert subs['accepted/a.py'].program.language.lang_id == 'python2'
    # A stated language makes a submission of a file we wouldn't detect
    assert subs['accepted/sol.txt'].program.language.lang_id == 'python3'


def test_unknown_language(tmp_path: Path) -> None:
    loaded = load(tmp_path, V_2023_07, ['accepted/a.py'], 'accepted/a.py:\n  language: nosuchlanguage\n')
    assert len(loaded.policy.parse_errors) == 1
    # The language is dropped, so it's detected as usual
    assert by_path(loaded)['accepted/a.py'].program.language.lang_id == 'python3'


def test_entrypoint_from_submissions_yaml(tmp_path: Path) -> None:
    yaml = 'accepted:\n  entrypoint: main.py\n'
    subs = by_path(load(tmp_path, V_2023_07, ['accepted/a.py', 'wrong_answer/b.py'], yaml))
    assert subs['accepted/a.py'].program.entrypoint_override == 'main.py'
    assert subs['wrong_answer/b.py'].program.entrypoint_override is None
