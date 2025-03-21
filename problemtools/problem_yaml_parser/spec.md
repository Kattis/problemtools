Specification is built up of a recursive definition of items, inspired by json-schemas.

Each item has to contain the field "type" with one of the defined types.

# Common fields for all types
## default
The field "default" will hold the fallback-value in the case that the user-defined value
does not exist or could not be parsed. Each type will have a standard-default that will
be used if default is not specified.

## type
Each item has to contain a type, which is one of the types defined. This decides what
type will end up there in the final result.

## flags
List of flags that can be used to signal things about this item.
- "deprecated": if specified in user config, give deprecation-warning

## parsing
If this item requires more complex parsing, a parsing rule can be added. This field is
a string that will map to one of the available parsing rules. A parsing rule can require
other fields to be initialized before it allows the parsing to happen.

Parsing rules will be defined with the following information:
- name of the rule
- type of the output
- prerequisite fields that should be validated before this one


# Types
The following are the types available to be specified.

## object
Standard default: {}

Has the following properties:
- "required": List of all strictly required properties, will give an error if one is missing
- "properties": Dictionary of property-names to their types

## list
Standard default: []

Has the following properties:
- "content": Specification of type contained within list

## string
Standard default: ""

Has the following properties:
- "alternatives": If specified, one of these have to match the string provided in the config. Additional rules may be associated for different alternatives. Multiple rules may be matched to one alternative, in which case all checks will be triggered.
    - "warn": _message_, send a the _message_ as a warning if alternative is matched
    - "forbid": [Path], forbid any value other than the default standard for all paths in list
    - "require": [Path], require all values to be different from the default standard of the type for all paths in list

"foo/bar/baz"
"foo/bar/baz:asd"

## int
Standard default: 0

Properties:
- minimum: _value_, minimum value allowed
- maximum: _value_, maximum value allowed

## float
Standard default: 0.0

Properties:
- minimum: _value_, minimum value allowed
- maximum: _value_, maximum value allowed

## bool
Standard default: False

"alternatives": {
    True: {
        "warn": "message",
        "forbid": [Path]
    },
    False: {
        "warn": "message",
        "forbid": [Path]
    }
}


No properties

# Stages
There are a couple of stages that will happen when loading and verifying config.

1. Data is loaded and compared to format-specfication-document. Parsing rules are applied in an order that resolves dependencies.
2. External data is injected.
3. copy-from directives are executed in an order such that all are resolved.
4. Checks are performed, like the ones in the string-types alternatives.