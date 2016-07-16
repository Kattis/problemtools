#!/bin/bash

set -e

ROOT=$(readlink -f $(dirname $0)/..)
VERSION=$(date +%Y%m%d)

if [ "$(git tag -l $VERSION)" != "" ]; then
    REV=1
    while [ "$(git tag -l $VERSION-rev$REV)" != "" ]; do
        REV=$((REV+1))
    done
    VERSION=$VERSION-rev$REV
fi

set -x

git flow release start $VERSION

git tag -a $VERSION -m "Release of version $VERSION"

# Update _version.py
$ROOT/admin/update_version.py.sh

# Update debian/changelog
git-dch $ROOT --release --new-version=$VERSION --git-author --debian-tag='%(version)s' --debian-branch=release/$VERSION --spawn-editor=never

git add $ROOT/problemtools/_version.py $ROOT/debian/changelog
git commit -m "Release of version $VERSION: bump version in problemtools/_version.py and debian/changelog"

git flow release finish $VERSION
