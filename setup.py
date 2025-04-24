#!/usr/bin/env python3

import os
import subprocess

import setuptools
import setuptools.command.build


class BuildSupport(setuptools.Command):
    """A custom command to build the support programs."""

    description = 'build the problemtools support programs'

    build_lib: str | None

    def initialize_options(self) -> None:
        self.build_lib = None

    def finalize_options(self) -> None:
        self.set_undefined_options('build_py', ('build_lib', 'build_lib'))

    def run(self):
        """Run command."""
        dest = os.path.join(os.path.realpath(self.build_lib), 'problemtools', 'support')
        command = ['make', '-C', 'support', 'install', 'DESTDIR=%s' % dest]
        subprocess.check_call(command)

# It's *very* unclear from setuptools' documentation what the best way to do this is.
#
# I think that the ideal way would be to insert BuildSupport as a SubCommand
# (https://setuptools.pypa.io/en/latest/userguide/extension.html), but I cannot find
# any documented way to inject a new subcommand (aside from overwriting one of
# the existing `build_*`, but those are only run conditionally).
class build(setuptools.command.build.build):
    """Updated build command that also builds support."""

    def run(self):
        self.run_command('build_support')
        super().run()

setuptools.setup(cmdclass={
          'build_support': BuildSupport,
          'build': build,
      },
)
