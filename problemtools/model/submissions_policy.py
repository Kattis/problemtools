"""What's expected of example submissions, and parsing of submissions.yaml into it."""

from dataclasses import dataclass, field
from typing import Any, Literal, cast

from ..globs import Glob
from ..submission_rules import PermittedRule, RequiredRule, Rule, ScoreRule
from . import Verdict
from .paths import RelativePath


@dataclass(frozen=True)
class TimeLimitBound:
    """The submission's runtime on the test cases in `scope` bounds the time limit: from below
    (the time limit must be comfortably above the runtime) or from above (comfortably below it)."""

    scope: Glob
    direction: Literal['lower', 'upper']


@dataclass(frozen=True)
class SubmissionsEntry:
    """What's expected of the submissions matched by `glob` (covering, so a directory matches all
    submissions in it). Comes from the defaults for the problem format, or from a key in
    submissions.yaml. `is_default` is set for entries from the defaults."""

    glob: Glob
    rules: list[Rule] = field(default_factory=list)
    time_limit_bounds: list[TimeLimitBound] = field(default_factory=list)
    language: str | None = None
    entrypoint: str | None = None
    model_solution: bool = False
    is_default: bool = False


@dataclass(frozen=True)
class SubmissionsPolicy:
    """All entries describing what's expected of submissions. A submission gets the rules and time
    limit bounds of every entry matching it.

    `parse_errors` describes the parts of submissions.yaml that couldn't be parsed, and thus aren't
    included in `entries`."""

    entries: list[SubmissionsEntry]
    parse_errors: list[str] = field(default_factory=list)

    def entries_for(self, path: RelativePath) -> list[SubmissionsEntry]:
        """The entries matching a submission, `path` being relative to the submissions directory."""
        return [entry for entry in self.entries if entry.glob.covers(path)]


_VERDICTS = frozenset({'AC', 'WA', 'TLE', 'RTE'})
#: Keys that can be given both for submissions, and for test data within them
_REQUIREMENT_KEYS = frozenset({'permitted', 'required', 'score', 'use_for_time_limit'})


def parse_submissions_yaml(data: Any) -> tuple[list[SubmissionsEntry], list[str]]:
    """Parse the contents of submissions.yaml (as loaded by yaml.safe_load) into entries.

    Never raises on bad content. Instead, anything that can't be parsed is left out (as small a part
    as possible, e.g. a single key), and described in the returned list of errors.

    This is hand-rolled rather than using pydantic (as we do for problem.yaml) for two reasons:
    - Pydantic validation is all-or-nothing per model, while we want to drop only the invalid parts,
      so that a single typo doesn't stop us from checking the rest of the submissions.
    - The format mixes fixed keys with arbitrary ones: under a submission glob, any key that isn't a
      known key (permitted, language, ...) is a test data glob. That's awkward to express in pydantic.

    Duplicate keys in the YAML are not detected: yaml.safe_load silently keeps the last value. See
    https://github.com/Kattis/problemtools/issues/462, which tracks the same issue for testdata.yaml."""
    if data is None:
        return [], []
    if not isinstance(data, dict):
        return [], [f'expected a mapping from submission globs to requirements, got {_describe(data)}']
    errors: list[str] = []
    entries = []
    for key, value in data.items():
        entry = _parse_entry(key, value, errors)
        if entry is not None:
            entries.append(entry)
    return entries, errors


