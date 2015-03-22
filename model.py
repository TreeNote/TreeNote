from PyQt5.QtCore import QAbstractItemModel, QModelIndex, Qt, QThread, QObject, pyqtSignal
import couchdb
import time
import sys
import subprocess
import threading
import socket


def synchronized(lock_name):
    """
    Synchronization decorator
    When the user changes the TreeModel with the view, the called method (like move_left) reads some Tree_items.
    But meanwhile an incoming, foreign database change may have deleted an affected Tree_item.
    Therefore we use a lock variable, which is used by the TreeModel methods and by the Updater-Thread.
    """

    def decorator(method):
        def synced_method(self, *args, **kws):
            lock = getattr(self, lock_name)
            with lock:
                return method(self, *args, **kws)

        return synced_method

    return decorator


class Updater(QThread):
    """
    This Thread watches the db for own and foreign changes and updates the view.
    """

    def __init__(self, tree_model):
        super(QThread, self).__init__()
        self.tree_model = tree_model

    def run(self):  # this updates the view
        all_changes = self.tree_model.db.changes(descending=True)
        last_seq = all_changes['results'][0]['seq']
        changes_list = self.tree_model.db.changes(feed='continuous', heartbeat=sys.maxsize, include_docs=True, since=last_seq)  # no need for heartbeet, because the db is local
        for line in changes_list:
            if 'doc' in line and 'deleted' not in line:
                print(line)
                db_item = line['doc']
                item_id = db_item['_id']
                if item_id in self.tree_model.id_index_dict:  # update the view only if the item is already loaded
                    with self.tree_model.lock:
                        index = self.tree_model.id_index_dict[item_id]
                        item = self.tree_model.getItem(index)
                        change_dict = db_item['change']
                        my_edit = change_dict['user'] == socket.gethostname()
                        def updated():
                            item.text = db_item['text']
                            self.tree_model.seq = line['seq']
                            if my_edit:
                                self.tree_model.update_selection_signal.emit(index, index, self.tree_model.seq)

                        def added():
                            position = change_dict['position']
                            parentItem = self.tree_model.getItem(index)
                            id_list = change_dict['id_list']
                            self.tree_model.beginInsertRows(index, position, position + len(id_list) - 1)
                            parentItem.insert_children(position, len(id_list))
                            for i, added_item_id in enumerate(id_list):
                                parentItem.childItems[position + i].id = added_item_id
                                parentItem.childItems[position + i].text = self.tree_model.db[added_item_id]['text']
                            self.tree_model.endInsertRows()
                            if my_edit:
                                index_first_added = self.tree_model.index(position, 0, index)
                                index_last_added = self.tree_model.index(position + len(id_list) - 1, 0, index)
                                if change_dict['set_edit_focus']:
                                    self.tree_model.update_selection_and_edit_signal.emit(index_first_added)
                                else:
                                    self.tree_model.seq = line['seq']
                                    self.tree_model.update_selection_signal.emit(index_first_added, index_last_added, self.tree_model.seq)
                                    self.last_selected_index = index_first_added

                        def removed():
                            self.tree_model.seq = line['seq']
                            position = change_dict['position']
                            count = change_dict['count']
                            self.tree_model.beginRemoveRows(index, position, position + count - 1)
                            item.childItems[position:position + count] = []
                            self.tree_model.endRemoveRows()
                            if my_edit:
                                # select the item below
                                if position == len(item.childItems):  # there is no item below, so select the one above
                                    position -= 1
                                if len(item.childItems) > 0:  # everythin is ok
                                    index_next_child = self.tree_model.index(position, 0, index)
                                    self.tree_model.update_selection_signal.emit(index_next_child, index_next_child, self.tree_model.seq)
                                else:  # all childs deleted, select parent
                                    self.tree_model.update_selection_signal.emit(index, index, self.tree_model.seq)

                        def moved_vertical():
                            self.tree_model.seq = line['seq']
                            up_or_down = change_dict['up_or_down']
                            position = change_dict['position']
                            count = change_dict['count']
                            if up_or_down == -1:
                                # if we want to move several items up, we can move the item-above below the selection instead:
                                item.childItems.insert(position + count - 1, item.childItems.pop(position - 1))
                                self.tree_model.index(position + count - 1, 0, index)  # calling index() refreshes the self.tree_model.id_index_dict of that item
                            elif up_or_down == +1:
                                item.childItems.insert(position, item.childItems.pop(position + count))
                                self.tree_model.index(position, 0, index)  # calling index() refreshes the self.tree_model.id_index_dict of that item
                            for i in range(count):
                                index_moved_item = self.tree_model.index(position + up_or_down + i, 0, index)  # calling index() refreshes the self.tree_model.id_index_dict of that item
                                if i == 0:
                                    index_first_moved_item = index_moved_item
                            self.tree_model.layout_changed_signal.emit()
                            if my_edit:
                                self.tree_model.update_selection_signal.emit(index_first_moved_item, index_moved_item, self.tree_model.seq)

                        eval(change_dict['method'] + '()')


