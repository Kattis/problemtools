# Kattis Problem Tools

master:
[![Master Build Status](https://travis-ci.org/Kattis/problemtools.svg?branch=master)](https://travis-ci.org/Kattis/problemtools).
develop:
[![Develop Build Status](https://travis-ci.org/Kattis/problemtools.svg?branch=develop)](https://travis-ci.org/Kattis/problemtools)

These are tools to manage problem packages using the Kattis problem package
format.


## Programs Provided

The problem tools provide the following three programs:

 - `verifyproblem`: run a complete check on a problem
 - `problem2pdf`: convert a problem statement to pdf
 - `problem2html`: convert a problem statement to html

Running any of them with command-line option `-h` gives
documentation on what arguments they accept.


## Example Problems

A few examples of problem packages can be found in [examples](examples).


## Installing and using problemtools

There are four recommended ways of installing and running problemtools.
(For non-Linux users, the last method below, to use Docker, is probably the least painful.)

### Method 1: Install the Python package

Run
```
pip install git+https://github.com/kattis/problemtools
```

Or if you don't want a system-wide installation,
```
pip install --user git+https://github.com/kattis/problemtools
```
With this second option, in order to get the command line scripts, you need
to make sure that the local user bin path used (e.g., on Linux,
`$HOME/.local/usr/local/bin`) is in your `$PATH`.

In order for problemtools to run properly, you also need to have LaTeX
and various LaTeX packages installed.  See [Requirements and
compatbility](#requirements-and-compatibility) below for details on
which packages are needed.


### Method 2: Run directly from the repository.

For this method, you need to clone the repository (just downloading a
zip archive of it does not work, because the project has submodules
that are not included in that zip archive).

In order for the tools to work, you first have to compile the various
support programs, which can be done by running `make` in the root
directory of problemtools.

When this is done, you can run the three programs
`bin/verifyproblem.sh`, `bin/problem2pdf.sh`, and
`bin/problem2html.sh` directly from the repository.

See [Requirements and compatibility](#requirements-and-compatibility)
below for what other software needs to be installed on your machine in
order for problemtools to work correctly.


### Method 3: Build and install the Debian package

This applies if you are running on Debian or a Debian derivative such
as Ubuntu.

As with method 2, you need to clone the repository (just downloading a
zip archive of it does not work, because the project has submodules
that are not included in that zip archive).

Run `make builddeb` in the root of the problemtools repository to
build the package.  It will be found as kattis-problemtools_X.Y.deb in
the directory containing problemtools (i.e., one level up from the
root of the repository).

To see which packages are required in order to be able to do this, see
the "Build-Depends" line of the file debian/control. *Note that the
dependencies needed to build the Debian package are not the same as
the depencies listed below, which are the dependencies for __running__
problemtools.*

The package can then be installed using (replace `<version>` as appropriate):

    sudo gdebi kattis-problemtools_<version>.deb

This installs the three provided programs in your path and they should
now be ready to use.


### Method 4: Use Docker

This method allows you to run the Kattis problemtools inside a docker container. This method is supported on **macOS**, **Windows 10** and several linux distros. This automatically installs all the required dependencies for the Kattis problemtools and places the correct programs on your `$PATH`.

To get started, install the [Docker CLI](https://docs.docker.com/install) and build the Kattis problemtools docker image using the Dockerfile in the top directory of this project. This will download the correct Ubuntu image and install all the Kattis problemtools.

    problemtools$ docker build -t kattis_problemtools_image .

(On some systems you may need to run the above command as a superuser.  Building the image takes a while.)

Once the image has finished installing, you can check it exists on your system using `docker images`. To launch an interactive container and play around with *verifyproblem*, *problem2pdf*, and *problem2html* run:

    docker run -it kattis_problemtools_image

**WARNING:** By default, docker containers to _NOT_ persist storage between runs, so any files you create or modify will be lost when the container stops running.

There are several ways of getting around this:

1) Persist any changes you want to keep to a remote file system/source control (e.g Github)

2) Use a [bind mount](https://docs.docker.com/storage/bind-mounts/) to mount a directory on your machine into the docker container.  This can be done as follows (see Docker documentation for further details):

    docker run -it -v ${FULL_PATH_TO_MOUNT}:/kattis_work_dir kattis_problemtools_image


## Requirements and compatibility

To run the tools, you need Python 2 with the YAML and PlasTeX libraries,
and a LaTeX installation.  In Ubuntu, the precise dependencies are as follows:

    libboost-regex1.54.0, libc6 (>= 2.14), libgcc1 (>= 1:4.1.1), automake, libgmp-dev, libgmp10, libgmpxx4ldbl, libstdc++6 (>= 4.4.0), python (>= 2.7), python (<< 2.8), python:any (>= 2.7.1-0ubuntu2), python-yaml, python-plastex, texlive-latex-recommended, texlive-fonts-recommended, texlive-latex-extra, texlive-lang-cyrillic, tidy, ghostscript

On Fedora, these dependencies can be installed with:

    sudo dnf install boost-regex gcc gmp-devel gmp-c++ python2 python2-pyyaml texlive-latex texlive-collection-fontsrecommended texlive-fancyhdr texlive-subfigure texlive-wrapfig texlive-import texlive-ulem texlive-xifthen texlive-overpic texlive-pbox tidy ghostscript

Followed by:

    pip2 install --user plastex

The problem tools have not been tested on other platforms.  If you do
test on another platform, we'd be happy to hear what worked and what
did not work, so that we can write proper instructions (and try to
figure out how to make the non-working stuff work).
