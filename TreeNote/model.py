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

import time
import re
import sys
from xml.sax.saxutils import escape

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *

import TreeNote.planned_model as planned_model


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

    def __init__(self, parentItem=None):
        self.parentItem = parentItem
        self.childItems = []
        self.text = ''
        self.type = NOTE
        self.date = ''
        self.color = NO_COLOR
        self.estimate = ''
        self.expanded = False
        self.quicklink_expanded = False
        self.search_text = ''  # for bookmarks
        self.shortcut = None  # for bookmarks
        self.saved_root_item_creation_date_time = None  # for bookmarks
        self.creation_date_time = time.time()
        self.selected = False
        self.planned = 0
        self.planned_order = 0

    def child_number(self):
        if self.parentItem is not None:
            return self.parentItem.childItems.index(self)
        return 0

    def add_child(self, position):
        item = Tree_item(self)
        self.childItems.insert(position, item)
        return item

    def __str__(self):
        return 'Tree_item({}, planned={}, planned_order={})'.format(self.text, self.planned, self.planned_order)


class TreeModel(QAbstractItemModel):
    def __init__(self, main_window, header_list):
        super(TreeModel, self).__init__()
        self.main_window = main_window
        self.changed = False
        self.undoStack = QUndoStack(self)

        self.rootItem = Tree_item(None)
        self.rootItem.text = '/'
        self.rootItem.header_list = header_list
        self.rootItem.add_child(0)
        self.rootItem.childItems[0].text = "This is your first entry. Hit 'return' to create another one."
        self.selected_item = self.rootItem.childItems[0]

    def child_indexes(self, parent_index):
        indexes = []
        for i in range(self.rowCount(parent_index)):
            indexes.append(self.index(i, 0, parent_index))
        return indexes

    # necessary, because persistentIndexList() seems not to include all indexes
    def indexes(self):
        indexes = []

        def add_indexes(parent_index):
            indexes.append(parent_index)
            for i in range(self.rowCount(parent_index)):
                add_indexes(self.index(i, 0, parent_index))

        add_indexes(QModelIndex())
        return indexes

    def items(self, root_item=None):
        if not root_item:
            root_item = self.rootItem
        items = []

        def add_items(item):
            items.append(item)
            for child in item.childItems:
                add_items(child)

        add_items(root_item)
        return items

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

    def getItem(self, index) -> Tree_item:
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
            # hidden option to show number of children behind each row
            if False:
                def count_children(index):
                    child_count = 0
                    for child_index in self.child_indexes(index):
                        child_count += 1
                        child_count += count_children(child_index)
                    return child_count

                return '{} {}'.format(item.text, count_children(index))
            return item.text
        elif index.column() == 1:
            return item.estimate
        else:  # index.column() == 2:
            return item.date

    def set_data(self, value, index, field='text'):
        class SetDataCommand(QUndoCommandStructure):
            _fields = ['model', 'index', 'value', 'column', 'field']
            title = self.tr("'Edit row'")

            def set_data(self, value):
                item = self.model.getItem(self.index)
                if self.column == 0:  # used for setting color etc, too
                    self.old_value = getattr(item, self.field)
                    setattr(item, self.field, value)
                    if self.field == TEXT:
                        if TAG_DELIMITER in value or TAG_DELIMITER in self.old_value:
                            self.model.main_window.setup_tag_model()
                        # rename internal links
                        for item in self.model.items():
                            old_link = INTERNAL_LINK_DELIMITER + self.old_value + INTERNAL_LINK_DELIMITER
                            new_link = INTERNAL_LINK_DELIMITER + value + INTERNAL_LINK_DELIMITER
                            if old_link in item.text:
                                item.text = item.text.replace(old_link, new_link)
                    elif self.field == PLANNED:
                        orders_of_same_planning_level = [other_item.planned_order for other_item in
                                                         self.model.main_window.planned_view.model().items() if
                                                         other_item.planned == value and other_item != item]
                        if orders_of_same_planning_level:
                            item.planned_order = max(orders_of_same_planning_level) + 1

                elif self.column == 1:
                    self.old_value = item.estimate
                    item.estimate = value
                elif self.column == 2:
                    self.old_value = item.date
                    # user has not selected a date other than 'today'
                    if type(value) == QDate and value == QDate.currentDate():
                        value = EMPTY_DATE
                    value = value.toString('dd.MM.yy') if type(value) == QDate else value
                    if value == EMPTY_DATE:  # user pressed del
                        value = ''
                    item.date = value

                self.model.dataChanged.emit(self.index,
                                            self.model.index(self.index.row(), len(self.model.rootItem.header_list) - 1,
                                                             self.index.parent()))

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

        self.undoStack.push(SetDataCommand(self, index, value, index.column(), field))

    def expand_saved(self, idx=QModelIndex(), print_view=None):
        def restore_children_expanded_state(index):
            for i, child_item in enumerate(self.getItem(index).childItems):
                child_index = self.index(i, 0, index)
                if print_view:
                    print_view.setExpanded(child_index, child_item.expanded)
                else:
                    proxy_index = self.main_window.filter_proxy_index_from_model_index(child_index)
                    self.main_window.focused_column().view.setExpanded(proxy_index, child_item.expanded)
                    self.main_window.quicklinks_view.setExpanded(child_index, child_item.quicklink_expanded)
                restore_children_expanded_state(child_index)

        self.main_window.focused_column().view.setAnimated(False)
        restore_children_expanded_state(idx)
        self.main_window.focused_column().view.setAnimated(True)

    # used for moving and inserting new rows. When inserting new rows, 'id_list' and 'indexes' are not used.
    def insert_remove_rows(self, position=None, parent_index=None, items=None, indexes=None, set_edit_focus=None,
                           select=True):

        # Delete design decision: We could delete items permanently.
        # But if then the user renames, deletes and then undoes both actions,
        # the undo of 'delete' would create an item with a new id. Therefore rename won't work.
        # So we just set a delete marker. On startup, all items with a delete marker are removed permanently.
        class InsertRemoveRowCommand(QUndoCommandStructure):
            _fields = ['model', 'position', 'parent_index', 'deleted_child_parent_index_position_list',
                       'set_edit_focus', 'indexes', 'items']
            title = self.tr("'Add or remove row'")

            @staticmethod  # static because it is called from the outside for moving
            def insert_existing_entry(model, position, parent_index, child_item_list, select=True):
                parent_item = model.getItem(parent_index)
                parent_item.expanded = True
                model.beginInsertRows(parent_index, position, position + len(child_item_list) - 1)
                for i, child_item in enumerate(child_item_list):
                    child_item.parentItem = parent_item
                    parent_item.childItems.insert(position + i, child_item)
                model.endInsertRows()

                model.main_window.save_file()

                indexes = []
                for i in range(len(child_item_list)):
                    indexes.append(model.index(position + i, 0, parent_index))
                if select:
                    model.main_window.select_from_to(indexes[0], indexes[-1])

                model.expand_saved(parent_index)
                return indexes

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

                self.model.main_window.save_file()

                # select the item below
                if self.model.main_window.current_view() is self.model.main_window.planned_view:
                    select_index = self.model.main_window.current_view().model().index(
                        self.model.main_window.current_index().row() + 1, 0)
                    if select_index:
                        self.model.main_window.select([select_index])
                else:
                    if len(parent_item.childItems) > 0:
                        # there is no item below, so select the one above
                        if position == len(parent_item.childItems):
                            position -= 1
                        index_next_child = self.model.index(position, 0, parent_index)
                        self.model.main_window.select([index_next_child])
                    # all children deleted, select parent
                    else:
                        self.model.main_window.select([parent_index])

                self.model.main_window.fill_bookmarkShortcutsMenu()
                self.model.main_window.setup_tag_model()

            def redo(self):  # is called when pushed to the stack
                if self.items:  # pasting real items
                    self.indexes = InsertRemoveRowCommand.insert_existing_entry(self.model, self.position,
                                                                                self.parent_index, self.items, True)
                elif self.position is not None:  # insert command
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
                        if self.model is not self.model.main_window.bookmark_model:
                            proxy_index = self.model.main_window.filter_proxy_index_from_model_index(index_of_new_entry)
                            # qt needs to init the expanded state,
                            # otherwise segmentation faults will appear when expanding programmatically
                            self.model.main_window.focused_column().view.expand(proxy_index)

                            self.model.main_window.select_from_to(index_of_new_entry, index_of_new_entry)
                            # open editor, when in tree view
                            # when in plan view, we need to increase planned attribute first, in insert_row()
                            if self.set_edit_focus and index_of_new_entry.model() is self.model.main_window.item_model \
                                    and self.model.main_window.current_view() is self.model.main_window.focused_column().view:
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
            # used when pasting real items
            if set_edit_focus is not None and items:
                self.undoStack.push(
                    InsertRemoveRowCommand(self, position, parent_index, None, set_edit_focus, None, items))
            # used when adding rows programmatically by pasting plain text. Then set_edit_focus is False.
            elif set_edit_focus is not None:
                self.undoStack.push(
                    InsertRemoveRowCommand(self, position, parent_index, None, set_edit_focus, None, None))
                # used from move methods, adds existing items to the parent
            # Don't add to stack, because already part of an UndoCommand
            elif items:
                InsertRemoveRowCommand.insert_existing_entry(self, position, parent_index, items, select)
            elif indexes is None:  # used from view, create a single new row / item
                set_edit_focus = True
                self.undoStack.push(
                    InsertRemoveRowCommand(self, position, parent_index, None, set_edit_focus, None, None))
        else:  # remove command
            self.undoStack.push(InsertRemoveRowCommand(self, position, parent_index, None, False, indexes, None))

    def file(self, indexes, new_parent):
        class FileCommand(QUndoCommandStructure):
            _fields = ['model', 'indexes_and_old_positions_dict', 'new_parent']
            title = self.tr("'File'")

            def move(self, index, new_parent, old_position=None):
                item = self.model.getItem(index)
                parent_item = self.model.getItem(index.parent())
                self.model.beginRemoveRows(index.parent(), item.child_number(), item.child_number())
                del parent_item.childItems[item.child_number()]
                self.model.endRemoveRows()
                as_last = self.model.rowCount(self.new_parent)
                new_position = old_position if old_position else as_last
                self.model.insert_remove_rows(position=new_position, parent_index=new_parent, items=[item],
                                              select=False)

            def redo(self):
                for index in self.indexes_and_old_positions_dict.keys():
                    self.move(index, self.new_parent)

            def undo(self):
                for index, value in self.indexes_and_old_positions_dict.items():
                    self.move(index, value[0], value[1])

        indexes_old_parents_positions_dict = {}
        for index in indexes:
            item = self.getItem(index)
            indexes_old_parents_positions_dict[index] = index.parent(), item.child_number()
        self.undoStack.push(FileCommand(self, indexes_old_parents_positions_dict, new_parent))

    def move_vertical(self, indexes, up_or_down):
        # up_or_down is -1 for up and +1 for down

        class MoveVerticalCommand(QUndoCommandStructure):
            _fields = ['model', 'indexes', 'up_or_down']
            title = self.tr("'Move vertically'")

            def move(self, up_or_down):
                if self.model.main_window.current_view() is self.model.main_window.planned_view:
                    index = self.indexes[0]
                    index_to_swap = self.model.main_window.planned_view.model().index(index.row() + up_or_down, 0)
                    item = self.model.getItem(self.indexes[0])
                    if index_to_swap.isValid():
                        item_to_swap = self.model.main_window.planned_view.model().getItem(index_to_swap)
                        if item_to_swap.planned == item.planned:
                            # swap the two order values
                            item.planned_order, item_to_swap.planned_order = item_to_swap.planned_order, item.planned_order
                            # since we moved the row, we have to select the index at the swapped position
                            index = index_to_swap
                        else:
                            item.planned += up_or_down
                            if item.planned == item_to_swap.planned:
                                item.planned_order = item_to_swap.planned_order + up_or_down * -1
                            else:
                                item.planned_order = 0
                    elif up_or_down < 0 and item.planned > 1 or up_or_down > 0 and item.planned < max(
                            NUMBER_PLAN_DICT.keys()):
                        item.planned += up_or_down
                    self.model.main_window.save_file()
                    self.model.main_window.select([index])
                else:
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
                    index_last_moved_item_new = self.model.index(old_child_number + up_or_down + count - 1, 0,
                                                                 parent_index)
                    self.model.changePersistentIndex(index_first_moved_item, index_first_moved_item_new)
                    self.model.changePersistentIndex(index_last_moved_item, index_last_moved_item_new)
                    self.model.changePersistentIndex(index_moving_item, index_moving_item_new)

                    self.model.layoutChanged.emit([QPersistentModelIndex(parent_index)])

                    self.model.main_window.select_from_to(index_first_moved_item_new, index_last_moved_item_new)
                    for row_index in self.model.main_window.focused_column().view.selectionModel().selectedRows():
                        self.model.main_window.focused_column().view.scrollTo(row_index)

                    for child_number in range(self.model.rowCount(parent_index)):
                        child_index = self.model.index(child_number, 0, parent_index)
                        state = self.model.getItem(child_index).expanded
                        proxy_index = self.model.main_window.filter_proxy_index_from_model_index(child_index)
                        self.model.main_window.focused_column().view.setExpanded(proxy_index, state)
                    self.model.main_window.save_file()

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
            title = self.tr("'Move horizontal'")

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

    def get_tags_set(self, cut_delimiter=True, all_tags=False):
        tags_set = set()
        current_root_index = QModelIndex() if all_tags else self.main_window.focused_column().view.rootIndex()
        for item in self.items(root_item=self.main_window.focused_column().filter_proxy.getItem(current_root_index)):
            for word in item.text.split():
                if word[0] == TAG_DELIMITER and word not in NO_TAG_LIST:
                    delimiter = '' if cut_delimiter else TAG_DELIMITER
                    tags_set.add(delimiter + word.strip(TAG_DELIMITER))
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

    def setData(self, index, value, role=None):
        self.set_data(value, index=index, field='text')

    def remove_rows(self, indexes):
        self.insert_remove_rows(indexes=indexes)


