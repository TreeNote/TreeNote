#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#################################################################################
# TreeNote
# A collaboratively usable outliner for personal knowledge and task management.
##
# Copyright (C) 2015 Jan Korte (jan.korte@uni-oldenburg.de)
##
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3 of the License.
#################################################################################

import re
import socket
import sys
from xml.sax.saxutils import escape

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *


def QDateFromString(string):
    d = QDate.fromString(string, 'dd.MM.yy')
    d.setDate(2000 + d.year() % 100, d.month(), d.day())
    return d


def indention_level(index, level=1):
    if index.parent() == QModelIndex():
        return level
    return indention_level(index.parent(), level=level + 1)


class QUndoCommandStructure(QUndoCommand):
    # this class is just for making the initialization of QUndoCommand easier.
    # Source:
    # http://chimera.labs.oreilly.com/books/1230000000393/ch08.html#_solution_129
    _fields = []  # Class variable that specifies expected fields

    def __init__(self, *args):
        if len(args) != len(self._fields):
            raise TypeError('Expected {} arguments'.format(len(self._fields)))

        # Set the arguments
        for name, value in zip(self._fields, args):
            setattr(self, name, value)

        super(QUndoCommandStructure, self).__init__(QApplication.translate('command', self.title))


class Tree_item():
    """
    To understand Qt's way of building a TreeView, read:
    http://doc.qt.io/qt-5/qtwidgets-itemviews-editabletreemodel-example.html
    """

    def __init__(self, parent=None):
        self.parentItem = parent
        self.childItems = []
        self.text = ''
        self.type = NOTE
        self.date = ''
        self.color = NO_COLOR
        self.estimate = ''
        self.expanded = True

        # just for bookmarks
        self.search_text = ''
        self.shortcut = ''

    def child_number(self):
        if self.parentItem is not None:
            return self.parentItem.childItems.index(self)
        return 0

    def add_child(self, position):
        item = Tree_item(self)
        self.childItems.insert(position, item)
        return item


