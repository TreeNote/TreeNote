from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
import couchdb
import time
import sys
import subprocess
import threading
import socket
import item_model
import simple_model

FULL_PATH = 'FULL_PATH'


class TagTreeItem(simple_model.TreeItem):
    def __init__(self, text, parent=None):
        self.parentItem = parent
        self.text = text
        self.childItems = []

    def add_and_return_child(self, item):
        for existing_item in self.childItems:
            if existing_item.text == item.text:
                return existing_item
        self.childItems.append(item)
        return item


class TagModel(simple_model.SimpleModel):
    def __init__(self):
        super(TagModel, self).__init__()
        self.rootItem = TagTreeItem(None)
        self.rootItem.header_list = ['Tags']

    def data(self, index, role):
        if not index.isValid():
            return None

        if role != Qt.DisplayRole and role != FULL_PATH:
            return None

        item = index.internalPointer()

        if role == FULL_PATH:
            tag_list = list()

            def append_items(item):
                tag_list.append(item.text)
                parent = item.parentItem
                if parent.text is not None:
                    append_items(parent)

            append_items(item)
            return ''.join(reversed(tag_list))

        return item.text


    def setupModelData(self, tags_set):
        self.beginResetModel()
        self.rootItem.childItems = []
        for whole_tag in sorted(tags_set, key=str.lower):
            splitted_tag = whole_tag.split(item_model.DELIMITER)

            def add_below(parent, remaining_tags):
                new_item = parent.add_and_return_child(TagTreeItem(item_model.DELIMITER + remaining_tags[0], parent))
                del remaining_tags[0]
                if len(remaining_tags) > 0:
                    add_below(new_item, remaining_tags)

            add_below(self.rootItem, splitted_tag)
        self.endResetModel()



