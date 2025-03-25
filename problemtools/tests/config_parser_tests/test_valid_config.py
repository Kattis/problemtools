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

injected_data_2023_07 = {
    "system_default": load_yaml("system_defaults.yaml"),
    "languages": ["python", "rust", "uhhh", "c++"]
}

def test_2023_07_config_minimal():
    data = construct_metadata('2023-07_specification.yaml', 'minimal_2023-07.yaml', injected_data_2023_07)
    data.check_config()

    print(f"warnings: {warnings}")
    print(f"errors: {errors}")
    assert len(errors) == 0