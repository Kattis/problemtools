# -*- coding: utf-8 -*-
import pytest

from problemtools import config

def config_paths_mock():
    import os
    return [os.path.join(os.path.dirname(__file__), 'config1'),
            os.path.join(os.path.dirname(__file__), 'config2')]


def test_load_basic_config(monkeypatch):
    monkeypatch.setattr(config, '__config_file_paths', config_paths_mock)

    conf = config.load_config('test.yaml')
    assert conf == {'prop1': 'hello', 'prop2': 5}


def test_load_updated_config(monkeypatch):
    monkeypatch.setattr(config, '__config_file_paths', config_paths_mock)

    conf = config.load_config('test2.yaml')
    assert conf == {'prop1': 'abc', 'prop2': 23, 'prop3': ['hello', 'world']}


def test_load_missing_config(monkeypatch):
    monkeypatch.setattr(config, '__config_file_paths', config_paths_mock)

    with pytest.raises(config.ConfigError):
        config.load_config('non_existent_file')


def test_load_broken_config(monkeypatch):
    monkeypatch.setattr(config, '__config_file_paths', config_paths_mock)

    with pytest.raises(config.ConfigError):
        config.load_config('broken.yaml')


def test_update_dict():
    update_dict = config.__dict__['__update_dict']

    dict1 = {'a': 1, 'b': {'sub1': 1, 'sub2': False}, 'c': 3}
    dict2 = {'b': {'sub3': 'new', 'sub2': 47}}
    dict3 = {'a': 0, 'b': 12}

    update_dict(dict1, dict2)
    assert dict1 == {'a': 1, 'b': {'sub1': 1, 'sub2': 47, 'sub3': 'new'}, 'c': 3}

    update_dict(dict1, dict3)
    assert dict1 == {'a': 0, 'b': 12, 'c': 3}
