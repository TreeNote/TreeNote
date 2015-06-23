#################################################################################
##  TreeNote
##  A collaboratively usable outliner for personal knowledge and task management.
##
##  Copyright (C) 2015 Jan Korte (jan.korte@uni-oldenburg.de)
##
##  This program is free software: you can redistribute it and/or modify
##  it under the terms of the GNU General Public License as published by
##  the Free Software Foundation, version 3 of the License.
#################################################################################

import sys
import socket
import re
from pprint import pprint

from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *


def QDateFromString(string):
    d = QDate.fromString(string, 'dd.MM.yy')
    d.setDate(2000 + d.year() % 100, d.month(), d.day())
    return d


class QUndoCommandStructure(QUndoCommand):
    # this class is just for making the initialization of QUndoCommand easier. Source: http://chimera.labs.oreilly.com/books/1230000000393/ch08.html#_solution_129
    _fields = []  # Class variable that specifies expected fields

    def __init__(self, *args):
        if len(args) != len(self._fields):
            raise TypeError('Expected {} arguments'.format(len(self._fields)))

        # Set the arguments
        for name, value in zip(self._fields, args):
            setattr(self, name, value)

        super(QUndoCommandStructure, self).__init__(QApplication.translate('command', self.title))


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
                # pprint(line)
                db_item = line['doc']
                if 'change' in db_item:
                    self.model.db_change_signal.emit(db_item, self.model)


class Tree_item(object):
    """
    This item holds all id, parent, childs, text, estimate and date attributes. Other attributes like color are in the db only.
    Attributes saved here are accessed faster than through the db.

    To understand Qt's way of building a TreeView, read:
    http://trevorius.com/scrapbook/uncategorized/pyqt-custom-abstractitemmodel/
    http://doc.qt.io/qt-5/qtwidgets-itemviews-editabletreemodel-example.html
    """

    def __init__(self, text, model, parent=None, id=None):
        self.model = model
        self.parentItem = parent
        self.id = id
        self.childItems = None

    def child_number(self):
        if self.parentItem is not None:
            return self.parentItem.childItems.index(self)
        return 0

    def init_childs(self, parent_index):
        if self.childItems is None:  # deserialise children from the db
            self.childItems = []
            children_id_list = self.children.split()
            for position in range(len(children_id_list)):
                id = children_id_list[position]
                self.add_child(position, id, parent_index)

    def add_child(self, position, id, parent_index):
        item = Tree_item('', self.model, self, id)
        db_item = self.model.db[id]
        # Tree_item has the same attributes like a DB_ITEM except 'children'
        # it's saved here, because access to here ist faster than to the db
        for key in TREE_ITEM_ATTRIBUTES_LIST:
            item.__setattr__(key, db_item[key])
        self.childItems.insert(position, item)

        new_index = self.model.index(position, 0, parent_index)
        self.model.id_index_dict[id] = QPersistentModelIndex(new_index)
        self.model.pointer_set.add(new_index.internalId())

    def update_attributes(self, db_item):
        for key in TREE_ITEM_ATTRIBUTES_LIST:
            self.__setattr__(key, db_item[key])


