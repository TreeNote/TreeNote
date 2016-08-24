from PyQt5.QtCore import *


class PlannedModel(QAbstractItemModel):
    def __init__(self, item_model):
        super(PlannedModel, self).__init__()
        self.item_model = item_model
        self.refresh_model()

    def refresh_model(self):
        self.beginResetModel()
        self.indexes = [index for index in self.item_model.indexes() if self.item_model.getItem(index).planned != 0]
        self.endResetModel()

    def columnCount(self, parent):
        return self.item_model.columnCount(parent)

    def headerData(self, column, orientation, role=Qt.DisplayRole):
        return self.item_model.headerData(column, orientation, role)

    def getItem(self, index):
        return self.item_model.getItem(index)

    def flags(self, index):
        return Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def index(self, row, column, parent):
        return self.createIndex(row, column, self.getItem(self.indexes[row]))

    def parent(self, index):
        return QModelIndex()

    def rowCount(self, parent):
        return len(self.indexes) if parent == QModelIndex() else 0

    def is_task_available(self, index):
        return self.item_model.is_task_available(index)

    def data(self, index, role):
        if not index.isValid():
            return None

        if role != Qt.DisplayRole and role != Qt.EditRole:
            return None

        return self.item_model.get_data(self.getItem(index), index)
