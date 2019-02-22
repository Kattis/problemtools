# Package for building the problemtools .deb package
# Ends up in the /usr/local/problemtools_build/deb/ directory
#
# Setting build argument PROBLEMTOOLS_VERSION causes a specific
# version of problemtools to be built (default is latest version of
# develop branch on GitHub)

FROM ubuntu:18.04

LABEL maintainer="austrin@kattis.com"

ENV DEBIAN_FRONTEND=noninteractive

# Install packages needed for build
RUN apt update && \
    apt install -y \
        automake \
        debhelper \
        dh-python \
        dpkg-dev \
        g++ \
        git \
        make \
        libboost-regex-dev \
        libgmp-dev \
        libgmp10 \
        libgmpxx4ldbl \
        python \
        python-pytest \
        python-setuptools \
        python-yaml

RUN mkdir -p /usr/local/problemtools_build

WORKDIR /usr/local/problemtools_build
RUN git clone --recursive https://github.com/kattis/problemtools

ARG PROBLEMTOOLS_VERSION=develop
RUN cd problemtools && git checkout ${PROBLEMTOOLS_VERSION} && make builddeb

RUN mkdir -p deb
RUN mv kattis-problemtools*.deb deb/
