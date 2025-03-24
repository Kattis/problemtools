from problemtools.config_parser import Metadata
from helper import *

def test_basic_config():
    injected = {
        'external': {
            "cool-string": "yo this string is ballin"
        }
    }
    data = construct_metadata('basic_config.yaml', 'follows_basic_config.yaml', injected)

    print(f"warnings: {warnings}")
    print(f"errors: {errors}")

    assert data["foo"] == 1337
    assert data["bar"] == "z"
    assert data["baz"] == True
    assert abs(data["boz"] - 3.5) < 0.01
    assert data["copied"] == "yo this string is ballin"
    assert len(warnings) > 0

legacy_injected_data = {
    "system_default": {
        "memory": 2048,
        "output": 8,
        "code": 128,
        "compilation_time": 60,
        "compilation_memory": 2048,
        "validation_time": 60,
        "validation_memory": 2048,
        "validation_output": 8
    }
}

def test_legacy_config_empty():
    data = construct_metadata('legacy_specification.yaml', 'empty_config.yaml', legacy_injected_data)
    print(f"warnings: {warnings}")
    print(f"errors: {errors}")