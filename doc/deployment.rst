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
Execute in cmd.exe / terminal:
:: 

	cd treenote_git_folder
	pyinstaller --windowed --icon=<FILE.ico> treenote.py

* Only on OS X: Add icon
	* Prepare an .icns file with your own graphic; open in it Preview.app; select-all and copy; in the Finder, Get Info on your app; click the icon in the info display and paste.
	* `GraphicConverter <http://www.lemkesoft.de/en/products/graphic-converter/>`_ is one of several applications that can save a JPEG or PNG image in the .icns format.