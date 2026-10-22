from pathlib import Path

from problemtools.globs import Glob
from problemtools.model import SubmissionsEntry, SubmissionsPolicy
from problemtools.model.paths import relpath

ACCEPTED = SubmissionsEntry(glob=Glob('accepted'))
ACCEPTED_PY = SubmissionsEntry(glob=Glob('accepted/*.py'))
SOL = SubmissionsEntry(glob=Glob('*/sol.{py,cc}'))
POLICY = SubmissionsPolicy(entries=[ACCEPTED, ACCEPTED_PY, SOL])


def entries_for(path: str) -> list[SubmissionsEntry]:
    return POLICY.entries_for(relpath(Path(path)))


def test_entries_for() -> None:
    assert entries_for('accepted/sol.py') == [ACCEPTED, ACCEPTED_PY, SOL]
    assert entries_for('accepted/sol.cc') == [ACCEPTED, SOL]
    assert entries_for('accepted/other.java') == [ACCEPTED]
    assert entries_for('wrong_answer/sol.py') == [SOL]
    assert entries_for('accepted_slow/other.py') == []
