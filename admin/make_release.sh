#!/usr/bin/env bash
#
# Uses gbp (available through Ubuntu package git-buildpackage)

set -e

ALLOW_DIRTY=false
while getopts "d" opt; do
    case $opt in
        d) ALLOW_DIRTY=true ;;
        \?) echo "Invalid option: -$opt" ;;
    esac
done

ROOT=$(readlink -f $(dirname $0)/..)
VERSION=1.$(date +%Y%m%d)

if [ "$(git tag -l v$VERSION)" != "" ]; then
    REV=1
    while [ "$(git tag -l v$VERSION-rev$REV)" != "" ]; do
        REV=$((REV+1))
    done
    VERSION=$VERSION-rev$REV
fi


# Steps:
#   Pick a version (done by the above loop)
#   Update debian/changelog using gbp
#   Create and merge pull request with the updated debian/changelog
#   Create a github release (using web UI) or gh
#   Push to pypi using github action
#   Push to docker using admin/update_docker.sh v$VERSION

CHANGELOG_VERSION=$(dpkg-parsechangelog -l $ROOT/debian/changelog --show-field Version)
if [[ $CHANGELOG_VERSION == $VERSION ]]; then
    echo "Debian changelog seems updated"
else
    echo "Updating debian changelog (this is surprisingly slow)"
    EMAIL=$(git config user.email) gbp dch $ROOT --release --new-version=$VERSION --ignore-branch --git-author --debian-tag='v%(version)s' --debian-branch=release/$VERSION --spawn-editor=never
    echo "Please commit the updated changelog, do a pull request, and get it merged, then run this script again on an up-to-date master branch"
    echo "  git checkout -b release_$VERSION"
    echo "  git add debian/changelog"
    echo "  git commit -m 'Update debian changelog for release $VERSION'"
    echo "  git git push --set-upstream origin release_$VERSION"
    exit 0
fi

cd $(dirname $(readlink -f $0))

if [[ -n $(git status -s) ]]; then
    echo "Repository is dirty."
    git status -s
    [[ "${ALLOW_DIRTY}" != "true" ]] && exit 1
fi

GITTAG=master
if [[ $(git rev-parse --abbrev-ref HEAD) != ${GITTAG} && $(git describe --exact-match --tags 2>/dev/null) != ${GITTAG} ]]; then
    echo "Repository is currently not on branch/tag ${GITTAG}."
    [[ "${ALLOW_DIRTY}" != "true" ]] && exit 1
fi

THIS_REPO_VERSION=$(git -C $(dirname -- "$0") rev-parse HEAD)
UPSTREAM_VERSION=$(git -C $(dirname -- "$0") ls-remote upstream master | cut -f1)
if [[ $THIS_REPO_VERSION != $UPSTREAM_VERSION ]]; then
    echo "Warning: git head of repo does not match upstream. You likely want to update this repo"
    [[ "${ALLOW_DIRTY}" != "true" ]] && exit 1
fi


echo "Below is untested, echoing commands instead of running them"
echo "Creating a draft release on github"
echo gh -R Kattis/problemtools release create -d v$VERSION
echo "After finalizing the release on GitHub, please:"
echo " - trigger the pypi release workflow"
echo " - run $ROOT/admin/update_docker.sh v$VERSION"