class Tree_item(object):
    """
    To understand Qt's way of building a TreeView, read:
    http://trevorius.com/scrapbook/uncategorized/pyqt-custom-abstractitemmodel/
    http://doc.qt.io/qt-5/qtwidgets-itemviews-editabletreemodel-example.html
    """

    def __init__(self, text, parent=None):
        self.parentItem = parent
        self.text = text
        self.childItems = None
        self.id = None

    def child_number(self):
        if self.parentItem is not None:
            return self.parentItem.childItems.index(self)
        return 0

    def insert_children(self, position, count):
        for row in range(count):
            item = Tree_item('', self)
            self.childItems.insert(position, item)

    def remove_children(self, position, count):
        for row in range(count):
            self.childItems.pop(position)


class TreeModel(QAbstractItemModel):
    """
    The methods of this model changes the database only. The view gets updated by the Updater-Thread.
    """
    update_selection_signal = pyqtSignal(QModelIndex, QModelIndex, int)
    update_selection_and_edit_signal = pyqtSignal(QModelIndex)
    layout_changed_signal = pyqtSignal()

    def __init__(self, parent=None):
        super(TreeModel, self).__init__(parent)

        self.lock = threading.RLock()

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

        get_create_db(db_name, server_url)
        local_server.replicate(db_name, server_url + db_name, continuous=True)
        local_server.replicate(server_url + db_name, db_name, continuous=True)

        self.rootItem = Tree_item('root item')
        self.rootItem.id = '0'
        self.id_index_dict['0'] = QModelIndex()

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

    @synchronized("lock")
    def index(self, row, column, parent=QModelIndex()):
        if parent.isValid() and parent.column() != 0:
            return QModelIndex()

        parentItem = self.getItem(parent)
        childItem = parentItem.childItems[row]

        if childItem:
            index = self.createIndex(row, column, childItem)
            self.id_index_dict[childItem.id] = index
            return index
        else:
            return QModelIndex()

    @synchronized("lock")
    def parent(self, index):
        if not index.isValid():
            return QModelIndex()

        childItem = self.getItem(index)
        parentItem = childItem.parentItem

        if parentItem == self.rootItem:
            return QModelIndex()

        return self.createIndex(parentItem.child_number(), 0, parentItem)

    @synchronized("lock")
    def rowCount(self, parent=QModelIndex()): # deserialises children from the db, too
        parentItem = self.getItem(parent)
        if parentItem.childItems is None:  # child_count get's called often. Improve performance by deserialising only once
            parentItem.childItems = []
            children_id_list = self.db[parentItem.id]['children'].split()
            parentItem.insert_children(0, len(children_id_list))
            for i in range(len(children_id_list)):
                parentItem.childItems[i].text = self.db[children_id_list[i]]['text']
                parentItem.childItems[i].id = children_id_list[i]
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

    @synchronized("lock")
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

    @synchronized("lock")
    def removeRows(self, indexes, delete=True, restore_selection=False):
        for index in reversed(indexes):
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
        return True

    @synchronized("lock")
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

    @synchronized("lock")
    def move_left(self, indexes):
        item = self.getItem(indexes[0])
        parent_parent_item = item.parentItem.parentItem
        if parent_parent_item is not None:  # stop moving left if parent is root_item
            self.remove_consecutive_rows_from_parent(indexes)

            # insert as a child of the parent's parent
            parent_parent_item_index = self.id_index_dict[parent_parent_item.id]
            position = item.parentItem.child_number() + 1
            self.insertRows(position, parent_parent_item_index, indexes)

    @synchronized("lock")
    def move_right(self, indexes):
        # insert as a child of the sibling above
        item = self.getItem(indexes[0])
        childNumber = item.child_number()
        if childNumber != 0:  # stop moving right if the moving item is the top item
            self.remove_consecutive_rows_from_parent(indexes)  # we have to restore the selection of the moved item, because removeRow() discards it

            sibling_index = self.index(childNumber - 1, 0, self.parent(indexes[0]))
            last_childnr_of_sibling = len(item.parentItem.childItems[childNumber - 1].childItems)
            self.insertRows(last_childnr_of_sibling, sibling_index, indexes)  # the solution 'delete and then insert the moving item' produces a flickering, so we insert first

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