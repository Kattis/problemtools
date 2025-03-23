from __future__ import annotations
import re
from .general import is_copyfrom
from typing import Any

class Path:
    INDEXING_REGEX = re.compile(r"^([A-Za-z_0-9\-]+)\[(\d+)\]$")

    @staticmethod
    def parse(path: str) -> Path:
        parts = path.split("/")
        res = []
        for part in parts:
            m = Path.INDEXING_REGEX.match(part)
            if m:
                res.append(m.group(1))
                res.append(int(m.group(2)))
            else:
                res.append(part)
        return Path(*res)

    @staticmethod
    def combine(*parts: str | int | Path) -> Path:
        res = []
        for part in parts:
            if isinstance(part, int):
                res.append(part)
                continue
            if isinstance(part, str):
                part = Path.parse(part)
            res.extend(list(part.path))  # type: ignore
        return Path(*res)

    def __init__(self, *path: str | int) -> None:
        self.path = path

    def index(self, data: dict) -> Any | None:
        rv = data
        for part in self.path:
            if isinstance(part, int):
                if not isinstance(rv, list):
                    return None
                try:
                    rv = rv[part]
                except IndexError:
                    return None
            else:
                if part not in rv:
                    return None
                rv = rv[part]
        return rv

    def spec_path(self) -> Path:
        res = []
        for part in self.path:
            if isinstance(part, str):
                res.append("properties")
                res.append(part)
            elif isinstance(part, int):
                res.append("content")
        return Path(*res)

    def data_paths(self, data: dict) -> list[Path]:
        """Finds all data paths that a spec_path is pointing towards (meaning it will explore all items in lists)"""

        def path_is_not_copyfrom(path: Path) -> bool:
            return not is_copyfrom(path.index(data))

        out = [Path()]
        state = "base"
        for part in self.path:
            if state == "base":
                if part == "properties":
                    state = "object-properties"
                elif part == "content":
                    state = "base"
                    new_out = []
                    for path in out:
                        val = path.index(data) or []
                        if is_copyfrom(val):  # skip copied
                            continue
                        assert isinstance(val, list)
                        new_out.extend(Path.combine(path, i) for i in range(len(val)))
                    out = new_out
                    if len(out) == 0:
                        return []
                else:
                    assert False
            elif state == "object-properties":
                combined_paths = [Path.combine(path, part) for path in out]
                out = [*filter(path_is_not_copyfrom, combined_paths)]
                state = 'base'

        return out

    def up(self, levels=1) -> Path:
        assert levels > 0
        return Path(*self.path[:-levels])

    def last_name(self) -> int | str:
        return self.path[-1]

    def __str__(self) -> str:
        strings = []
        for part in self.path:
            if isinstance(part, int):
                strings[-1] += f"[{part}]"
            else:
                strings.append(part)
        return "/".join(strings)

    def __repr__(self):
        return f"Path({self})"

    def __eq__(self, value):
        return self.path == value.path

    def __hash__(self):
        return hash(self.path)