class ProxyTools():
    # when the editor commits it's data, it calls this method
    # it is overwritten from QAbstractProxyModel

    def setData(self, index, value, role=None):
        self.sourceModel().setData(self.mapToSource(index), value, role=role)
        self.sourceModel().main_window.save_file()
        return True

    def map_to_source(self, indexes):
        mapped_indexes = []
        for index in indexes:
            if index.model() is self.sourceModel().main_window.planned_view.model():
                index = self.sourceModel().main_window.planned_view.model().map_to_original_index(index)
            if index.model() is not self.sourceModel():
                index = self.mapToSource(index)
            mapped_indexes.append(index)
        return mapped_indexes

    def set_data(self, value, indexes=None, field='text'):
        for index in self.map_to_source(indexes):
            self.sourceModel().set_data(value, index=index, field=field)
        self.sourceModel().main_window.save_file()

    def adjust_estimate(self, adjustment, indexes):
        for index in self.map_to_source(indexes):
            old_estimate = self.sourceModel().getItem(index).estimate
            if old_estimate == '':
                old_estimate = 0
            new_estimate = int(old_estimate) + adjustment
            if new_estimate < 1:
                new_estimate = ''
            self.sourceModel().set_data(str(new_estimate), index=index, field=ESTIMATE)
        self.sourceModel().main_window.save_file()

    def remove_rows(self, indexes):
        self.sourceModel().remove_rows(self.map_to_source(indexes))

    def toggle_task(self, indexes):
        for index in self.map_to_source(indexes):
            self.sourceModel().toggle_task(index)
        self.sourceModel().main_window.save_file()

    def toggle_project(self, indexes):
        for index in self.map_to_source(indexes):
            self.sourceModel().toggle_project(index)
        self.sourceModel().main_window.save_file()

    def is_task_available(self, index):
        return self.sourceModel().is_task_available(self.mapToSource(index))

    def insert_row(self, position, parent_index):
        self.sourceModel().insert_remove_rows(position=position, parent_index=self.mapToSource(parent_index))
        self.sourceModel().main_window.save_file()

    def move_horizontal(self, indexes, direction):
        if len(indexes) > 0:
            self.sourceModel().move_horizontal([self.mapToSource(index) for index in indexes], direction)
            self.sourceModel().main_window.save_file()

    def move_vertical(self, indexes, up_or_down):
        if len(indexes) > 0:
            self.sourceModel().move_vertical(self.map_to_source(indexes), up_or_down)

    def file(self, indexes, new_parent):
        self.sourceModel().file([self.mapToSource(index) for index in indexes], new_parent)
        self.sourceModel().main_window.save_file()

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

    def filterAcceptsRow(self, row, parent_index):
        index = self.sourceModel().index(row, 0, parent_index)
        return False if not index.isValid() else self.filter_accepts_row(self.filter, index)

    def somehow_parent(self, focused_item, recursion_item):
        if not recursion_item.parentItem:
            return False
        elif recursion_item.parentItem is focused_item:
            return True
        else:
            return self.somehow_parent(focused_item, recursion_item.parentItem)

    def filter_accepts_row(self, filter, index, focused_item=None):
        item = self.sourceModel().getItem(index)

        if focused_item:
            if not self.somehow_parent(focused_item, item):
                return False

                # return True if this row's data is accepted
        tokens = filter.split()  # all tokens must be in the row's data
        for token in tokens:
            if token.startswith(SORT):  # ignore / let it pass
                continue
            elif token.startswith('c='):
                color_character = token[2]
                if item.color == CHAR_QCOLOR_DICT.get(color_character):
                    continue
            elif token.startswith('t='):
                task_character = token[2]
                type = CHAR_TYPE_DICT.get(task_character)
                if item.type == type:
                    # just available tasks
                    if type == TASK and not self.sourceModel().is_task_available(index):
                        break
                    continue
            elif token.startswith(DATE_BELOW):
                count_characters = token[5:-1]
                if count_characters and item.date:
                    count = int(count_characters)
                    date_type_character = token[-1]
                    if date_type_character == 'd':
                        future_date = QDate.currentDate().addDays(count)
                    elif date_type_character == 'w':
                        future_date = QDate.currentDate().addDays(7 * count)
                    elif date_type_character == 'm':
                        future_date = QDate.currentDate().addMonths(1)
                    elif date_type_character == 'y':
                        future_date = QDate.currentDate().addYears(1)
                    else:
                        break
                    if QDateFromString(item.date) <= future_date:
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
            elif token.startswith(HIDE_TAGS):
                # accept (continue) when row has no tag
                if not re.search(' ' + TAG_DELIMITER, item.text):
                    continue
            elif token.startswith(HIDE_FUTURE_START_DATE):
                # accept (continue) when no date or date is not in future
                if item.date == '' or QDateFromString(item.date) <= QDate.currentDate():
                    continue
            # searching for "blue" shall find "a blue flower" but not "bluetooth"
            elif ' ' + token.casefold() + ' ' in ' ' + item.text.casefold() + ' ':
                continue
            # searching for "*blue*" shall find "bluetooth"
            elif token[0] == '*' and token[-1] == '*' and token[1:-1].casefold() in item.text.casefold():
                continue
            break  # user type stuff that's not found
        else:  # just executed when not breaked
            return True  # all tokens are in the row

        # return True if a child row is accepted
        # but not with the hide checkboxes
        if not token.startswith(HIDE_FUTURE_START_DATE) and not token.startswith(HIDE_TAGS):
            for row in range(len(item.childItems)):
                if self.filter_accepts_row(filter, self.sourceModel().index(row, 0, index)):
                    return True

        return False

    def lessThan(self, left_index, right_index):
        column = left_index.column()
        left_data = left_index.data()
        right_data = right_index.data()
        if column == 0:
            return True
        elif column == 1:
            new_left_data = int(left_data) if left_data != '' else sys.maxsize
            new_right_data = int(right_data) if right_data != '' else sys.maxsize
        elif column == 2:
            new_left_data = QDateFromString(left_data)
            new_right_data = QDateFromString(right_data)

        return new_left_data > new_right_data


