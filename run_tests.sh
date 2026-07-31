#!/bin/bash
set -e

cd "$(dirname "$0")"

venv/bin/pip install -q -r requirements-dev.txt
if [ -f requirements.txt ]; then venv/bin/pip install -q -r requirements.txt; fi
venv/bin/python admin/check_ruff_version.py
venv/bin/ruff check .
venv/bin/ruff format --check .
venv/bin/pytest
venv/bin/mypy --non-interactive --config-file mypy.ini -p problemtools
