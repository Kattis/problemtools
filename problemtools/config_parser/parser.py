from typing import Callable
from .config_path import Path
from .general import SpecificationError
from .matcher import AlternativeMatch
from collections import Counter

type_mapping = {
    "string": str,
    "object": dict,
    "list": list,
    "bool": bool,
    "int": int,
    "float": float,
}

type_field_mapping = {
    "*": ["default", "type", "flags", "parsing"],
    "string": ["alternatives"],
    "bool": ["alternatives"],
    "int": ["alternatives"],
    "float": ["alternatives"],
    "object": ["required", "properties"],
    "list": ["content"],
}


class Parser:
    NAME: str = ""
    OUTPUT_TYPE: str = ""
    
    @staticmethod
    def get_dependencies() -> list[Path]:
        return []

    def __init__(
        self,
        data: dict,
        specification: dict,
        path: Path,
        warning_func: Callable,
        error_func: Callable,
    ):
        self.data = data
        self.specification = specification
        self.path = path
        self.spec_path = path.spec_path()
        self.warning_func = warning_func
        self.error_func = error_func

        if not self.NAME:
            raise NotImplementedError(
                "Subclasses of Parser need to set the name of the parsing rule"
            )
        if not self.OUTPUT_TYPE:
            raise NotImplementedError(
                "Subclasses of Parser need to set the output type of the parsing rule"
            )

        required_type = self.spec_path.index(specification)["type"]
        if required_type != self.OUTPUT_TYPE:
            raise SpecificationError(
                f"Parsing rule ({self.NAME}) for {path} outputs {self.OUTPUT_TYPE}, but the output should be of type {required_type}"
            )

        if self.OUTPUT_TYPE in ("string", "int", "float", "bool"):
            alternatives = Path.combine(self.spec_path, "alternatives").index(
                self.specification,
                None
            )
            if alternatives is None:
                self.alternatives = None
            else:
                self.alternatives = [
                    AlternativeMatch.get_matcher(self.OUTPUT_TYPE, key) for key, _ in alternatives.items()
                ]
        else:
            self.alternatives = None

    def parse(self):
        out = self._parse(self.path.index(self.data, None))
        
        if out is not None:
            flags = Path.combine(self.spec_path, "flags").index(self.specification, [])
            if "deprecated" in flags:
                self.warning_func(f"deprecated property was provided ({self.path})")

            if self.OUTPUT_TYPE == "object":
                required = (
                    Path.combine(self.spec_path, "required").index(self.specification, [])
                )
                for req in required:
                    req_path = Path.combine(self.path, req)
                    if req_path.index(self.data) is None:
                        self.error_func(f"Missing required property: {req_path}")

                remove = []
                known_props = Path.combine(self.spec_path, "properties").index(
                    self.specification
                )
                for prop in out.keys():
                    if prop not in known_props:
                        self.warning_func(f"Unknown property: {Path.combine(self.path, prop)}")
                        remove.append(prop)
                for r in remove:
                    del out[r]

            if self.alternatives is not None:                    
                if not any(matcher.check(out) for matcher in self.alternatives):
                    alts = ", ".join(f'"{matcher}"' for matcher in self.alternatives)
                    self.error_func(
                        f"Property {self.path} with value {out} did not match any of the specified alternatives ({alts})"
                    )
                    out = None

        if out is None:
            fallback = Path.combine(self.spec_path, "default").index(self.specification, type_mapping[self.OUTPUT_TYPE]())
            if type(fallback) is str and fallback.startswith("copy-from:"):
                fallback = ("copy-from", Path.parse(fallback.split(":")[1]))
            return fallback

        if not (
            isinstance(out, tuple) or isinstance(out, type_mapping[self.OUTPUT_TYPE])
        ):
            raise SpecificationError(
                f'Parsing rule "{self.NAME}" did not output the correct type. Output was: {out}'
            )
        return out

    def _parse(self, val):
        raise NotImplementedError("Subclasses of Parse need to implement _parse()")

    def smallest_edit_dist(a: str, b: list[str]) -> str:
        def edit_dist(a: str, b: str) -> int:
            n = len(a)
            m = len(b)
            dp = [[0] * (m + 1) for _ in range(n + 1)]
            for i in range(n + 1):
                dp[i][0] = i
            for j in range(m + 1):
                dp[0][j] = j
            for i in range(1, n + 1):
                for j in range(1, m + 1):
                    if a[i - 1] == b[j - 1]:
                        dp[i][j] = dp[i - 1][j - 1]
                    else:
                        dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
            return dp[n][m]
        best = b[0]
        best_dist = edit_dist(a, best)
        for s in b[1:]:
            dist = edit_dist(a, s)
            if dist < best_dist:
                best = s
                best_dist = dist
        return best

    @staticmethod
    def get_parser_type(specification: dict) -> type:
        parsing_rule = specification.get("parsing")
        if parsing_rule is None:
            typ = specification.get("type")

            if typ is None:
                had = "', '".join(specification.keys())
                raise SpecificationError(
                    f"Specification did not have a MUST HAVE field 'type', the provided fields were: ('{had}')"
                )

            if typ not in type_mapping:
                valid = "', '".join(type_mapping.keys())
                closest = Parser.smallest_edit_dist(typ, [*type_mapping.keys()])
                raise SpecificationError(
                    f"Type '{typ}' is not a valid type. Did you mean: '{closest}'? Otherwise valid types are: ('{valid}')"
                )


            fields = specification.keys()
            allowed_fields = type_field_mapping.get(typ, []) + type_field_mapping["*"]
            for field in fields:
                if field not in allowed_fields:
                    raise SpecificationError(
                        f"Field '{field}' is not allowed for type '{typ}', did you mean '{Parser.smallest_edit_dist(field, allowed_fields)}'?"
                    )

            parsing_rule = f"default-{typ}-parser"
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
            self.warning_func(
                f"Expected value of type string but got {val}, casting to string ({self.path})"
            )
            val = str(val)
        return val