class Delegate(QStyledItemDelegate):
    def __init__(self, main_window, model, view_header):
        super(Delegate, self).__init__(main_window)
        self.model = model
        self.main_window = main_window
        self.view_header = view_header

    def paint(self, painter, option, index):
        item = self.model.getItem(index)

        html = escape(index.data())
        # color tags by surrounding them with coloring html brackets
        html = re.sub(r'((\n|^| )(' + TAG_DELIMITER + r'\w+)+($| |\n))',
                      r'<font color=' + TAG_COLOR.name() + r'>\1</font>', html)
        html = re.sub(FIND_INTERNAL_LINK, r'<font color=' + INTERNAL_LINK_COLOR.name() + r'>\1 </font>', html)
        html = re.sub(r'(repeat=\d(d|w|m|y)($| |\n))', r'<font color=' + REPEAT_COLOR.name() + r'>\1</font>', html)
        html = html.replace('\n', '<br>')

        if index.column() == 0 and item.planned != 0:
            html += r' <font color=' + PLANNED_COLOR.name() + r'>' + NUMBER_PLAN_DICT[item.planned] + r'</font>'

        # planned view: paint parent at the start
        # but not if the parent is the 'normal' parent which was set in the settings
        if self.model is self.main_window.planned_view.model() and \
                        index.column() == 0 and item.parentItem != self.main_window.item_model.rootItem and \
                        str(item.parentItem.creation_date_time) != str(
                    self.main_window.new_rows_plan_item_creation_date):
            html = r'<font color={}>{}</font> {}'.format(DARK_GREY, item.parentItem.text, html)

        is_not_available = item.type == TASK and not self.model.is_task_available(index)
        if item.type == DONE_TASK or is_not_available:  # not available tasks in a sequential project are grey
            html = "<font color={}>{}</font>".format(QColor(Qt.darkGray).name(), html)

        if item.color == NO_COLOR:
            text_color = self.view_header.palette().text().color().name()
        else:
            text_color = QColor(item.color).name()
        html = "<font color={}>{}</font>".format(text_color, html)
        html = '<p style="white-space: pre-wrap">' + html + '</p>'

        document = self.create_document(index, html, option.rect.width())

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
        checkbox_size = QFontMetrics(QFont(FONT, self.main_window.fontsize)).height() - CHECKBOX_SMALLER
        padding_x = checkbox_size if paint_task_icon else 1
        painter.translate(option.rect.left() - 5 + padding_x, option.rect.top() + self.main_window.padding)
        document.drawContents(painter)
        painter.restore()

        if paint_task_icon:
            painter.save()
            type = NOT_AVAILABLE_TASK if is_not_available else item.type
            icon = QImage(':/' + type)
            qImage = icon.scaledToHeight(checkbox_size)
            # place in the middle of the row
            painter.drawImage(option.rect.x(), option.rect.center().y() - qImage.height() / 2, qImage)
            painter.restore()

    def create_document(self, index, html, available_width):
        document = QTextDocument()
        document.setDefaultFont(QFont(FONT, self.main_window.fontsize))
        textOption = QTextOption()
        textOption.setWrapMode(QTextOption.WordWrap)
        textOption.setTabStop(TAB_WIDTH)
        document.setDefaultTextOption(textOption)
        if self.model.getItem(index).type != NOTE:
            available_width -= QFontMetrics(QFont(FONT, self.main_window.fontsize)).height() - CHECKBOX_SMALLER
        # +3 because the createEditor is wider, and if we don't add here,
        # there may happen line wrap when the user starts editing
        document.setTextWidth(available_width + 3)
        document.setHtml(html)
        return document

    def sizeHint(self, option, index):
        html = escape(index.data())
        column_width = self.view_header.sectionSize(0)
        document = self.create_document(index, html.replace('\n', '<br>'), column_width - indention_level(index) *
                                        self.main_window.focused_column().view.indentation())
        return QSize(0, document.size().height() + self.main_window.padding * 2)

    def createEditor(self, parent, option, index):
        if index.column() == 0:
            suggestions_list = list(self.main_window.item_model.get_tags_set(cut_delimiter=False, all_tags=True))
            tree_item_list = [item.text for item in self.main_window.item_model.items()]
            edit = AutoCompleteEdit(parent, suggestions_list, tree_item_list, self)
            padding_left = -5
            if self.model.getItem(index).type != NOTE:
                padding_left += QFontMetrics(QFont(FONT, self.main_window.fontsize)).height() - CHECKBOX_SMALLER
            edit.setStyleSheet(
                'AutoCompleteEdit {padding-left: ' + str(padding_left) + 'px; padding-top: ' +
                str(self.main_window.padding - 1) + 'px;}')
            return edit
        if index.column() == 1:
            line_edit = QLineEdit(parent)
            line_edit.setValidator(QIntValidator(0, 999, self))
            line_edit.setStyleSheet('QLineEdit {padding-left: 16px;}')
            line_edit.setFont(QFont(FONT, self.main_window.fontsize))
            return line_edit
        else:  # index.column() == 2:
            date_edit = OpenPopupDateEdit(parent, self)
            date = QDate.currentDate() if index.data() == '' else QDateFromString(index.data())
            date_edit.setDate(date)
            date_edit.setCalendarPopup(True)
            date_edit.setCalendarWidget(EscCalendarWidget(parent))
            date_edit.setStyleSheet('QDateEdit {padding-left: 14px;}')
            return date_edit

    def setEditorData(self, editor, index):
        if isinstance(editor, QTextEdit):
            editor.setText(index.data())
        else:
            QStyledItemDelegate.setEditorData(self, editor, index)

    def eventFilter(self, editor, event):
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            current_index = self.main_window.current_index()
            self.closeEditor.emit(editor, QAbstractItemDelegate.NoHint)
            self.main_window.select_from_to(current_index, current_index)
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
        html = item.text
        if item.shortcut:
            html += ' (' + item.shortcut + ')'
        document.setHtml(html)
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
        self.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.setMinimumWidth(280)
        self.clicked.connect(self.commit_and_done)
        # sadly, capture of the tab key is different on Windows and Mac.
        # so we need it here for windows and at OpenPopupDateEdit for Mac
        if sys.platform != "darwin":
            self.installEventFilter(self)
            self.first_tab_done = True

    def commit_and_done(self):
        open_popup_date_edit = self.parent().parent()
        open_popup_date_edit.commit()
        self.done()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.done()

    def done(self):
        open_popup_date_edit = self.parent().parent()
        open_popup_date_edit.delegate.closeEditor.emit(open_popup_date_edit, QAbstractItemDelegate.NoHint)
        current_index = open_popup_date_edit.delegate.main_window.current_index()
        open_popup_date_edit.delegate.main_window.select_from_to(current_index, current_index)

    def eventFilter(self, obj, event):
        open_popup_date_edit = self.parent().parent()
        if event.type() == QEvent.ShortcutOverride and (event.key() == Qt.Key_Return or event.key() == Qt.Key_Tab):
            open_popup_date_edit.commit()
            self.done()
        elif event.type() == QEvent.ShortcutOverride and event.key() == Qt.Key_Delete:
            open_popup_date_edit.setSpecialValueText(' ')
            open_popup_date_edit.setDate(QDateFromString(EMPTY_DATE))  # workaround to set empty date
            open_popup_date_edit.commit()
            self.done()
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

    def __init__(self, parent, tag_list, tree_item_list, delegate):
        super(AutoCompleteEdit, self).__init__(parent)
        self.delegate = delegate
        self._separator = ' '
        self.tag_completer = QCompleter(tag_list)
        self.internal_link_completer = QCompleter(tree_item_list)
        for completer in self.tag_completer, self.internal_link_completer:
            completer.setFilterMode(Qt.MatchContains)
            completer.setWidget(self)
            completer.activated[str].connect(self._insertCompletion)
        self._keysToIgnore = [Qt.Key_Enter, Qt.Key_Return, Qt.Key_Escape, Qt.Key_Tab]
        self.setFont(QFont(FONT, self.delegate.main_window.fontsize))
        self.setTabStopWidth(TAB_WIDTH)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress and event.matches(QKeySequence.Paste):
            line_breaks = QApplication.clipboard().text().count('\n')
            self.increase_row_height_and_show_complete_editor(line_breaks)
        elif event.type() == QEvent.ShortcutOverride and event.key() == Qt.Key_Tab:
            self.delegate.main_window.edit_row()
        return False  # don't stop the event being handled further

    def _insertCompletion(self, completion):
        """
        This is the event handler for the QCompleter.activated(QString) signal,
        it is called when the user selects an item in the completer popup.
        """
        if self.tag_completer.completionPrefix():
            typed_letters_to_replace = self.tag_completer.completionPrefix()
        else:
            typed_letters_to_replace = self.internal_link_completer.completionPrefix()
        before_tag = self.toPlainText()[
                     :self.textCursor().position() - len(typed_letters_to_replace)]
        after_tag = self.toPlainText()[self.textCursor().position():]
        if self.internal_link_completer.completionPrefix():
            completion += INTERNAL_LINK_DELIMITER
        until_cursor = before_tag + completion + ' '
        self.setPlainText(until_cursor + after_tag)
        cursor = self.textCursor()
        cursor.setPosition(len(until_cursor))
        self.setTextCursor(cursor)
        self.tag_completer.setCompletionPrefix('')
        self.internal_link_completer.setCompletionPrefix('')

    def textUnderCursor(self):
        text = self.toPlainText()
        textUnderCursor = ''
        i = self.textCursor().position() - 1
        while i >= 0 and text[i] != self._separator:
            textUnderCursor = text[i] + textUnderCursor
            i -= 1
        return textUnderCursor

    def increase_row_height_and_show_complete_editor(self, added_rows):
        rows = self.document().size().height()
        font_height = QFontMetrics(QFont(FONT, self.delegate.main_window.fontsize)).height()
        row_height = font_height + self.delegate.main_window.padding * 2
        self.setFixedHeight(rows * row_height + added_rows * row_height)

    def keyPressEvent(self, event):
        # multiline editing
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            # new line on alt + enter
            if event.modifiers() & Qt.MetaModifier or event.modifiers() & Qt.ShiftModifier or \
                            event.modifiers() & Qt.AltModifier:
                if event.modifiers() & Qt.AltModifier:  # fix alt + enter in Qt
                    event = QKeyEvent(QEvent.KeyPress, event.key(), Qt.NoModifier)
                self.increase_row_height_and_show_complete_editor(1)
            else:  # complete edit on enter
                if not self.tag_completer.popup().isVisible() and not self.internal_link_completer.popup().isVisible():
                    self.delegate.commitData.emit(self)
                    self.delegate.closeEditor.emit(self, QAbstractItemDelegate.NoHint)

        # completer stuff
        if event.key() in self._keysToIgnore and \
                (self.tag_completer.popup().isVisible() or self.internal_link_completer.popup().isVisible()):
            event.ignore()
            return
        super(AutoCompleteEdit, self).keyPressEvent(event)
        completionPrefix = self.textUnderCursor()
        if completionPrefix and completionPrefix[0] == INTERNAL_LINK_DELIMITER:
            completionPrefix = completionPrefix[1:]
        if len(completionPrefix) == 0:
            self.tag_completer.popup().hide()
            self.internal_link_completer.popup().hide()
            return

        def upate_completions(completer):
            if completionPrefix != completer.completionPrefix():
                self._updateCompleterPopupItems(completer, completionPrefix)
            # if something was just typed
            if len(event.text()) > 0:
                completer.complete()

        if self.textUnderCursor()[0] == TAG_DELIMITER:
            upate_completions(self.tag_completer)
        elif self.textUnderCursor()[0] == INTERNAL_LINK_DELIMITER:
            upate_completions(self.internal_link_completer)

    # Filters the completer's popup items to only show items with the given prefix.
    def _updateCompleterPopupItems(self, completer, completionPrefix):
        completer.setCompletionPrefix(completionPrefix)
        completer.popup().setCurrentIndex(completer.completionModel().index(0, 0))


