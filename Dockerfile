# Download ubuntu image with python and pip
FROM nitincypher/docker-ubuntu-python-pip

RUN apt-get update && \
    apt-get install -y sudo && \
    apt-get install -y git && \
    apt-get install -y automake && \
    apt-get install -y tidy && \
    apt-get install -y libboost-all-dev && \
    apt-get install -y libgmp-dev libgmp10 libgmpxx4ldbl && \
    apt-get install -y python-plastex && \
    apt-get install -y texlive-latex-recommended texlive-fonts-recommended texlive-latex-extra texlive-lang-cyrillic && \
    apt-get install -y python-yaml && \
    apt-get install -y vim && \
    apt-get install -y openjdk-8-jdk && \
    apt-get install -y g++ && \
    pip2 install --upgrade pip && \
    pip install git+https://github.com/kattis/problemtools
