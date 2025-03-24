from problemtools.config_parser import Metadata
from yaml import safe_load
import os

base_dir = os.path.join(os.path.dirname(__file__), 'config')

def load_yaml(filename) -> dict:
    with open(os.path.join(base_dir, filename), 'r') as f:
        content = safe_load(f)
    return content

warnings = []
errors = []

def warnings_add(text: str):
    warnings.append(text)

def errors_add(text: str):
    errors.append(text)

def construct_metadata(spec_file, config_file, injected_data) -> Metadata:
    errors.clear()
    warnings.clear()
    spec = load_yaml(spec_file)
    config = load_yaml(config_file)
    md = Metadata(spec)
    md.set_error_callback(errors_add)
    md.set_warning_callback(warnings_add)
    md.load_config(config, injected_data)
    return md