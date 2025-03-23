from problemtools.config_parser import Metadata
from problemtools.config_parser import SpecificationError
from helper import construct_metadata, warnings, errors

def test_misspelled_type():
    try:
        construct_metadata('config_type_misspelled.yaml', 'follows_config_misspelled.yaml', {})
        assert False, 'Should have raised SpecificationError'

    except SpecificationError as e:
        e = str(e)
        assert e.startswith("Specification did not have a MUST HAVE field 'type',")
    print(f'warnings: {warnings}')
    print(f'errors: {errors}')

def test_misspelled_typevalue():
    try:
        construct_metadata('config_type_value_misspelled.yaml', 'follows_config_misspelled.yaml', {})
        assert False, 'Should have raised SpecificationError'
    except SpecificationError as e:
        e = str(e)
        assert e.startswith('Type ')
        assert 'is not a valid type. Did you mean:' in e
    print(f'warnings: {warnings}')
    print(f'errors: {errors}')

def test_misspelled_field():
    try:
        construct_metadata('config_field_misspelled.yaml', 'follows_config_misspelled.yaml', {})
        assert False, 'Should have raised SpecificationError'
    except SpecificationError as e:
        e = str(e)
        assert e.startswith('Field ')
        assert ' is not allowed for type ' in e
    print(f'warnings: {warnings}')
    print(f'errors: {errors}')

def test_misspelled_alternatives():
    try:
        construct_metadata('config_alternatives_misspelled.yaml', 'follows_config_misspelled.yaml', {})
        assert False, 'Should have raised SpecificationError'
    except SpecificationError as e:
        e = str(e)
        assert e == 'Bool match string should be either "true" or "false"'

    print(f'warnings: {warnings}')
    print(f'errors: {errors}')