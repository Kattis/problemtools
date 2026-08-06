import os
import signal
import textwrap
import time
from pathlib import Path

from problemtools.run.executable import Executable
from problemtools.run import program


def _process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:
        if Path(f'/proc/{pid}/stat').read_text().split()[2] == 'Z':
            return False
    except OSError:
        pass
    return True


def test_run_kills_forked_children_after_time_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(program.limit, 'try_limit', lambda *_args: None)
    child_pid_file = tmp_path / 'child.pid'
    program_path = tmp_path / 'forking-timeout.py'
    program_path.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env python3
            import os
            import signal
            import time

            child_pid = os.fork()
            if child_pid == 0:
                with open({str(child_pid_file)!r}, 'w') as child_pid_output:
                    child_pid_output.write(str(os.getpid()))
                while True:
                    time.sleep(60)

            while not os.path.exists({str(child_pid_file)!r}):
                time.sleep(0.01)
            os.kill(os.getpid(), signal.SIGXCPU)
            """
        )
    )
    program_path.chmod(0o755)

    status, _ = Executable(str(program_path)).run(timelim=1, work_dir=str(tmp_path))

    child_pid = int(child_pid_file.read_text())
    try:
        assert os.WIFSIGNALED(status)
        assert os.WTERMSIG(status) == signal.SIGXCPU
        for _ in range(100):
            if not _process_exists(child_pid):
                break
            time.sleep(0.01)
        assert not _process_exists(child_pid)
    finally:
        if _process_exists(child_pid):
            os.kill(child_pid, signal.SIGKILL)
