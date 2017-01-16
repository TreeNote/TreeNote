#!/usr/bin/env python3

import sys
from setuptools import setup

from treenote.version import __version__

if sys.version_info[0] < 3 or sys.version_info[1] < 5:
    sys.exit('Error: Python 3.5 is required.')

setup(name='TreeNote',
      version=__version__,
      description='An intuitive outliner for personal knowledge and task management',
      long_description='''\
The author has used many time management programs over the last four years.
When the number of tasks grew, a neat system like Getting Things Done became essential.
Therefore the development of TreeNote was influenced by powerful tools like Omnifocus (Mac only) and Org mode (too complex).
However, TreeNote is as intuitive to use as the light tools Wunderlist and Evernote.

To run TreeNote simply type `treenote` in a Terminal.

For more details, please go to the `home page`_.

.. _`home page`: http://treenote.org''',
      author='Jan Korte',
      author_email='j.korte@me.com',
      url='http://treenote.org',
      license='GPL3',
      packages=['treenote', 'treenote.resources'],
      include_package_data=True, # This tells setuptools to install any data files it finds in your packages. The data files must be specified via the distutils’ MANIFEST.in file.
      data_files=[
          ("share/applications", ["treenote/resources/treenote_entry.desktop"]),
          ("share/pixmaps", ["treenote/resources/images/treenote.png"]),
          ("share/mime/packages", ["treenote/resources/x-treenote.xml"])
      ],
      entry_points={
          "gui_scripts": [
              "treenote=treenote.treenote_main:main"
          ],
      },
      classifiers=[
          'Development Status :: 5 - Production/Stable',
          'Environment :: X11 Applications :: Qt',
          'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
          'Programming Language :: Python :: 3 :: Only',
          'Topic :: Text Editors',
      ]
      )
