Deployment
============


Set up the deployment environment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

* Only needed on windows: Install `pywin32 <http://sourceforge.net/projects/pywin32/files/pywin32/Build%20219/pywin32-219.win32-py3.4.exe/download>`_
* Install PyInstaller
	* Download and extract the `setup <https://github.com/pyinstaller/pyinstaller/archive/python3.zip>`_
	* Execute ``python setup.py install`` in cmd.exe / terminal





Deploy
^^^^^^^^^^^^^
* Windows: Execute in cmd.exe: ``pyinstaller --windowed --icon=/images/logo.ico treenote.py``

* Ubuntu: ``pyinstaller --windowed --icon=/images/logo.png treenote.py``