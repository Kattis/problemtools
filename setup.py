#!/usr/bin/env python3

import os
import subprocess

import setuptools
import setuptools.command.build
import setuptools.command.sdist


class BuildSupport(setuptools.Command):
    """A custom command to build the support programs."""

    description = 'build the problemtools support programs'

    build_lib: str | None

    def initialize_options(self) -> None:
        self.build_lib = None

    def finalize_options(self) -> None:
        self.set_undefined_options('build_py', ('build_lib', 'build_lib'))

    def run(self):
        dest = os.path.join(os.path.realpath(self.build_lib), 'problemtools', 'support')
        command = ['make', '-C', 'support', 'install', 'DESTDIR=%s' % dest]
        subprocess.check_call(command)


class CheckoutChecktestdata(setuptools.Command):
    """A custom command to build the support programs."""

    description = 'checkout the git submodule for checktestdata (via make)'

    def initialize_options(self) -> None:
        pass

    def finalize_options(self) -> None:
        pass

    def run(self):
        command = ['make', 'checktestdata']
        subprocess.check_call(command)


# It's *very* unclear from setuptools' documentation what the best way to do this is.
#
# I think that the ideal way would be to insert BuildSupport as a SubCommand
# (https://setuptools.pypa.io/en/latest/userguide/extension.html), but I cannot find
# any documented way to inject a new subcommand (aside from overwriting one of
# the existing `build_*`, but those are only run conditionally).
class build(setuptools.command.build.build):
    def run(self):
        self.run_command('build_support')
        super().run()


# To make python -m build work from a fresh checkout, we also need to hook sdist to
# do a git submodule checkout so that the source code for checktestdata is included
# in the sdist (an alternative approach would be to include .git in the sdist (eww).
class sdist(setuptools.command.sdist.sdist):
    def run(self):
        self.run_command('checkout_checktestdata')
        super().run()


setuptools.setup(
    cmdclass={
        'build_support': BuildSupport,
        'build': build,
        'checkout_checktestdata': CheckoutChecktestdata,
        'sdist': sdist,
    },
)
