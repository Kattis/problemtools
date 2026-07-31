#!/bin/bash
set -e

cd "$(dirname "$0")"

venv/bin/pip install -q -r requirements-dev.txt
venv/bin/ruff check .
venv/bin/ruff format --check .
venv/bin/pytest
venv/bin/mypy --non-interactive --config-file mypy.ini -p problemtools
