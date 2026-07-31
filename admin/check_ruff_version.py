# Run from your venv with repo root as cwd. E.g., venv/bin/python3 admin/check_ruff_version.py
"""Fail if the installed ruff version differs from .pre-commit-config.yaml's pinned rev."""

import pathlib
import subprocess
import sys

import yaml


def installed_ruff_version() -> str:
    ruff = pathlib.Path(sys.executable).parent / 'ruff'
    output = subprocess.check_output([ruff, '--version'], text=True)
    return output.strip().split()[-1]


def precommit_ruff_rev() -> str:
    with open('.pre-commit-config.yaml') as f:
        config = yaml.safe_load(f)
    for repo in config['repos']:
        if 'ruff-pre-commit' in repo['repo']:
            return repo['rev'].lstrip('v')
    raise RuntimeError('ruff-pre-commit repo not found in .pre-commit-config.yaml')


def main() -> int:
    installed = installed_ruff_version()
    pinned = precommit_ruff_rev()
    if installed != pinned:
        print(
            f'ruff version mismatch: installed ruff is {installed}, but '
            f'.pre-commit-config.yaml pins v{pinned}. Keep requirements-dev.in '
            f'and .pre-commit-config.yaml in sync.',
            file=sys.stderr,
        )
        return 1
    print(f'ruff version {installed} matches .pre-commit-config.yaml')
    return 0


if __name__ == '__main__':
    sys.exit(main())
