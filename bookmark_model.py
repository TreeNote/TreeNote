from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
import couchdb
import time
import sys
import subprocess
import threading
import socket
import model
import simple_model



class BookmarkModel(simple_model.SimpleModel):
    def __init__(self):
        super(BookmarkModel, self).__init__()
        self.rootItem.header_list = ['Bookmarks']

    def add(self, search_text):
        self.beginResetModel()
        self.rootItem.childItems.append(simple_model.TreeItem(search_text, self.rootItem))
        self.endResetModel()




