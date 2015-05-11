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
SEARCH_TEXT = 'search_text'
SHORTCUT = 'shortcut'
NEW_BOOKMARK_DB_ITEM = {NAME: '', SEARCH_TEXT: '', SHORTCUT: ''}

class BookmarkItem(simple_model.TreeItem):
    def __init__(self, text, id, parent=None):
        self.parentItem = parent
        self.text = text
        self.childItems = []
        self.id = id

# each user has local bookmarks
class BookmarkModel(simple_model.SimpleModel):
    def __init__(self, db):
        super(BookmarkModel, self).__init__()
        self.rootItem = BookmarkItem('root', '0', None)
        self.rootItem.header_list = ['Bookmarks']
        self.db = db
        map = "function(doc) { \
                    emit(doc, null); \
                }"
        res = self.db.query(map)
        for row in res:
            db_item = self.db[row.id]
            self.rootItem.childItems.append(BookmarkItem(db_item[NAME],row.id, self.rootItem))

    def add_or_update(self, name, search_text, shortcut, index=None):
        self.beginResetModel()
        if index is None:
            item_id, _ = self.db.save(NEW_BOOKMARK_DB_ITEM.copy())
            db_item = self.db[item_id]
            self.rootItem.childItems.append(BookmarkItem(name, item_id, self.rootItem))
        else:
            item = self.getItem(index)
            db_item = self.db[item.id]
            item.text = name
        db_item[NAME] = name
        db_item[SEARCH_TEXT] = search_text
        db_item[SHORTCUT] = shortcut
        self.db[item_id] = db_item
        self.endResetModel()

    def delete(self, search_text):
        self.beginResetModel()
        self.rootItem.childItems.append(BookmarkItem(search_text, self.rootItem))
        item_id, _ = self.db.save(BookmarkItem.copy())
        db_item = self.db[item_id]
        db_item[NAME] = search_text
        self.db[item_id] = db_item
        self.endResetModel()




