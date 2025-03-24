from helper import *

legacy_injected_data = {
    "system_default": load_yaml("system_defaults.yaml")
}

def test_require():
    md = construct_metadata('legacy_specification.yaml', 'legacy_config_fails_require.yaml', legacy_injected_data)
    md.check_config()
    print(errors)
    assert len(errors) == 1
    
def test_forbid():
    md = construct_metadata('legacy_specification.yaml', 'legacy_config_fails_forbid.yaml', legacy_injected_data)
    md.check_config()
    print(errors)
    assert len(errors) == 1

def test_alternatives():
    md = construct_metadata('legacy_specification.yaml', 'legacy_config_fails_alternative_match.yaml', legacy_injected_data)
    md.check_config()
    print(errors)
    assert len(errors) == 1