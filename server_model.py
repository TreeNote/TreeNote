from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import couchdb
import model
import sys
import subprocess
import time


def get_db(url, database_name):
    if sys.platform == "darwin":
        subprocess.call(['/usr/bin/open', '/Applications/Apache CouchDB.app'])

    def get_create_db(url, new_db_name):

        if url != '':
            # todo check if couchdb was started, else exit loop and print exc
            # http://stackoverflow.com/questions/1378974/is-there-a-way-to-start-stop-linux-processes-with-python
            server = couchdb.Server(url)
        else: # local db
            # todo check if couchdb was started, else exit loop and print exc
            server = couchdb.Server()
        try:
            # del server[new_db_name]
            return server, server[new_db_name]
        except couchdb.http.ResourceNotFound:
            new_db = server.create(new_db_name)
            new_db[model.ROOT_ID] = (model.NEW_DB_ITEM.copy())
            print("Database does not exist. Created the database.")
            return server, new_db
        except couchdb.http.Unauthorized as err:
            print(err.message)

        except couchdb.http.ServerError as err:
            print(err.message)

    local_server = None
    while local_server is None:  # wait until couchdb is started
        try:
            time.sleep(0.1)
            local_server, db = get_create_db(url, database_name)
            break
        except Exception as e:
            print("Trying to connect to database, but: " + str(e))
    return db

    if url != '':
        get_create_db(db_name, url)
        local_server.replicate(db_name, url + db_name, continuous=True)
        local_server.replicate(url + db_name, db_name, continuous=True)


class Server():
    def __init__(self, bookmark_name, url, database_name):
        self.bookmark_name = bookmark_name
        self.url = url
        self.database_name = database_name
        self.model = model.TreeModel(get_db(url, database_name), header_list=['Text', 'Start date', 'Estimate'])


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
        if role != Qt.DisplayRole: return None
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
