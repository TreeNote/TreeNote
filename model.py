from PyQt5.QtCore import QAbstractItemModel, QModelIndex, Qt, QThread, QObject, pyqtSignal, QSortFilterProxyModel, QPersistentModelIndex
import couchdb
import time
import sys
import subprocess
import threading
import socket


class Updater(QThread):
    """
    This Thread watches the db for own and foreign changes and updates the view.
    """

    def __init__(self, model):
        super(QThread, self).__init__()
        self.model = model

    def run(self):  # this updates the view
        all_changes = self.model.db.changes(descending=True)
        last_seq = all_changes['results'][0]['seq']
        changes_list = self.model.db.changes(feed='continuous', heartbeat=sys.maxsize, include_docs=True, since=last_seq)  # no need for heartbeet, because the db is local
        for line in changes_list:
            if 'doc' in line:
                print(line)
                db_item = line['doc']
                item_id = db_item['_id']
                # todo if item_id in self.model.id_index_dict:  # update the view only if the item is already loaded
                if 'change' in db_item:
                    change_dict = db_item['change']
                    my_edit = change_dict['user'] == socket.gethostname()
                    method = change_dict['method']
                    if method == 'updated':
                        self.model.updated_signal.emit(item_id, db_item['text'], my_edit)
                    elif method == 'added':
                        self.model.added_signal.emit(item_id, change_dict['position'], change_dict['id_list'], my_edit, change_dict['set_edit_focus'])
                    elif method == 'removed':
                        self.model.removed_signal.emit(item_id, change_dict['position'], change_dict['count'], my_edit)
                    elif method == 'moved_vertical':
                        self.model.moved_vertical_signal.emit(item_id, change_dict['position'], change_dict['count'], change_dict['up_or_down'], my_edit)
                elif '_deleted' in db_item:
                    self.model.deleted_signal.emit(item_id)



class Tree_item(object):
    """
    To understand Qt's way of building a TreeView, read:
    http://trevorius.com/scrapbook/uncategorized/pyqt-custom-abstractitemmodel/
    http://doc.qt.io/qt-5/qtwidgets-itemviews-editabletreemodel-example.html
    """

    def __init__(self, text, model, parent=None):
        self.model = model
        self.parentItem = parent
        self.text = text
        self.childItems = None
        self.id = None

    def child_number(self):
        if self.parentItem is not None:
            return self.parentItem.childItems.index(self)
        return 0

    def init_childs(self, parent_index):
        if self.childItems is None:  # deserialise children from the db
            self.childItems = []
            children_id_list = self.model.db[self.id]['children'].split()
            for position in range(len(children_id_list)):
                id = children_id_list[position]
                self.add_child(position, self.model.db[children_id_list[position]]['text'], id)
                new_index = self.model.index(position, 0, parent_index)
                self.model.id_index_dict[id] = QPersistentModelIndex(new_index)
                self.model.pointer_set.add(new_index.internalId())

    def add_child(self, position, text, id):
        item = Tree_item('', self.model, self)
        self.childItems.insert(position, item)
        self.childItems[position].text = text
        self.childItems[position].id = id

    def remove_children(self, position, count):
        for row in range(count):
            self.childItems.pop(position)


