FROM ubuntu:20.04

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
            python3-minimal \
            python3-pip \
            python3-plastex \
            python3-yaml \
            sudo \
            texlive-fonts-recommended \
            texlive-lang-cyrillic \
            texlive-latex-extra \
            texlive-plain-generic \
            tidy \
            vim

RUN pip3 install git+https://github.com/kattis/problemtools
