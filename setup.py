#!/usr/bin/env python2

from setuptools import setup, find_packages
from setuptools.command.bdist_egg import bdist_egg as _bdist_egg
import distutils.cmd
from distutils.command.build import build as _build
import os
import subprocess


class BuildSupport(distutils.cmd.Command):
    """A custom command to build the support programs."""

    description = 'build the problemtools support programs'

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        """Run command."""
        # FIXME this seems very fragile...
        dest = os.path.join(os.path.realpath(self.distribution.command_obj['build'].build_lib),
                            'problemtools', 'support')
        command = ['make', '-C', 'support', 'install', 'DESTDIR=%s' % dest]
        self.announce('Running command: %s' % ' '.join(command), level=distutils.log.INFO)
        subprocess.check_call(command)


class bdist_egg(_bdist_egg):
    """Updated bdist_egg command that also builds support."""

    def run(self):
        self.run_command('build_support')
        _bdist_egg.run(self)


class build(_build):
    """Updated build command that also builds support."""

    def run(self):
        self.run_command('build_support')
        _build.run(self)


def get_version():
    base_dir = os.path.dirname(__file__)

    __version__ = None
    try:
        __version__ = subprocess.check_output(['git', 'describe']).strip()
        update_script = os.path.join(base_dir, 'admin', 'update_version.py.sh')
        subprocess.check_call([update_script])
    except:
        pass

    if __version__ is None:
        version_file = os.path.join(base_dir, 'problemtools', '_version.py')
        with open(version_file, 'r') as version_in:
            exec(version_in.read())

    return __version__


setup(name='problemtools',
      version=get_version(),
      description='Kattis Problem Tools',
      maintainer='Per Austrin',
      maintainer_email='austrin@kattis.com',
      url='https://github.com/Kattis/problemtools',
      license='MIT',
      packages=find_packages(),
      entry_points = {
          'console_scripts': [
              'verifyproblem=problemtools.verifyproblem:main',
              'problem2html=problemtools.problem2html:main',
              'problem2pdf=problemtools.problem2pdf:main',
          ]
      },
      include_package_data=True,
      install_requires=[
          'PyYAML',
          'plasTeX',
      ],
#      Temporarily disabled, see setup.cfg
#      For now tests can be run manually with pytest
#      setup_requires=['pytest-runner'],
#      tests_require=['pytest'],
      cmdclass={
          'build_support': BuildSupport,
          'bdist_egg': bdist_egg,
          'build': build
      },
)
