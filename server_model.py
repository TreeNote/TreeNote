from PyQt5.QtCore import *

import model


class Server():

    def __init__(self, bookmark_name, url, database_name, db):
        self.bookmark_name = bookmark_name
        self.url = url
        self.database_name = database_name
        self.model = model.TreeModel(db, header_list=['Text', 'Start date', 'Estimate'])


class ServerModel(QAbstractListModel):

    def __init__(self):
        super(ServerModel, self).__init__()
        self.servers = []

    def headerData(self, column, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return 'Databases'
        return None

    def columnCount(self, parent):
        return 1

    def rowCount(self, parent):
        return len(self.servers)

    def get_server(self, index):
        return self.servers[index.row()]

    def get_server(self, index):
        return self.servers[index.row()]

    def data(self, index, role):
        if role != Qt.DisplayRole:
            return None
        return self.get_server(index).bookmark_name

    def set_data(self, index, bookmark_name, url, db_name):
        self.servers[index.row()].bookmark_name = bookmark_name
        self.servers[index.row()].url = url
        self.servers[index.row()].db_name = db_name

    def add_server(self, server):
        self.beginResetModel()
        self.servers.append(server)
        self.endResetModel()

    def delete_server(self, index):
        self.beginResetModel()
        del self.servers[index.row()]
        self.endResetModel()
