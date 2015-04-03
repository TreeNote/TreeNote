# TreeNote
An intuitive outliner for personal knowledge and task management. Supports collaborative, simultaneous editing.<br>
This software is part of a bachelor thesis and currently developed.


## Install
### Ubuntu
    sudo apt-get install python3-pyqt5 couchdb
    sudo pip3 install couchdb
    python3 main.py
    
### Fedora 21
    sudo yum install python3-qt5 couchdb python3-pip
    sudo pip3 install couchdb
    sudo systemctl start couchdb.service
	python3 main.py
    
### OS X
Install Python 3 from https://www.python.org/downloads/

Install Qt from http://www.qt.io/download-open-source/

Download the SIP source package from http://www.riverbankcomputing.com/software/sip/download<br>
Unarchive and run:

    python3 configure.py
    make
    sudo make install

Install the PyQt source package from http://www.riverbankcomputing.com/software/pyqt/download5 in the same way.

Install CouchDB from http://couchdb.apache.org/#download

Run `sudo pip3 install couchdb`

### Windows
Download Python 3 from https://www.python.org/downloads/<br>
Install, but when you are at the window "customize python" check the box "add python.exe to path"

Install the Qt + PyQt binary package from http://www.riverbankcomputing.com/software/pyqt/download5

Install CouchDB from http://couchdb.apache.org/#download

Open cmd.exe and enter `python -m pip install couchdb`

## Develop
I can recommend this integrated development environment: https://www.jetbrains.com/pycharm

## Screenshot

![Screemshot](/images/screenshot.png)