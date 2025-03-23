from problemtools.config_parser import Metadata
from helper import *

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