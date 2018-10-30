FROM ubuntu:18.04

MAINTAINER austrin@kattis.com

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y \
            automake \
            g++ \
            git \
            libboost-all-dev \
            libgmp-dev \
            libgmp10 \
            libgmpxx4ldbl \
            openjdk-8-jdk \
            python-minimal \
            python-pip \
            python-plastex \
            python-yaml \
            sudo \
            texlive-fonts-recommended \
            texlive-lang-cyrillic \
            texlive-latex-extra \
            texlive-latex-recommended \
            tidy \
            vim

RUN pip install git+https://github.com/kattis/problemtools