class DefaultObjectParser(Parser):
    NAME = "default-object-parser"
    OUTPUT_TYPE = "object"

    def _parse(self, val):
        if val is None:
            return None

        if not isinstance(val, dict):
            self.error_func(f"Expected an object, got {val} ({self.path})")
            return None

        return val


class DefaultListParser(Parser):
    NAME = "default-list-parser"
    OUTPUT_TYPE = "list"

    def _parse(self, val):
        if val is None:
            return None

        if not isinstance(val, list):
            self.error_func(f"Expected a list, got {val} ({self.path})")
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
                self.warning_func(
                    f"Expected type int, got {val}. Casting to {cast} ({self.path})"
                )
                val = cast
            except ValueError:
                self.error_func(f"Expected a int, got {val} ({self.path})")
                return None

        return val


class DefaultFloatParser(Parser):
    NAME = "default-float-parser"
    OUTPUT_TYPE = "float"

    def _parse(self, val):
        if val is None:
            return None

        if not isinstance(val, (int, float)):
            try:
                cast = float(val)
                self.warning_func(
                    f"Expected type float, got {val}. Casting to {cast} ({self.path})"
                )
                val = cast
            except ValueError:
                self.error_func(f"Expected a float, got {val} ({self.path})")
                return None

        return float(val)


class DefaultBoolParser(Parser):
    NAME = "default-bool-parser"
    OUTPUT_TYPE = "bool"

    def _parse(self, val):
        if val is None:
            return None

        if isinstance(val, str):
            if val.lower() in ("true", "false"):
                interpretation = val.lower() == "true"
                self.warning_func(
                    f'Expected type bool but got stringified bool: "{val}" which will be interpreted as {interpretation} ({self.path})'
                )
                val = interpretation
            else:
                self.error_func(f'Expected type bool, but got "{val}" ({self.path})')
                return None

        if not isinstance(val, bool):
            self.error_func(f"Expected type bool, got {val} ({self.path})")
            return None

        return val