class TreeModel(QAbstractItemModel):
    """
    The methods of this model changes the database only. The view gets updated by the Updater-Thread.
    """
    db_change_signal = pyqtSignal(dict, QAbstractItemModel)

    def __init__(self, db, header_list=None, parent=None):
        super(TreeModel, self).__init__(parent)
        self.db = db
        self.undoStack = QUndoStack(self)

        # If a database change is arriving, we just have the id. To get the corresponding Tree_item, we store it's QModelIndex in this dict:
        self.id_index_dict = dict()  # New indexes are created by TreeModel.index(). That function stores the index in this dict. This dict may grow huge during runtime.
        self.pointer_set = set()

        # delete items with deleted flag permanently
        map = "function(doc) { \
                    if (doc." + DELETED + " != '') \
                        emit(doc, null); \
                }"
        res = self.db.query(map)
        for row in res:
            self.db.delete(self.db[row.id])

        self.rootItem = Tree_item('root item', self)
        self.rootItem.header_list = header_list
        self.rootItem.id = ROOT_ID
        self.rootItem.children = db[ROOT_ID]['children']
        self.rootItem.type = NOTE
        index = QModelIndex()
        self.id_index_dict[ROOT_ID] = index
        self.pointer_set.add(QModelIndex().internalId())

        self.updater = Updater(self)
        self.updater.start()

    def headerData(self, column, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.rootItem.header_list[column]

        return None

    def columnCount(self, parent=None):
        return 3

    def flags(self, index):
        if not index.isValid():
            return 0

        return Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def get_db_item(self, index):
        item = self.getItem(index)
        return self.db[item.id]

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
        if row >= len(parentItem.childItems):  # bugfix
            return QModelIndex()

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

        if role == Qt.SizeHintRole:
            return QSize(-1, 21)  # row height

        if role != Qt.DisplayRole and role != Qt.EditRole:
            return None

        item = self.getItem(index)
        if index.column() == 0:
            return item.text
        elif index.column() == 1:
            return item.date
        else:  # index.column() == 2:
            return item.estimate

    # directly used by bookmark dialog, because it has no index of the new created item
    def set_data_with_id(self, value, item_id, column, field='text'):
        class SetDataCommand(QUndoCommandStructure):
            _fields = ['model', 'item_id', 'value', 'column', 'field']
            title = 'Edit row'

            def set_data(self, value):
                db_item = self.model.db[self.item_id]
                if self.column == 0:  # used for setting color etc, too
                    self.old_value = db_item[self.field]
                    db_item[self.field] = value
                elif self.column == 1:
                    self.old_value = db_item['date']
                    if type(value) == QDate and value == QDate.currentDate():  # user has not selected a date other than 'today'
                        value = EMPTY_DATE
                    value = value.toString('dd.MM.yy') if type(value) == QDate else value
                    if value == EMPTY_DATE:  # user pressed del
                        value = ''
                    db_item['date'] = value
                elif self.column == 2:
                    self.old_value = db_item['estimate']
                    db_item['estimate'] = value
                db_item['change'] = dict(method='updated', user=socket.gethostname())
                self.model.db[self.item_id] = db_item

            def redo(self):
                self.set_data(self.value)

            def undo(self):
                self.set_data(self.old_value)

        self.undoStack.push(SetDataCommand(self, item_id, value, column, field))
        return True

    def set_data(self, value, index, field='text'):
        item_id = self.getItem(index).id
        column = index.column()
        return self.set_data_with_id(value, item_id, column, field)

    # used for moving and inserting new rows. When inserting new rows, 'id_list' and 'indexes' are not used.
    def insert_remove_rows(self, position=None, parent_item_id=None, id_list=None, indexes=None):

        # Delete design decision: We could delete items permanently. But if then the user renames, deletes and then undoes both actions, the undo of 'delete' would create an item with a new id. Therefore rename won't work.
        # So we just set a delete marker. On startup, all items with a delete marker are removed permanently.
        class InsertRemoveRowCommand(QUndoCommandStructure):
            _fields = ['model', 'position', 'parent_item_id', 'id_list', 'set_edit_focus', 'delete_child_from_parent_id_list']
            title = 'Add or remove row'

            # set delete = false for redoing (re-adding) if it was deleted
            def set_deleted_marker(self, string, child_item_id):
                child_db_item = self.model.db[child_item_id]
                child_db_item[DELETED] = string
                child_db_item['change'] = dict(method=DELETED, user=socket.gethostname())
                self.model.db[child_db_item.id] = child_db_item

                # set deleted marker for children
                def delete_childs(db_item):
                    children_list = db_item['children'].split()
                    for ch_item_id in children_list:
                        delete_childs(self.model.db[ch_item_id])
                        ch_db_item = self.model.db.get(ch_item_id)
                        if ch_db_item is not None:
                            ch_db_item[DELETED] = string
                            ch_db_item['change'] = dict(method=DELETED, user=socket.gethostname())
                            self.model.db[ch_db_item.id] = ch_db_item

                delete_childs(child_db_item)

            @staticmethod  # static because it is called from the outside for moving
            def add_rows(model, position, parent_item_id, id_list, set_edit_focus):
                db_item = model.db[parent_item_id]
                children_list = db_item['children'].split()
                children_list_new = children_list[:position] + id_list + children_list[position:]
                db_item['children'] = ' '.join(children_list_new)
                db_item['change'] = dict(method='added', id_list=id_list, position=position, set_edit_focus=set_edit_focus, user=socket.gethostname())
                model.db[parent_item_id] = db_item

            # uses delete markers, because without them undoing would be more difficult
            def remove_rows(self):
                for child_item_id, parent_item_id, _ in self.delete_child_from_parent_id_list:
                    self.set_deleted_marker('True', child_item_id)
                    # remove from parent and inform the updater thread
                    parent_db_item = self.model.db[parent_item_id]
                    children_list = parent_db_item['children'].split()
                    parent_db_item['change'] = dict(method='removed', position=children_list.index(child_item_id), count=1, user=socket.gethostname())
                    children_list.remove(child_item_id)
                    parent_db_item['children'] = ' '.join(children_list)
                    self.model.db[parent_item_id] = parent_db_item

            def redo(self):  # is called when pushed to the stack
                if position is not None:  # insert command
                    if self.id_list is None:  # for newly created items. else: add existing item (for move)
                        child_id, _ = self.model.db.save(NEW_DB_ITEM.copy())
                        self.id_list = [child_id]

                        # type of new items depends on their parent: note -> note, projekt -> task
                        parent_type = self.model.db[parent_item_id]['type']
                        child_type = NOTE if parent_type == NOTE else TASK
                        self.model.set_db_item_field(child_id, 'type', child_type)

                    self.set_deleted_marker('', self.id_list[0])  # remove delete marker. just one item is inserted / re-inserted
                    self.add_rows(self.model, self.position, self.parent_item_id, self.id_list, self.set_edit_focus)
                    self.set_edit_focus = False  # when redo is called the second time (when the user is redoing), he doesn't want edit focus
                    self.delete_child_from_parent_id_list = [(self.id_list[0], parent_item_id, None)]  # info for undoing
                else:
                    self.remove_rows()

            def undo(self):
                if self.position is not None:  # undo insert command
                    self.remove_rows()
                else:  # undo remove command
                    for child_item_id, parent_item_id, position in self.delete_child_from_parent_id_list:
                        self.set_deleted_marker('', child_item_id)
                        self.add_rows(self.model, position, parent_item_id, [child_item_id], False)

        if position is not None:  # insert command
            if id_list is None:
                # used from view, create a single new row / self.db item
                set_edit_focus = True
                self.undoStack.push(InsertRemoveRowCommand(self, position, parent_item_id, None, set_edit_focus, None))
            else:  # used from move methods, add existing db items to the parent. Don't add to stack, because already part of an UndoCommand
                set_edit_focus = False
                InsertRemoveRowCommand.add_rows(self, position, parent_item_id, id_list, set_edit_focus)
        else:  # remove command
            delete_child_from_parent_id_list = list()
            for index in indexes:
                child_item = self.getItem(index)
                delete_child_from_parent_id_list.append((child_item.id, child_item.parentItem.id, child_item.child_number()))  # save the position information for adding (undo)
            self.undoStack.push(InsertRemoveRowCommand(self, position, parent_item_id, id_list, False, delete_child_from_parent_id_list))

    def move_vertical(self, indexes, up_or_down):
        # up_or_down is -1 for up and +1 for down

        class MoveVerticalCommand(QUndoCommandStructure):
            _fields = ['model', 'item_id', 'parent_item_id', 'count', 'up_or_down']
            title = 'Move vertically'

            def move(self, up_or_down):
                db_item = self.model.db[self.parent_item_id]
                children_list = db_item['children'].split()
                old_position = children_list.index(self.item_id)
                if up_or_down == -1 and old_position == 0 or up_or_down == +1 and old_position + self.count - 1 == len(children_list) - 1:  # don't move if already at top or bottom
                    return
                self.model.layoutAboutToBeChanged.emit()
                if up_or_down == -1:  # if we want to move several items up, we can move the item-above below the selection instead
                    swapped_item = children_list.pop(old_position - 1)
                    swapped_item_new_position = old_position + self.count - 1
                elif up_or_down == +1:
                    swapped_item = children_list.pop(old_position + self.count)
                    swapped_item_new_position = old_position
                children_list.insert(swapped_item_new_position, swapped_item)
                db_item['children'] = ' '.join(children_list)
                db_item['change'] = dict(method='moved_vertical', position=old_position, count=self.count, up_or_down=up_or_down, user=socket.gethostname())
                self.model.db[self.parent_item_id] = db_item

            def redo(self):
                self.move(self.up_or_down)

            def undo(self):
                self.move(self.up_or_down * -1)

        item = self.getItem(indexes[0])
        self.undoStack.push(MoveVerticalCommand(self, item.id, item.parentItem.id, len(indexes), up_or_down))

    def move_horizontal(self, indexes, direction):
        item = self.getItem(indexes[0])
        id_list = list()
        for index in indexes:
            id_list.append(self.getItem(index).id)

        parent_parent_item = item.parentItem.parentItem
        if parent_parent_item is None and direction == -1:  # stop moving left if parent is root_item
            return
        elif parent_parent_item is not None:  # just for moving left
            parent_parent_item_id = parent_parent_item.id
        else:  # for moving right we don't need 'parent_parent_item_id'
            parent_parent_item_id = None

        original_position = item.child_number()
        if original_position == 0 and direction == 1:  # stop moving right if the moving item is the top item
            return
        sibling_index = self.index(original_position - 1, 0, self.parent(indexes[0]))
        sibling_id = self.getItem(sibling_index).id
        last_childnr_of_sibling = len(item.parentItem.childItems[original_position - 1].childItems)

        class MoveHorizontalCommand(QUndoCommandStructure):
            _fields = ['model', 'direction', 'parent_parent_item_id', 'parent_item_id',
                       'child_item_id', 'id_list', 'position', 'original_position', 'sibling_id', 'last_childnr_of_sibling']
            title = 'move horizontal'

            def move(self, from_parent, insert_in, position):
                self.model.remove_consecutive_rows_from_parent(from_parent, self.child_item_id, len(self.id_list))
                self.model.insert_remove_rows(position, insert_in, self.id_list)

            def redo(self):
                if self.direction == -1:  # left
                    self.move(self.parent_item_id, self.parent_parent_item_id, self.position)  # insert as a child of the parent's parent
                else:  # right
                    self.move(self.parent_item_id, self.sibling_id, self.last_childnr_of_sibling)  # insert as a child of the sibling above

            def undo(self):
                if self.direction == 1:  # undo moving right
                    self.move(self.sibling_id, self.parent_item_id, self.original_position)
                else:  # undo moving left
                    self.move(self.parent_parent_item_id, self.parent_item_id, self.original_position)

        position = item.parentItem.child_number() + 1
        self.undoStack.push(MoveHorizontalCommand(self, direction, parent_parent_item_id, item.parentItem.id,
                                                  item.id, id_list, position, original_position, sibling_id, last_childnr_of_sibling))

    def remove_consecutive_rows_from_parent(self, parent_item_id, child_item_id, count):  # just for moving
        parent_db_item = self.db[parent_item_id]
        children_list = parent_db_item['children'].split()
        position = children_list.index(child_item_id)
        parent_db_item['change'] = dict(method='removed', position=position, count=count, user=socket.gethostname())
        children_list[position:position + count] = []
        parent_db_item['children'] = ' '.join(children_list)
        self.db[parent_item_id] = parent_db_item

    def get_tags_set(self, cut_delimiter=True):
        tags_set = set()
        map = "function(doc) { \
                    if (doc.text && doc.text.indexOf('" + DELIMITER + "') != -1 && doc." + DELETED + " == '') \
                        emit(doc, null); \
                }"
        res = self.db.query(map)
        for row in res:
            word_list = row.key['text'].split()
            for word in word_list:
                if word[0] == DELIMITER:
                    delimiter = '' if cut_delimiter else DELIMITER
                    tags_set.add(delimiter + word.strip(DELIMITER))
        return tags_set

    def is_task_available(self, index):
        """
        return True if the parent is no sequential project
        returns True if it is the next available task from the parent sequential project
        """
        item = self.getItem(index)

        if item.type == NOTE:
            return True

        project_item = item.parentItem
        if project_item.type == PAUSED:
            return False
        if project_item.type != SEQ:
            return True

        project_index = self.parent(index)
        project_parent_index = self.parent(project_index)
        available_index = self.get_next_available_task(project_index.row(), project_parent_index)
        if available_index == index:
            return True

        return False

    def get_next_available_task(self, row, parent):
        index = self.index(row, 0, parent)
        item = self.getItem(index)
        if item.type == TASK:
            return True
        for row in range(self.rowCount(index)):
            if self.get_next_available_task(row, index):
                return self.index(row, 0, index)
        return False

    def toggle_task(self, index):
        db_item = self.get_db_item(index)
        type = db_item['type']
        if type != TASK and type != DONE_TASK:  # type is NOTE or a project
            self.set_data(TASK, index=index, field='type')
        elif type == TASK:
            repeat_in_list = re.findall(r'repeat=((?:\w|\d)*)(?:$| )', db_item['text'])  # get what is behin the equal sign
            if len(repeat_in_list) == 1:
                repeat_in = repeat_in_list[0]
                old_qdate = QDateFromString(db_item['date'])
                if repeat_in[1] == 'd':
                    new_qdate = old_qdate.addDays(int(repeat_in[0]))
                elif repeat_in[1] == 'w':
                    new_qdate = old_qdate.addDays(7 * int(repeat_in[0]))
                elif repeat_in[1] == 'm':
                    new_qdate = old_qdate.addMonths(int(repeat_in[0]))
                elif repeat_in[1] == 'y':
                    new_qdate = old_qdate.addYears(int(repeat_in[0]))
                self.set_data(new_qdate.toString('dd.MM.yy'), index=index, field='date')
            else:
                self.set_data(DONE_TASK, index=index, field='type')
        elif type == DONE_TASK:
            self.set_data(NOTE, index=index, field='type')

    def toggle_project(self, index):
        db_item = self.get_db_item(index)
        type = db_item['type']
        if type == NOTE or type == DONE_TASK or type == TASK:  # type is Note or Task
            self.set_data(SEQ, index=index, field='type')
        elif type == SEQ:
            self.set_data(PAR, index=index, field='type')
        elif type == PAR:
            self.set_data(PAUSED, index=index, field='type')
        elif type == PAUSED:
            self.set_data(NOTE, index=index, field='type')

    def set_db_item_field(self, item_id, field, value):
        db_item = self.db[item_id]
        db_item[field] = value
        self.db[item_id] = db_item

    def setData(self, index, value, role=None):
        return self.set_data(value, index=index, field='text')

    def remove_rows(self, indexes):
        self.insert_remove_rows(indexes=indexes)


class ProxyTools():
    # when the editor commits it's data, it calls this method
    # it is overwritten from QAbstractProxyModel
    def setData(self, index, value, role=None):
        return self.sourceModel().setData(self.mapToSource(index), value, role=role)

    def set_data(self, value, index=None, field='text'):
        return self.sourceModel().set_data(value, index=self.mapToSource(index), field=field)

    def remove_rows(self, indexes):
        self.sourceModel().remove_rows([self.mapToSource(index) for index in indexes])

    def toggle_task(self, index):
        self.sourceModel().toggle_task(self.mapToSource(index))

    def toggle_project(self, index):
        self.sourceModel().toggle_project(self.mapToSource(index))

    def get_db_item_id(self, index):
        return self.sourceModel().get_db_item(self.mapToSource(index))['_id']

    def get_db_item(self, index):
        return self.sourceModel().get_db_item(self.mapToSource(index))

    def is_task_available(self, index):
        return self.sourceModel().is_task_available(self.mapToSource(index))

    def insert_row(self, position, parent):
        self.sourceModel().insert_remove_rows(position, self.getItem(parent).id)

    def move_horizontal(self, indexes, direction):
        if len(indexes) > 0:
            self.sourceModel().move_horizontal([self.mapToSource(index) for index in indexes], direction)

    def move_vertical(self, indexes, up_or_down):
        if len(indexes) > 0:
            self.sourceModel().move_vertical([self.mapToSource(index) for index in indexes], up_or_down)

    def getItem(self, index):
        return self.sourceModel().getItem(self.mapToSource(index))


class FilterProxyModel(QSortFilterProxyModel, ProxyTools):
    # many of the default implementations of functions in QSortFilterProxyModel are written so that they call the equivalent functions in the relevant source model.
    # This simple proxying mechanism may need to be overridden for source models with more complex behavior; for example, if the source model provides a custom hasChildren() implementation, you should also provide one in the proxy model.
    # The QSortFilterProxyModel acts as a wrapper for the original model. If you need to convert source QModelIndexes to sorted/filtered model indexes or vice versa, use mapToSource(), mapFromSource(), mapSelectionToSource(), and mapSelectionFromSource().

    def filterAcceptsRow(self, row, parent):
        index = self.sourceModel().index(row, 0, parent)
        if not index.isValid():
            return False

        item = self.sourceModel().getItem(index)

        # return True if this row's data is accepted
        tokens = self.filter.split()  # all tokens must be in the row's data
        for token in tokens:
            if token.startswith((FLATTEN, SORT)):  # ignore these
                continue
            elif token.startswith('c='):
                color_character = token[2:3]
                if item.color == CHAR_QCOLOR_DICT.get(color_character):
                    continue
            elif token.startswith('t='):
                task_character = token[2:3]
                type = CHAR_TYPE_DICT.get(task_character)
                if item.type == type:
                    # just available tasks
                    if type == TASK and not self.sourceModel().is_task_available(index):
                        break
                    continue
            elif re.match(r'e(<|>|=)', token):
                if item.estimate == '':
                    break
                less_greater_equal_sign = token[1]
                if less_greater_equal_sign == '=':
                    less_greater_equal_sign = '=='
                estimate_search = token[2:]
                if eval(item.estimate + less_greater_equal_sign + estimate_search):
                    continue
            elif token.startswith(ONLY_START_DATE):
                if item.date != '':
                    continue
            elif token.startswith(HIDE_TAGS):
                # accept (continue) when row has no tag
                if not re.search(' ' + DELIMITER, index.data()):
                    continue
            elif token.startswith(HIDE_FUTURE_START_DATE):
                # accept (continue) when no date or date is not in future
                if item.date == '' or QDateFromString(item.date) <= QDate.currentDate():
                    continue
            elif token.startswith(FOCUS + '='):
                if FLATTEN not in self.filter:  # ignore
                    continue
                else:
                    # focus + flatten: show just childs of flatten
                    # return if somehow_child_id is a child or grandchild etc of parent_id
                    def is_somehow_child_of_flatten_id(somehow_child_id, parent_id):
                        if somehow_child_id in self.sourceModel().sourceModel().db[parent_id]['children']:
                            return True
                        parameter_children_list = self.sourceModel().sourceModel().db[parent_id]['children'].split()
                        for child_id in parameter_children_list:
                            if is_somehow_child_of_flatten_id(somehow_child_id, child_id):
                                return True
                        return False

                    flatten_id = token[len(FOCUS + '='):]
                    if is_somehow_child_of_flatten_id(item.id, flatten_id):
                        continue
            elif token.startswith(SORT + '='):  # ignore
                continue
            elif token in index.data():
                continue
            break  # user type stuff that's not found
        else:  # just executed when not breaked
            return True  # all tokens are in the row

        # return True if a child row is accepted
        for row in range(self.sourceModel().rowCount(index)):
            if self.filterAcceptsRow(row, index):
                return True

        return False

    def lessThan(self, left_index, right_index):
        column = left_index.column()
        left_data = left_index.data()
        right_data = right_index.data()
        if column == 0:
            return True
        elif column == 1:
            new_left_data = QDateFromString(left_data)
            new_right_data = QDateFromString(right_data)
        elif column == 2:
            new_left_data = int(left_data) if left_data != '' else 0
            new_right_data = int(right_data) if right_data != '' else 0
        return new_left_data > new_right_data


class FlatProxyModel(QAbstractProxyModel, ProxyTools):
    def __init__(self, parent=None):
        super(FlatProxyModel, self).__init__(parent)

    @pyqtSlot(QModelIndex, QModelIndex)
    def sourceDataChanged(self, topLeft, bottomRight):
        self.dataChanged.emit(self.mapFromSource(topLeft), self.mapFromSource(bottomRight))

    @pyqtSlot(QModelIndex, int, int)
    def sourceRowsInserted(self, parent, start, end):
        self.beginResetModel()
        self.buildMap(self.sourceModel())
        self.endResetModel()
        # the buildMap() method is cpu hungry (really? maybe the usage of the mapping is as hungry)
        # but in the below solution, child rows get moved when insetering, too
        # self.columns_list[0].insert(start, self.sourceModel().index(start, 0, parent))
        # self.columns_list[1].insert(start, self.sourceModel().index(start, 1, parent))
        # self.columns_list[2].insert(start, self.sourceModel().index(start, 2, parent))

    # source: http://stackoverflow.com/questions/21564976/how-to-create-a-proxy-model-that-would-flatten-nodes-of-a-qabstractitemmodel-int
    # but we have more than one column and therefore need to build a matrix instead of a list
    # and we need to listen to changes of the source model and edit our matrixes accordingly
    def buildMap(self, model, parent=QModelIndex(), row=0):
        if row == 0:
            # self.m_rowMap = {}  # use: row, column = m_rowMap[index]
            # self.m_indexMap = {}  # use: index = m_indexMap[row, col]
            self.columns_list = [[], [], []]
        rows = model.rowCount(parent)
        for r in range(rows):
            index_0 = model.index(r, 0, parent)
            self.columns_list[0].append(index_0)
            self.columns_list[1].append(model.index(r, 1, parent))
            self.columns_list[2].append(model.index(r, 2, parent))
            # self.m_rowMap[index_0] = row, 0
            # self.m_rowMap[index_1] = row, 1
            # self.m_rowMap[index_2] = row, 2
            # self.m_indexMap[row, 0] = index_0
            # self.m_indexMap[row, 1] = index_1
            # self.m_indexMap[row, 2] = index_2
            row = row + 1
            if model.hasChildren(index_0):
                # add rows of children
                row = self.buildMap(model, index_0, row)
        return row

    def setSourceModel(self, model):
        QAbstractProxyModel.setSourceModel(self, model)
        self.buildMap(model)
        model.dataChanged.connect(self.sourceDataChanged)
        model.rowsInserted.connect(self.sourceRowsInserted)
        model.rowsRemoved.connect(self.sourceRowsInserted)

    def mapFromSource(self, index):
        column = index.column()
        if index not in self.columns_list[column]: return QModelIndex()
        row = self.columns_list[column].index(index)
        return self.createIndex(row, column)

    def mapToSource(self, index):
        column = index.column()
        row = index.row()
        if not index.isValid() or row == -1 or row >= len(self.columns_list[column]): return QModelIndex()
        return self.columns_list[column][row]

    def columnCount(self, parent):
        return QAbstractProxyModel.sourceModel(self).columnCount(self.mapToSource(parent))

    def rowCount(self, parent):
        return len(self.columns_list[0]) if not parent.isValid() else 0

    def index(self, row, column, parent):
        if parent.isValid(): return QModelIndex()
        return self.createIndex(row, column)

    def parent(self, index):
        return QModelIndex()


class Delegate(QStyledItemDelegate):
    def __init__(self, parent, model):
        super(Delegate, self).__init__(parent)
        self.model = model
        self.main_window = parent

    def paint(self, painter, option, index):
        item = self.model.getItem(index)

        word_list = index.data().split()
        for idx, word in enumerate(word_list):
            if word[0] == DELIMITER:
                word_list[idx] = "<font color={}>{}</font>".format(TAG_COLOR.name(), word)
            elif len(re.findall(r'repeat=\d(d|w|m|y)($| )', word)) > 0:
                word_list[idx] = "<font color={}>{}</font>".format(REPEAT_COLOR.name(), word)
        document = QTextDocument()
        html = ' '.join(word_list)
        is_not_available = item.type == TASK and not self.model.is_task_available(index)
        if item.type == DONE_TASK or is_not_available:  # not available tasks in a sequential project are grey
            html = "<font color={}>{}</font>".format(QColor(Qt.darkGray).name(), html)
        if option.state & QStyle.State_Selected:
            color = self.main_window.palette().highlight().color()
        elif option.features == QStyleOptionViewItem.Alternate:
            color = QApplication.palette().alternateBase()
        else:
            color = QApplication.palette().base()
        text_color = QApplication.palette().text().color().name() if item.color == NO_COLOR else QColor(item.color).name()
        html = "<font color={}>{}</font>".format(text_color, html)
        document.setHtml(html)
        painter.save()
        painter.fillRect(option.rect, color)
        gap_for_checkbox = 17
        painter.translate(option.rect.x() + gap_for_checkbox - 2, option.rect.y() - 3)  # -3: put the text in the middle of the line
        document.drawContents(painter)
        painter.restore()

        if item.type != NOTE and index.column() == 0:  # set icon of task or project
            painter.save()
            iconsize = option.decorationSize
            type = NOT_AVAILABLE_TASK if is_not_available else item.type
            icon = QImage(':/' + type)
            painter.drawImage(option.rect.x(), option.rect.y() + 3, icon.scaledToHeight(iconsize.height()))
            painter.restore()

    def createEditor(self, parent, option, index):
        if index.column() == 0:
            suggestions_model = self.main_window.item_model.get_tags_set(cut_delimiter=False)
            edit = AutoCompleteEdit(parent, list(suggestions_model))
            edit.setStyleSheet('QLineEdit {padding-left: 16px;}')
            return edit
        if index.column() == 1:
            date_edit = OpenPopupDateEdit(parent, self)
            date = QDate.currentDate() if index.data() == '' else QDateFromString(index.data())
            date_edit.setDate(date)
            date_edit.setCalendarPopup(True)
            date_edit.setCalendarWidget(EscCalendarWidget(parent))
            date_edit.setStyleSheet('QDateEdit {padding-left: 14px;}')
            return date_edit
        else:  # index.column() == 2:
            line_edit = QLineEdit(parent)
            line_edit.setValidator(QIntValidator(0, 999, self))
            line_edit.setStyleSheet('QLineEdit {padding-left: 16px;}')
            return line_edit

    def setEditorData(self, editor, index):
        QStyledItemDelegate.setEditorData(self, editor, index)

    def setModelData(self, editor, model, index):
        QStyledItemDelegate.setModelData(self, editor, model, index)

    def eventFilter(self, editor, event):
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            current_index = self.main_window.current_index()
            self.closeEditor.emit(editor, QAbstractItemDelegate.NoHint)
            self.main_window.set_selection(current_index,current_index)
            return False
        return QStyledItemDelegate.eventFilter(self, editor, event);


class BookmarkDelegate(QStyledItemDelegate):
    def __init__(self, parent, model):
        super(BookmarkDelegate, self).__init__(parent)
        self.model = model
        self.main_window = parent

    def paint(self, painter, option, index):
        item = self.model.getItem(index)
        db_item = self.model.db[item.id]
        document = QTextDocument()
        shortcut = db_item[SHORTCUT]
        if shortcut.startswith('Ctrl+'):
            shortcut = shortcut.replace('Ctrl+', '')
        if shortcut != '':
            shortcut += ' '
        document.setPlainText(shortcut + db_item[TEXT])
        if option.state & QStyle.State_Selected:
            color = self.main_window.palette().highlight().color()
        else:
            color = QApplication.palette().base()
        painter.save()
        painter.fillRect(option.rect, color)
        painter.translate(option.rect.x() - 2, option.rect.y() - 3)  # -3: put the text in the middle of the line
        document.drawContents(painter)
        painter.restore()


class EscCalendarWidget(QCalendarWidget):
    def __init__(self, parent):
        super(EscCalendarWidget, self).__init__(parent)
        if sys.platform != "darwin": # sadly, capture of the tab key is different on Windows and Mac. so we need it here for windows and at OpenPopupDateEdit for Mac
            self.installEventFilter(self)
            self.sent = False

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            open_popup_date_edit = self.parent().parent()
            open_popup_date_edit.delegate.closeEditor.emit(open_popup_date_edit, QAbstractItemDelegate.NoHint)
            current_index = open_popup_date_edit.delegate.main_window.current_index()
            open_popup_date_edit.delegate.main_window.set_selection(current_index,current_index)

    def eventFilter(self, obj, event):
        open_popup_date_edit = self.parent().parent()
        if event.type() == QEvent.ShortcutOverride and event.key() == Qt.Key_Tab:
            if not self.sent: # annoying bug that this event get's sent two times. so filter one event out.
                open_popup_date_edit.delegate.main_window.edit_row_without_check()
                self.sent = True
        if event.type() == QEvent.ShortcutOverride and event.key() == Qt.Key_Delete:
            open_popup_date_edit.setSpecialValueText(' ')
            open_popup_date_edit.setDate(QDateFromString(EMPTY_DATE))  # workaround to set empty date
            open_popup_date_edit.commit()
        return False  # don't stop the event being handled further


class OpenPopupDateEdit(QDateEdit):
    def __init__(self, parent, delegate):
        super(OpenPopupDateEdit, self).__init__(parent)
        self.delegate = delegate
        if sys.platform == "darwin":
            self.installEventFilter(self)

    def focusInEvent(self, event):  # open popup on focus. source: http://forum.qt.io/topic/26821/solved-activating-calender-popup-on-focus-in-event
        self.calendarWidget().activated.connect(self.commit)  # commit edit as soon as the user goes back from the calendar popup to the dateEdit
        opt = QStyleOptionSpinBox()
        self.initStyleOption(opt)
        rect = self.style().subControlRect(QStyle.CC_SpinBox, opt, QStyle.SC_SpinBoxDown)
        e = QMouseEvent(QEvent.MouseButtonPress, rect.center(), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        QApplication.sendEvent(self, e)

    def commit(self):
        self.delegate.commitData.emit(self)
        self.delegate.closeEditor.emit(self, QAbstractItemDelegate.NoHint)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.ShortcutOverride and event.key() == Qt.Key_Tab:
            self.delegate.main_window.edit_row()
        if event.type() == QEvent.ShortcutOverride and event.key() == Qt.Key_Delete:
            self.setSpecialValueText(' ')
            self.setDate(QDateFromString(EMPTY_DATE))  # workaround to set empty date
            self.commit()
        return False  # don't stop the event being handled further


class AutoCompleteEdit(QLineEdit):  # source: http://blog.elentok.com/2011/08/autocomplete-textbox-for-multiple.html
    def __init__(self, parent, model, separator=' '):
        super(AutoCompleteEdit, self).__init__(parent)
        self._separator = separator
        self._completer = QCompleter(model)
        self._completer.setFilterMode(Qt.MatchContains)
        self._completer.setWidget(self)
        self._completer.activated[str].connect(self._insertCompletion)
        self._keysToIgnore = [Qt.Key_Enter,
                              Qt.Key_Return,
                              Qt.Key_Escape,
                              Qt.Key_Tab]

    def _insertCompletion(self, completion):
        """
        This is the event handler for the QCompleter.activated(QString) signal,
        it is called when the user selects an item in the completer popup.
        """
        old_text_minus_new_word = self.text()[:-len(self._completer.completionPrefix())]
        self.setText(old_text_minus_new_word + completion + ' ')

    def textUnderCursor(self):
        text = self.text()
        textUnderCursor = ''
        i = self.cursorPosition() - 1
        while i >= 0 and text[i] != self._separator:
            textUnderCursor = text[i] + textUnderCursor
            i -= 1
        return textUnderCursor

    def keyPressEvent(self, event):
        if self._completer.popup().isVisible():
            if event.key() in self._keysToIgnore:
                event.ignore()
                return
        super(AutoCompleteEdit, self).keyPressEvent(event)
        completionPrefix = self.textUnderCursor()
        if len(completionPrefix) == 0:
            self._completer.popup().hide()
            return
        if completionPrefix[0] == DELIMITER:
            if completionPrefix != self._completer.completionPrefix():
                self._updateCompleterPopupItems(completionPrefix)
            if len(event.text()) > 0 and len(completionPrefix) > 0:
                self._completer.complete()

    def _updateCompleterPopupItems(self, completionPrefix):
        """
        Filters the completer's popup items to only show items
        with the given prefix.
        """
        self._completer.setCompletionPrefix(completionPrefix)
        self._completer.popup().setCurrentIndex(
            self._completer.completionModel().index(0, 0))


ONLY_START_DATE = 'only_date'
HIDE_FUTURE_START_DATE = 'hide_future_date'
HIDE_TAGS = 'has_tag'
FLATTEN = 'flatten'
SORT = 'sort'
ESTIMATE = 'estimate'
STARTDATE = 'startdate'
ASC = '_ascending'
DESC = '_descending'
ROOT_ID = '0'
TEXT_GRAY = QColor(188, 195, 208)
SELECTION_GRAY = QColor('#555B6E')
BACKGROUND_GRAY = QColor(57, 57, 57)  # darker
ALTERNATE_BACKGROUND_GRAY = QColor(59, 59, 59) # slightly brighter
FOREGROUND_GRAY = QColor(78, 80, 82)  # brighter
HIGHLIGHT_ORANGE = QColor(195, 144, 72)
TAG_COLOR = QColor('#71CD58')  # green
REPEAT_COLOR = QColor('#CF4573')  # red
NO_COLOR = 'NO_COLOR'
CHAR_QCOLOR_DICT = {
    'g': QColor('#85E326').name(),  # green
    'y': QColor('#EEEF22').name(),  # yellow
    'b': QColor('#8A9ADD').name(),  # blue
    'r': QColor('#CE3535').name(),  # red
    'o': QColor('#DFBC30').name(),  # orange
    'n': NO_COLOR
}
DELIMITER = ':'
DONE_TASK = 'done'  # same as icon file names
TASK = 'todo'
NOTE = 'note'
NOT_AVAILABLE_TASK = 'not_available_todo'
SEQ = 'sequential'
PAR = 'parallel'
PAUSED = 'paused'
CHAR_TYPE_DICT = {
    'd': DONE_TASK,  # done task
    't': TASK,  # task
    'n': NOTE  # note
}
FOCUS = 'focus'
EMPTY_DATE = '14.09.52'  # random date. we regard this date as 'empty'
DELETED = 'deleted'
SEARCH_TEXT = 'search_text'
SHORTCUT = 'shortcut'
TEXT = 'text'
TREE_ITEM_ATTRIBUTES_LIST = [TEXT, 'children', 'type', 'date', 'color', DELETED, 'estimate']
NEW_DB_ITEM = {TEXT: '', 'children': '', 'type': NOTE, 'date': '', 'color': NO_COLOR, DELETED: '', 'estimate': '',
               SEARCH_TEXT: '', SHORTCUT: ''}  # just for bookmarks
FOCUS_TEXT = 'Focus on current row'