class TreeModel(QAbstractItemModel):
    def __init__(self, main_window, header_list):
        super(TreeModel, self).__init__()
        self.main_window = main_window
        self.changed = False
        self.undoStack = QUndoStack(self)

        self.rootItem = Tree_item(None)
        self.rootItem.header_list = header_list
        self.rootItem.type = NOTE

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

    def getItem(self, index):
        if index.isValid():
            item = index.internalPointer()
            if item:
                return item

        return self.rootItem

    def index(self, row, column, parent=QModelIndex()):
        if row < 0 or parent.isValid() and parent.column() != 0:
            return QModelIndex()

        parentItem = self.getItem(parent)
        if row >= len(parentItem.childItems):
            return QModelIndex()

        childItem = parentItem.childItems[row]
        return self.createIndex(row, column, childItem)

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()

        childItem = self.getItem(index)
        parentItem = childItem.parentItem

        if parentItem == self.rootItem:
            return QModelIndex()
        return self.createIndex(parentItem.child_number(), 0, parentItem)

    def rowCount(self, parent=QModelIndex()):
        parentItem = self.getItem(parent)
        return len(parentItem.childItems)

    def data(self, index, role):
        if not index.isValid():
            return None

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
    def set_data_with_id(self, value, index, column, field='text'):
        class SetDataCommand(QUndoCommandStructure):
            _fields = ['model', 'index', 'value', 'column', 'field']
            title = 'Edit row'

            def set_data(self, value):
                item = self.model.getItem(self.index)
                if self.column == 0:  # used for setting color etc, too
                    self.old_value = getattr(item, self.field)
                    setattr(item, self.field, value)
                elif self.column == 1:
                    self.old_value = item.date
                    # user has not selected a date other than 'today'
                    if type(value) == QDate and value == QDate.currentDate():
                        value = EMPTY_DATE
                    value = value.toString('dd.MM.yy') if type(value) == QDate else value
                    if value == EMPTY_DATE:  # user pressed del
                        value = ''
                    item.date = value
                elif self.column == 2:
                    self.old_value = item.estimate
                    item.estimate = value

                self.model.main_window.set_selection(self.index, self.index)
                self.model.main_window.setup_tag_model()
                self.model.dataChanged.emit(self.index, self.index)

                # update next available task in a sequential project
                project_index = self.model.parent(index)
                project_parent_index = self.model.parent(project_index)
                available_index = self.model.get_next_available_task(project_index.row(), project_parent_index)
                if isinstance(available_index, QModelIndex):
                    self.model.dataChanged.emit(available_index, available_index)

                # update the sort by changing the ordering
                sorted_column = self.model.main_window.focused_column().view.header().sortIndicatorSection()
                if sorted_column == 1 or sorted_column == 2:
                    order = self.model.main_window.focused_column().view.header().sortIndicatorOrder()
                    self.model.main_window.focused_column().view.sortByColumn(sorted_column, 1 - order)
                    self.model.main_window.focused_column().view.sortByColumn(sorted_column, order)

            def redo(self):
                self.set_data(self.value)

            def undo(self):
                self.set_data(self.old_value)

        self.undoStack.push(SetDataCommand(self, index, value, column, field))
        return True

    def set_data(self, value, index, field='text'):
        return self.set_data_with_id(value, index, index.column(), field)

    # used for moving and inserting new rows. When inserting new rows, 'id_list' and 'indexes' are not used.
    def insert_remove_rows(self, position=None, parent_index=None, items=None, indexes=None, set_edit_focus=None):

        # Delete design decision: We could delete items permanently.
        # But if then the user renames, deletes and then undoes both actions,
        # the undo of 'delete' would create an item with a new id. Therefore rename won't work.
        # So we just set a delete marker. On startup, all items with a delete marker are removed permanently.
        class InsertRemoveRowCommand(QUndoCommandStructure):
            _fields = ['model', 'position', 'parent_index', 'deleted_child_parent_index_position_list',
                       'set_edit_focus', 'indexes']
            title = 'Add or remove row'

            @staticmethod  # static because it is called from the outside for moving
            def insert_existing_entry(model, position, parent_index, child_item_list):
                parent_item = model.getItem(parent_index)
                parent_item.expanded = True
                model.beginInsertRows(parent_index, position, position + len(child_item_list) - 1)
                for i, child_item in enumerate(child_item_list):
                    child_item.parentItem = parent_item
                    parent_item.childItems.insert(position + i, child_item)
                model.endInsertRows()
                index_first_moved_item = model.index(position, 0, parent_index)
                index_last_moved_item = model.index(position + len(child_item_list) - 1, 0, parent_index)
                model.main_window.set_selection(index_first_moved_item, index_last_moved_item)

                model.main_window.focused_column().view.setAnimated(False)

                def restore_children_expanded_state(index):
                    for i, child_item in enumerate(model.getItem(index).childItems):
                        child_index = model.index(i, 0, index)
                        proxy_index = model.main_window.filter_proxy_index_from_model_index(child_index)
                        model.main_window.focused_column().view.setExpanded(proxy_index, child_item.expanded)
                        restore_children_expanded_state(child_index)

                restore_children_expanded_state(parent_index)
                model.main_window.focused_column().view.setAnimated(True)

            # uses delete markers, because without them undoing would be more difficult
            def remove_rows(self):
                self.deleted_child_parent_index_position_list = []
                for index in self.indexes:
                    parent_index = self.model.parent(index)
                    parent_item = self.model.getItem(parent_index)
                    item = self.model.getItem(index)
                    position = item.child_number()
                    self.deleted_child_parent_index_position_list.append((item, parent_index, position))
                    self.model.beginRemoveRows(parent_index, position, position)
                    del parent_item.childItems[position]
                    self.model.endRemoveRows()

                # select the item below
                if len(parent_item.childItems) > 0:
                    # there is no item below, so select the one above
                    if position == len(parent_item.childItems):
                        position -= 1
                    index_next_child = self.model.index(position, 0, parent_index)
                    self.model.main_window.set_selection(index_next_child, index_next_child)
                # all children deleted, select parent
                else:
                    self.model.main_window.set_selection(parent_index, parent_index)

                    # self.fill_bookmarkShortcutsMenu() # todo

            def redo(self):  # is called when pushed to the stack
                if self.position is not None:  # insert command
                    # if redoing an insert, insert the deleted item instead of creating a new one
                    if self.deleted_child_parent_index_position_list:
                        for child_item, parent_index, position in self.deleted_child_parent_index_position_list:
                            self.insert_existing_entry(self.model, position, parent_index, [child_item])
                        # if redoing an insert, it should not get edit focus
                        self.set_edit_focus = False
                    else:
                        parent_item = self.model.getItem(self.parent_index)
                        parent_item.expanded = True
                        self.model.beginInsertRows(self.parent_index, self.position, self.position)
                        child = parent_item.add_child(self.position)
                        # type of new items depends on their parent: note -> note, projekt -> task
                        child.type = NOTE if parent_item.type == NOTE else TASK
                        self.model.endInsertRows()

                        index_of_new_entry = self.model.index(self.position, 0, self.parent_index)
                        proxy_index = self.model.main_window.filter_proxy_index_from_model_index(index_of_new_entry)
                        # qt needs to init the expanded state,
                        # otherwise segmentation faults will appear when expanding programmatically
                        self.model.main_window.focused_column().view.expand(proxy_index)

                        self.model.main_window.set_selection(index_of_new_entry, index_of_new_entry)
                        if self.set_edit_focus and index_of_new_entry.model() is self.model.main_window.item_model:
                            self.model.main_window.focusWidget().edit(
                                self.model.main_window.filter_proxy_index_from_model_index(index_of_new_entry))

                        # save index for case it gets deleted with 'undo insert'
                        self.indexes = [index_of_new_entry]
                else:
                    self.remove_rows()

            def undo(self):
                if self.position is not None:  # undo insert command
                    self.remove_rows()
                else:  # undo remove command
                    for child_item, parent_index, position in self.deleted_child_parent_index_position_list:
                        self.insert_existing_entry(self.model, position, parent_index, [child_item])

        if position is not None:  # insert command
            if set_edit_focus:  # used when adding rows programmatically e.g. pasting
                self.undoStack.push(InsertRemoveRowCommand(self, position, parent_index, None, set_edit_focus, None))
            # used from move methods, add existing db items to the parent.
            # Don't add to stack, because already part of an UndoCommand
            elif items:
                InsertRemoveRowCommand.insert_existing_entry(self, position, parent_index, items)
            elif indexes is None:  # used from view, create a single new row / self.db item
                set_edit_focus = True
                self.undoStack.push(InsertRemoveRowCommand(self, position, parent_index, None, set_edit_focus, None))
        else:  # remove command
            self.undoStack.push(InsertRemoveRowCommand(self, position, parent_index, None, False, indexes))

    def move_vertical(self, indexes, up_or_down):
        # up_or_down is -1 for up and +1 for down

        class MoveVerticalCommand(QUndoCommandStructure):
            _fields = ['model', 'indexes', 'up_or_down']
            title = 'Move vertically'

            def move(self, up_or_down):
                item = self.model.getItem(self.indexes[0])
                parent_index = self.model.parent(self.indexes[0])
                parent_item = self.model.getItem(parent_index)
                count = len(indexes)
                old_child_number = item.child_number()

                self.model.layoutAboutToBeChanged.emit([QPersistentModelIndex(parent_index)])

                index_first_moved_item = self.model.index(old_child_number, 0, parent_index)
                index_last_moved_item = self.model.index(old_child_number + count - 1, 0, parent_index)

                # if we want to move several items up, we can move the item-above below the selection instead
                if up_or_down == -1:
                    if old_child_number == 0:
                        return
                    new_position = item.child_number() + count - 1
                    old_position = old_child_number - 1
                    index_moving_item = self.model.index(old_position, 0, parent_index)
                elif up_or_down == +1:
                    if old_child_number == len(parent_item.childItems) - 1:
                        return
                    new_position = item.child_number()
                    old_position = old_child_number + count
                index_moving_item = self.model.index(old_position, 0, parent_index)
                parent_item.childItems.insert(new_position, parent_item.childItems.pop(old_position))
                index_moving_item_new = self.model.index(new_position, 0, parent_index)

                index_first_moved_item_new = self.model.index(old_child_number + up_or_down, 0, parent_index)
                index_last_moved_item_new = self.model.index(old_child_number + up_or_down + count - 1, 0, parent_index)
                self.model.changePersistentIndex(index_first_moved_item, index_first_moved_item_new)
                self.model.changePersistentIndex(index_last_moved_item, index_last_moved_item_new)
                self.model.changePersistentIndex(index_moving_item, index_moving_item_new)

                self.model.layoutChanged.emit([QPersistentModelIndex(parent_index)])

                self.model.main_window.set_selection(index_first_moved_item_new, index_last_moved_item_new)

                for child_number in range(self.model.rowCount(parent_index)):
                    child_index = self.model.index(child_number, 0, parent_index)
                    state = self.model.getItem(child_index).expanded
                    proxy_index = self.model.main_window.filter_proxy_index_from_model_index(child_index)
                    self.model.main_window.focused_column().view.setExpanded(proxy_index, state)

            def redo(self):
                self.move(self.up_or_down)

            def undo(self):
                self.move(self.up_or_down * -1)

        self.undoStack.push(MoveVerticalCommand(self, indexes, up_or_down))

    def move_horizontal(self, indexes, direction):
        item = self.getItem(indexes[0])
        position = item.parentItem.child_number() + 1
        original_position = item.child_number()
        sibling_index = self.index(original_position - 1, 0, self.parent(indexes[0]))
        parent_index = self.parent(indexes[0])
        parent_parent_index = self.parent(parent_index)
        last_childnr_of_sibling = len(item.parentItem.childItems[original_position - 1].childItems)

        # stop moving left if parent is root_item
        if parent_index == QModelIndex() and direction == -1:
            return

        # stop moving right if the moving item is the top item
        if original_position == 0 and direction == 1:
            return

        class MoveHorizontalCommand(QUndoCommandStructure):
            _fields = ['model', 'direction', 'parent_parent_index', 'parent_index', 'indexes_to_insert',
                       'position', 'original_position', 'sibling_index', 'last_childnr_of_sibling']
            title = 'move horizontal'

            def move(self, parent_index, insert_in_index, position, original_position):
                items = [self.model.getItem(index) for index in self.indexes_to_insert]
                parent_item = self.model.getItem(parent_index)
                # remove consecutive rows from_parent
                self.model.beginRemoveRows(parent_index, original_position,
                                           original_position + len(items) - 1)
                del parent_item.childItems[original_position:original_position + len(items)]
                self.model.endRemoveRows()
                # add rows to new parent
                self.model.insert_remove_rows(position=position, parent_index=insert_in_index, items=items)

            def redo(self):
                # left
                if self.direction == -1:
                    # insert as a child of the parent's parent
                    self.move(self.parent_index, self.parent_parent_index, self.position, self.original_position)
                # right
                else:
                    # insert as a child of the sibling above
                    self.move(self.parent_index, self.sibling_index, self.last_childnr_of_sibling,
                              self.original_position)

            def undo(self):
                # undo moving left
                if self.direction == - 1:
                    self.move(self.parent_parent_index, self.parent_index, self.original_position, self.position)
                # undo moving right
                else:
                    self.move(self.sibling_index, self.parent_index,
                              self.original_position, self.last_childnr_of_sibling)

        self.undoStack.push(
            MoveHorizontalCommand(self, direction, parent_parent_index, parent_index, indexes, position,
                                  original_position, sibling_index, last_childnr_of_sibling))

    def get_tags_set(self, cut_delimiter=True):
        tags_set = set()
        for index in self.match(self.index(0, 0), Qt.DisplayRole, DELIMITER, -1, Qt.MatchContains | Qt.MatchRecursive):
            word_list = index.data().split()
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
        item = self.getItem(index)
        if item.type != TASK and item.type != DONE_TASK:  # type is NOTE or a project
            self.set_data(TASK, index=index, field='type')
        elif item.type == TASK:
            # get what is behin the equal sign
            repeat_in_list = re.findall(r'repeat=((?:\w|\d)*)(?:$| )', item.text)
            if len(repeat_in_list) == 1:
                repeat_in = repeat_in_list[0]
                old_qdate = QDateFromString(item.date)
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
        elif item.type == DONE_TASK:
            self.set_data(NOTE, index=index, field='type')

    def toggle_project(self, index):
        item = self.getItem(index)
        if item.type == NOTE or item.type == DONE_TASK or item.type == TASK:  # type is Note or Task
            self.set_data(SEQ, index=index, field='type')
        elif item.type == SEQ:
            self.set_data(PAR, index=index, field='type')
        elif item.type == PAR:
            self.set_data(PAUSED, index=index, field='type')
        elif item.type == PAUSED:
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

    def insert_row(self, position, parent_index):
        self.sourceModel().insert_remove_rows(position=position, parent_index=self.mapToSource(parent_index))

    def move_horizontal(self, indexes, direction):
        if len(indexes) > 0:
            self.sourceModel().move_horizontal([self.mapToSource(index) for index in indexes], direction)

    def move_vertical(self, indexes, up_or_down):
        if len(indexes) > 0:
            self.sourceModel().move_vertical([self.mapToSource(index) for index in indexes], up_or_down)

    def getItem(self, index):
        return self.sourceModel().getItem(self.mapToSource(index))


