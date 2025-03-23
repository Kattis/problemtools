import re
from typing import Any, Callable, Literal, Pattern, Match, ParamSpec, TypeVar
from collections import defaultdict

class SpecificationError(Exception):
    pass

type_mapping = {
    "string": str,
    "object": dict,
    "list": list,
    "int": int,
    "float": float
}

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
        return Path(*res)

    @staticmethod
    def combine(*parts: str|int|'Path') -> 'Path':
        res = []
        for part in parts:
            if isinstance(part, int):
                res.append(part)
                continue
            if isinstance(part, str):
                part = Path.parse(part)
            res.extend(list(part.path)) #type: ignore
        return Path(*res)

    def __init__(self, *path: str|int) -> None:
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
        return Path(*res)

    def __str__(self) -> str:
        strings = []
        for part in self.path:
            if isinstance(part, int):
                strings[-1] += f'[{part}]'
            else:
                strings.append(part)
        return '/'.join(strings)
    
    def __eq__(self, value):
        return self.path == value.path
    
    def __hash__(self):
        return hash(self.path)

class AlternativeMatch:
    def __init__(self, matchstr):
        raise NotImplementedError("Specialize in subclass")

    def check(self, val) -> bool:
        raise NotImplementedError("Specialize in subclass")
    
    @staticmethod
    def get_matcher(type, matchstr) -> 'AlternativeMatch':
        matchers = {
            'string': StringMatch,
            'int': IntMatch,
            'float': FloatMatch,
            'bool': BoolMatch
        }
        assert type in matchers
        return matchers[type](matchstr)

class StringMatch(AlternativeMatch):
    def __init__(self, matchstr):
        self.regex = re.compile(matchstr)
    
    def check(self, val) -> bool:
        return self.regex.match(val)
    
    def __str__(self) -> str:
        self.regex.pattern

class IntMatch(AlternativeMatch):
    def __init__(self, matchstr: str):
        try:
            if matchstr.count(':') > 1:
                raise ValueError
            if ':' in matchstr:
                self.start, self.end = [int(p) if p else None for p in map(str.strip, matchstr.split())]
            else:
                matchstr = matchstr.strip()
                if not matchstr:
                    raise SpecificationError('Match string for integer was left empty')
                self.start = self.end = int(matchstr)
        except ValueError:
            raise SpecificationError('Int match string should be of the form "A:B" where A and B can be parsed as ints or left empty, or a single integer')
    
    def check(self, val) -> bool:
        if not isinstance(val, int):
            return False
        if self.start is not None:
            if val < self.start:
                return False
        if self.end is not None:
            if val > self.start:
                return False
        return True
    
    def __str__(self):
        if A == B:
            return str(A)
        A = str(self.start) if self.start is not None else ""
        B = str(self.end) if self.end is not None else ""
        return f'{A}:{B}'

class FloatMatch(AlternativeMatch):
    def __init__(self, matchstr: str):
        try:
            if matchstr.count(':') != 1:
                raise ValueError
            first, second = [p.strip() for p in matchstr.split()]
            self.start = float(first) if first else float('-inf')
            self.end = float(second) if second else float('inf')
        except ValueError:
            raise SpecificationError('Float match string should be of the form "A:B" where A and B can be parsed as floats or left empty')
    
    def check(self, val) -> bool:
        return isinstance(val, float) and self.start <= val <= self.end
    
    def __str__(self):
        A = str(self.start) if self.start != float('-inf') else ""
        B = str(self.end) if self.end != float('inf') else ""
        return f'{A}:{B}'

class BoolMatch(AlternativeMatch):
    def __init__(self, matchstr: str):
        matchstr = matchstr.strip().lower()
        assert matchstr in ('true', 'false')
        self.val = {'true':True,'false':False}[matchstr]
    
    def check(self, val) -> bool:
        return isinstance(val, bool) and val == self.val
    
    def __str__(self):
        return str(self.val)

