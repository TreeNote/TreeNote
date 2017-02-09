#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from PyQt5.QtCore import QAbstractItemModel, QModelIndex, Qt

import treenote.model as model

FULL_PATH = 'FULL_PATH'


class TagTreeItem(object):

    def __init__(self, text, parent=None):
        self.parentItem = parent
        self.text = text
        self.childItems = []

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

    def add_and_return_child(self, item):
        for existing_item in self.childItems:
            if existing_item.text == item.text:
                return existing_item

        self.childItems.append(item)
        return item


class TagModel(QAbstractItemModel):

    def __init__(self):
        super(TagModel, self).__init__()
        self.rootItem = TagTreeItem(None)

    def columnCount(self, parent):
        return 1

    def headerData(self, column, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return 'Tags'
        return None

    def getItem(self, index):
        if index.isValid():
            item = index.internalPointer()
            if item:
                return item

        return self.rootItem

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags

        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def index(self, row, column, parent):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        if not parent.isValid():
            parentItem = self.rootItem
        else:
            parentItem = parent.internalPointer()

        childItem = parentItem.child(row)
        if childItem:
            return self.createIndex(row, column, childItem)
        else:
            return QModelIndex()

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()

        childItem = index.internalPointer()
        parentItem = childItem.parent()

        if parentItem == self.rootItem:
            return QModelIndex()

        return self.createIndex(parentItem.row(), 0, parentItem)

    def rowCount(self, parent):
        if parent.column() > 0:
            return 0

        if not parent.isValid():
            parentItem = self.rootItem
        else:
            parentItem = parent.internalPointer()

        return parentItem.childCount()

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
            splitted_tag = whole_tag.split(model.TAG_DELIMITER)

            def add_below(parent, remaining_tags):
                new_item = parent.add_and_return_child(TagTreeItem(model.TAG_DELIMITER + remaining_tags[0], parent))
                del remaining_tags[0]
                if len(remaining_tags) > 0:
                    add_below(new_item, remaining_tags)

            add_below(self.rootItem, splitted_tag)
        self.endResetModel()
