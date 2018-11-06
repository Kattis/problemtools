#!/usr/bin/env bash

set -e

ROOT=$(readlink -f $(dirname $0)/..)

if (($# > 0)); then
    VERSION=$1
else
    VERSION=$(git describe)
    # remove leading 'v' from git tag
    VERSION=${VERSION:1}
    # PEP440 compliance: change "-{#commits}-{last commit ID}" suffix to ".dev{#commits}"
    VERSION=$(echo $VERSION | sed -r "s/-(.*)-.*$/.dev\1/g")
fi

cat <<EOF > $ROOT/problemtools/_version.py
# Auto-generated from git changelog, do not edit!
__version__ = '$VERSION'
EOF

echo $VERSION
