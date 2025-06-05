#!/bin/bash
set -e

ALLOW_DIRTY=false
GITTAG=master
DOCKERTAG=develop
UPDATE_LATEST=false

while getopts "d" opt; do
    case $opt in
        d) ALLOW_DIRTY=true ;;
        \?) echo "Invalid option: -$opt" ;;
    esac
done

shift $((OPTIND-1))

if [ "$1" != "" ]; then
    GITTAG=$1
    DOCKERTAG=$1
    UPDATE_LATEST=true
fi

cd $(dirname $(readlink -f $0))/docker

if [[ -n $(git status -s) ]]; then
    echo "Repository is dirty."
    git status -s
    [[ "${ALLOW_DIRTY}" != "true" ]] && exit 1
fi

if [[ $(git rev-parse --abbrev-ref HEAD) != ${GITTAG} && $(git describe --exact-match --tags 2>/dev/null) != ${GITTAG} ]]; then
    echo "Repository is currently not on branch/tag ${GITTAG}."
    [[ "${ALLOW_DIRTY}" != "true" ]] && exit 1
fi

echo "Updating Ubuntu base image"
docker pull ubuntu:24.04

# Make our internal images, and our githubci image. Order is important, images depend on each other
echo "Building intermediate images, plus githubci image"
for IMAGE in runreqs build icpclangs fulllangs githubci; do
    docker build \
        -f Dockerfile.${IMAGE} \
        -t problemtools/${IMAGE}:${DOCKERTAG} \
        --build-arg PROBLEMTOOLS_VERSION="${DOCKERTAG}" \
        .
done


echo "Building deb"
mkdir -p artifacts
sudo rm -rf artifacts/deb
# Use our build image to build a deb
docker run --rm -v "$(pwd)/../..:/problemtools" -v "$(pwd)/artifacts/deb:/artifacts" problemtools/build:${DOCKERTAG} \
    /bin/bash -c "
        set -e ;
        mkdir /build ;
        cd /build ;
        git config --global --add safe.directory /problemtools/.git ;
        git clone --branch ${GITTAG} /problemtools ;
        cd problemtools ;
        make builddeb ;
        cp ../*.deb /artifacts"
sudo chown -R $USER:$USER artifacts/


echo "Testing deb"
if ! docker run --rm -t -v "$(pwd)/../..:/problemtools" -v "$(pwd)/artifacts/deb:/artifacts" problemtools/fulllangs:${DOCKERTAG} \
    /bin/bash -c '
        set -e ;
        shopt -s extglob ;
        dpkg -i /artifacts/kattis-problemtools* ;
        verifyproblem /problemtools/examples/!(README.md)'; then
            echo Running verifyproblem on all examples failed. Please review output above to debug.;
            exit 1
fi
echo Tests pass


echo "Building complete images with problemtools baked in"
for IMAGE in minimal icpc full; do
    docker build \
        -f Dockerfile.${IMAGE} \
        -t problemtools/${IMAGE}:${DOCKERTAG} \
        --build-arg PROBLEMTOOLS_VERSION="${DOCKERTAG}" \
        .
done


if [ "${UPDATE_LATEST}" = "true" ]; then
    echo "Build complete. If you are happy with the images, run the following:"
    for IMAGE in minimal icpc full githubci; do
        echo "    docker tag problemtools/${IMAGE}:${DOCKERTAG} problemtools/${IMAGE}:latest"
        echo "    docker push problemtools/${IMAGE}:${DOCKERTAG}"
        echo "    docker push problemtools/${IMAGE}:latest"
    done
fi
