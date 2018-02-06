# TreeNote

[![Join the chat at https://gitter.im/TreeNote/TreeNote](https://badges.gitter.im/Join%20Chat.svg)](https://gitter.im/TreeNote/TreeNote?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge) [![Build Status](https://travis-ci.org/MarkusHackspacher/TreeNote.svg?branch=master)](https://travis-ci.org/MarkusHackspacher/TreeNote)

An intuitive outliner for personal knowledge and task management.

##### Contents

- [About](#about)
- [Download](#download)
- [Documentation](#documentation)
- [Contribute](#contribute)
- [Mobile app](#mobile-app)
- [Contributors and participation](#contributors-and-participation)

# About

## It's freedom
This program is free and open source. It's easy to suggest and implement new features.

## It's science
Half a year of research flowed into the development. I developed this application in my bachelor thesis in the year 2016, graded A+ and written at the University of Oldenburg.

## It's mighty
The author has used many time management programs over the last four years. When the number of tasks grew, a neat system like [Getting Things Done](http://www.amazon.com/Getting-Things-Done-Stress-Free-Productivity/dp/0142000280) became essential. Therefore the development of TreeNote was influenced by powerful tools like [Omnifocus](https://www.omnigroup.com/omnifocus) (Mac only) and [Org mode](http://orgmode.org/) (too complex). However, TreeNote is as intuitive to use as the light tools [Wunderlist](https://www.wunderlist.com) and [Evernote](https://evernote.com).

When starting TreeNote for the first time, you will see a detailed manual which guides you through the features.

## Project status (February 2018)
Me and couple of friends are using TreeNote on a daily basis since years. It is a central and valuable piece for our self-management. TreeNote is well tested and bug-free. I have no time to add features, but will fix bugs if they appear and will explain the code to anyone interested.

![Screenshot](/treenote/resources/images/screenshot.png)


# Download
* **Linux**: TreeNote requieres an installation of the programming language Python 3 and the GUI framework PyQt5, before it can be run from source. It is installed as follows:
	* <i class="fl-archlinux"></i> **Arch Linux**: Search in the AUR for 'treenote' with e.g. Pamac or enter `yaourt -S treenote-git` in a Terminal.
	* <i class="fl-ubuntu"></i> **Debian and Ubuntu**: Enter `sudo apt-get install python3-pip`, then `sudo pip3 install pyqt5 treenote` in a Terminal. Run by entering `nohup dbus-run-session treenote &`.
	* <i class="fl-fedora"></i> **Fedora**: Enter `sudo yum install python3-pip`, then `sudo pip3 install pyqt5 treenote` in a Terminal. Run by entering  `nohup treenote &`.
	* <i class="fl-tux"></i> **Other Linux distros**: Enter `sudo pip3 install pyqt5 treenote` in a Terminal. Run by entering  `nohup treenote &`.
* <i class="fa fa-windows"></i> **Windows**: [Download <i class="fa fa-arrow-circle-o-down" aria-hidden="true"></i>](https://github.com/TreeNote/TreeNote/releases/download/v1.7.8/treenote_v1.7.8_windows.zip) and extract the archive, then doubleclick the `treenote.exe` file inside. 
* <i class="fa fa-apple"></i> **Mac OS X**: [Download <i class="fa fa-arrow-circle-o-down" aria-hidden="true"></i>](https://github.com/TreeNote/TreeNote/releases/download/v1.7.8/treenote_v1.7.8_mac.zip)

 For upgrading a version on Linux, run `sudo pip3 install pyqt5 treenote --upgrade`. 
 
## Stay up to date
I will implement auto-updates. Until then, register for my newsletter to get notified when a new version is ready:
<form action="https://formspree.io/j.korte@me.com" method="POST">
	<div class="form-group">
	<input type="hidden" name="_next" value="/registered/"/>
	    <input type="email" name="_replyto" class="form-control" placeholder="Your email adress">
  	</div>
	<div class="form-group">
		<button type="submit" class="btn btn-default">Register</button>
    </div>
</form> 

## Roadmap
* Collaborative editing through connection to my master thesis outliner webapp
* Auto-update for Windows and Mac, packages for more Linux distros
* Drag'n'Drop
* Insert images
* Insert mails, open them in the email client again
* When the user deletes an item: Move it to an archive instead of permanently deleting it

## Changelog
Apart from the listed huge changes new versions often contain small improvements and bugfixes, look in the detailed [Git log](https://github.com/TreeNote/TreeNote/commits/master) if you are interested.

#### [Version 1.7.8](https://github.com/TreeNote/TreeNote/releases/tag/v1.7.8) (February 16, 2017)
- New PyQt version finally fixes graphical glitches and crashes when using W and S (move item up or down)

#### [Version 1.7.7](https://github.com/TreeNote/TreeNote/releases/tag/v1.7.7) (February 7, 2017)
- Test for write permission when selecting a filename for saving

#### [Version 1.7.6](https://github.com/TreeNote/TreeNote/releases/tag/v1.7.6) (February 5, 2017)
- I adjusted the code for the Linux packages, so **this version can't read .treenote files from older versions. Export your tree with the old version and import it again with the new version.**
- Fixed a PyQt bug causing W and S (move item up or down) not to work anymore

#### [Version 1.7](https://github.com/TreeNote/TreeNote/releases/tag/v1.7) (January 3, 2017)
- It was necessary to remove the automatic update check. A future release will contain automatic update installation. Please register for my newsletter until then.
- New feature: Link to files
- The manual is complete now
- The user interface and the manual is available in English and German now
- Bug fixes

#### [Version 1.6](https://github.com/TreeNote/TreeNote/releases/tag/v1.6) (October 6, 2016)
- New filter `date<1d` gives all items whose date is at most tomorrow
- Bookmarks with children get highlighted (every 3 hours)
- Pasted plain text trees get recognized, whatever indention they have (spaces, tabs)
- Many more bug fixes

#### [Version 1.5](https://github.com/TreeNote/TreeNote/releases/tag/v1.5) (September 11, 2016)
- Specify backup folder
- Focus in plan tab focuses in tree tab
- The menu has accelerator keys now
- Fixed 'Backups don't work on windows'
- Fixed 'Expanded state is not saved when expanding a row with the mouse'

#### [Version 1.4](https://github.com/TreeNote/TreeNote/releases/tag/v1.4) (August 30, 2016)
- **This version can't read .treenote files from older versions, so export your tree with the old version and import it again with the new version.**
- Bookmarks: Save optionally current root item
- Copy, paste, cut
- Print function
- Added a path bar
- Internal links
- File selected rows
- Planning view
- Increase estimate shortcut
- Set estimate in minutes with shortcuts like 10 30 60 120
- Shortcuts like '5d' to set start date to in 5 days
- Fix: Autocomplete with all tags of the tree when focused, not just with current focused tag subset
- Fix: When coloring multiple rows, the selection was not kept
- Fix: Vertical move out of the view now scrolls to the selection
- Fix: New line inside a row at the bottom edge shall scroll the tree upwards, otherwise the just entered new line is not in the visible part of the view

#### [Version 1.3](https://github.com/TreeNote/TreeNote/releases/tag/v1.3) (July 13, 2016)
* Fullscreen mode
* User interface: Collapse filter widgets 
* List tags of visible items only
* Huge performance improvements
* Import from the mac todo application 'The Hit List'

#### [Version 1.2](https://github.com/TreeNote/TreeNote/releases/tag/v1.2) (June 20, 2016)
* You can set indentation size in the settings
* Clearer opened / closed icons
* Fixed error in update dialog
* No extra column for the checkboxes
* Export all databases which have changes to the folder 'backups' each .... minutes 
* Removed CouchDB dependency and with that the feature to add several databases. You now have a single local JSON tree only and can't edit databases collaberatively anymore. However, editing is blazingly fast now and without bugs or crashes. I liked the feature of collaberatively editing and want to implement it sometime with a better database backend.

#### [Version 1.1](https://github.com/TreeNote/TreeNote/releases/tag/v1.1.0) (Feb 14, 2016)
* Automatic update check
* Copy a selection of the tree to the clipboard in plain text
* Paste a plain text list or tree from the clipboard into the tree
* Export the database to a plain text file
* Long texts inside an entry are automatically wrapped. While editing an entry, press alt + enter for a line break.
* Change font*size and padding (in the menu)
* Hide the sidebars (with a button)
* Go up / Open parent row (in the menu)
* Fixed styling bugs on windows
* Many small improvements and bugfixes (more details in the Git log)

#### [Version 1.0](https://github.com/TreeNote/TreeNote/releases/tag/v1.0.0) (June 23, 2015)
* Initial release after a half year of intensive development during my bachelor thesis




# Documentation

TreeNote is written in the most beautiful programming language available: Python.
It pays off to learn it. So start with one of [these great books](http://www.pixelmonkey.org/2015/06/06/pybooks).  

## Architecture
TreeNote uses the GUI library PyQt, which is a Python wrapper for the popular Qt library. Qt has a really good documentation. If you want to know what a particular class is able to to, just google it, e.g. ‘qtreeview 5’ (the 5 is for Qt version 5) and it will give you [http://doc.qt.io/qt-5/qtreeview.html](http://doc.qt.io/qt-5/qtreeview.html).

If you don’t know how to do something:

-   Look at the [PyQt examples](https://github.com/baoboa/pyqt5/tree/master/examples)
-   Look into the book [Rapid GUI Programming with Python and Qt](http://www.amazon.com/Programming-Python-Prentice-Software-Development/dp/0132354187).
-   Google e.g. ‘drag drop qt’ and you will find some results on stackoverflow.com. All the C++ Qt code is easily convertable to Python.

The `QTreeView` interacts with the underlying data structure through the class `TreeModel`, a subclass of the `QAbstractItemModel`. The overwritten methods can be divided into two categories:

1. When the **views needs data** to build or change itself, it calls the following methods:
	* Each `QModelIndex` contains a pointer to a `Tree_item`. It can be retrieved with `getItem(index)`.
	* `index(row, parent_index)` and `parent(index)` return a specific `QModelIndex`
	* `rowCount(index)` returns not just the row count of the `Tree_item` to the given `index`, but calls `Tree_item : init_childs` to get the children from the database and insert them as new `Tree_item` objects into the local data instance.


2. When the **user does an action**, methods like `insertRows(), removeRows(), move_left()` and `setData()` are called. They edit the underlying data model. 

## Search
Filtering is done with the `QSortFilterProxyModel` very easily. It is
inserted between the regular model and the view and passes through only
the desired items, for example the ones which match to a search string.

## Translation
1. Create / update the translation files in `resources/locales/` from the current code by executing `pylupdate5 treenote.pro`
2. Doubleclick these .ts files to translate them with Qt Linguist
3. Compile the .ts files by executing `lrelease resources/locales/*.ts`. This creates .qm files which are used by application.
4. Check the translation by running TreeNote with `export LANGUAGE=de_DE` then `python3 treenote.py`

## Deployment  (creating executable files)

### Set up the deployment environment
- Linux and Windows: Install PyInstaller by entering `pip3 install pyinstaller` in cmd.exe / terminal
- Mac OS X: PyInstaller does not work with the pip version of PyQt [yet](https://github.com/pyinstaller/pyinstaller/issues/2152), so we have to do the following:
	- Download the latest dev version of PyInstaller, e.g. with `git clone https://github.com/pyinstaller/pyinstaller.git`	
	- Install `Xcode` from the AppStore
	- Install [Qt](http://www.qt.io/download-open-source/)
	- Download the [SIP source package](http://www.riverbankcomputing.com/software/sip/download). Unarchive it and run:
	
	        >     python3 configure.py
	        >     make
	        >     sudo make install
	- Download the [PyQt source package](http://www.riverbankcomputing.com/software/pyqt/download5). Unarchive it and run (takes several minutes):

	        >     python3 configure.py --qmake=/Users/YourUsername/Qt/5.7/clang_64/bin/qmake 
	        >     make
	        >     sudo make install        

### Deploy
1. Increase the 1.x version number in version.py. For bugfixes increase 1.11.x only.
2. Create binaries with PyInstaller: 
	* Create binaries
		- Windows
			- Execute in cmd.exe:
		            `pyinstaller --path=C:\Users\YourUsername\AppData\Local\Programs\Python\Python35\Lib\site-packages\PyQt5\Qt\bin --noconsole --icon=treenote\resources\images\treenote.ico TreeNote.py` (the --path option is needed until [this bug](https://github.com/pyinstaller/pyinstaller/issues/2152) is fixed)
			- Copy the resources folder into the new treenote folder
		- Mac OS X
			- Execute in Terminal:
		            `python3 /path/to/pyinstaller.py --noconsole --icon=treenote/resources/images/treenote.icns TreeNote.py`
			- Right-click on treenote.app and choose “Show Package Contents”. Copy the resources folder to 'treenote.app/Contents/MacOS'	
	* Zip the new TreeNote folder / the TreeNote.app and name it e.g. `treenote_v1.7.7_windows.zip`	
	* Test the release by running the binary
3. Create a GitHub release, add a changelog and upload the .zip files 
4. Update the download links and the changelog on the [download site](https://github.com/TreeNote/treenote.github.io/edit/master/download.md)
5. Create a pip release:
	- Once: Enter your pip credentials in a file in your home folder like here: https://packaging.python.org/distributing/#create-an-account
	- `python setup.py sdist`	
	- `twine upload dist/*`
6. For major versions: Write a mail to interested people


### Creating an Python package
- Create a package with `python setup.py bdist_wheel`
- Install the new package with `pip3 install dist/TreeNote-1.7.0-py3-none-any.whl` for testing
- Upload it with `twine upload dist/*`
- [Full guide](https://packaging.python.org/distributing/#packaging-your-project)

### Creating an Arch Linux package
`makepkg --printsrcinfo > .SRCINFO`



# Contribute

## Install and run
1. Install the dependencies
    
    <i class="fl-ubuntu"></i> Ubuntu
    
    - Enter in Terminal:<br>
            `sudo apt-get install git python3-pip`<br>
            `sudo apt-get purge appmenu-qt5`<br>
            `sudo pip3 install pyqt5`

    <br><i class="fl-fedora"></i> Fedora
    
    - Enter in Terminal:<br>
            `sudo yum install git python3-pip`<br>
            `sudo pip3 install pyqt5`

    <br><i class="fa fa-windows" aria-hidden="true"></i> Windows
    
    - Install [Git](https://git-scm.com/download)
    - Install [Python 3](https://www.python.org/downloads/). During installation check the checkbox 'Add to path'.
    - Install Python modules by entering `pip install pyqt5` in cmd.exe

    <br><i class="fa fa-apple" aria-hidden="true"></i> OS X
    
    - Install [Python 3](https://www.python.org/downloads/).
    - Install Python modules by entering `pip3 install pyqt5` in Terminal
    <br><br>

2. Clone the Git repo by opening a command line and entering `git clone https://github.com/TreeNote/TreeNote.git`
3. Navigate into the code folder with `cd TreeNote/treenote`
4. Run with `python3 TreeNote.py`

* To update the code to the latest changes, run `git pull` inside the TreeNote folder
* For developing, I recommend the IDE [PyCharm](https://www.jetbrains.com/pycharm/). 
  * Set 120 code width
  * You may want to disable warnings (then you can recognize in the scrollbar the lines you edit)
* To share your code changes, I recommend the Git GUI [GitKraken](http://gitkraken.com/)

## Style conventions
- Only methods overriding Qt methods inherit Qts `camelCase` naming scheme, everything else is Pythons `snake_case` naming scheme. Even slots. 
- Use docstrings:

    ```
    def function(a, b):
        """Do something and return a list."""

    class SampleClass(object):
        """Summary of class here.

        Longer class information.
        Longer class information.
        """
    ```
- The layout of a class should be like this:
    - docstring
    - \_\_magic\_\_ methods
    - other methods
    - overrides of Qt methods
    


# Mobile app

The webapp which I will produce in my master thesis will be usable on a smartphone.
It works offline, too.
It won't have personal task management stuff like start dates, but when there is a demand, I could code it.

## Android app

This app was created by me and a fellow student at university.
It is working nice, but I don't like its progamming language (Java is so cumbersome compared to Python).
Therefore I will not develop it any further.
If you want to pick it up, I can explain you some code, but in general it should be written cleanly.

[Demo-Video (in german)](https://youtu.be/K3lhwsl76LU)

Download the [.apk file](https://github.com/TreeNote/TreeNoteAndroid/releases/latest).
If you have a Google Play Developer Account, feel free to publish the app.

Synchronisation with a JSON file in your OwnCloud is possible.
However, Desktop TreeNote is not able to synchronize with a JSON file.
When I finished my master thesis I will have a neat tree API, someone may implement it to the Android app to have fluent synchronisation.

The code is [on GitHub](https://github.com/TreeNote/TreeNoteAndroid/).

<img style="float: left; width: 30%; margin-right: 1%; margin-bottom: 0.5em;" src="http://raw.githubusercontent.com/TreeNote/TreeNoteAndroid/master/screenshot_1.png"><img style="float: left; width: 30%; margin-right: 1%; margin-bottom: 0.5em;" src="http://raw.githubusercontent.com/TreeNote/TreeNoteAndroid/master/screenshot_2.png"><img style="float: left; width: 30%; margin-right: 1%; margin-bottom: 0.5em;" src="http://raw.githubusercontent.com/TreeNote/TreeNoteAndroid/master/screenshot_3.png">


# Contributors and participation

* [Jan Korte](https://github.com/Tamriel)
* [Florian Bruhin](https://github.com/The-Compiler)
* [Markus Hackspacher](https://github.com/MarkusHackspacher)
