import copy
import datetime
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal, Self, Type, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from . import config
from . import formatversion


class ProblemType(StrEnum):
    PASS_FAIL = 'pass-fail'
    SCORING = 'scoring'
    MULTI_PASS = 'multi-pass'
    INTERACTIVE = 'interactive'
    SUBMIT_ANSWER = 'submit-answer'


class License(StrEnum):
    UNKNOWN = 'unknown'
    PUBLIC_DOMAIN = 'public domain'
    CC0 = 'cc0'
    CC_BY = 'cc by'
    CC_BY_SA = 'cc by-sa'
    EDUCATIONAL = 'educational'
    PERMISSION = 'permission'


@dataclass
class Person:
    name: str
    email: str | None = None
    orcid: str | None = None
    kattis: str | None = None

    @classmethod
    def from_string(cls: Type[Self], s: str) -> Self:
        match = re.match(r'^(.*?)\s+<(.*)>$', s.strip())
        if match:
            return cls(name=match.group(1), email=match.group(2))
        return cls(name=s)


@dataclass
class Source:
    name: str
    url: str | None = None


@dataclass
class TimeMultipliers:
    ac_to_time_limit: float = 2.0
    time_limit_to_tle: float = 1.5


@dataclass
class Limits:
    memory: int
    output: int
    code: int
    compilation_time: int
    compilation_memory: int
    validation_time: int
    validation_memory: int
    validation_output: int
    time_multipliers: TimeMultipliers = field(default_factory=TimeMultipliers)
    time_limit: float | None = None
    time_resolution: float = 1.0
    validation_passes: int = 2


@dataclass
class Credits:
    """
    Credits format where all persons have been converted to Person objects.
    For use in our internal representation.
    """

    authors: list[Person] = field(default_factory=list)
    contributors: list[Person] = field(default_factory=list)
    testers: list[Person] = field(default_factory=list)
    translators: dict[str, list[Person]] = field(default_factory=dict)
    packagers: list[Person] = field(default_factory=list)
    acknowledgements: list[Person] = field(default_factory=list)


@dataclass
class InputCredits:
    """
    A more permissive dataclass for credits, as the input in 2023-07 looks.
    For use when validating input.
    """

    # Type in the input format is messy
    PersonOrPersons = Union[str | list[Union[Person, str]]]

    authors: PersonOrPersons = field(default_factory=list)
    contributors: PersonOrPersons = field(default_factory=list)
    testers: PersonOrPersons = field(default_factory=list)
    translators: dict[str, PersonOrPersons] = field(default_factory=dict)
    packagers: PersonOrPersons = field(default_factory=list)
    acknowledgements: PersonOrPersons = field(default_factory=list)


class Metadata2023_07(BaseModel):
    """
    The metadata for a problem as input in version 2023-07-draft.
    """

    problem_format_version: str
    name: dict[str, str] | str
    uuid: UUID
    type: list[ProblemType] | ProblemType = ProblemType.PASS_FAIL
    version: str | None = None
    credits: dict | str | None = None
    source: list[Union[str, Source]] | Source | str = []
    license: License = License.UNKNOWN
    rights_owner: str | None = None
    embargo_until: datetime.datetime | None = None
    limits: Limits
    keywords: list[str] = []
    languages: list[str] | Literal['all'] = 'all'
    allow_file_writing: bool = True
    constants: dict[str, int | float | str] = {}

    model_config = ConfigDict(extra='forbid')


@dataclass
class LegacyGrading:
    objective: Literal['max', 'min'] = 'max'
    show_test_data_groups: bool = False
    # These 3 fields predate the version called "legacy"
    accept_score: float | None = None
    reject_score: float | None = None
    range: str | None = None
    on_reject: Literal['first_error', 'worst_error', 'grade'] | None = None


@dataclass
class LegacyLimits:
    memory: int
    output: int
    code: int
    compilation_time: int
    compilation_memory: int
    validation_time: int
    validation_memory: int
    validation_output: int
    time_multiplier: float = 5.0
    time_safety_margin: float = 2.0


class MetadataLegacy(BaseModel):
    """
    The metadata for a problem as input in version legacy (plus a few fields
    which pre-date the version called legacy).
    """

    problem_format_version: str = formatversion.VERSION_LEGACY
    type: Literal['pass-fail'] | Literal['scoring'] = 'pass-fail'
    name: str | None = None
    uuid: UUID | None = None
    author: str | None = None
    source: str | None = None
    source_url: str | None = None
    license: License = License.UNKNOWN
    rights_owner: str | None = None
    limits: LegacyLimits
    validation: str = 'default'
    validator_flags: str = ''
    grading: LegacyGrading = LegacyGrading()
    keywords: str = ''

    model_config = ConfigDict(extra='forbid')


