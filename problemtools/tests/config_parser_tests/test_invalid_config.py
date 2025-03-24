from problemtools.config_parser import Metadata
from problemtools.config_parser import SpecificationError
from helper import construct_metadata, warnings, errors

def run_test(config_yaml, follows_config_yaml, starts_with_error=None, additional_assert_function=None):
    """
    Run a basic test and check for raised SpecificationError message.
    """
    try:
        construct_metadata(config_yaml, follows_config_yaml, {})
        assert False, 'Should have raised SpecificationError'

    except SpecificationError as e:
        e = str(e)
        if starts_with_error:
            assert e.startswith(starts_with_error)
        if additional_assert_function:
            assert additional_assert_function(e)

    print(f'warnings: {warnings}')
    print(f'errors: {errors}')

def test_misspelled_type():
    run_test(
        'config_type_misspelled.yaml',
        'follows_config_misspelled.yaml',
        starts_with_error="Specification did not have a MUST HAVE field 'type',"
    )

def test_misspelled_typevalue():
    run_test(
        'config_type_value_misspelled.yaml',
        'follows_config_misspelled.yaml',
        starts_with_error='Type ',
        additional_assert_function=lambda e: 'is not a valid type. Did you mean:' in e
    )

def test_misspelled_field():
    run_test(
        'config_field_misspelled.yaml',
        'follows_config_misspelled.yaml',
        starts_with_error='Field ',
        additional_assert_function=lambda e: ' is not allowed for type ' in e
    )

def test_misspelled_true_alternatives_1():
    run_test(
        'config_alternatives_bool_misspelled_1.yaml',
        'follows_config_misspelled.yaml',
        starts_with_error='Bool match string should be either "true" or "false"'
    )

def test_misspelled_true_alternatives_2():
    run_test(
        'config_alternatives_bool_misspelled_2.yaml',
        'follows_config_misspelled.yaml',
        starts_with_error='Bool match string should be either "true" or "false"'
    )