class RightsOwnerLegacy(Parser):
    NAME = "rights-owner-legacy"
    OUTPUT_TYPE = "string"
    
    @staticmethod
    def get_dependencies() -> list[Path]:
        return [Path("author"), Path("source"), Path("license")]
    
    def _parse(self, val):
        if isinstance(val, str):
            return val
        
        if val is None and Path("license").index(self.data) != "public domain":
            author = Path("author").index(self.data)
            if len(author) > 0:
                return author
            source = Path("source").index(self.data)
            if len(source) > 0:
                return source
        
        return None

class LegacyValidation(Parser):
    NAME = "legacy-validation"
    OUTPUT_TYPE = "object"
    
    def _parse(self, val):
        if val is None:
            return None
        
        if not isinstance(val, str):
            self.error_func(f'Property {self.path} was expected to be given as type string')
            return None
        
        args = val.split()
        if args[0] not in ("default", "custom"):
            self.error_func(f'First argument of {self.path} was expected to be either "default" or "custom"')
            return None
        
        if len(set(args)) != len(args):
            self.warning_func(f'Arguments of {self.path} contains duplicate values')
            
        for arg in args[1:]:
            if arg not in ("score", "interactive"):
                self.warning_func(f'Invalid argument "{arg}" in {self.path}')
                
        return {
            "type": args[0],
            "interactive": "interactive" in args,
            "score": "score" in args
        }

class SpaceSeparatedStrings(Parser):
    NAME = "space-separated-strings"
    OUTPUT_TYPE = "list"
    
    def _parse(self, val):
        if val is None:
            return None
        
        if not isinstance(val, str):
            self.error_func(f'Property {self.path} was expected to be of type string')
            return None
        
        return val.split()

class MinMaxFloatString(Parser):
    NAME = "min-max-float-string"
    OUTPUT_TYPE = "object"
    
    def _parse(self, val):
        if val is None:
            return None
        
        if not isinstance(val, str):
            self.error_func(f'Property {self.path} was expected to be of type string')
            return None
        
        args = val.split()
        if len(args) != 2:
            self.error_func(f'Property {self.path} was expected to contain exactly two space-separated floats')
            return None
        
        try:
            a, b = map(float, args)
        except ValueError:
            self.error_func(f'Failed to parse arguments of {self.path} as floats')
                
        return {"min": a, "max": b}

class Type2023_07(Parser):
    NAME = "type-2023-07"
    OUTPUT_TYPE = "object"
    
    def _parse(self, val):
        if val is None:
            return None
        
        if type(val) is str:
            val = [val]
        
        if type(val) is not list:
            self.error_func(f'Property {self.path} was expected to be of type list or a single string. Got {type(val)}')
            return None
        
        if len(val) == 0:
            self.error_func(f'Property {self.path} was empty list, but it should contain at least one element')
            return None
        
        valid_options = {"pass-fail", "scoring", "multi-pass", "interactive", "submit-answer"}
        out = {option: False for option in valid_options}
        
        for option in val:
            if option not in valid_options:
                self.error_func(f'Property {self.path} received invalid option "{option}"')
                return None
            else:
                if out[option]:
                    self.error_func(f'Property {self.path} must not contain duplicate elements. Found duplicate "{option}"')
                    return None
                out[option] = True
        
        return out
        
class Name2023_07(Parser):
    NAME = "name-2023-07"
    OUTPUT_TYPE = "object"
    
    def _parse(self, val):
        if val is None:
            return None
        
        if type(val) is str:
            return {"en": val}
        
        if type(val) is not dict:
            self.error_func(f'Property {self.path} should be of type string or a dictionary of language-codes to strings. Got {type(val)}')
            return None
        
        return val