class FilterProxyModel(QSortFilterProxyModel, ProxyTools):
    # many of the default implementations of functions in QSortFilterProxyModel are written so that they call the
    # equivalent functions in the relevant source model.
    # This simple proxying mechanism may need to be overridden for source models with more complex behavior;
    # for example, if the source model provides a custom hasChildren() implementation,
    # you should also provide one in the proxy model.
    # The QSortFilterProxyModel acts as a wrapper for the original model. If
    # you need to convert source QModelIndexes to sorted/filtered model
    # indexes or vice versa, use mapToSource(), mapFromSource(),
    # mapSelectionToSource(), and mapSelectionFromSource().

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
            elif token.startswith('FOCUS' + '='):
                # todo
                if FLATTEN not in self.filter:  # ignore
                    continue
                else:
                    # focus + flatten: show just children of flatten
                    # return if somehow_child_id is a child or grandchild etc of parent_id
                    def is_somehow_child_of_flatten_id(somehow_child_id, parent_id):
                        if somehow_child_id in self.sourceModel().sourceModel().db[parent_id]['children']:
                            return True
                        parameter_children_list = self.sourceModel().sourceModel().db[parent_id]['children'].split()
                        for child_id in parameter_children_list:
                            if is_somehow_child_of_flatten_id(somehow_child_id, child_id):
                                return True
                        return False

                    flatten_id = token[len('FOCUS' + '='):]
                    if is_somehow_child_of_flatten_id(item.id, flatten_id):
                        continue
            elif token.startswith(SORT + '='):  # ignore
                continue
            elif token.casefold() in index.data().casefold():
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

    # source: http://stackoverflow.com/
    # questions/21564976/how-to-create-a-proxy-model-that-would-flatten-nodes-of-a-qabstractitemmodel-int
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
        if index not in self.columns_list[column]:
            return QModelIndex()
        row = self.columns_list[column].index(index)
        return self.createIndex(row, column)

    def mapToSource(self, index):
        column = index.column()
        row = index.row()
        if not index.isValid() or row == -1 or row >= len(self.columns_list[column]):
            return QModelIndex()
        return self.columns_list[column][row]

    def columnCount(self, parent):
        return QAbstractProxyModel.sourceModel(self).columnCount(self.mapToSource(parent))

    def rowCount(self, parent):
        return len(self.columns_list[0]) if not parent.isValid() else 0

    def index(self, row, column, parent):
        if parent.isValid():
            return QModelIndex()
        return self.createIndex(row, column)

    def parent(self, index):
        return QModelIndex()


