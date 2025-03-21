import re
from typing import Any, Callable, Literal, Pattern, Match, ParamSpec, TypeVar


class Path:
    INDEXING_REGEX = re.compile(r'^([A-Za-z_0-9\-]+)\[(\d+)\]$')
    @staticmethod
    def parse(path: str) -> 'Path':
        parts = path.split('/')
        res = []
        for part in parts:
            m = Path.INDEXING_REGEX.match(part) 
            if m:
                res.append(m.group(1))
                res.append(int(m.group(2)))
            else:
                res.append(part)
        return Path(tuple(res))

    @staticmethod
    def combine(*parts: list[str|int|'Path']) -> 'Path':
        res = []
        for part in parts:
            if isinstance(part, int):
                res.append(part)
                continue
            if isinstance(part, str):
                part = Path.parse(part)
            res.extend(list(part.path)) #type: ignore
        return Path(tuple(res))

    def __init__(self, path: tuple[str|int]) -> None:
        self.path = path

    def index(self, data: dict) -> Any|None:
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

    def spec_path(self) -> 'Path':
        res = []
        for part in self.path:
            if isinstance(part, str):
                res.append("properties")
                res.append("part")
            elif isinstance(part, int):
                res.append("content")
        return Path(tuple(res))

    def __str__(self) -> str:
        strings = []
        for part in self.path:
            if isinstance(part, int):
                strings[-1] += f'[{part}]'
            else:
                strings.append(part)
        return '/'.join(strings)

class Metadata:
    def __init__(self, specification: dict) -> None:
        self.spec = specification
        self.error_func = lambda s: print(f"ERROR: {s}")
        self.warning_func = lambda s: print(f"WARNING: {s}")
        self.data = None

    def __getitem__(self, key: str) -> Any:
        if self.data is None:
            raise Exception('data has not been loaded yet')
        return Path.parse(key).index(self.data)

    def set_error_callback(self, fun: Callable):
        self.error_func = fun

    def set_warning_callback(self, fun: Callable):
        self.warning_func = fun

    def load_config(self, config: dict) -> None:
        pass

    def check_config(self) -> None:
        pass

    #TODO: type for path
    def get_validator(self, layout: dict, path) -> 'BaseValidator':
        type_map = {
            "string": StringValidator,
            "int": IntValidator,
            "float": FloatValidator,
            "object": ObjectValidator,
        }
        typ = layout.get("type")
        if typ not in type_map:
            raise NotImplementedError(f"Unrecognized type: {typ}")
        return type_map[typ](layout, self, path)

class BaseValidator:
    def __init__(self, layout: dict, metadata: Metadata, path: str = ""):
        self.layout = layout
        self.metadata = metadata
        self.path = path

    def verify(self, value):
        """
        Verifies the value:
          - Applies defaults
          - Converts types
          - Logs warnings/errors if needed
        """
        raise NotImplementedError("Subclasses must implement verify")

    def check(self, value):
        """
        Performs extra-checks (like forbid/require logic)
        get_path_func can be used to fetch other values by path.
        """
        raise NotImplementedError("Subclasses must implement check")


class StringValidator(BaseValidator):
    def __init__(self, layout: dict, metadata: Metadata, path: str = ""):
        super().__init__(layout, metadata, path)
        alternatives = self.layout.get("alternatives")
        if alternatives:
            self.patterns = {alt: re.compile('^' + alt + '$') for alt in alternatives}
        else:
            self.patterns = None

    def verify(self, value):
        if value is None:
            value = self.layout.get("default", "")
        if not isinstance(value, str):
            self.metadata.warning_func(f'Property {self.path} was expected to be of type string')
            value = str(value)
        if self.patterns:
            if not any(pattern.match(value) for pattern in self.patterns.values()):
                self.metadata.error_func(f"Property {self.path} is {value} but must match one of {list(self.patterns.keys())}")
                value = self.layout.get("default", "")
        return value

    def check(self, value):
        if not self.patterns:
            return
        match = next((key for key, pattern in self.patterns.items() if pattern.match(value)), None)
        checks = self.layout["alternatives"][match]
        for forbidden in checks.get("forbid", []):
            other_path, expected = forbidden.split(':')
            if self.metadata[other_path] == expected:
                self.metadata.error_func(f"Property {self.path} has value {value} which forbids property {other_path} to have value {expected}")
        for required in checks.get("required", []):
            if not self.metadata[required]: #TODO: This is not a good way to handle this check I think
                self.metadata.error_func(f"Property {self.path} has value {value} which requires property {required}")
        if "warn" in checks:
            self.metadata.warning_func(checks["warn"])

class ObjectValidator(BaseValidator):
    def verify(self, value):
        if value is None:
            return self.layout.get("default", {})
        if self.layout.get("parsing") == "legacy-validation":
            if not isinstance(value, str):
                self.metadata.error_func(f"Property {self.path} was expected to be a string")
                return {}
            elements = value.split()
            value = {
                "type": elements[0],
                "interactive": "interactive" in elements[1:],
                "score": "score" in elements[1:]
            }
        if not isinstance(value, dict):
            self.metadata.error_func(f"property {self.path} was expected to be a dictionary")
            return {}
        for prop in self.layout.get("required", []):
            if prop not in value:
                self.metadata.error_func(f"Missing required property: {self.path}/{prop}")
        for prop in value.keys():
            if prop not in self.layout["properties"]:
                self.metadata.warning_func(f"Unknown property: {self.path}/{prop}")
        return value
    
    def check(self, value):
        pass

class ListValidator(BaseValidator):
    def verify(self, value):
        if value is None:
            return self.layout.get("default", [])
        if self.layout.get("parsing") == "space-separated-strings":
            if not isinstance(value, str):
                self.metadata.error_func(f"Property {self.path} was expected to be a string")
                return []
            value = value.split()
        if not isinstance(value, list):
            self.metadata.error_func(f"property {self.path} was expected to be a list")
            return []
        return value
    
    def check(self, value):
        pass

class FloatValidator(BaseValidator):
    def verify(self, value):
        if value is None:
            return self.layout.get("default", 0.0)
        if not isinstance(value, float):
            try:
                value = float(value)
            except Exception:
                self.metadata.error_func(f"Property {self.path} was expected to be a float")
                value = self.layout.get("default", 0.0)
        return value
    
    def check(self, value):
        pass

class IntValidator(BaseValidator):
    def verify(self, value):
        if value is None:
            return self.layout.get("default", 0)
        if not isinstance(value, int):
            try:
                value = int(value)
                self.metadata.warning_func(f"Property {self.path} should be of type integer, interpreting as {value}")
            except Exception:
                self.metadata.error_func(f"Property {self.path} was expected to be an integer")
                value = self.layout.get("default", 0)
        return value

    def check(self, value):
        pass

