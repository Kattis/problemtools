# Kattis Problem Tools

master:
![Master Build Status](https://github.com/kattis/problemtools/actions/workflows/python-app.yml/badge.svg?branch=master)
develop:
![Develop Build Status](https://github.com/kattis/problemtools/actions/workflows/python-app.yml/badge.svg?branch=develop)

These are tools to manage problem packages using the Kattis problem package
format.


## Programs Provided

The problem tools provide the following three programs:

 - `verifyproblem`: run a complete check on a problem
 - `problem2pdf`: convert a problem statement to pdf
 - `problem2html`: convert a problem statement to html

Running any of them with the command-line option `-h` gives
documentation on what arguments they accept.


## Example Problems

A few examples of problem packages can be found in [examples](examples).


## Installing problemtools

There are four supported ways of installing and running problemtools.
(For non-Linux users, "Method 2" below, to use Docker, is probably the least painful.)

### Method 1: Install the Python package

Run
```
sudo pip3 install git+https://github.com/kattis/problemtools
```

Or if you don't want a system-wide installation,
```
pip3 install --user git+https://github.com/kattis/problemtools
```
With this second option, in order to get the command line scripts, you need
to make sure that the local user bin path used (e.g., on Linux,
`$HOME/.local/bin`) is in your `$PATH`.

In order for problemtools to build and run properly, you also need to have LaTeX
and various LaTeX packages installed.  See [Requirements and
compatbility](#requirements-and-compatibility) below for details on
which packages are needed.


### Method 2: Use Docker

This method allows you to run the Kattis problemtools inside a Docker container. This method is supported on any system for which Docker exists, including **macOS** and **Windows 10**.

We maintain three official problemtools Docker images on Docker Hub:

- [`problemtools/full`](https://hub.docker.com/r/problemtools/full/): this image contains problemtools along with compilers/interpreters for all supported programming languages.

- [`problemtools/icpc`](https://hub.docker.com/r/problemtools/icpc/): this image contains problemtools along with compilers/interpreters for the programming languages allowed in the International Collegiate Programming Contest (ICPC): C, C++, Java, Kotlin, and Python 3.  Note that the compiler/interpreter versions used might not be exactly the same as those used in the current ICPC season.

- [`problemtools/minimal`](https://hub.docker.com/r/problemtools/minimal/): this image only contains problemtools, no additional programming languages.  As such, it is not particularly useful on its own, but if you are organizing a contest and want to set up a problemtools environment containing exactly the right set of compilers/interpreters for your contest, this is the recommended starting point.

For example, suppose you want to use the `problemtools/icpc` image.  To get started, install the [Docker CLI](https://docs.docker.com/install), and then pull the image:

    docker pull problemtools/icpc

Once the image has finished downloading, you can check that it exists on your system using `docker images`. To launch an interactive container and play around with *verifyproblem*, *problem2pdf*, and *problem2html* run:

    docker run --rm -it problemtools/icpc

By default, docker containers do _NOT_ persist storage between runs, so any files you create or modify will be lost when the container stops running.  Two common ways of dealing with this are:

1) Use a [bind mount](https://docs.docker.com/storage/bind-mounts/) to mount a directory on your machine into the docker container.  This can be done as follows (see Docker documentation for further details):
    ```
    docker run --rm -it -v ${FULL_PATH_TO_MOUNT}:/kattis_work_dir problemtools/icpc
    ```
2) Persist any changes you want to keep to a remote file system/source control (e.g., a remote Git repository; note, however, that you would first need to install Git in the image).

#### Building your own images

If you want a more complete environment in the Docker images (e.g., if
you want to install git or your favorite editor), feel free to extend
them in whichever way you like.

The `problemtools/{minimal,icpc,full}` images point to the latest
release versions of problemtools.  If, for some reason, you want an
image containing the latest development version, you have to build it
yourself from scratch (while there are
`problemtools/{minimal,icpc,full}:develop` Docker images on Docker
Hub, these are only updated sporadically for testing purposes and not
kept up to date).


### Method 3: Run directly from the repository.

If you intend to help develop problemtools, or if you just want a
bare-bones way of running them, this is your option.

For this method, you need to clone the repository (just downloading a
zip archive of it does not work because the project has submodules
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


### Method 4: Build and install the Debian package

This applies if you are running on Debian or a Debian derivative, such
as Ubuntu.

As with method 3, you need to clone the repository (just downloading a
zip archive of it does not work because the project has submodules
that are not included in that zip archive).

Run `make builddeb` in the root of the problemtools repository to
build the package.  It will be found as kattis-problemtools_X.Y.deb in
the directory containing problemtools (i.e., one level up from the
root of the repository).

Apart from the build dependencies listed [below](#ubuntu), building
the Debian package requires that the following tools are installed:

    debhelper dh-python dpkg-dev

The package can then be installed using (replace `<version>` as appropriate):

    sudo gdebi kattis-problemtools_<version>.deb

This installs the three provided programs in your path and they should
now be ready to use.


## Configuration

System-wide problemtools configuration files are placed in
`/etc/kattis/problemtools/`, and user-specific configuration files are placed
in `$HOME/.config/problemtools/` (or in `$XDG_CONFIG_HOME` if this is defined).  The following files can be used to change
problemtools' configuration:

1. `languages.yaml`.  Use it to override problemtools' default
   programming language configuration.  For instance, while the
   problemtools default is to use the CPython `/usr/bin/python3`
   interpreter for Python 3, many contests, as well as the Kattis
   online judge, use Pypy as the interpreter for Python 3.  To change
   this on your machine, you can simply place a file
   `/etc/kattis/problemtools/languages.yaml` (or
   `~/.config/problemtools/languages.yaml` if you only want to make the
   change for your user) containing the following:

   ```yaml
   python3:
      name: 'Python 3 w/Pypy'
      run: '/usr/bin/pypy3 "{mainfile}"'
   ```
   Here, overriding the name of the language is not strictly
   necessary, but it is often helpful to clearly indicate that Pypy is
   being used.

   For more details on the format of the language specifications and
   what the default settings are, see the [default version of
   languages.yaml](problemtools/config/languages.yaml)

2. `problem.yaml`.  For most users, this should not be edited.  If you
   are not sure whether you should use it, then you probably shouldn't.
   This file can be used to specify the system defaults for those
   problem limits which are not given a fixed default value in the
   [problem format specification](http://www.problemarchive.org/wiki/index.php/Problem_Format#limits).
   The system defaults assumed by problemtools can be found in
   (problemtools/config/problem.yaml).  For instance, if you are
   primarily working against a system with a default memory limit of 2 GiB,
   you can place a file `~/.config/problemtools/problem.yaml` containing:

   ```yaml
   limits:
       memory: 2048 # (unit is MiB)
   ```

   (In principle, it is possible to override the defaults of other values than the
   system-dependent defaults in the problem.yaml metadata files this way, but such
   usage is very strongly discouraged.)


## Requirements and compatibility

To build and run the tools, you need Python 3 with the YAML and PlasTeX libraries,
and a LaTeX installation.

### Ubuntu

The dependencies needed to *build/install* problemtools can be installed with:

    sudo apt install automake g++ make libboost-regex-dev libgmp-dev libgmp10 libgmpxx4ldbl python3 python3-pytest python3-setuptools python3-yaml python3-plastex

And the dependencies needed to *run* problemtools can be installed with:

    sudo apt install ghostscript libgmpxx4ldbl python3-minimal python-pkg-resources python3-plastex python3-yaml texlive-fonts-recommended texlive-lang-cyrillic texlive-latex-extra texlive-plain-generic tidy

### Fedora

On Fedora, these dependencies can be installed with:

    sudo dnf install boost-regex gcc gmp-devel gmp-c++ python3 python3-pyyaml texlive-latex texlive-collection-fontsrecommended texlive-fancyhdr texlive-subfigure texlive-wrapfig texlive-import texlive-ulem texlive-xifthen texlive-overpic texlive-pbox tidy ghostscript

Followed by:

    pip3 install --user plastex

### Arch
Package is available on the AUR [kattis-problemtools-git](https://aur.archlinux.org/packages/kattis-problemtools-git). Use your favorite AUR helper or follow the installation instructions found [here](https://wiki.archlinux.org/title/Arch_User_Repository#Installing_and_upgrading_packages).

### Other platforms

The problem tools have not been tested on other platforms.  If you do
test on another platform, we would be happy to hear what worked and what
did not work, so that we can write proper instructions (and try to
figure out how to make the non-working stuff work).