class Delegate(QStyledItemDelegate):
    def __init__(self, parent, model, view_header):
        super(Delegate, self).__init__(parent)
        self.model = model
        self.main_window = parent
        self.view_header = view_header

    def paint(self, painter, option, index):
        item = self.model.getItem(index)

        html = escape(index.data())
        # color tags by surrounding them with coloring html brackets
        html = re.sub(r'((\n|^| )(' + DELIMITER + r'\w+)+($| |\n))',
                      r'<font color=' + TAG_COLOR.name() + r'>\1</font>', html)
        html = re.sub(r'(repeat=\d(d|w|m|y)($| |\n))', r'<font color=' + REPEAT_COLOR.name() + r'>\1</font>', html)
        html = html.replace('\n', '<br>')

        is_not_available = item.type == TASK and not self.model.is_task_available(index)
        if item.type == DONE_TASK or is_not_available:  # not available tasks in a sequential project are grey
            html = "<font color={}>{}</font>".format(QColor(Qt.darkGray).name(), html)

        if item.color == NO_COLOR:
            text_color = QApplication.palette().text().color().name()
        else:
            text_color = QColor(item.color).name()
        html = "<font color={}>{}</font>".format(text_color, html)
        html = '<p style="white-space: pre-wrap">' + html + '</p>'

        document = self.create_document(html, option.rect.width())

        painter.save()
        pen = QPen()
        pen.setBrush(option.palette.highlight())
        pen.setWidthF(0.2)
        painter.setPen(pen)
        y = option.rect.bottomLeft().y()
        painter.drawLine(0, y, self.view_header.length(), y)
        painter.restore()

        paint_task_icon = item.type != NOTE and index.column() == 0

        painter.save()
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        padding_x = GAP_FOR_CHECKBOX if paint_task_icon else 1
        painter.translate(option.rect.left() - 5 + padding_x, option.rect.top() + self.main_window.padding)
        document.drawContents(painter)
        painter.restore()

        if paint_task_icon:
            painter.save()
            iconsize = option.decorationSize
            type = NOT_AVAILABLE_TASK if is_not_available else item.type
            icon = QImage(':/' + type)
            qImage = icon.scaledToHeight(iconsize.height())
            # place in the middle of the row
            painter.drawImage(option.rect.x(), option.rect.center().y() - qImage.height() / 2, qImage)
            painter.restore()

    def create_document(self, html, available_width):
        document = QTextDocument()
        document.setDefaultFont(QFont(FONT, self.main_window.fontsize))
        textOption = QTextOption()
        textOption.setWrapMode(QTextOption.WordWrap)
        textOption.setTabStop(TAB_WIDTH)
        document.setDefaultTextOption(textOption)
        # -2 because the editor is two pixels smaller, and if we don't subtract here,
        # there may happen line wrap when the user starts editing
        document.setTextWidth(available_width - GAP_FOR_CHECKBOX - 2)
        document.setHtml(html)
        return document

    def sizeHint(self, option, index):
        html = escape(index.data())
        column_width = self.view_header.sectionSize(0)
        indention = 1 if self.main_window.flatten else indention_level(index)
        document = self.create_document(
            html.replace('\n', '<br>'),
            column_width - indention * 20)  # 20 = space left of all rows
        return QSize(0, document.size().height() + self.main_window.padding * 2)

    def createEditor(self, parent, option, index):
        if index.column() == 0:
            suggestions_model = self.main_window.item_model.get_tags_set(cut_delimiter=False)
            edit = AutoCompleteEdit(parent, list(suggestions_model), self)
            padding_left = -5
            if self.model.getItem(index).type != NOTE:
                padding_left += GAP_FOR_CHECKBOX - 1
            edit.setStyleSheet(
                'AutoCompleteEdit {padding-left: ' + str(padding_left) + 'px; padding-top: ' +
                str(self.main_window.padding - 1) + 'px;}')
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
            line_edit.setFont(QFont(FONT, self.main_window.fontsize))
            return line_edit

    def setEditorData(self, editor, index):
        if isinstance(editor, QTextEdit):
            editor.setText(index.data())
        else:
            QStyledItemDelegate.setEditorData(self, editor, index)

    def eventFilter(self, editor, event):
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            current_index = self.main_window.current_index()
            self.closeEditor.emit(editor, QAbstractItemDelegate.NoHint)
            self.main_window.set_selection(current_index, current_index)
            return False
        return QStyledItemDelegate.eventFilter(self, editor, event)


