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

## More might be added...

# Types

## object
Standard default: {}

Has the following properties:
- "required": List of all strictly required properties, will give an error if one is missing
- ""

## list
Standard default: []

## string
Standard default: ""

## int
standard default: 0

## float
standard default: 0.0
