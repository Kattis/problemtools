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

There are three recommended ways of installing and running problemtools.

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

Run `make builddeb` in the root of the problemtools repository to
build the package.  It will be found as kattis-problemtools_X.Y.deb in
the directory containing problemtools (i.e., one level up from the
root of the repository).

To see which packages are required in order to be able to do this, see
the "Build-Depends" line of the file debian/control.

The package can then be installed using (replace `<version>` as appropriate):

    sudo gdebi kattis-problemtools_<version>.deb

This installs the three provided programs in your path and they should
now be ready to use.


## Requirements and compatibility

To run the tools, you need Python 2 with the YAML and PlasTeX libraries,
and a LaTeX installation.  In Ubuntu, the precise dependencies are as follows:

    libboost-regex1.54.0, libc6 (>= 2.14), libgcc1 (>= 1:4.1.1), libgmp10, libgmpxx4ldbl, libstdc++6 (>= 4.4.0), python (>= 2.7), python (<< 2.8), python:any (>= 2.7.1-0ubuntu2), python-yaml, python-plastex, texlive-latex-recommended, texlive-fonts-recommended, texlive-latex-extra, texlive-lang-cyrillic, tidy, ghostscript

The problem tools have not been tested on other platforms.  If you do
test on another platform, we'd be happy to hear what worked and what
did not work, so that we can write proper instructions (and try to
figure out how to make the non-working stuff work).

