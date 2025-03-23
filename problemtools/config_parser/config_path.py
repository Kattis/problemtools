from __future__ import annotations
import re
from typing import Any

class PathError(Exception):
    pass

def is_copyfrom(val: Any) -> bool:
    return isinstance(val, tuple) and val[0] == "copy-from"

class Path:
    """Class for indexing nested dictionaries, that may also contain lists.
    The text version separates keys by "/".
    To index a list, use list[index]. An example of a string path is "/foo/bar[3]/baz",
    which means indexing as dict["foo"]["bar"][3]["baz"].
    """
    DICT_MATCH = re.compile(r"[A-Za-z_\-][A-Za-z_\d\-]*")
    LIST_MATCH = re.compile(r"\d+")
    
    @staticmethod
    def parse(path: str) -> Path:
        def parse_part(part: str):
            if Path.DICT_MATCH.match(part):
                return part
            elif Path.LIST_MATCH.match(part):
                return int(part)
            raise PathError(f'Could not parse path: "{path}"')
        return Path(*(parse_part(p) for p in re.sub(r'\[(\d+)\]', r'/\1', path).split("/")))

    @staticmethod
    def combine(*parts: str | int | Path) -> Path:
        """Fuse multiple paths together into one path"""
        res = []
        for part in parts:
            if isinstance(part, int):
                res.append(part)
            elif isinstance(part, str):
                res.extend(Path.parse(part).path)
            elif isinstance(part, Path):
                res.extend(list(part.path))
            else:
                raise PathError(f'Unknown type in parts: {type(part)}')
        return Path(*res)

    def __init__(self, *path: str | int) -> None:
        for p in path:
            if isinstance(p, int):
                if p < 0:
                    raise PathError('Indexes should be positive')
            elif isinstance(p, str):
                if not Path.DICT_MATCH.match(p):
                    raise PathError(f'Invalid dictionary-key: "{p}"')
            else:
                raise PathError(f'Invalid type for path: "{type(p)}"')
        self.path = path

    def index(self, data: dict, fallback: Any = ...) -> Any:
        rv = data
        for part in self.path:
            if isinstance(part, int):
                if not isinstance(rv, list):
                    if fallback == ...:
                        raise PathError(f'Tried to index non-list type with an integer ({self.path})')
                    return fallback
                try:
                    rv = rv[part]
                except IndexError:
                    if fallback == ...:
                        raise PathError(f'Tried to index list out of range ({self.path})')
                    return fallback
            else:
                if part not in rv:
                    if fallback == ...:
                        raise PathError(f'Tried to access invalid key "{part}" ({self.path})')
                    return fallback
                rv = rv[part]
        return rv

    def set(self, data: dict, value):
        if self == Path():
            raise PathError('Can not set root of dictionary with Path')
        self.up(1).index(data)[self.last_name()] = value

    def spec_path(self) -> Path:
        """Get corresponding specification-path to property"""
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
            return not is_copyfrom(path.index(data, None))

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
        return "/" + "/".join(strings)

    def __repr__(self):
        return f"Path({self})"

    def __eq__(self, value):
        return self.path == value.path

    def __hash__(self):
        return hash(self.path)