def _parse_entry(key: Any, value: Any, errors: list[str]) -> SubmissionsEntry | None:
    glob = _parse_glob(key, 'submission glob', errors)
    if glob is None:
        return None
    where = repr(key)
    if not isinstance(value, dict):
        errors.append(f'{where}: expected a mapping, got {_describe(value)}')
        return None

    rules: list[Rule] = []
    bounds: list[TimeLimitBound] = []
    language = entrypoint = None
    model_solution = False
    for k, v in value.items():
        if k in _REQUIREMENT_KEYS:
            _parse_requirement(k, v, Glob(''), where, rules, bounds, errors)
            continue
        match k:
            case 'language':
                language = _parse_str(v, f'{where}: language', errors)
            case 'entrypoint':
                entrypoint = _parse_str(v, f'{where}: entrypoint', errors)
            case 'model_solution':
                if isinstance(v, bool):
                    model_solution = v
                else:
                    errors.append(f'{where}: model_solution: expected true or false, got {_describe(v)}')
            case 'authors':
                pass  # Not used for anything, so we don't bother parsing it
            case _:
                # Anything else is a glob on test data, with requirements for that test data
                _parse_test_data_requirements(k, v, where, rules, bounds, errors)

    return SubmissionsEntry(
        glob=glob,
        rules=rules,
        time_limit_bounds=bounds,
        language=language,
        entrypoint=entrypoint,
        model_solution=model_solution,
    )


def _parse_test_data_requirements(
    key: Any, value: Any, where: str, rules: list[Rule], bounds: list[TimeLimitBound], errors: list[str]
) -> None:
    scope = _parse_glob(key, f'{where}: test data glob', errors)
    if scope is None:
        return
    where = f'{where}, {key!r}'
    if not isinstance(value, dict):
        errors.append(f'{where}: expected a mapping, got {_describe(value)}')
        return
    for k, v in value.items():
        if k in _REQUIREMENT_KEYS:
            _parse_requirement(k, v, scope, where, rules, bounds, errors)
        else:
            errors.append(f'{where}: unknown key {k!r}')


def _parse_requirement(
    key: str, value: Any, scope: Glob, where: str, rules: list[Rule], bounds: list[TimeLimitBound], errors: list[str]
) -> None:
    """Parse one of the _REQUIREMENT_KEYS, appending to `rules` or `bounds` on success."""
    where = f'{where}: {key}'
    match key:
        case 'permitted' | 'required':
            verdicts = _parse_verdicts(value, where, errors)
            if verdicts is not None:
                rule_class = PermittedRule if key == 'permitted' else RequiredRule
                rules.append(rule_class(scope=scope, verdicts=verdicts))
        case 'score':
            score = _parse_score(value, where, errors)
            if score is not None:
                rules.append(ScoreRule(scope=scope, min_score=score[0], max_score=score[1]))
        case 'use_for_time_limit':
            if value in ('lower', 'upper'):
                bounds.append(TimeLimitBound(scope=scope, direction=value))
            else:
                errors.append(f"{where}: expected 'lower' or 'upper', got {_describe(value)}")
        case _:
            raise AssertionError(f'Unhandled requirement key {key!r}')


def _parse_glob(value: Any, what: str, errors: list[str]) -> Glob | None:
    if not isinstance(value, str):
        errors.append(f'{what} must be a string, got {_describe(value)}')
        return None
    try:
        return Glob(value)
    except ValueError as e:
        errors.append(f'{what}: {e}')
        return None


def _parse_str(value: Any, where: str, errors: list[str]) -> str | None:
    if isinstance(value, str):
        return value
    errors.append(f'{where}: expected a string, got {_describe(value)}')
    return None


def _parse_verdicts(value: Any, where: str, errors: list[str]) -> frozenset[Verdict] | None:
    if not isinstance(value, list) or not all(v in _VERDICTS for v in value):
        errors.append(f'{where}: expected a list of verdicts ({", ".join(sorted(_VERDICTS))}), got {_describe(value)}')
        return None
    return frozenset(cast(list[Verdict], value))


def _parse_score(value: Any, where: str, errors: list[str]) -> tuple[float, float] | None:
    """A score is either a number, or a list [min, max] of two numbers."""
    if _is_number(value):
        return float(value), float(value)
    if isinstance(value, list) and len(value) == 2 and all(_is_number(v) for v in value):
        if value[0] <= value[1]:
            return float(value[0]), float(value[1])
        errors.append(f'{where}: the minimum score is larger than the maximum, in {_describe(value)}')
        return None
    errors.append(f'{where}: expected a number, or a list [min, max] of two numbers, got {_describe(value)}')
    return None


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _describe(value: Any) -> str:
    """Describe a value parsed from YAML, for use in an error message."""
    return 'nothing' if value is None else repr(value)