class Metadata:
    def __init__(self, specification: dict) -> None:
        self.spec = specification
        self.error_func = lambda s: print(f"ERROR: {s}")
        self.warning_func = lambda s: print(f"WARNING: {s}")
        self.data = None

    def __getitem__(self, key: str|Path) -> Any:
        if self.data is None:
            raise Exception('data has not been loaded yet')
        if isinstance(key, str):
            return Path.parse(key).index(self.data)
        return key.index(self.data)

    def set_error_callback(self, fun: Callable):
        self.error_func = fun

    def set_warning_callback(self, fun: Callable):
        self.warning_func = fun

    def load_config(self, config: dict, injected_data: dict) -> None:
        self.data: dict = DefaultObjectParser(config, self.spec, Path(), self.warning_func, self.error_func).parse()
        
        ready: list[tuple[Path, str]] = []
        dependencies = {}
        depends_on = defaultdict(list)
        solved = set()
        for prop, spec in self.spec["properties"].items():
            parser = Parser.get_parser_type(spec)
            deps = parser.PATH_DEPENDENCIES
            if deps:
                dependencies[(Path(), prop)] = len(deps)
                for d in deps:
                    depends_on[d].append((Path(), prop))
            else:
                ready.append((Path(), prop))
            
        while ready:
            p, c = ready.pop()
            full_path = Path.combine(p, c)
            spec = full_path.spec_path().index(self.spec)
            parser = Parser.get_parser_type(spec)(self.data, self.spec, full_path, self.warning_func, self.error_func)
            p.index(self.data)[c] = parser.parse()
            if spec["type"] == "object":
                for prop, c_spec in self.spec["properties"].items():
                    c_parser = Parser.get_parser_type(c_spec)
                    deps = set(c_parser.PATH_DEPENDENCIES) - solved
                    if deps:
                        dependencies[(full_path, prop)] = len(deps)
                        for d in deps:
                            depends_on[d].append((full_path, prop))
                    else:
                        ready.append((full_path, prop))
            elif spec["type"] == "list":
                c_spec = Parser.get_parser_type(spec["content"])
                deps = set(c_parser.PATH_DEPENDENCIES) - solved
                for i in range(len(full_path.index(self.data))):
                    if deps:
                        dependencies[(full_path, i)] = len(deps)
                        for d in deps:
                            depends_on[d].append((full_path, i)) 
                    else:
                        ready.append((full_path, i))
            for x in depends_on[full_path]:
                dependencies[x] -= 1
                if dependencies[x] == 0:
                    ready.append(x)
                    del dependencies[x]
        if any(v > 0 for v in dependencies.items()):
            raise SpecificationError("Circular dependency in specification by parsing rules")
        self.data.update(injected_data)
        # TODO: copy-from directives

    def check_config(self) -> None:
        pass

class Parser:
    NAME: str = ""
    PATH_DEPENDENCIES: list[Path] = []
    OUTPUT_TYPE: str = ""
    
    def __init__(self, data: dict, specification: dict, path: Path, warning_func: Callable, error_func: Callable):
        self.data = data
        self.specification = specification
        self.path = path
        self.spec_path = path.spec_path()
        self.warning_func = warning_func
        self.error_func = error_func
        
        if not self.NAME:
            raise NotImplementedError("Subclasses of Parser need to set the name of the parsing rule")
        if not self.OUTPUT_TYPE:
            raise NotImplementedError("Subclasses of Parser need to set the output type of the parsing rule")
        
        required_type = self.spec_path.index(specification)["type"]
        if required_type != self.OUTPUT_TYPE:
            raise SpecificationError(f"Parsing rule for {path} outputs {self.OUTPUT_TYPE}, but the output should be of type {required_type}")
        
        if self.OUTPUT_TYPE in ("string", "int", "float", "bool"):
            alternatives = Path.combine(self.spec_path, "alternatives").index(self.specification)
            if alternatives is None:
                self.alternatives = None
            else:
                self.alternatives = [(AlternativeMatch.get_matcher(self.OUTPUT_TYPE, key), val) for key, val in alternatives.items()]
        else:
            self.alternatives = None
    
    def parse(self):
        val = self.path.index(self.data)
        out = self._parse(val)
        
        flags = Path.combine(self.spec_path, "flags").index(self.specification) or []
        if 'deprecated' in flags and out is not None:
            self.warning_func(f'deprecated property was provided ({self.path})')
        
        if self.alternatives is not None:
            found_match = False
            for matcher, checks in self.alternatives:
                if matcher.check(out):
                    found_match = True
                    if "warn" in checks:
                        self.warning_func(checks["warn"])
            if not found_match:
                alts = ', '.join(f'"{matcher}"' for matcher in self.alternatives.keys())
                self.error_func(f"Property {self.path} did not match any of the specified alternatives ({alts})")
                out = None

        if out is None:
            fallback = Path.combine(self.spec_path, "default").index(self.specification)
            if fallback is not None:
                if isinstance(fallback, str) and fallback.startswith('copy-from:'):
                    fallback = ('copy-from', fallback.split(':')[1])
                return fallback
            return type_mapping[self.OUTPUT_TYPE]()
        
        if not (isinstance(out, tuple) or isinstance(out, type_mapping[self.OUTPUT_TYPE])):
            raise SpecificationError(f'Parsing rule "{self.NAME}" did not output the correct type. Output was: {out}')
        return out
    
    def _parse(self, val):
        raise NotImplementedError("Subclasses of Parse need to implement _parse()")

    @staticmethod
    def get_parser_type(specification: dict) -> type:
        parsing_rule = specification.get('parsing')
        if parsing_rule is None:
            typ = specification.get("type")
            parsing_rule = f'default-{typ}-parser'
        if parsing_rule not in parsers:
            raise SpecificationError(f'Parser "{parsing_rule}" is not implemented')
        return parsers[parsing_rule]
        