class TreeModel(QAbstractItemModel):
    """
    The methods of this model changes the database only. The view gets updated by the Updater-Thread.
    """
    updated_signal = pyqtSignal(str, str, bool)
    added_signal = pyqtSignal(str, int, list, bool, bool)
    removed_signal = pyqtSignal(str, int, int, bool)
    moved_vertical_signal = pyqtSignal(str, int, int, int, bool)
    deleted_signal = pyqtSignal(str)

    def __init__(self, parent=None):
        super(TreeModel, self).__init__(parent)

        if sys.platform == "darwin":
            subprocess.call(['/usr/bin/open', '/Applications/Apache CouchDB.app'])

        def get_create_db(new_db_name, db_url=None):
            if db_url:
                server = couchdb.Server(db_url)
            else:
                server = couchdb.Server()
            try:
                #del server[new_db_name]
                return server, server[new_db_name]
            except couchdb.http.ResourceNotFound:
                new_db = server.create(new_db_name)
                new_db['0'] = ({'text': 'root', 'children': ''})
                print("Database does not exist. Created the database.")
                return server, new_db
            except couchdb.http.Unauthorized as err:
                print(err.message)

            except couchdb.http.ServerError as err:
                print(err.message)

        # If a database change is arriving, we just have the id. To get the corresponding Tree_item, we store it's QModelIndex in this dict:
        self.id_index_dict = dict()  # New indexes are created by TreeModel.index(). That function stores the index in this dict.
        self.pointer_set = set()

        db_name = 'tree'
        server_url = 'http://192.168.178.42:5984/'
        local_server = None
        while local_server is None:  # wait until couchdb is started
            try:
                time.sleep(0.1)
                local_server, self.db = get_create_db(db_name)
                break
            except:
                pass

        # get_create_db(db_name, server_url)
        # local_server.replicate(db_name, server_url + db_name, continuous=True)
        # local_server.replicate(server_url + db_name, db_name, continuous=True)

        self.rootItem = Tree_item('root item', self)
        self.rootItem.id = '0'
        index = QModelIndex()
        self.id_index_dict['0'] = index
        self.pointer_set.add(QModelIndex().internalId())


        self.updater = Updater(self)
        self.updater.start()

    def columnCount(self, parent):
        return 1

    def flags(self, index):
        if not index.isValid():
            return 0

        return Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def getItem(self, index):
        if index.isValid():
            item = index.internalPointer()
            if item:
                return item

        return self.rootItem

    def index(self, row, column, parent=QModelIndex()):
        if parent.isValid() and parent.column() != 0:
            return QModelIndex()

        if parent.internalId() not in self.pointer_set:
            return QModelIndex()

        parentItem = self.getItem(parent)
        childItem = parentItem.childItems[row]
        return self.createIndex(row, column, childItem)

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()

        if index.internalId() not in self.pointer_set:
            return QModelIndex()

        childItem = self.getItem(index)
        parentItem = childItem.parentItem

        if parentItem == self.rootItem:
            return QModelIndex()
        return self.createIndex(parentItem.child_number(), 0, parentItem)

    def rowCount(self, parent=QModelIndex()):
        parentItem = self.getItem(parent)
        parentItem.init_childs(parent)
        return len(parentItem.childItems)

    def data(self, index, role):
        if not index.isValid():
            return None

        if role != Qt.DisplayRole and role != Qt.EditRole:
            return None

        item = self.getItem(index)
        return item.text

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole:
            return False

        item = self.getItem(index)
        db_item = self.db[item.id]
        db_item['text'] = value

        db_item['change'] = dict(method='updated', user=socket.gethostname())
        self.db[item.id] = db_item
        return True

    def insertRows(self, position, parent, indexes=None):
        id_list = list()
        if indexes is None:  # used from view, create a single new row / self.db item
            set_edit_focus = True
            child_id, _ = self.db.save({'text': '', 'children': ''})
            id_list.append(child_id)
        else:  # used from move methods, add existing db items to the parent
            set_edit_focus = False
            for index in indexes:  # todo ginge auch über position
                id_list.append(self.getItem(index).id)
        parent_item_id = self.getItem(parent).id
        db_item = self.db[parent_item_id]
        children_list = db_item['children'].split()
        children_list_new = children_list[:position] + id_list + children_list[position:]
        db_item['children'] = ' '.join(children_list_new)
        db_item['change'] = dict(method='added', id_list=id_list, position=position, set_edit_focus=set_edit_focus, user=socket.gethostname())
        self.db[parent_item_id] = db_item
        return True

    def removeRows(self, indexes, delete=True, restore_selection=False):
        for index in indexes:
            child_item = self.getItem(index)
            child_db_item = self.db.get(child_item.id)
            if child_db_item is not None:
                self.db.delete(child_db_item)

                def delete_childs(item):
                    for ch_item in item.childItems:
                        delete_childs(ch_item)
                        ch_db_item = self.db.get(ch_item.id)
                        if ch_db_item is not None:
                            self.db.delete(ch_db_item)

                delete_childs(child_item)

                parent_item_id = child_item.parentItem.id
                parent_db_item = self.db[parent_item_id]
                children_list = parent_db_item['children'].split()
                parent_db_item['change'] = dict(method='removed', position=children_list.index(child_item.id), count=1, user=socket.gethostname())
                children_list.remove(child_item.id)
                parent_db_item['children'] = ' '.join(children_list)
                self.db[parent_item_id] = parent_db_item

    def move_vertical(self, indexes, up_or_down):
        # up_or_down is -1 for up and +1 for down
        item = self.getItem(indexes[0])
        parent_item_id = item.parentItem.id
        db_item = self.db[parent_item_id]
        children_list = db_item['children'].split()
        old_position = children_list.index(item.id)
        if up_or_down == -1 and old_position == 0 or up_or_down == +1 and old_position + len(indexes) - 1 == len(children_list) - 1:  # don't move if already at top or bottom
            return
        self.layoutAboutToBeChanged.emit()
        if up_or_down == -1:  # if we want to move several items up, we can move the item-above below the selection instead
            swapped_item = children_list.pop(old_position - 1)
            swapped_item_new_position = old_position + len(indexes) - 1
        elif up_or_down == +1:
            swapped_item = children_list.pop(old_position + len(indexes))
            swapped_item_new_position = old_position
        children_list.insert(swapped_item_new_position, swapped_item)
        db_item['children'] = ' '.join(children_list)
        db_item['change'] = dict(method='moved_vertical', position=old_position, count=len(indexes), up_or_down=up_or_down, user=socket.gethostname())
        self.db[parent_item_id] = db_item

    def move_left(self, indexes):
        item = self.getItem(indexes[0])
        parent_parent_item = item.parentItem.parentItem
        if parent_parent_item is not None:  # stop moving left if parent is root_item
            self.remove_consecutive_rows_from_parent(indexes)

            # insert as a child of the parent's parent
            parent_parent_item_index = QModelIndex(self.id_index_dict[parent_parent_item.id])
            position = item.parentItem.child_number() + 1
            self.insertRows(position, parent_parent_item_index, indexes)

    def move_right(self, indexes):
        # insert as a child of the sibling above
        item = self.getItem(indexes[0])
        childNumber = item.child_number()
        if childNumber != 0:  # stop moving right if the moving item is the top item
            self.remove_consecutive_rows_from_parent(indexes)  # we have to restore the selection of the moved item, because removeRow() discards it

            sibling_index = self.index(childNumber - 1, 0, self.parent(indexes[0]))
            last_childnr_of_sibling = len(item.parentItem.childItems[childNumber - 1].childItems)
            self.insertRows(last_childnr_of_sibling, sibling_index, indexes)

    def remove_consecutive_rows_from_parent(self, indexes):  # just for moving
        child_item = self.getItem(indexes[0])
        parent_item_id = child_item.parentItem.id
        parent_db_item = self.db[parent_item_id]
        children_list = parent_db_item['children'].split()
        position = children_list.index(child_item.id)
        parent_db_item['change'] = dict(method='removed', position=position, count=len(indexes), user=socket.gethostname())
        children_list[position:position + len(indexes)] = []
        parent_db_item['children'] = ' '.join(children_list)
        self.db[parent_item_id] = parent_db_item


