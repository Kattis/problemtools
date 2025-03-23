from __future__ import annotations
import re
from typing import Any, Callable, Generator, Literal, Pattern, Match, ParamSpec, TypeVar
from collections import defaultdict, deque
from copy import deepcopy
from .general import SpecificationError, is_copyfrom, type_field_mapping, type_mapping
from .matcher import AlternativeMatch
from .config_path import Path
from .parser import Parser, DefaultObjectParser


class Metadata:
    def __init__(self, specification: dict) -> None:
        self.spec = specification
        self.error_func = lambda s: print(f"ERROR: {s}")
        self.warning_func = lambda s: print(f"WARNING: {s}")
        self.data = None

    def __getitem__(self, key: str | Path) -> Any:
        if self.data is None:
            raise Exception("data has not been loaded yet")
        if isinstance(key, str):
            return Path.parse(key).index(self.data)
        return key.index(self.data)

    def set_error_callback(self, fun: Callable):
        self.error_func = fun

    def set_warning_callback(self, fun: Callable):
        self.warning_func = fun

    def invert_graph(dependency_graph: dict[Path, list[Path]]):
        depends_on_graph = {k: [] for k in dependency_graph.keys()}
        for dependant, dependencies in dependency_graph.items():
            for dependency in dependencies:
                depends_on_graph[dependency].append(dependant)
        return depends_on_graph

    def topo_sort(dependency_graph: dict[Path, list[Path]]) -> Generator[Path]:
        # Dependancy graph:
        # Path : [Depends on Path, ...]

        in_degree = {p: len(l) for p, l in dependency_graph.items()}

        q = deque(p for p in dependency_graph.keys() if in_degree[p] == 0)

        depends_on_graph = Metadata.invert_graph(dependency_graph)

        while q:
            current = q.popleft()
            yield current

            for dependency in depends_on_graph[current]:
                in_degree[dependency] -= 1

                if in_degree[dependency] == 0:
                    q.append(dependency)

        if any(x > 0 for x in in_degree.values()):
            nodes = ", ".join(
                str(path) for path, count in in_degree.items() if count > 0
            )
            raise SpecificationError(
                f"Unresolvable, cyclic dependencies involving ({nodes})"
            )

    def get_path_dependencies(self) -> dict[Path, list[Path]]:
        stack = [(Path(), Path("properties", prop)) for prop in self.spec["properties"]]
        graph = {}
        while stack:
            parent, p = stack.pop()
            spec = p.index(self.spec)
            deps = Parser.get_parser_type(spec).get_dependencies()
            if len(parent.path) > 0:
                deps.append(parent)
            graph[p] = deps
            for dep in deps:
                assert dep != p
            if spec["type"] == "object":
                stack.extend(
                    (p, Path.combine(p, "properties", prop))
                    for prop in spec["properties"]
                )
            elif spec["type"] == "list":
                stack.append((p, Path.combine(p, "content")))
        return graph

    def get_copy_dependencies(self) -> dict[Path, list[Path]]:
        stack = [(Path(), Path(child)) for child in self.data.keys()]
        graph = {Path(): []}

        while stack:
            parent, path = stack.pop()
            val = path.index(self.data)
            graph[parent].append(path)
            deps = []
            if is_copyfrom(val):
                deps.append(val[1])
            graph[path] = deps
            if isinstance(val, dict):
                stack.extend((path, Path.combine(path, child)) for child in val.keys())
            elif isinstance(val, list):
                stack.extend((path, Path.combine(path, i)) for i in range(len(val)))

        return graph

    def load_config(self, config: dict, injected_data: dict) -> None:
        self.data: dict = DefaultObjectParser(
            config, self.spec, Path(), self.warning_func, self.error_func
        ).parse()
        for cfg_path in Metadata.topo_sort(self.get_path_dependencies()):
            spec = cfg_path.index(self.spec)
            for full_path in cfg_path.data_paths(self.data):
                parser = Parser.get_parser_type(spec)(
                    self.data, self.spec, full_path, self.warning_func, self.error_func
                )
                full_path.up().index(self.data)[full_path.last_name()] = parser.parse()
        self.data.update(injected_data)

        for full_path in Metadata.topo_sort(self.get_copy_dependencies()):
            val = full_path.index(self.data)
            if is_copyfrom(val):
                if any(isinstance(part, int) for part in val[1].path):
                    raise SpecificationError(
                        f"copy-from directives may not copy from lists (property: {full_path}, copy-property: {val[1]})"
                    )
                copy_val = deepcopy(val[1].index(self.data))
                if copy_val is None:
                    raise SpecificationError(
                        f"copy-from directive returned None (property: {full_path}, copy-property: {val[1]})"
                    )
                if not isinstance(
                    copy_val,
                    type_mapping[full_path.spec_path().index(self.spec)["type"]],
                ):
                    raise SpecificationError(
                        f"copy-from directive provided the wrong type (property: {full_path}, copy-property: {val[1]})"
                    )
                full_path.up().index(self.data)[full_path.last_name()] = copy_val

    def check_config(self) -> None:
        pass


