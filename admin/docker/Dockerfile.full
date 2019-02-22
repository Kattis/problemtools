# Full problemtools docker image, containing problemtools and all
# supported programming languages.
#

ARG PROBLEMTOOLS_VERSION=develop
FROM problemtools/icpc:${PROBLEMTOOLS_VERSION}

LABEL maintainer="austrin@kattis.com"

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y \
            mono-complete \
            ghc haskell-platform \
            libmozjs-52-dev \
            gccgo \
            fp-compiler \
            php-cli \
            swi-prolog \
            scala \
            sbcl \
            ocaml-nox \
            rustc \
   ;