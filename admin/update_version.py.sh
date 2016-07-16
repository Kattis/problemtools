#!/bin/bash

set -e

ROOT=$(readlink -f $(dirname $0)/..)

if (($# > 0)); then
    VERSION=$1
else
    VERSION=$(git describe)
fi

cat <<EOF > $ROOT/problemtools/_version.py
# Auto-generated from git changelog, do not edit!
__version__ = '$VERSION'
EOF
