import collections
import os
import yaml
from pathlib import Path
from typing import Mapping


class ConfigError(Exception):
    pass


def load_config(configuration_file: str, priority_dirs: list[Path] = []) -> dict:
    """Load a problemtools configuration file.

    Args:
        configuration_file (str): name of configuration file.  Name is
        relative to config directory so typically just a file name
        without paths, e.g. "languages.yaml".
    """
    res: dict | None = None

    for dirname in __config_file_paths() + priority_dirs:
        path = dirname / configuration_file
        new_config = None
        if path.is_file():
            try:
                with open(path, 'r') as config:
                    new_config = yaml.safe_load(config.read())
            except (yaml.parser.ParserError, yaml.scanner.ScannerError) as err:
                raise ConfigError(f'Config file {path}: failed to parse: {err}')
        if res is None:
            if new_config is None:
                raise ConfigError(f'Base configuration file {configuration_file} not found in {path}')
            res = new_config
        elif new_config is not None:
            __update_dict(res, new_config)

    assert res is not None, 'Failed to load config (should never happen, we should have hit an error in loop above)'
    return res


def __config_file_paths() -> list[Path]:
    """
    Paths in which to look for config files, by increasing order of
    priority (i.e., any config in the last path should take precedence
    over the others).
    """
    return [
        Path(__file__).parent / 'config',
        Path('/etc/kattis/problemtools'),
        Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'problemtools',
    ]


def __update_dict(orig: dict, update: Mapping) -> None:
    """Deep update of a dictionary

    For each entry (k, v) in update such that both orig[k] and v are
    dictionaries, orig[k] is recurisvely updated to v.

    For all other entries (k, v), orig[k] is set to v.
    """
    for key, value in update.items():
        if key in orig and isinstance(value, collections.abc.Mapping) and isinstance(orig[key], collections.abc.Mapping):
            __update_dict(orig[key], value)
        else:
            orig[key] = value
