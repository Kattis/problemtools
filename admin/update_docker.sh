#!/bin/bash
set -e

TAG=develop
UPDATE_LATEST=false
if [ "$1" != "" ]; then
    TAG=$1
    UPDATE_LATEST=true
fi


cd $(dirname $(readlink -f $0))/docker
set -x

# Make the build image and extract build artifacts
# ===============================================
sudo docker build \
     -f Dockerfile.build \
     -t problemtools/build:${TAG} \
     --no-cache \
     --build-arg PROBLEMTOOLS_VERSION="${TAG}" \
     .
mkdir -p artifacts
rm -rf artifacts/deb/*
sudo docker run --rm -v "$(pwd)/artifacts/:/artifacts" problemtools/build:${TAG} cp -r /usr/local/problemtools_build/deb /artifacts
sudo chown -R $USER:$USER artifacts/


# Build the actual problemtools images
# ===============================================
for IMAGE in minimal icpc full; do
    sudo docker build\
         -f Dockerfile.${IMAGE}\
         -t problemtools/${IMAGE}:${TAG}\
         --build-arg PROBLEMTOOLS_VERSION=${TAG}\
         .
    if [ "$UPDATE_LATEST" = "true" ]; then
        sudo docker tag problemtools/${IMAGE}:${TAG} problemtools/${IMAGE}:latest
    fi
done


# Push to Docker Hub
# ===============================================
sudo docker login
for IMAGE in minimal icpc full; do
    sudo docker push problemtools/${IMAGE}:${TAG}
    if [ "$UPDATE_LATEST" = "true" ]; then
        sudo docker push problemtools/${IMAGE}:latest
    fi
done
