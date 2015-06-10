Deploy
============


Linux
-----
Coming...


Windows
-------

Set up the deployment environment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
* Install `pywin32 <http://sourceforge.net/projects/pywin32/files/pywin32/Build%20219/pywin32-219.win32-py3.4.exe/download>`_
* Install PyInstaller
	* Download and extract the `setup <https://github.com/pyinstaller/pyinstaller/archive/python3.zip>`_
	* Execute ``python setup.py install`` in cmd.exe

Deploy
^^^^^^^^^^^^^
Execute in cmd.exe:
:: 

	cd treenote_git_folder
	pyinstaller --windowed treenote.py


OS X
-----
Coming...