class FilterProxyModel(QSortFilterProxyModel):
    # many of the default implementations of functions in QSortFilterProxyModel are written so that they call the equivalent functions in the relevant source model.
    # This simple proxying mechanism may need to be overridden for source models with more complex behavior; for example, if the source model provides a custom hasChildren() implementation, you should also provide one in the proxy model.
    # The QSortFilterProxyModel acts as a wrapper for the original model. If you need to convert source QModelIndexes to sorted/filtered model indexes or vice versa, use mapToSource(), mapFromSource(), mapSelectionToSource(), and mapSelectionFromSource().
    def filterAcceptsRow(self, row, parent):
        index = self.sourceModel().index(row, 0, parent)
        if not index.isValid():
            return False

        if self.filter in index.data():
            return True

        for row in range(self.sourceModel().rowCount(index)):
            if self.filterAcceptsRow(row, index):
                return True;

        return False

    def map_indexes_to_source(self, indexes):
        indexes_source = []
        for index in indexes:
            indexes_source.append(self.mapToSource(index))
        return indexes_source

    def move_right(self, indexes):
        if len(indexes) > 0:
            self.sourceModel().move_right(self.map_indexes_to_source(indexes))

    def move_left(self, indexes):
        if len(indexes) > 0:
            self.sourceModel().move_left(self.map_indexes_to_source(indexes))

    def move_vertical(self, indexes, up_or_down):
        if len(indexes) > 0:
            self.sourceModel().move_vertical(self.map_indexes_to_source(indexes), up_or_down)

    def insertRow(self, position, parent):
        self.sourceModel().insertRows(position, self.mapToSource(parent))

    def removeRows(self, indexes):
        self.sourceModel().removeRows(self.map_indexes_to_source(indexes))
