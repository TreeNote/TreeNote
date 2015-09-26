Deployment
============


Set up the deployment environment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

* Only needed on Windows: Install `pywin32 <http://sourceforge.net/projects/pywin32/files/pywin32/Build%20219/pywin32-219.win32-py3.4.exe/download>`_
* Install PyInstaller
	* Download and extract the `setup <https://github.com/pyinstaller/pyinstaller/archive/python3.zip>`_
		* Only needed on OS X: Due to pyinstaller issue #1332 find the file `hook-PyQt5.py` and uncomment the lines inside as follows:

			::	

				if is_darwin:
				    datas = [
				#        (qt5_menu_nib_dir(), ''),
				    ]

	* Execute ``python setup.py install`` in cmd.exe / terminal





Deploy
^^^^^^^^^^^^^
Increase version number in version.py

* Windows
	* Execute in cmd.exe: ``pyinstaller --windowed --icon=images\logo.ico treenote.py``
	* Copy and paste the .json files into the new treenote folder

* Ubuntu
	* Execute ``pyinstaller --windowed --icon=/images/logo.png treenote.py``
	* Copy and paste the .json files into the new treenote folder

* OS X
	* Execute ``pyinstaller --windowed --icon=/images/logo.icns treenote.py``
	* Right-click on treenote.app and choose "Show Package Contents". Copy and paste the .json files to treenote.app/Contents/MacOS