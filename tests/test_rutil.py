import os
from pathlib import Path

from problemtools.run.rutil import check_build_dir


def test_regular_files_and_directories_ok(tmp_path: Path) -> None:
    (tmp_path / 'sub').mkdir()
    (tmp_path / 'sub' / 'main.o').write_bytes(b'')
    (tmp_path / 'run').write_bytes(b'')
    assert check_build_dir(tmp_path) is None


def test_symlinks_and_fifos_are_errors(tmp_path: Path) -> None:
    (tmp_path / 'sub').mkdir()
    (tmp_path / 'run').write_bytes(b'')
    (tmp_path / 'sub' / 'link').symlink_to('../run')
    (tmp_path / 'dirlink').symlink_to('sub')
    os.mkfifo(tmp_path / 'pipe')
    errmsg = check_build_dir(tmp_path)
    assert errmsg is not None
    assert errmsg.endswith(f': dirlink, pipe, {Path("sub/link")}')
