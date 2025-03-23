from helper import *
import yaml

config = construct_metadata('complex_copies.yaml', 'empty_config.yaml', {})

expected = {
    "a": {
        "k": 2,
        "l": 1000
    },
    "b": {
        "c": 123,
        "d": {
            "k": 2,
            "l": 1000
        }
    },
    "h": {
        "i": 1000,
        "j": {
            "k": 2,
            "l": 1000
        }
    }
}

if config.data != expected:
    print("Data did not match expected result:")
    print("expected:")
    print(yaml.dump(expected))
    print("got:")
    print(yaml.dump(config.data))
    assert False
