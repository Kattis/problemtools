#!/usr/bin/python

from distutils.core import setup

setup(name='Kattis Problemtools',
      version='1.1',
      description='The Kattis Problem Tools',
      maintainer='Per Austrin',
      maintainer_email='austrin@kattis.com',
      url='https://github.com/Kattis/problemtools',
      packages=['problemtools','problemtools.ProblemPlasTeX', 'problemtools.run'],
      package_dir = {'problemtools': 'src'}
 )
