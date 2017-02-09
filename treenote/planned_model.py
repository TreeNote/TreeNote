#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from PyQt5.QtCore import QAbstractItemModel, QModelIndex, Qt


class PlannedModel(QAbstractItemModel):
    def __init__(self, item_model, filter_proxy):
        super(PlannedModel, self).__init__()
        self.item_model = item_model
        self.filter_proxy = filter_proxy
        self.refresh_model()

    def indexes(self):
        return (self.map_to_planned_index(index) for index in self.orignal_indexes)

    def items(self):
        return (self.item_model.getItem(index) for index in self.orignal_indexes)

    def refresh_model(self):
        # we map to the indexes of the item_model
        self.beginResetModel()
        self.orignal_indexes = [index for index in self.item_model.indexes() if
                                self.item_model.getItem(index).planned != 0]
        if self.filter_proxy.filter:
            self.orignal_indexes = [index for index in self.orignal_indexes if
                                    self.filter_proxy.filterAcceptsRow(index.row(), index.parent())]
        # sort by planned level, then by planned_order
        self.orignal_indexes.sort(
            key=lambda index: (self.item_model.getItem(index).planned, self.item_model.getItem(index).planned_order))
        self.endResetModel()

    def columnCount(self, parent):
        return self.item_model.columnCount(parent)

    def headerData(self, column, orientation, role=Qt.DisplayRole):
        return self.item_model.headerData(column, orientation, role)

    def getItem(self, index):
        return self.item_model.getItem(index.internalPointer())

    def flags(self, index):
        return Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def index(self, row, column, parent=None):
        if row >= len(self.orignal_indexes):
            return QModelIndex()
        return self.createIndex(row, column, self.orignal_indexes[row])

    def parent(self, index):
        return QModelIndex()

    def rowCount(self, parent):
        return len(self.orignal_indexes) if parent == QModelIndex() else 0

    def is_task_available(self, index):
        return self.item_model.is_task_available(index.internalPointer())

    def setData(self, index, value, role=None):
        self.item_model.set_data(value, index=self.map_to_original_index(index), field='text')
        return True

    def data(self, index, role):
        return self.item_model.data(self.map_to_original_index(index), role)

    def map_to_original_index(self, planned_index):
        original_index = planned_index.internalPointer()
        item = original_index.internalPointer()
        # we cant pass the original_index, because it has the wrong column()
        # therefore we create an index with the same column which links to the original item
        original_index_with_same_column = self.item_model.createIndex(planned_index.row(), planned_index.column(), item)
        return original_index_with_same_column

    def map_to_planned_index(self, original_index):
        for i, index in enumerate(self.orignal_indexes):
            if index == original_index:
                return self.index(i, 0)
        return QModelIndex()