class BookmarkDelegate(QStyledItemDelegate):
    def __init__(self, parent, model):
        super(BookmarkDelegate, self).__init__(parent)
        self.model = model
        self.main_window = parent

    def paint(self, painter, option, index):
        item = self.model.getItem(index)
        document = QTextDocument()
        if item.shortcut.startswith('Ctrl+'):
            item.shortcut = item.shortcut.replace('Ctrl+', '')
        if item.shortcut != '':
            item.shortcut += ' '
        first_text_row = re.sub(r'\n(.|\n)*', ' ...', item.text)
        document.setPlainText(item.shortcut + first_text_row)
        if option.state & QStyle.State_Selected:
            color = option.palette.highlight()
        else:
            color = QApplication.palette().base()
        painter.save()
        painter.fillRect(option.rect, color)
        needed_space = 2 if sys.platform == "darwin" else 4  # put the text in the middle of the line
        painter.translate(option.rect.x() - 2, option.rect.y() - needed_space + SIDEBARS_PADDING)
        document.drawContents(painter)
        painter.restore()

    def sizeHint(self, option, index):
        font_height = QFontMetrics(QFont(FONT, self.main_window.fontsize)).height()
        return QSize(0, font_height + SIDEBARS_PADDING * 2)


class EscCalendarWidget(QCalendarWidget):
    def __init__(self, parent):
        super(EscCalendarWidget, self).__init__(parent)
        # sadly, capture of the tab key is different on Windows and Mac.
        # so we need it here for windows and at OpenPopupDateEdit for Mac
        if sys.platform != "darwin":
            self.installEventFilter(self)
            self.first_tab_done = True

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            open_popup_date_edit = self.parent().parent()
            open_popup_date_edit.delegate.closeEditor.emit(open_popup_date_edit, QAbstractItemDelegate.NoHint)
            current_index = open_popup_date_edit.delegate.main_window.current_index()
            open_popup_date_edit.delegate.main_window.set_selection(current_index, current_index)

    def eventFilter(self, obj, event):
        open_popup_date_edit = self.parent().parent()
        if event.type() == QEvent.ShortcutOverride and event.key() == Qt.Key_Tab:
            # annoying bug that this event is sent two times. so filter the first event out.
            if self.first_tab_done and sys.platform == 'linux':  # linux behaves different to windows
                self.first_tab_done = False
            else:
                open_popup_date_edit.delegate.main_window.edit_estimate()
        if event.type() == QEvent.ShortcutOverride and event.key() == Qt.Key_Delete:
            open_popup_date_edit.setSpecialValueText(' ')
            open_popup_date_edit.setDate(QDateFromString(EMPTY_DATE))  # workaround to set empty date
            open_popup_date_edit.commit()
        return False  # don't stop the event being handled further


