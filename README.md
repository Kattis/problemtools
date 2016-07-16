# Kattis Problem Tools

[![Build Status](https://travis-ci.org/Kattis/problemtools.svg?branch=master)](https://travis-ci.org/Kattis/problemtools)

These are tools to manage problem packages using the Kattis problem package
format.


## Programs Provided

The problem tools provide the following three programs:

 - `verifyproblem`: run a complete check on a problem
 - `problem2pdf`: convert a problem statement to pdf
 - `problem2html`: convert a problem statement to html

Running any of them without any command-line options gives
documentation on what parameters they accept.


## Example Problems

A few examples of problem packages can be found in [examples](examples).


## Installing and using problemtools

There are two recommended ways of installing and running problemtools.

### Method 1: Build and install the Debian package

This applies if you are running on Debian or a Debian derivative such
as Ubuntu.

Run `make builddeb` in the root of the problemtools repository to
build the package.  It will be found as kattis-problemtools_X.Y.deb in
the directory containing problemtools (i.e., one level up from the
root of the repository).

To see which packages are required in order to be able to do this, see
the "Build-Depends" line of the file debian/control.

The package can then be installed using (replace X.Y as appropriate):

    sudo gdebi kattis-problemtools_X.Y.deb

This installs the three provided programs in your path and they should
now be ready to use.


### Method 2: Run directly from the repository.

In order for the tools to work, you first have to compile the various
support programs, which can be done by running `make` in the root
directory of problemtools.

The checktestdata program requires a relatively recent gcc version
(4.8 suffices), but is only needed for running checktestdata input
validation scripts.  The rest of problemtools will run fine without
it, but in this case you need to build the other programs separately,
e.g. by running

    (cd support/default_validator && make)
    (cd support/interactive && make)

When this is done, you can run the three programs `verifyproblem.py`,
`problem2pdf.py`, and `problem2html.py` directly from the src
directory of problemtools.


## Requirements and compatibility

To run the tools, you need Python 2 with the YAML and PlasTeX libraries,
and a LaTeX installation.  In Ubuntu, the precise dependencies are as follows:

    libboost-regex1.54.0, libc6 (>= 2.14), libgcc1 (>= 1:4.1.1), libgmp10, libgmpxx4ldbl, libstdc++6 (>= 4.4.0), python (>= 2.7), python (<< 2.8), python:any (>= 2.7.1-0ubuntu2), python-yaml, python-plastex, texlive-latex-recommended, texlive-fonts-recommended, texlive-latex-extra, texlive-lang-cyrillic, tidy, ghostscript

The problem tools have not been tested on other platforms.  If you do
test on another platform, we'd be happy to hear what worked and what
did not work, so that we can write proper instructions (and try to
figure out how to make the non-working stuff work).