class Credits2023_07(Parser):
    NAME = "credits-2023-07"
    OUTPUT_TYPE = "object"
    
    def _parse(self, val):
        if val is None:
            return None
        
        if type(val) is str:
            return {"authors": val}
        
        if type(val) is not dict:
            self.error_func(f'Property {self.path} should be either a single string, or a dictionary')
            return None
        
        return val

class StringToList(Parser):
    NAME = "string-to-list"
    OUTPUT_TYPE = "list"
    
    def _parse(self, val):
        if val is None:
            return None
        
        if type(val) is str:
            return [val]
        
        if type(val) is not list:
            self.error_func(f'Property {self.path} should be either a single string or a list of strings')
            return None
        
        return val

class Source2023_07(Parser):
    NAME = "source-2023-07"
    OUTPUT_TYPE = "list"
    
    def _parse(self, val):
        if val is None:
            return None

        if type(val) is str:
            return [{"name":val}]
        
        if type(val) is dict:
            return [val]
        
        if type(val) is not list:
            self.error_func(f'Property {self.path} should be of type string, object or a list')
            return None
        
        return val
    
class SourceItem2023_07(Parser):
    NAME = "source-item-2023-07"
    OUTPUT_TYPE = "object"
    
    def _parse(self, val):
        if val is None:
            return {"name": "???"}
        
        if type(val) is str:
            return {"name": val}
        
        if type(val) is dict:
            if "name" not in val:
                self.error_func(f'Property {self.path} needs key "name"')
                val["name"] = "???"
            return val
        
        self.error_func(f'Property {self.path} should be of type string or object, got {type(val)}')
        return {"name": "???"}

class RightsOwner2023_07(Parser):
    NAME = "rights-owner-2023-07"
    OUTPUT_TYPE = "string"
    
    @staticmethod
    def get_dependencies() -> list[Path]:
        return [Path("credits", "authors"), Path("source", 0), Path("license")]
    
    def _parse(self, val):
        if type(val) is str:
            return val
        
        if val is None and Path("license").index(self.data) != "public domain":
            authors = Path("credits", "authors").index(self.data)
            if len(authors) > 0:
                return ' and '.join(authors)
            source = Path("source").index(self.data)
            if len(source) > 0:
                return ' and '.join(s["name"] for s in source)
        
        return None

class LanguagesParsing(Parser):
    NAME = "languages-parsing"
    OUTPUT_TYPE = "list"
    
    def _parse(self, val):
        if val is None:
            return ("copy-from", Path("languages"))
        
        if type(val) is str:
            if val == "all":
                return ("copy-from", Path("languages"))
            else:
                self.error_func(f'Property {self.path} should be a list or the string "all", got "{val}"')

        if type(val) is not list:
            self.error_func(f'Property {self.path} should be a list or the string "all", got {val}')
            return ("copy-from", Path("languages"))
        
        if len(val) == 0:
            self.error_func(f'Property {self.path} needs to contain at least one language')
            return ("copy-from", Path("languages"))
        
        return val

parser_classes = [
    DefaultObjectParser,
    DefaultListParser,
    DefaultStringParser,
    DefaultIntParser,
    DefaultFloatParser,
    DefaultBoolParser,
    RightsOwnerLegacy,
    LegacyValidation,
    SpaceSeparatedStrings,
    MinMaxFloatString,
    Type2023_07,
    Name2023_07,
    Credits2023_07,
    StringToList,
    Source2023_07,
    SourceItem2023_07,
    RightsOwner2023_07,
    LanguagesParsing,
]

parsers = { p.NAME: p for p in parser_classes }
if len(parser_classes) != len(parsers):
    duplicates = [f' - {prop}, {cnt} occurences' for prop, cnt in Counter(c.NAME for c in parser_classes).items() if cnt > 1]
    raise NotImplementedError(f"Duplicate name(s) detected in parsers:\n{'\n'.join(duplicates)}")
