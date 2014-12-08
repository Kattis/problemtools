# Kattis Problem Tools

These are tools to manage problem packages using the Kattis problem package
format.

## Requirements

To run the tools, you need Python with the YAML and PlasTeX libraries,
and a LaTeX installation.  In Ubuntu, the precise dependencies are as follows:

    sudo apt-get install python python-yaml python-plastex \
       texlive-latex-recommended texlive-fonts-recommended \
       texlive-latex-extra texlive-lang-cyrillic imagemagick tidy

The problem tools have not been tested on other platforms.  If you do
test on another platform, we'd be happy to hear what worked and what
did not work, so that we can write proper instructions (and try to
figure out how to make the non-working stuff work).

Build `checktestdata`, `default_validator` and `interactive` before running
`verifyproblem.py`.  Checktestdata requires a relatively recent gcc version
(4.8 suffices), but is only needed for running checktestdata input validation
scripts, the rest of problemtools will run fine without it.

    (cd checktestdata && make)
    (cd default_validator && make)
    (cd interactive && make)

## Programs Provided

The problem tools provide the following three programs:

 - `verifyproblem.py`: run a complete check on a problem
 - `problem2pdf.py`: convert a problem statement to pdf
 - `problem2html.py`: convert a problem statement to html

Running any of them without any command-line options gives
documentation on what parameters they accept.