class DefaultStringParser(Parser):
    NAME = "default-string-parser"
    OUTPUT_TYPE = "string"
    
    def _parse(self, val):
        if val is None:
            return None
        if not isinstance(val, str):
            self.warning_func(f'Expected value of type string but got {val}, casting to string ({self.path})')
            val = str(val)
        return val

class DefaultObjectParser(Parser):
    NAME = "default-object-parser"
    OUTPUT_TYPE = "object"
    
    def _parse(self, val):
        if val is None:
            return None
        
        if not isinstance(val, dict):
            self.error_func(f'Expected an object, got {val} ({self.path})')
            return None
        
        required = Path.combine(self.spec_path, 'required').index(self.specification) or []
        for req in required:
            req_path = Path.combine(self.path, req)
            if req_path.index(self.data) is None:
                self.error_func(f'Missing required property: {req_path}')
    
        remove = []
        known_props = Path.combine(self.spec_path, 'properties').index(self.specification)
        for prop in val.keys():
            if prop not in known_props:
                self.warning_func(f'Unknown property: {Path.combine(self.path, prop)}')
                remove.append(prop)
        for r in remove:
            del val[r]

        return val

class DefaultListParser(Parser):
    NAME = "default-list-parser"
    OUTPUT_TYPE = "list"
    
    def _parse(self, val):
        if val is None:
            return None
        
        if not isinstance(val, list):
            self.error_func(f'Expected a list, got {val} ({self.path})')
            return None
        
        return val   
        
class DefaultIntParser(Parser):
    NAME = "default-int-parser"
    OUTPUT_TYPE = "int"
    
    def _parse(self, val):
        if val is None:
            return None
        
        if not isinstance(val, int):
            try:
                cast = int(val)
                self.warning_func(f'Expected type int, got {val}. Casting to {cast} ({self.path})')
                val = cast
            except ValueError:
                self.error_func(f'Expected a int, got {val} ({self.path})')
                return None
        
        return val

class DefaultFloatParser(Parser):
    NAME = "default-float-parser"
    OUTPUT_TYPE = "float"
    
    def _parse(self, val):
        if val is None:
            return None
        
        if not isinstance(val, float):
            try:
                cast = float(val)
                self.warning_func(f'Expected type float, got {val}. Casting to {cast} ({self.path})')
                val = cast
            except ValueError:
                self.error_func(f'Expected a float, got {val} ({self.path})')
                return None
        
        return val
    
class DefaultBoolParser(Parser):
    NAME = "default-bool-parser"
    OUTPUT_TYPE = "bool"
    
    def _parse(self, val):
        if val is None:
            return None
        
        if isinstance(val, str):
            if val.lower() in ("true", "false"):
                interpretation = val.lower() == 'true'
                self.warning_func(f'Expected type bool but got a string "{val}" which will be interpreted as {interpretation} ({self.path})')
                val = interpretation
            else:
                self.error_func(f'Expected type bool but got "{val}" ({self.path})')
                return None
            
        if not isinstance(val, bool):
            self.error_func(f'Expected type bool, got {val} ({self.path})')
            return None
        
        return val

parsers = {p.NAME: p for p in 
           [DefaultObjectParser, DefaultListParser, DefaultStringParser,
            DefaultIntParser, DefaultFloatParser, DefaultBoolParser]
}


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

