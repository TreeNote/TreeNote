Installation
============


Ubuntu
------
::

	sudo apt-get install python3-pyqt5 couchdb
	sudo pip3 install couchdb
	python3 main.py


Fedora
------
::

	sudo yum install python3-qt5 couchdb python3-pip
	sudo pip3 install couchdb
	sudo systemctl start couchdb.service
	python3 main.py


Windows
-------
* Download `Python 3 <https://www.python.org/downloads/>`_. Install, but when you are at the window "customize python" check the box "add python.exe to path"
* Install the `Qt + PyQt binary package <http://www.riverbankcomputing.com/software/pyqt/download5>`_
* Install `CouchDB <http://couchdb.apache.org/#download>`_
* Open cmd.exe and enter ``python -m pip install couchdb``


OS X
------
* Install `Python 3 <https://www.python.org/downloads/>`_
* Install `Qt <http://www.qt.io/download-open-source/>`_. You may check to install the sources, too.
* Download the `SIP source package <http://www.riverbankcomputing.com/software/sip/download>`_. Unarchive it and run:

	::	

	    python3 configure.py --qmake=/Users/YourUsername/Qt/5.4/clang_64/bin/qmake 
	    make
	    sudo make install

* Install the `PyQt source package <http://www.riverbankcomputing.com/software/pyqt/download5>`_ in the same way.
* Install `CouchDB <http://couchdb.apache.org/#download>`_
* Run ``sudo pip3 install couchdb``


Integrated development environment
----------------------------------
I can recommend `PyCharm <https://www.jetbrains.com/pycharm>`_.


Edit this documentation
-----------------------
This documentation is built from the sources in GitHub. Click on the link at the top right to edit them.
It is written in reStructuredText, so have a short look at the `syntax manual <http://rest-sphinx-memo.readthedocs.org/en/latest/ReST.html>`_. You may want to use a `preview-software <https://mg.pov.lt/restview/>`_.