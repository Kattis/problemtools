# Minimalistic problemtools docker image, containing only problemtools
# and its dependencies, no languages (except whichever are
# dependencies of problemtools, e.g. Python 2)
#
# Build requirements:
# - The problemtools .deb package must be available from the host file
#   system under a file name matching
#   artifacts/deb/kattis-problemtools*.deb
#   (Version of that .deb file should match the build argument
#    PROBLEMTOOLS_VERSION but this is not checked.)

ARG PROBLEMTOOLS_VERSION=develop
FROM ubuntu:18.04

LABEL maintainer="austrin@kattis.com"

ENV DEBIAN_FRONTEND=noninteractive

RUN apt update && \
    apt install -y \
        ghostscript \
        libgmpxx4ldbl \
        python-minimal \
        python-pkg-resources \
        python-plastex \
        python-yaml \
        texlive-fonts-recommended \
        texlive-generic-recommended \
        texlive-lang-cyrillic \
        texlive-latex-extra \
        texlive-latex-recommended \
        tidy

RUN mkdir -p /usr/local/artifacts
WORKDIR /usr/local/artifacts
COPY artifacts/deb .
RUN dpkg -i kattis-problemtools*.deb

WORKDIR /
