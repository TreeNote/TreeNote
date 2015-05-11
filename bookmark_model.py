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
import collections

NAME = 'name'
SEARCH_TEXT = 'search_text'
ICON = 'icon'
SHORTCUT = 'shortcut'
NEW_BOOKMARK_DB_ITEM = {NAME: '', SEARCH_TEXT: '', ICON: '', SHORTCUT: ''}


class BookmarkItem(simple_model.TreeItem):
    def __init__(self, text, parent=None):
        self.parentItem = parent
        self.text = text
        self.childItems = collections.OrderedDict()

    def child(self, row):
        return self.childItems[row]

    def childCount(self):
        return len(self.childItems)

    def parent(self):
        return self.parentItem

    def row(self):
        if self.parentItem:
            return self.parentItem.childItems.index(self)

        return 0

class BookmarkModel(simple_model.SimpleModel):
    def __init__(self, db):
        super(BookmarkModel, self).__init__()
        self.rootItem.header_list = ['Bookmarks']
        self.db = db
        map = "function(doc) { \
                    emit(doc, null); \
                }"
        res = self.db.query(map)
        for row in res:
            db_item = self.db[row.id]
            self.rootItem.childItems.append(BookmarkItem(db_item[NAME], self.rootItem))

    def add(self, search_text):
        self.beginResetModel()
        self.rootItem.childItems.append(BookmarkItem(search_text, self.rootItem))
        item_id, _ = self.db.save(NEW_BOOKMARK_DB_ITEM.copy())
        db_item = self.db[item_id]
        db_item[NAME] = search_text
        self.db[item_id] = db_item
        self.endResetModel()

    def update(self, item_id, name, search_text, icon, shortcut):
        self.beginResetModel()
        self.rootItem.childItems.ge(BookmarkItem(search_text, self.rootItem))
        db_item = self.db[item_id]
        db_item[NAME] = name
        db_item[SEARCH_TEXT] = search_text
        db_item[ICON] = icon
        db_item[SHORTCUT] = shortcut
        self.db[item_id] = db_item
        self.endResetModel()

    def delete(self, search_text):
        self.beginResetModel()
        self.rootItem.childItems.append(BookmarkItem(search_text, self.rootItem))
        item_id, _ = self.db.save(NEW_BOOKMARK_DB_ITEM.copy())
        db_item = self.db[item_id]
        db_item[NAME] = search_text
        self.db[item_id] = db_item
        self.endResetModel()