class OpenPopupDateEdit(QDateEdit):
    def __init__(self, parent, delegate):
        super(OpenPopupDateEdit, self).__init__(parent)
        self.delegate = delegate
        self.setFont(QFont(FONT, self.delegate.main_window.fontsize))
        if sys.platform == "darwin":
            self.first_tab_done = True
            self.installEventFilter(self)

    # open popup on focus. source: http://forum.qt.io/topic/26821/solved-activating-calender-popup-on-focus-in-event
    def focusInEvent(self, event):
        # commit edit as soon as the user goes back from the calendar popup to the dateEdit
        self.calendarWidget().activated.connect(self.commit)
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
            if self.first_tab_done:
                self.first_tab_done = False
            else:
                self.delegate.main_window.edit_row()
        if event.type() == QEvent.ShortcutOverride and event.key() == Qt.Key_Delete:
            self.setSpecialValueText(' ')
            self.setDate(QDateFromString(EMPTY_DATE))  # workaround to set empty date
            self.commit()
        return False  # don't stop the event being handled further


class AutoCompleteEdit(QPlainTextEdit):
    # source: http://blog.elentok.com/2011/08/autocomplete-textbox-for-multiple.html

    def __init__(self, parent, model, delegate):
        super(AutoCompleteEdit, self).__init__(parent)
        self.delegate = delegate
        self._separator = ' '
        self._completer = QCompleter(model)
        self._completer.setFilterMode(Qt.MatchContains)
        self._completer.setWidget(self)
        self._completer.activated[str].connect(self._insertCompletion)
        self._keysToIgnore = [Qt.Key_Enter, Qt.Key_Return, Qt.Key_Escape, Qt.Key_Tab]
        self.setFont(QFont(FONT, self.delegate.main_window.fontsize))
        self.setTabStopWidth(TAB_WIDTH)
        self.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.ShortcutOverride and event.key() == Qt.Key_Tab:
            self.delegate.main_window.edit_row()
        return False  # don't stop the event being handled further

    def _insertCompletion(self, completion):
        """
        This is the event handler for the QCompleter.activated(QString) signal,
        it is called when the user selects an item in the completer popup.
        """
        before_tag = self.toPlainText()[:self.textCursor().position() - len(self._completer.completionPrefix())]
        after_tag = self.toPlainText()[self.textCursor().position():]
        until_cursor = before_tag + completion + ' '
        self.setText(until_cursor + after_tag)
        cursor = self.textCursor()
        cursor.setPosition(len(until_cursor))
        self.setTextCursor(cursor)

    def textUnderCursor(self):
        text = self.toPlainText()
        textUnderCursor = ''
        i = self.textCursor().position() - 1
        while i >= 0 and text[i] != self._separator:
            textUnderCursor = text[i] + textUnderCursor
            i -= 1
        return textUnderCursor

    def keyPressEvent(self, event):
        # multiline editing
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            # new line on alt + enter
            if event.modifiers() & Qt.MetaModifier or event.modifiers() & Qt.ShiftModifier or \
                            event.modifiers() & Qt.AltModifier:
                rows = self.document().size().height()
                font_height = QFontMetrics(QFont(FONT, self.delegate.main_window.fontsize)).height()
                row_height = font_height + self.delegate.main_window.padding * 2
                self.setFixedHeight(rows * row_height + row_height)  # one row_height more, because we just added a line
                if event.modifiers() & Qt.AltModifier:  # fix alt + enter in Qt
                    event = QKeyEvent(QEvent.KeyPress, event.key(), Qt.NoModifier)
            else:  # complete edit on enter
                if not self._completer.popup().isVisible():
                    self.delegate.commitData.emit(self)
                    self.delegate.closeEditor.emit(self, QAbstractItemDelegate.NoHint)

        # completer stuff
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
        self._completer.popup().setCurrentIndex(self._completer.completionModel().index(0, 0))


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
SELECTION_LIGHT_BLUE = QColor(181, 213, 253)
ALTERNATE_BACKGROUND_GRAY_LIGHT = QColor(246, 246, 246)
BACKGROUND_GRAY = QColor(57, 57, 57)  # darker
ALTERNATE_BACKGROUND_GRAY = QColor(59, 59, 59)  # slightly brighter
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
EMPTY_DATE = '14.09.52'  # random date. we regard this date as 'empty'
DELETED = 'deleted'
SEARCH_TEXT = 'search_text'  # for bookmarks
SHORTCUT = 'shortcut'
TEXT = 'text'
FOCUS_TEXT = 'Focus on current row'
GAP_FOR_CHECKBOX = 22
FONT = 'Source Sans Pro'
SIDEBARS_PADDING = -1 if sys.platform == "darwin" else 2
SIDEBARS_PADDING_EXTRA_SPACE = 3 if sys.platform == "darwin" else 0
TAB_WIDTH = 30
