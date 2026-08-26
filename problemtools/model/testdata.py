from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from re import Pattern
from typing import Any

import yaml

from .. import config
from ..metadata import Metadata

DEFAULT_CONFIG = config.load_config('testdata.yaml')
SCORING_ONLY_KEYS = ['accept_score', 'reject_score', 'range']


@dataclass(frozen=True)
class TestCase:
    """A single test case: an input file paired with its answer file.

    `path` is relative to the data directory and has no extension, e.g. for
    data/secret/hello.in, path is secret/hello."""

    infile: Path
    ansfile: Path
    path: Path
    input_validator_flags: list[str]
    output_validator_flags: list[str]

    def __str__(self) -> str:
        return f'testcase {self.path}'

    def matches_filter(self, filter_re: Pattern[str]) -> bool:
        return filter_re.search(str(self.path)) is not None

    def is_in_sample_group(self) -> bool:
        return str(self.path).startswith('sample')

    def get_all_testcases(self) -> list[TestCase]:
        return [self]


@dataclass(frozen=True)
class TestDataGroup:
    """A group of test cases and/or nested test case groups, configured by testdata.yaml.

    `config` is the fully merged configuration for this group: own testdata.yaml, overlaid on
    the parent group's config, overlaid with legacy per-problem grading overrides, overlaid with
    package defaults."""

    name: str
    datadir: Path
    config: dict[str, Any]
    is_root: bool
    items: list[TestCase | TestDataGroup] = field(default_factory=list)

    def __str__(self) -> str:
        return f'testcase group {self.name}'

    def matches_filter(self, filter_re: Pattern[str]) -> bool:
        return True

    def get_testcases(self) -> list[TestCase]:
        return [item for item in self.items if isinstance(item, TestCase)]

    def get_subgroups(self) -> list[TestDataGroup]:
        return [item for item in self.items if isinstance(item, TestDataGroup)]

    def get_all_testcases(self) -> list[TestCase]:
        result: list[TestCase] = []
        for item in self.items:
            result.extend(item.get_all_testcases())
        return result

    def has_custom_groups(self) -> bool:
        return any(group.get_subgroups() for group in self.get_subgroups())

    def get_score_range(self) -> tuple[float, float]:
        try:
            score_range = self.config['range']
            min_score, max_score = list(map(float, score_range.split()))
            return (min_score, max_score)
        except Exception:
            return (float('-inf'), float('inf'))


def load_testdata(probdir: Path, metadata: Metadata) -> TestDataGroup:
    """Load the full testdata tree rooted at <probdir>/data."""
    return _load_group(probdir, probdir / 'data', {}, metadata, is_root=True)


def _load_group_config(datadir: Path) -> dict[str, Any]:
    configfile = datadir / 'testdata.yaml'
    if not configfile.is_file():
        return {}
    loaded = yaml.safe_load(configfile.read_text())
    return loaded if loaded is not None else {}


def _load_group(probdir: Path, datadir: Path, parent_config: dict[str, Any], metadata: Metadata, is_root: bool) -> TestDataGroup:
    name = os.path.relpath(datadir, probdir).replace(os.sep, '.')

    merged_config = _load_group_config(datadir)

    # For non-root groups, missing properties are inherited from the parent group
    for key, parent_value in parent_config.items():
        merged_config.setdefault(key, parent_value)

    # TODO: Decide if these should stay
    # Some deprecated properties are inherited from problem config during a transition period
    legacy_grading = metadata.legacy_grading
    for key in ['accept_score', 'reject_score', 'range']:
        value = getattr(legacy_grading, key)
        if value is not None:
            merged_config[key] = value
    if legacy_grading.on_reject == 'first_error':
        merged_config['on_reject'] = 'break'
    if legacy_grading.on_reject == 'grade':
        merged_config['on_reject'] = 'continue'

    if metadata.is_pass_fail():
        for key in SCORING_ONLY_KEYS:
            merged_config.setdefault(key, None)

    for key, default in DEFAULT_CONFIG.items():
        merged_config.setdefault(key, default)

    items: list[TestCase | TestDataGroup] = []
    if datadir.is_dir():
        for entry in sorted(datadir.iterdir()):
            if entry.is_dir():
                items.append(_load_group(probdir, entry, merged_config, metadata, is_root=False))
            elif entry.suffix == '.ans' and entry.with_suffix('.in').is_file():
                items.append(_load_testcase(entry, probdir / 'data', merged_config, metadata))
    return TestDataGroup(name=name, datadir=datadir, config=merged_config, is_root=is_root, items=items)


def _load_testcase(ansfile: Path, data_root: Path, group_config: dict[str, Any], metadata: Metadata) -> TestCase:
    infile = ansfile.with_suffix('.in')
    return TestCase(
        infile=infile,
        ansfile=ansfile,
        path=infile.with_suffix('').relative_to(data_root),
        input_validator_flags=group_config['input_validator_flags'].split(),
        output_validator_flags=(metadata.legacy_validator_flags.split() + group_config.get('output_validator_flags', '').split()),
    )
