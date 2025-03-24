from problemtools.config_parser import Metadata
from helper import *

def test_basic_config():
    injected = {
        'external': {
            "cool-string": "yo this string is ballin"
        }
    }
    data = construct_metadata('basic_config.yaml', 'follows_basic_config.yaml', injected)
    data.check_config()
    
    print(f"warnings: {warnings}")
    print(f"errors: {errors}")

    assert data["foo"] == 1337
    assert data["bar"] == "z"
    assert data["baz"] == True
    assert abs(data["boz"] - 3.5) < 0.01
    assert data["copied"] == "yo this string is ballin"
    assert len(warnings) > 0

legacy_injected_data = {
    "system_default": load_yaml("system_defaults.yaml")
}

def test_legacy_config_empty():
    data = construct_metadata('legacy_specification.yaml', 'empty_config.yaml', legacy_injected_data)
    print(f"warnings: {warnings}")
    print(f"errors: {errors}")