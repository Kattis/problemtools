#!/bin/bash

set -e

ROOT=$(readlink -f $(dirname $0)/..)
VERSION=$(git describe)

cat <<EOF > $ROOT/problemtools/_version.py
# Auto-generated from git changelog, do not edit!
__version__ = '$VERSION'
EOF
