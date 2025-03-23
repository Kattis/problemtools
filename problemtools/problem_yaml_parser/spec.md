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
- "alternatives": See section "alternatives"

## int
Standard default: 0

Properties:
- "alternatives": See section "alternatives"

## float
Standard default: 0.0

Properties:
- "alternatives": See section "alternatives"

## bool
Standard default: False

Properties:
- "alternatives": See section "alternatives"

# Stages
There are a couple of stages that will happen when loading and verifying config.

1. Data is loaded and compared to format-specfication-document. Parsing rules are applied in an order that resolves dependencies.
2. External data is injected.
3. copy-from directives are executed in an order such that all are resolved.
4. Checks are performed, like the ones in the string-types alternatives.

# alternatives
This is a property that exists on the types string, bool, ints and floats.

The value of "alternatives" is a dictionary, with keys that indicate certain "matches", see section about "matching" for different types for more details. Each match is a key that maps to another dictionary with checks. Further info can be found about these checks in the "Checks" section. Below is an example of how the property can look on a string-parameter.


```yaml
type: string
default: unknown
alternatives:
    unknown:
        warn: License is unknown
        require:
        - rights_owner: ".+"
    cc0|cc by|cc by-sa|educational|permission:
        require:
        - rights_owner: ".+"
    public domain:
        forbid:
        - rights_owner: ".+"
```

## matching
The following formats are used to match the different types.
### string
For strings, matches will be given as regex strings.
### bool
For bools, the values "true" and "false" will be given and compared like expected. This check is case-insensitive.
### int
For ints, matches will be given as a string formated like "A:B", where A and B are integers. This will form an inclusive interval that is matched. A or B may be excluded to indicate that one endpoint is infinite. A single number may also be provided, which will match only that number. All numbers should be given in decimal notation.

### float
Similar to int, but A and B are floats instead of integers. Single numbers may not be provided due to floating point imprecisions. The floats should be able to be parsed using Python's built in float parsing.

## Checks
Each alternative may provide certain checks. The checks are described in the following subsections. Each check has a name and an argument, with the name being a key in the dictionary for that alternative, and the argument being the value for that key.

If the value found in the parsed config does not match any value in the alternatives, this will generate an error. If alternatives is not provided in the config, this will be treated as all alternatives being okay without any checks.

### warn
If this check is provided, a warning will be generated with the text in the argument if the alternative is matched. This can be used to give an indication that an alternative should preferrably not be used, like an unknown license.

### require
This check ensures certain properties in the config match a certain value (see "matches" for further details about matching). The argument is a list of dictionaries which map a path to a property to the value it should match to. If it does not match, an error will be generated during the check stage.

### forbid
Works the same as require, but instead of requiring the properties to match, it forbids them from matching.