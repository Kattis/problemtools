#!/usr/bin/python

from setuptools import setup

setup(name='problemtools',
      version='1.1',
      description='Kattis Problem Tools',
      maintainer='Per Austrin',
      maintainer_email='austrin@kattis.com',
      url='https://github.com/Kattis/problemtools',
      license='MIT',
      package_dir = {'problemtools': 'src'},
      packages=[
          'problemtools',
          'problemtools.ProblemPlasTeX',
          'problemtools.run',
      ],
      install_requires=[
          'PyYAML',
      ],
      entry_points = {
          'console_scripts': [
              'verifyproblem=problemtools.verifyproblem:main',
              'problem2html=problemtools.problem2html:main',
              'problem2pdf=problemtools.problem2pdf:main',
          ]
      },
      include_package_data=True,
 )