NO_TAG_LIST = [':', ':"', ':)', ':/', ':).']
HIDE_FUTURE_START_DATE = 'hide_future_date'
HIDE_TAGS = 'has_tag'
SORT = 'sort'
ESTIMATE = 'estimate'
STARTDATE = 'startdate'
ASC = '_ascending'
DESC = '_descending'
TEXT_GRAY = QColor('#bcc3d0')  # bright grey
SELECTION_GRAY = QColor('#555B6E')
SELECTION_LIGHT_BLUE = QColor(181, 213, 253)
ALTERNATE_BACKGROUND_GRAY_LIGHT = QColor(246, 246, 246)
BACKGROUND_GRAY = QColor(57, 57, 57)  # darker
ALTERNATE_BACKGROUND_GRAY = QColor(59, 59, 59)  # slightly brighter
FOREGROUND_GRAY = QColor(78, 80, 82)  # brighter
HIGHLIGHT_ORANGE = QColor(195, 144, 72)
TAG_COLOR = QColor('#71CD58')  # green
INTERNAL_LINK_COLOR = QColor('#00b797')
REPEAT_COLOR = QColor('#CF4573')  # red
NO_COLOR = 'NO_COLOR'
DARK_GREY = QColor('#808080').name()
RED = QColor('#FF2F00').name()
CHAR_QCOLOR_DICT = {
    'g': QColor('#85E326').name(),  # green
    'y': QColor('#EEEF22').name(),  # yellow
    'b': QColor('#8A9ADD').name(),  # blue
    'r': RED,  # red
    'o': QColor('#FF9500').name(),  # orange
    'v': QColor('#FF40FF').name(),  # violet
    'n': NO_COLOR
}
PLANNED_COLOR = QColor('#44A6C7')
NUMBER_PLAN_DICT = {
    0: '0 nichts',
    1: '1 sofort',
    2: '2 später',
    3: '3 morgen',
    4: '4 dringend und wichtig',
    5: '5 dringend und egal',
    6: '6 hat_Zeit und wichtig',
    7: '7 hat_Zeit und egal',
}
TAG_DELIMITER = r':'
INTERNAL_LINK_DELIMITER = r'#'
FIND_INTERNAL_LINK = r'((\n|^| )(' + INTERNAL_LINK_DELIMITER + r'\w(\w| )+' + INTERNAL_LINK_DELIMITER + '))( |$)'
DONE_TASK = 'done'  # same as icon file names
TASK = 'todo'
NOTE = 'note'
NOT_AVAILABLE_TASK = 'not_available_todo'
SEQ = 'sequential'
PAR = 'parallel'
PAUSED = 'paused'
PLANNED = 'planned'
PLANNED_ORDER = 'planned_order'
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
CHECKBOX_SMALLER = 7
FONT = 'Source Sans Pro'
SIDEBARS_PADDING = -1 if sys.platform == "darwin" else 2
SIDEBARS_PADDING_EXTRA_SPACE = 3 if sys.platform == "darwin" else 0
TAB_WIDTH = 30
DATE_BELOW = 'date<'
