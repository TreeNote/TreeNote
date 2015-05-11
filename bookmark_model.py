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

NAME = 'name'
NEW_BOOKMARK_DB_ITEM = {NAME: '', 'search_text': '', 'icon': '', 'shortcut': ''}


class BookmarkModel(simple_model.SimpleModel):
    def __init__(self, db):
        super(BookmarkModel, self).__init__()
        self.db = db
        self.rootItem.header_list = ['Bookmarks']

    def rowCount(self, parent=QModelIndex()):
        if parent.column() > 0:
            return 0

        if not parent.isValid():
            parentItem = self.rootItem
        else:
            parentItem = parent.internalPointer()

        # todo
        return parentItem.childCount()

    def add(self, search_text):
        self.beginResetModel()
        self.rootItem.childItems.append(simple_model.TreeItem(search_text, self.rootItem))
        item_id, _ = self.db.save(NEW_BOOKMARK_DB_ITEM.copy())
        db_item = self.db[item_id]
        db_item[NAME] = search_text
        self.db[item_id] = db_item
        self.endResetModel()




