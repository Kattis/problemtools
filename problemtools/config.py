import collections
import os
import yaml


class ConfigError(Exception):
    pass


def load_config(configuration_file):
    """Load a problemtools configuration file.

    Args:
        configuration_file (str): name of configuration file.  Name is
        relative to config directory so typically just a file name
        without paths, e.g. "languages.yaml".
    """
    res = None

    for dirname in __config_file_paths():
        path = os.path.join(dirname, configuration_file)
        new_config = None
        if os.path.isfile(path):
            try:
                with open(path, 'r') as config:
                    new_config = yaml.safe_load(config.read())
            except (yaml.parser.ParserError, yaml.parser.ScannerError) as err:
                raise ConfigError('Config file %s: failed to parse: %s' % (path, err))
        if res is None:
            if new_config is None:
                raise ConfigError('Base configuration file %s not found in %s'
                                  % (configuration_file, path))
            res = new_config
        elif new_config is not None:
            __update_dict(res, new_config)

    return res


def __config_file_paths():
    """
    Paths in which to look for config files, by increasing order of
    priority (i.e., any config in the last path should take precedence
    over the others).
    """
    return [os.path.join(os.path.dirname(__file__), 'config'),
            os.path.join('/etc', 'kattis', 'problemtools'),
            os.path.join(os.environ.get('XDG_CONFIG_HOME',
                                        os.path.join(os.path.expanduser('~'), '.config')),
                         'problemtools')]


def __update_dict(orig, update):
    """Deep update of a dictionary

    For each entry (k, v) in update such that both orig[k] and v are
    dictionaries, orig[k] is recurisvely updated to v.

    For all other entries (k, v), orig[k] is set to v.
    """
    for (key, value) in update.items():
        if (key in orig and
            isinstance(value, collections.abc.Mapping) and
            isinstance(orig[key], collections.abc.Mapping)):
            __update_dict(orig[key], value)
        else:
            orig[key] = value
