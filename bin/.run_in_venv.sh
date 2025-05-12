#!/usr/bin/env bash
#
# Helper script for the other wrapper scripts to check that a venv exists, or
# give a helpful message if it doesn't.

VENVPATH="$(dirname "$(dirname "$(readlink -f "$0")")")/venv"

if [ ! -x "$VENVPATH/bin/python" ]; then
    echo "I could not find a python venv at $VENVPATH."
    echo "To use these wrapper scripts, please set up a venv by:"
    echo " cd $(dirname "$VENVPATH")"
    echo " python3 -m venv venv"
    echo " venv/bin/pip install -r requirements.txt"
    exit 1
fi

export PYTHONPATH
PYTHONPATH="$(dirname "$(dirname "$(readlink -f "$0")")")${PYTHONPATH:+:}$PYTHONPATH"
exec "$VENVPATH/bin/python" -m "$@"
