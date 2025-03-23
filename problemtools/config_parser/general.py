from typing import Any

class SpecificationError(Exception):
    pass

def is_copyfrom(val: Any) -> bool:
    return isinstance(val, tuple) and val[0] == "copy-from"

type_field_mapping = {
    "*": ["default", "type", "flags", "parsing"],
    "string": ["alternatives"],
    "bool": ["alternatives"],
    "int": ["alternatives"],
    "float": ["alternatives"],
    "object": ["required", "properties"],
    "list": ["content"],
}

type_mapping = {
    "string": str,
    "object": dict,
    "list": list,
    "bool": bool,
    "int": int,
    "float": float,
}