class Metadata(BaseModel):
    """
    The metadata for a problem, as used internally in problemtools. Closely
    follows the 2023-07-draft version, but is more fully parsed, and adds
    a few legacy fields to represent information not in 2023-07.

    Metadata serializes to a valid 2023-07-draft configuration.
    """

    problem_format_version: str
    type: list[str]
    name: dict[str, str]
    uuid: UUID | None
    version: str | None
    credits: Credits
    source: list[Source]
    license: License
    rights_owner: str | None
    embargo_until: datetime.datetime | None
    limits: Limits
    keywords: list[str]
    languages: list[str] | Literal['all']
    allow_file_writing: bool
    constants: dict
    legacy_grading: LegacyGrading = Field(default_factory=LegacyGrading, exclude=True)
    legacy_validation: str = Field(default='', exclude=True)
    legacy_validator_flags: str = Field(default='', exclude=True)
    legacy_custom_score: bool = Field(default=False, exclude=True)  # True iff legacy_validation is custom and score.

    model_config = ConfigDict(extra='forbid')

    def is_pass_fail(self) -> bool:
        return not self.is_scoring()

    def is_scoring(self) -> bool:
        return ProblemType.SCORING in self.type

    def is_interactive(self) -> bool:
        return ProblemType.INTERACTIVE in self.type

    @classmethod
    def from_legacy(cls: Type[Self], legacy: MetadataLegacy, names_from_statements: dict[str, str]) -> Self:
        metadata = legacy.model_dump()
        metadata['type'] = [metadata['type']]
        # Support for *ancient* problems where names_from_statements is empty
        metadata['name'] = names_from_statements if names_from_statements else {'': metadata['name']}
        metadata['version'] = None

        def parse_author_field(author: str) -> list[Person]:
            authors = re.split(r',\s*|\s+and\s+|\s+&\s+', author)
            authors = [x.strip(' \t\r\n') for x in authors]
            authors = [x for x in authors if len(x) > 0]
            return [Person.from_string(author) for author in authors]

        metadata['credits'] = {}
        if metadata['author'] is not None:
            metadata['credits']['authors'] = parse_author_field(metadata['author'])
        del metadata['author']
        metadata['source'] = [] if metadata['source'] is None else [Source(metadata['source'], metadata['source_url'])]
        del metadata['source_url']
        metadata['embargo_until'] = None
        metadata['limits']['time_multipliers'] = {
            'ac_to_time_limit': metadata['limits']['time_multiplier'],
            'time_limit_to_tle': metadata['limits']['time_safety_margin'],
        }
        del metadata['limits']['time_multiplier']
        del metadata['limits']['time_safety_margin']
        metadata['keywords'] = metadata['keywords'].split()
        metadata['languages'] = 'all'
        metadata['allow_file_writing'] = True
        metadata['constants'] = {}

        # The interactive flag from validation now lives in type, copy it over.
        validation = metadata['validation'].split()
        if validation[0] == 'custom':
            if 'interactive' in validation[1:]:
                metadata['type'].append('interactive')
            if 'score' in validation[1:]:
                metadata['legacy_custom_score'] = True
        # Copy over the legacy info that does not fit cleanly
        for key in 'grading', 'validator_flags', 'validation':
            metadata[f'legacy_{key}'] = metadata[key]
            del metadata[key]
        return cls.model_validate(metadata)

    @classmethod
    def from_2023_07(cls: Type[Self], md2023_07: Metadata2023_07) -> Self:
        metadata = md2023_07.model_dump()
        metadata['type'] = [metadata['type']] if isinstance(metadata['type'], str) else metadata['type']
        metadata['name'] = {'en': metadata['name']} if isinstance(metadata['name'], str) else metadata['name']

        def parse_source(source: str | Source) -> Source:
            return Source(name=source, url=None) if isinstance(source, str) else source

        # Convenience function to deal with the fact that lists of persons/sources are
        # either a string, or a list of strings or dicts (if dicts, pydantic
        # already parsed those for us).
        def parse_list(callback, lst: str | list) -> list:
            if isinstance(lst, str):
                return [callback(lst)]
            return list(map(callback, lst))

        metadata['source'] = parse_list(parse_source, metadata['source'])

        def parse_person(person: str | Person) -> Person:
            return Person.from_string(person) if isinstance(person, str) else person

        if metadata['credits'] is None:
            metadata['credits'] = {}
        elif isinstance(metadata['credits'], str):
            metadata['credits'] = {'authors': [parse_person(metadata['credits'])]}
        else:
            for key in metadata['credits']:
                if key == 'translators':  # special case, we nest deeper here
                    for lang in metadata['credits'][key]:
                        metadata['credits'][key][lang] = parse_list(parse_person, metadata['credits'][key][lang])
                else:
                    metadata['credits'][key] = parse_list(parse_person, metadata['credits'][key])
        return cls.model_validate(metadata)


def parse_metadata(
    version: formatversion.FormatData, problem_yaml_data: dict[str, Any], names_from_statements: dict[str, str]
) -> Metadata:
    """
    Parses a data structure from problem.yaml into a Metadata model
    :raises pydantic.ValidationError: We intentionally leak pydantic's exception on errors, as it's well designed
    """

    # We need to mix in the system default config values before doing model validation
    data = copy.deepcopy(problem_yaml_data)
    # Check if the user has done something silly like making limits a string. If so, we
    # don't merge in anything, and let pydantic complain later.
    if isinstance(data.get('limits', {}), dict):
        system_defaults = config.load_config('problem.yaml')
        data['limits'] = system_defaults['limits'] | data.get('limits', {})

    if version.name == formatversion.VERSION_LEGACY:
        legacy_model = MetadataLegacy.model_validate(data)
        return Metadata.from_legacy(legacy_model, names_from_statements)
    else:
        assert version.name == formatversion.VERSION_2023_07
        model_2023_07 = Metadata2023_07.model_validate(data)
        return Metadata.from_2023_07(model_2023_07)
