FROM ubuntu:18.04

RUN export DEBIAN_FRONTEND=noninteractive && \
    apt-get update && \
    apt-get install -y sudo git curl automake tidy libboost-all-dev libgmp-dev libgmp10 libgmpxx4ldbl python-plastex texlive-latex-recommended texlive-fonts-recommended texlive-latex-extra texlive-lang-cyrillic python-yaml vim python-minimal openjdk-8-jdk g++ && \
    curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py && \
    python get-pip.py && \
    pip2 install --upgrade pip && \
    pip install git+https://github.com/kattis/problemtools
