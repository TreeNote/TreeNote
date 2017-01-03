#!/usr/bin/env python3

long_description = '''\
The author has used many time management programs over the last four years.
When the number of tasks grew, a neat system like Getting Things Done became essential.
Therefore the development of TreeNote was influenced by powerful tools like Omnifocus (Mac only) and Org mode (too complex).
However, TreeNote is as intuitive to use as the light tools Wunderlist and Evernote.

For more details, please go to the `home page`_.

.. _`home page`: http://treenote.org'''

import sys
from distutils.core import setup
from setuptools import setup

from TreeNote import version_nr

if sys.version_info[0] < 3:
    sys.exit('Error: Python 3.x is required.')

classifiers = [
    'Development Status :: 5 - Production/Stable',
    'Environment :: X11 Applications :: Qt',
    'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
    'Programming Language :: Python :: 3 :: Only',
    'Topic :: Text Editors',
]

setup(name='TreeNote',
      version=version_nr,
      description='An intuitive outliner for personal knowledge and task management',
      long_description=long_description,
      author='Jan Korte',
      author_email='j.korte@me.com',
      url='http://treenote.org',
      packages=['TreeNote', 'TreeNote.resources'],
      include_package_data=True,
      entry_points={
          'console_scripts': ['treenote=TreeNote:main'],
      },
      classifiers=classifiers,
      license='GPL3'
      )
