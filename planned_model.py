from PyQt5.QtCore import *


class PlannedModel(QAbstractItemModel):
    def __init__(self, item_model, filter_proxy):
        super(PlannedModel, self).__init__()
        self.item_model = item_model
        self.filter_proxy = filter_proxy
        self.refresh_model()

    def refresh_model(self):
        # we map to the indexes of the item_model
        self.beginResetModel()
        self.indexes = [index for index in self.item_model.indexes() if self.item_model.getItem(index).planned != 0]
        if self.filter_proxy.filter:
            self.indexes = [index for index in self.indexes if
                            self.filter_proxy.filterAcceptsRow(index.row(), index.parent())]
        self.indexes.sort(key=lambda index: self.item_model.getItem(index).planned)
        self.endResetModel()

    def columnCount(self, parent):
        return self.item_model.columnCount(parent)

    def headerData(self, column, orientation, role=Qt.DisplayRole):
        return self.item_model.headerData(column, orientation, role)

    def getItem(self, index):
        return self.item_model.getItem(index.internalPointer())

    def flags(self, index):
        return Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def index(self, row, column, parent):
        return self.createIndex(row, column, self.indexes[row])

    def parent(self, index):
        return QModelIndex()

    def rowCount(self, parent):
        return len(self.indexes) if parent == QModelIndex() else 0

    def is_task_available(self, index):
        return self.item_model.is_task_available(index.internalPointer())

    def setData(self, index, value, role=None):
        self.item_model.set_data(value, index=self.map_to_original_index(index), field='text')
        return True

    def data(self, index, role):
        return self.item_model.data(self.map_to_original_index(index), role)

    def map_to_original_index(self, index):
        original_index = index.internalPointer()
        item = original_index.internalPointer()
        # we cant pass the original_index, because it has the wrong column()
        # therefore we create an index with the same column which links to the original item
        original_index_with_same_column = self.createIndex(index.row(), index.column(), item)
        return original_index_with_same_column
