from PyQt5 import QtWidgets
import sys
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import qrc_resources
import item_model
import tag_model
import subprocess
import socket
import webbrowser
import re
import time
import couchdb
from functools import partial

EDIT_BOOKMARK = 'Edit bookmark'


class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()

        self.model = item_model.TreeModel(self.get_db('items'), header_list=['Text', 'Start date', 'Estimate'])
        self.model.db_change_signal[dict, QAbstractItemModel].connect(self.db_change_signal)

        self.bookmark_model = item_model.TreeModel(self.get_db('bookmarks'), header_list=['Bookmarks'])
        self.bookmark_model.db_change_signal[dict, QAbstractItemModel].connect(self.db_change_signal)

        self.mainSplitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(self.mainSplitter)

        self.actions = list()

        def add_action(name, qaction):
            setattr(self, name, qaction)
            self.actions.append(qaction)

        add_action('aboutAct', QAction(self.tr('&About'), self, triggered=self.about))
        add_action('unsplitWindowAct', QAction(self.tr('&Unsplit window'), self, shortcut='Ctrl+Shift+S', triggered=self.unsplit_window))
        self.unsplitWindowAct.setEnabled(False)  # todo put in update actions
        add_action('splitWindowAct', QAction(self.tr('&Split window'), self, shortcut='Ctrl+S', triggered=self.split_window))
        add_action('editRowAction', QAction(self.tr('&Edit row'), self, shortcut='Tab', triggered=self.edit_row))
        add_action('deleteSelectedRowsAction', QAction(self.tr('&Delete selected rows'), self, shortcut='delete', triggered=self.removeSelection))
        add_action('insertRowAction', QAction(self.tr('&Insert row'), self, shortcut='Return', triggered=self.insert_row))
        add_action('insertChildAction', QAction(self.tr('&Insert child'), self, shortcut='Shift+Return', triggered=self.insert_child))
        add_action('moveUpAction', QAction(self.tr('&Up'), self, shortcut='W', triggered=self.move_up))
        add_action('moveDownAction', QAction(self.tr('&Down'), self, shortcut='S', triggered=self.move_down))
        add_action('moveLeftAction', QAction(self.tr('&Left'), self, shortcut='A', triggered=self.move_left))
        add_action('moveRightAction', QAction(self.tr('&Right'), self, shortcut='D', triggered=self.move_right))
        add_action('expandAllChildrenAction', QAction(self.tr('&Expand all children'), self, shortcut='Shift+Right', triggered=self.expand_all_children))
        add_action('collapseAllChildrenAction', QAction(self.tr('&Collapse all children'), self, shortcut='Shift+Left', triggered=self.collapse_all_children))
        add_action('focusSearchBarAction', QAction(self.tr('&Focus search bar'), self, shortcut='Ctrl+F', triggered=self.focus_search_bar))
        add_action('colorGreenAction', QAction('&Green', self, shortcut='G', triggered=lambda: self.color_row('g')))
        add_action('colorYellowAction', QAction('&Yellow', self, shortcut='Y', triggered=lambda: self.color_row('y')))
        add_action('colorBlueAction', QAction('&Blue', self, shortcut='B', triggered=lambda: self.color_row('b')))
        add_action('colorRedAction', QAction('&Red', self, shortcut='R', triggered=lambda: self.color_row('r')))
        add_action('colorOrangeAction', QAction('&Orange', self, shortcut='O', triggered=lambda: self.color_row('o')))
        add_action('colorNoColorAction', QAction('&No color', self, shortcut='N', triggered=lambda: self.color_row('n')))
        add_action('toggleTaskAction', QAction(self.tr('&Toggle: note, todo, done'), self, shortcut='Space', triggered=self.toggle_task))
        add_action('openLinkAction', QAction(self.tr('&Open selected rows with URLs'), self, shortcut='L', triggered=self.open_links))
        add_action('renameTagAction', QAction(self.tr('&Rename tag'), self, triggered=lambda: RenameTagDialog(self, self.grid_holder().tag_view.currentIndex().data()).exec_()))
        add_action('editBookmarkAction', QAction(self.tr(EDIT_BOOKMARK), self, triggered=lambda: BookmarkDialog(self, index=self.grid_holder().bookmarks_view.selectionModel().currentIndex()).exec_()))
        add_action('moveBookmarkUpAction', QAction(self.tr('Move bookmark up'), self, shortcut='W', triggered=self.move_up))
        add_action('moveBookmarkDownAction', QAction(self.tr('Move bookmark down'), self, shortcut='S', triggered=self.move_down))
        add_action('deleteBookmarkAction', QAction(self.tr('Delete selected bookmarks'), self, shortcut='delete', triggered=self.removeBookmarkSelection))
        add_action('resetViewAction', QAction(self.tr('&Reset view'), self, shortcut='esc', triggered=self.reset_view))
        add_action('toggleProjectAction', QAction(self.tr('&Toggle: note, sequential project, parallel project, paused project'), self, shortcut='P', triggered=self.toggle_project))
        add_action('appendRepeatAction', QAction(self.tr('&Repeat'), self, triggered=self.append_repeat))
        add_action('undoAction', self.model.undoStack.createUndoAction(self))
        self.undoAction.setShortcut('CTRL+Z')
        add_action('redoAction', self.model.undoStack.createRedoAction(self))
        self.redoAction.setShortcut('CTRL+Shift+Z')

        self.fileMenu = self.menuBar().addMenu(self.tr('&File'))
        self.fileMenu.addAction(self.undoAction)
        self.fileMenu.addAction(self.redoAction)
        self.fileMenu.addAction(self.renameTagAction)
        self.fileMenu.addAction(self.editBookmarkAction)
        self.fileMenu.addAction(self.moveBookmarkUpAction)
        self.fileMenu.addAction(self.moveBookmarkDownAction)
        self.fileMenu.addAction(self.deleteBookmarkAction)

        self.structureMenu = self.menuBar().addMenu(self.tr('&Edit structure'))
        self.structureMenu.addAction(self.insertRowAction)
        self.structureMenu.addAction(self.insertChildAction)
        self.structureMenu.addAction(self.deleteSelectedRowsAction)

        self.moveMenu = self.structureMenu.addMenu(self.tr('&Move row'))
        self.moveMenu.addAction(self.moveUpAction)
        self.moveMenu.addAction(self.moveDownAction)
        self.moveMenu.addAction(self.moveLeftAction)
        self.moveMenu.addAction(self.moveRightAction)

        self.taskMenu = self.menuBar().addMenu(self.tr('&Edit row'))
        self.taskMenu.addAction(self.editRowAction)
        self.taskMenu.addAction(self.toggleTaskAction)
        self.taskMenu.addAction(self.toggleProjectAction)
        self.taskMenu.addAction(self.appendRepeatAction)
        self.colorMenu = self.taskMenu.addMenu(self.tr('&Color selected rows'))
        self.colorMenu.addAction(self.colorGreenAction)
        self.colorMenu.addAction(self.colorYellowAction)
        self.colorMenu.addAction(self.colorBlueAction)
        self.colorMenu.addAction(self.colorRedAction)
        self.colorMenu.addAction(self.colorOrangeAction)
        self.colorMenu.addAction(self.colorNoColorAction)

        self.viewMenu = self.menuBar().addMenu(self.tr('&View'))
        self.viewMenu.addAction(self.expandAllChildrenAction)
        self.viewMenu.addAction(self.collapseAllChildrenAction)
        self.viewMenu.addAction(self.splitWindowAct)
        self.viewMenu.addAction(self.unsplitWindowAct)
        self.viewMenu.addAction(self.focusSearchBarAction)
        self.viewMenu.addAction(self.openLinkAction)
        self.viewMenu.addAction(self.resetViewAction)

        self.bookmarkShortcutsMenu = self.menuBar().addMenu(self.tr('Bookmark shortcuts'))
        self.fill_bookmarkShortcutsMenu()

        self.helpMenu = self.menuBar().addMenu(self.tr('&Help'))
        self.helpMenu.addAction(self.aboutAct)

        # make single key menu shortcuts work on all operating systems http://thebreakfastpost.com/2014/06/03/single-key-menu-shortcuts-with-qt5-on-osx/
        self.signalMapper = QSignalMapper(self)  # This class collects a set of parameterless signals, and re-emits them with a string corresponding to the object that sent the signal.
        self.signalMapper.mapped[str].connect(self.evoke_singlekey_action)
        for action in self.actions:
            if action is self.moveBookmarkUpAction or \
                            action is self.moveBookmarkDownAction or \
                            action is self.deleteBookmarkAction:  # the shortcuts of these are already used
                continue
            keySequence = action.shortcut()
            if keySequence.count() == 1:
                shortcut = QShortcut(keySequence, self)
                shortcut.activated.connect(self.signalMapper.map)
                self.signalMapper.setMapping(shortcut, action.text())  # pass the action's name
                action.shortcut = QKeySequence()  # disable the old shortcut

        self.split_window()
        self.grid_holder().view.setFocus()
        self.updateActions()

        settings = QSettings()
        self.resize(settings.value('size', QSize(400, 400)))
        self.move(settings.value('pos', QPoint(200, 200)))

    def fill_bookmarkShortcutsMenu(self):
        self.bookmarkShortcutsMenu.clear()
        map = "function(doc) { emit(doc, null); }"  # all items
        res = self.bookmark_model.db.query(map)
        for row in res:
            db_item = self.bookmark_model.db[row.id]
            if row.id != item_model.ROOT_ID:
                self.bookmarkShortcutsMenu.addAction(QAction(db_item[item_model.TEXT], self, shortcut=db_item[item_model.SHORTCUT],
                                                             triggered=partial(self.filter_bookmark, row.id)))

    def get_db(self, db_name):
        if sys.platform == "darwin":
            subprocess.call(['/usr/bin/open', '/Applications/Apache CouchDB.app'])

        def get_create_db(new_db_name, db_url=None):

            if db_url:
                # todo check if couchdb was started, else exit loop and print exc
                # http://stackoverflow.com/questions/1378974/is-there-a-way-to-start-stop-linux-processes-with-python
                server = couchdb.Server(db_url)
            else:
                # todo check if couchdb was started, else exit loop and print exc
                server = couchdb.Server()
            try:
                # del server[new_db_name]
                return server, server[new_db_name]
            except couchdb.http.ResourceNotFound:
                new_db = server.create(new_db_name)
                new_db[item_model.ROOT_ID] = (item_model.NEW_DB_ITEM.copy())
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
                local_server, db = get_create_db(db_name)
                break
            except Exception as e:
                print("Trying to connect to database, but: " + str(e))
        return db

        server_url = 'http://192.168.178.42:5984/'
        # get_create_db(db_name, server_url)
        # local_server.replicate(db_name, server_url + db_name, continuous=True)
        # local_server.replicate(server_url + db_name, db_name, continuous=True)

    def grid_holder(self):  # returns focused grid_holder
        for i in range(0, self.mainSplitter.count()):
            if self.mainSplitter.widget(i).hasFocus():
                return self.mainSplitter.widget(i)
        return self.mainSplitter.widget(0)

    def setup_tag_model(self):
        self.grid_holder().tag_view.model().setupModelData(self.model.get_tags_set())

        def expand_node(parent_index, bool_expand):
            self.grid_holder().tag_view.setExpanded(parent_index, bool_expand)
            for row_num in range(self.grid_holder().tag_view.model().rowCount(parent_index)):
                child_index = self.grid_holder().tag_view.model().index(row_num, 0, parent_index)
                self.grid_holder().tag_view.setExpanded(parent_index, bool_expand)
                expand_node(child_index, bool_expand)

        expand_node(self.grid_holder().tag_view.selectionModel().currentIndex(), True)

    def closeEvent(self, event):
        settings = QSettings()
        settings.setValue('pos', self.pos())
        settings.setValue('size', self.size())
        self.model.updater.terminate()
        if sys.platform == "darwin":
            subprocess.call(['osascript', '-e', 'tell application "Apache CouchDB" to quit'])

        print(len(self.model.pointer_set))  # for debugging: is the len == #rows + root?

    def evoke_singlekey_action(self, action_name):  # fix shortcuts for mac
        for action in self.actions:
            if action.text() == action_name and action.isEnabled():
                action.trigger()
                break

    def updateActions(self):
        pass  # todo embed split action
        # todo rename tag action just when a tag is selected

    def toggle_sorting(self, column):
        if column == 0:
            self.grid_holder().view.sortByColumn(-1, Qt.AscendingOrder)
            self.grid_holder().view.setSortingEnabled(False)
            self.grid_holder().view.header().setSectionsClickable(True)
        else:
            if not self.grid_holder().view.isSortingEnabled():
                self.grid_holder().view.setSortingEnabled(True)

    def filter_tag(self):
        current_index = self.grid_holder().tag_view.selectionModel().currentIndex()
        current_tag = self.grid_holder().tag_view.model().data(current_index, tag_model.FULL_PATH)
        if current_tag is not None:
            search_bar_text = self.grid_holder().search_bar.text()
            new_text = re.sub(r':(\w|:)* ', current_tag + ' ', search_bar_text)  # matches a tag
            if ':' not in search_bar_text:
                new_text += ' ' + current_tag + ' '
            self.grid_holder().search_bar.setText(new_text)

    # set the search bar text according to the selected bookmark
    def filter_bookmark(self, item_id):
        new_search_bar_text = self.bookmark_model.db[item_id][item_model.SEARCH_TEXT]
        self.grid_holder().search_bar.setText(new_search_bar_text)
        # if shortcut was used: select bookmarks row for visual highlight
        index = self.bookmark_model.id_index_dict[item_id]
        self.set_selection(index, index)
        self.grid_holder().view.setFocus()

    def filter_bookmark_click(self, index):
        item_id = self.bookmark_model.getItem(index).id
        self.filter_bookmark(item_id)

    def filter(self, key, value):
        character = value[0]
        search_bar_text = self.grid_holder().search_bar.text()
        # 'all' selected: remove existing same filter
        if character == 'a':
            search_bar_text = re.sub(key + r'(<|>|=|\w|\d)* ', '', search_bar_text)
        else:
            # key is a compare operator
            if len(key) == 1:
                key += value[0]
                character = value[1:]
            # filter is already in the search bar: replace existing same filter
            if re.search(key[0] + r'(<|>|=)', search_bar_text):
                search_bar_text = re.sub(key[0] + r'(<|>|=|\w|\d)* ', key + character + ' ', search_bar_text)
            else:
                # add filter
                search_bar_text += ' ' + key + character + ' '
        self.grid_holder().search_bar.setText(search_bar_text)

    def db_change_signal(self, db_item, model):
        change_dict = db_item['change']
        my_edit = change_dict['user'] == socket.gethostname()
        method = change_dict['method']
        position = change_dict.get('position')
        count = change_dict.get('count')
        item_id = db_item['_id']

        # ignore cases when the 'update delete marker' change comes before the corresponding item is created
        if item_id not in model.id_index_dict:
            return
        index = QModelIndex(model.id_index_dict[item_id])

        item = model.getItem(index)

        if method == 'updated':
            item.text = db_item['text']
            item.date = db_item['date']
            item.estimate = db_item['estimate']
            if my_edit:
                self.set_selection(index, index)
            self.setup_tag_model()
            model.dataChanged.emit(index, index)

            # update next available task in a sequential project
            project_index = model.parent(index)
            project_parent_index = model.parent(project_index)
            available_index = model.get_next_available_task(project_index.row(), project_parent_index)
            if isinstance(available_index, QModelIndex):
                model.dataChanged.emit(available_index, available_index)

            # update the sort by changing the ordering
            sorted_column = self.grid_holder().view.header().sortIndicatorSection()
            if sorted_column == 1 or sorted_column == 2:
                order = self.grid_holder().view.header().sortIndicatorOrder()
                self.grid_holder().view.sortByColumn(sorted_column, 1 - order)
                self.grid_holder().view.sortByColumn(sorted_column, order)

        elif method == 'added':
            id_list = change_dict['id_list']
            model.beginInsertRows(index, position, position + len(id_list) - 1)
            for i, added_item_id in enumerate(id_list):
                item.add_child(position + i, added_item_id, index)
            model.endInsertRows()
            if my_edit:
                index_first_added = model.index(position, 0, index)
                index_last_added = model.index(position + len(id_list) - 1, 0, index)
                if not change_dict['set_edit_focus']:
                    self.set_selection(index_first_added, index_last_added)
                else:  # update selection_and_edit
                    if index_first_added.model() is self.model:
                        index_first_added = self.grid_holder().proxy.mapFromSource(index_first_added)
                        self.focusWidget().selectionModel().setCurrentIndex(index_first_added, QItemSelectionModel.ClearAndSelect)
                        self.focusWidget().edit(index_first_added)
                    else:  # bookmark
                        self.grid_holder().bookmarks_view.selectionModel().setCurrentIndex(index_first_added, QItemSelectionModel.ClearAndSelect)

        elif method == 'removed':
            model.beginRemoveRows(index, position, position + count - 1)
            item.childItems[position:position + count] = []
            model.endRemoveRows()
            if my_edit:
                # select the item below
                if position == len(item.childItems):  # there is no item below, so select the one above
                    position -= 1
                if len(item.childItems) > 0:
                    index_next_child = model.index(position, 0, index)
                    self.set_selection(index_next_child, index_next_child)
                else:  # all childs deleted, select parent
                    self.set_selection(index, index)

        elif method == 'moved_vertical':
            up_or_down = change_dict['up_or_down']
            if up_or_down == -1:
                # if we want to move several items up, we can move the item-above below the selection instead:
                item.childItems.insert(position + count - 1, item.childItems.pop(position - 1))
            elif up_or_down == +1:
                item.childItems.insert(position, item.childItems.pop(position + count))
            for i in range(count):
                index_moved_item = model.index(position + up_or_down + i, 0, index)  # calling index() refreshes the self.tree_model.id_index_dict of that item
                if i == 0:
                    index_first_moved_item = index_moved_item
            index_first_moved_item.model().layoutChanged.emit()
            if my_edit:
                self.set_selection(index_first_moved_item, index_moved_item)

        elif method == item_model.DELETED:
            if model.db[item_id][item_model.DELETED] == '':
                model.pointer_set.add(index.internalId())
            else:
                model.pointer_set.remove(index.internalId())
            self.setup_tag_model()


    def set_selection(self, index_from, index_to):
        if self.grid_holder().view.state() != QAbstractItemView.EditingState:
            if index_from.model() is self.model:
                index_to = self.grid_holder().proxy.mapFromSource(index_to)
                index_from = self.grid_holder().proxy.mapFromSource(index_from)
            else:
                self.grid_holder().bookmarks_view.setFocus()
            index_from = index_from.sibling(index_from.row(), 0)
            index_to = index_to.sibling(index_to.row(), self.model.columnCount() - 1)
            self.focusWidget().selectionModel().setCurrentIndex(index_from, QItemSelectionModel.ClearAndSelect)  # todo not always correct index when moving
            self.focusWidget().selectionModel().select(QItemSelection(index_from, index_to), QItemSelectionModel.ClearAndSelect)

    def reset_view(self):
        self.grid_holder().task.comboBox.setCurrentIndex(0)
        self.grid_holder().estimate.comboBox.setCurrentIndex(0)
        self.grid_holder().color.comboBox.setCurrentIndex(0)
        self.grid_holder().search_bar.setText('')
        top_most_index = self.grid_holder().proxy.index(0, 0, QModelIndex())
        self.set_selection(top_most_index, top_most_index)
        self.grid_holder().bookmarks_view.selectionModel().setCurrentIndex(QModelIndex(), QItemSelectionModel.ClearAndSelect)
        self.grid_holder().view.setRootIndex(QModelIndex())
        self.grid_holder().focus_button.setChecked(False)

    def search(self, search_text):
        self.grid_holder().proxy.filter = search_text
        self.grid_holder().proxy.invalidateFilter()
        # deselect tag if user changes the search string
        selected_tags = self.grid_holder().tag_view.selectionModel().selectedRows()
        if len(selected_tags) > 0 and selected_tags[0].data() not in search_text:
            self.grid_holder().tag_view.selectionModel().setCurrentIndex(QModelIndex(), QItemSelectionModel.Clear)
            # changing dropdown index accordingly is not that easy, because changing it fires "color_clicked" which edits search bar...


    def expand_node(self, parent_index, bool_expand):
        self.grid_holder().view.setExpanded(parent_index, bool_expand)
        for row_num in range(self.grid_holder().proxy.rowCount(parent_index)):
            child_index = self.grid_holder().proxy.index(row_num, 0, parent_index)
            self.grid_holder().view.setExpanded(parent_index, bool_expand)
            self.expand_node(child_index, bool_expand)

    def rename_tag(self, tag, new_name):
        map = "function(doc) {{ \
                    if (doc.text.indexOf('{}') != -1 ) \
                        emit(doc, null); \
                }}".format(tag)
        res = self.model.db.query(map)
        for row in res:
            db_item = self.model.db[row.id]
            db_item['text'] = db_item['text'].replace(tag, new_name)
            db_item['change'] = dict(method='updated', user=socket.gethostname())
            self.model.db[row.id] = db_item


    def open_rename_tag_contextmenu(self, point):
        index = self.grid_holder().tag_view.indexAt(point)
        if not index.isValid(): # show context menu only when clicked on an item, not when clicked on empty space
            return
        menu = QMenu()
        renameTagAction = menu.addAction(self.tr("Rename tag"))
        action = menu.exec_(self.grid_holder().tag_view.viewport().mapToGlobal(point))
        if action is not renameTagAction:
            return
        tag = index.data()
        RenameTagDialog(self, tag).exec_()

    def open_edit_bookmark_contextmenu(self, point):
        index = self.grid_holder().bookmarks_view.indexAt(point)
        if not index.isValid():
            return
        menu = QMenu()
        editBookmarkAction = menu.addAction(self.tr(EDIT_BOOKMARK))
        deleteBookmarkAction = menu.addAction(self.tr('Delete bookmark'))
        action = menu.exec_(self.grid_holder().bookmarks_view.viewport().mapToGlobal(point))
        if action is editBookmarkAction:
            BookmarkDialog(self, index=index).exec_()
        elif action is deleteBookmarkAction:
            self.removeBookmarkSelection()

    # structure menu actions

    def expand_all_children(self):
        self.expand_node(self.grid_holder().view.selectionModel().selectedRows()[0], True)

    def collapse_all_children(self):
        self.expand_node(self.grid_holder().view.selectionModel().selectedRows()[0], False)

    def move_up(self):
        indexes = self.focusWidget().selectionModel().selectedRows()
        indexes[0].model().move_vertical(indexes, -1)

    def move_down(self):
        indexes = self.focusWidget().selectionModel().selectedRows()
        indexes[0].model().move_vertical(indexes, +1)

    def move_left(self):
        if self.focusWidget() is self.grid_holder().view:
            self.grid_holder().proxy.move_horizontal(self.grid_holder().view.selectionModel().selectedRows(), -1)

    def move_right(self):
        if self.focusWidget() is self.grid_holder().view:
            self.grid_holder().proxy.move_horizontal(self.grid_holder().view.selectionModel().selectedRows(), +1)

    def insert_child(self):
        index = self.grid_holder().view.selectionModel().currentIndex()
        if self.grid_holder().view.state() == QAbstractItemView.EditingState:
            # commit data by changing the current selection # todo doku
            self.grid_holder().view.selectionModel().currentChanged.emit(index, index)
        self.grid_holder().proxy.insertRow(0, index)

    def insert_row(self):
        index = self.grid_holder().view.selectionModel().currentIndex()
        if self.grid_holder().view.hasFocus():
            self.grid_holder().proxy.insertRow(index.row() + 1, index.parent())
        elif self.grid_holder().view.state() == QAbstractItemView.EditingState:
            # commit data by changing the current selection
            self.grid_holder().view.selectionModel().currentChanged.emit(index, index)

    def removeSelection(self):
        indexes = self.focusWidget().selectionModel().selectedRows()
        self.grid_holder().proxy.removeRows(indexes)


    def removeBookmarkSelection(self):
        self.grid_holder().bookmarks_view.setFocus()
        indexes = self.focusWidget().selectionModel().selectedRows()
        self.bookmark_model.insert_remove_rows(indexes=indexes)

    # task menu actions

    def edit_row(self):
        current_index = self.grid_holder().view.selectionModel().currentIndex()
        if self.grid_holder().view.state() == QAbstractItemView.EditingState:  # change column with tab key
            next_column_number = (current_index.column() + 1) % 3
            sibling_index = current_index.sibling(current_index.row(), next_column_number)
            self.grid_holder().view.selectionModel().setCurrentIndex(sibling_index, QItemSelectionModel.ClearAndSelect)
            self.grid_holder().view.edit(sibling_index)
        elif self.grid_holder().view.hasFocus():
            self.grid_holder().view.edit(current_index)
        else:
            self.grid_holder().view.setFocus()

    def toggle_task(self):
        if self.grid_holder().view.hasFocus():
            for row_index in self.grid_holder().view.selectionModel().selectedRows():
                self.grid_holder().proxy.toggle_task(row_index)

    def toggle_project(self):
        if self.grid_holder().view.hasFocus():
            for row_index in self.grid_holder().view.selectionModel().selectedRows():
                self.grid_holder().proxy.toggle_project(row_index)

    def append_repeat(self):
        current_index = self.grid_holder().view.selectionModel().currentIndex()
        self.grid_holder().proxy.setData(current_index.data() + ' repeat=1w', index=current_index)
        self.edit_row()

    def color_row(self, color_character):
        if self.grid_holder().view.hasFocus():  # todo not needed if action is only available when row selected
            for row_index in self.grid_holder().view.selectionModel().selectedRows():
                self.grid_holder().proxy.setData(item_model.CHAR_QCOLOR_DICT[color_character], index=row_index, field='color')

    # view menu actions

    def focus_search_bar(self):
        self.grid_holder().search_bar.setFocus()

    def focus(self):
        search_bar_text = self.grid_holder().search_bar.text()
        idx = self.grid_holder().view.selectionModel().currentIndex()
        item_id = idx.model().get_db_item_id(idx)
        self.grid_holder().search_bar.setText(search_bar_text + ' ' + item_model.FOCUS + '=' + item_id)
        self.grid_holder().view.setRootIndex(idx)

    def open_links(self):
        for row_index in self.grid_holder().view.selectionModel().selectedRows():
            url_regex = r"""(?i)\b((?:https?:(?:/{1,3}|[a-z0-9%])|[a-z0-9.\-]+[.](?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)/)(?:[^\s()<>{}\[\]]+|\([^\s()]*?\([^\s()]+\)[^\s()]*?\)|\([^\s]+?\))+(?:\([^\s()]*?\([^\s()]+\)[^\s()]*?\)|\([^\s]+?\)|[^\s`!()\[\]{};:'".,<>?«»“”‘’])|(?:(?<!@)[a-z0-9]+(?:[.\-][a-z0-9]+)*[.](?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)\b/?(?!@)))"""  # source: http://daringfireball.net/2010/07/improved_regex_for_matching_urls
            url_list = re.findall(url_regex, row_index.data())
            for url in url_list:
                if not url.startswith('http://'):
                    url = 'http://' + url
                webbrowser.open(url)

    def split_window(self):  # creates the view, too
        grid_holder = QWidget()

        grid_holder.bookmarks_view = QTreeView()
        grid_holder.bookmarks_view.setModel(self.bookmark_model)
        grid_holder.bookmarks_view.setItemDelegate(item_model.BookmarkDelegate(self, self.bookmark_model))
        grid_holder.bookmarks_view.clicked.connect(self.filter_bookmark_click)
        grid_holder.bookmarks_view.setContextMenuPolicy(Qt.CustomContextMenu)
        grid_holder.bookmarks_view.customContextMenuRequested.connect(self.open_edit_bookmark_contextmenu)
        grid_holder.bookmarks_view.hideColumn(1)
        grid_holder.bookmarks_view.hideColumn(2)

        grid_holder.root_view = QTreeView()
        grid_holder.root_view.setModel(self.model)
        # grid_holder.root_view.clicked.connect(self.filter_bookmark) # todo
        grid_holder.root_view.setHeader(CustomHeaderView('Root'))
        grid_holder.root_view.hideColumn(1)
        grid_holder.root_view.hideColumn(2)

        grid_holder.view = QTreeView()
        size_policy_view = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        size_policy_view.setHorizontalStretch(2)  # 2/3
        grid_holder.view.setSizePolicy(size_policy_view)
        grid_holder.view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        grid_holder.proxy = item_model.FilterProxyModel()
        grid_holder.proxy.setSourceModel(self.model)
        grid_holder.proxy.setDynamicSortFilter(True)  # re-sort and re-filter data whenever the original model changes
        grid_holder.proxy.filter = ''
        grid_holder.view.setModel(grid_holder.proxy)
        grid_holder.view.setItemDelegate(item_model.Delegate(self, grid_holder.proxy))
        grid_holder.view.selectionModel().selectionChanged.connect(self.updateActions)
        grid_holder.view.setColumnWidth(0, 300)  # todo update ratio when window size changes
        grid_holder.view.setColumnWidth(1, 100)
        grid_holder.view.header().sectionClicked[int].connect(self.toggle_sorting)
        grid_holder.view.header().setSectionsClickable(True)

        grid_holder.search_bar = MyQLineEdit(self)
        grid_holder.search_bar.textChanged[str].connect(self.search)
        grid_holder.search_bar.setPlaceholderText(self.tr('Filter'))

        bookmark_button = QPushButton()
        bookmark_button.setIcon(QIcon(':/star'))
        bookmark_button.setStyleSheet('QPushButton {\
            margin-top: 11px;\
            width: 20px;\
            height: 20px;\
            padding: 2px; }')
        bookmark_button.clicked.connect(lambda: BookmarkDialog(self, search_bar_text=grid_holder.search_bar.text()).exec_())

        search_holder = QWidget()
        layout = QBoxLayout(QBoxLayout.LeftToRight)
        layout.addWidget(grid_holder.search_bar)
        layout.addWidget(bookmark_button)
        layout.setContentsMargins(0, 0, 0, 0)
        search_holder.setLayout(layout)

        grid_holder.task = LabelledDropDown(self, 't=', self.tr('Task:'), self.tr('all'), item_model.NOTE, item_model.TASK, item_model.DONE_TASK)
        grid_holder.estimate = LabelledDropDown(self, 'e', self.tr('Estimate:'), self.tr('all'), self.tr('<20'), self.tr('=60'), self.tr('>60'))
        grid_holder.color = LabelledDropDown(self, 'c=', self.tr('Color:'), self.tr('all'), self.tr('green'), self.tr('yellow'), self.tr('blue'), self.tr('red'), self.tr('orange'), self.tr('no color'))

        grid_holder.focus_button = QPushButton(item_model.FOCUS_TEXT)
        grid_holder.focus_button.setCheckable(True)
        grid_holder.focus_button.setStyleSheet('QPushButton { padding: 4px; }')
        grid_holder.focus_button.clicked.connect(self.focus)

        grid_holder.tag_view = QTreeView()
        grid_holder.tag_view.setContextMenuPolicy(Qt.CustomContextMenu)
        grid_holder.tag_view.customContextMenuRequested.connect(self.open_rename_tag_contextmenu)
        size_policy_tag_view = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        size_policy_tag_view.setHorizontalStretch(1 / 2)  # smaller
        size_policy_tag_view.setVerticalStretch(1)  # bigger
        grid_holder.tag_view.setSizePolicy(size_policy_tag_view)
        grid_holder.tag_view.setModel(tag_model.TagModel())
        grid_holder.tag_view.selectionModel().selectionChanged.connect(self.filter_tag)

        grid = QGridLayout()
        grid.setSpacing(11)  # space between contained widgets
        grid.setContentsMargins(0, 0, 11, 0)  # left, top, right, bottom

        grid.addWidget(grid_holder.bookmarks_view, 0, 0, 4, 1)  # fromRow, fromColumn, rowSpan, columnSpan.
        grid.addWidget(grid_holder.root_view, 4, 0, 4, 1)  # fromRow, fromColumn, rowSpan, columnSpan.

        grid.addWidget(grid_holder.view, 0, 1, 8, 1)  # fromRow, fromColumn, rowSpan, columnSpan.

        grid.addWidget(search_holder, 0, 2, 1, 1)
        grid.addWidget(QLabel(self.tr('')), 1, 2, 1, 1, Qt.AlignCenter)  # or QSpacerItem(40, 20, QSizePolicy::Expanding, QSizePolicy::Minimum);
        grid.addWidget(QLabel(self.tr('Add filters:')), 2, 2, 1, 1, Qt.AlignCenter)
        grid.addWidget(grid_holder.task, 3, 2, 1, 1)
        grid.addWidget(grid_holder.estimate, 4, 2, 1, 1)
        grid.addWidget(grid_holder.color, 5, 2, 1, 1)
        grid.addWidget(grid_holder.focus_button, 6, 2, 1, 1, Qt.AlignLeft)
        grid.addWidget(grid_holder.tag_view, 7, 2, 1, 1)
        grid_holder.setLayout(grid)
        self.mainSplitter.addWidget(grid_holder)
        self.setup_tag_model()

        grid_holder.view.setFocus()
        top_most_index = self.grid_holder().proxy.index(0, 0, QModelIndex())
        self.set_selection(top_most_index, top_most_index)
        self.grid_holder().bookmarks_view.selectionModel().setCurrentIndex(QModelIndex(), QItemSelectionModel.ClearAndSelect)

        self.unsplitWindowAct.setEnabled(True)


    def unsplit_window(self):
        index_last_widget = self.mainSplitter.count() - 1
        self.mainSplitter.widget(index_last_widget).setParent(None)
        if self.mainSplitter.count() == 1:
            self.unsplitWindowAct.setEnabled(False)

    # help menu actions

    def about(self):
        QMessageBox.about(self, self.tr('About'), self.tr('teeeext'))


class MyQLineEdit(QLineEdit):
    def __init__(self, main):
        super(QLineEdit, self).__init__()
        self.main = main
        self.setStyleSheet('QLineEdit {\
        margin-top: 11px;\
        padding-left: 20px;\
        padding-top: 3px;\
        padding-right: 3px;\
        padding-bottom: 3px;\
        background: url(:/search);\
        background-position: left;\
        background-repeat: no-repeat;\
        border-radius: 3px;\
        height: 22px;}')

    def keyPressEvent(self, event):
        # arror key down: select first child
        if event.key() == Qt.Key_Down:
            index = self.main.grid_holder().proxy.index(0, 0, QModelIndex())
            self.main.set_selection(index, index)
            self.main.focusNextChild()
        else:
            QLineEdit.keyPressEvent(self, event)


class BookmarkDialog(QDialog):
    # init it with either search_bar_text or index set
    # search_bar_text is set: create new bookmark
    # index is set: edit existing bookmark
    def __init__(self, parent, search_bar_text=None, index=None):
        super(BookmarkDialog, self).__init__(parent)
        self.parent = parent
        self.search_bar_text = search_bar_text
        self.index = index
        if index is not None:
            item = parent.bookmark_model.getItem(index)
            db_item = parent.bookmark_model.db[item.id]

        name = '' if index is None else db_item[item_model.TEXT]
        self.name_edit = QLineEdit(name)

        if search_bar_text is None:
            search_bar_text = db_item[item_model.SEARCH_TEXT]
        self.search_bar_text_edit = QLineEdit(search_bar_text)

        shortcut = '' if index is None else db_item[item_model.SHORTCUT]
        self.shortcut_edit = QLineEdit(shortcut)
        self.shortcut_edit.setPlaceholderText('e.g. Ctrl+1')

        buttonBox = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Cancel)

        grid = QGridLayout()
        grid.addWidget(QLabel('Bookmark name:'), 0, 0)  # row, column
        grid.addWidget(QLabel('Saved filters:'), 1, 0)
        grid.addWidget(QLabel('Shortcut (optional):'), 2, 0)
        grid.addWidget(self.name_edit, 0, 1)
        grid.addWidget(self.search_bar_text_edit, 1, 1)
        grid.addWidget(self.shortcut_edit, 2, 1)
        grid.addWidget(buttonBox, 3, 0, 1, 2, Qt.AlignRight)  # fromRow, fromColumn, rowSpan, columnSpan.
        self.setLayout(grid)
        buttonBox.button(QDialogButtonBox.Apply).clicked.connect(self.apply)
        buttonBox.button(QDialogButtonBox.Cancel).clicked.connect(self.reject)
        if self.index is None:
            self.setWindowTitle("Bookmark current filters")
        else:
            self.setWindowTitle("Edit bookmark")

    def apply(self):
        if self.index is None:
            new_item_position = len(self.parent.bookmark_model.rootItem.childItems)
            self.parent.bookmark_model.insert_remove_rows(new_item_position, item_model.ROOT_ID)
            children_list = self.parent.bookmark_model.db[item_model.ROOT_ID]['children'].split()
            item_id = children_list[-1]
        else:
            item_id = self.parent.bookmark_model.get_db_item_id(self.index)
        self.parent.bookmark_model.setData(self.name_edit.text(), item_id=item_id, column=0, field='text')
        self.parent.bookmark_model.setData(self.search_bar_text_edit.text(), item_id=item_id, column=0, field=item_model.SEARCH_TEXT)
        self.parent.bookmark_model.setData(self.shortcut_edit.text(), item_id=item_id, column=0, field=item_model.SHORTCUT)
        self.parent.fill_bookmarkShortcutsMenu()
        super(BookmarkDialog, self).accept()


class RenameTagDialog(QDialog):
    def __init__(self, parent, tag):
        super(RenameTagDialog, self).__init__(parent)
        self.parent = parent
        self.tag = tag
        self.line_edit = QLineEdit(tag)
        buttonBox = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Cancel)

        grid = QGridLayout()
        grid.addWidget(self.line_edit, 0, 0)
        grid.addWidget(buttonBox, 1, 0)
        self.setLayout(grid)
        buttonBox.button(QDialogButtonBox.Apply).clicked.connect(self.apply)
        buttonBox.button(QDialogButtonBox.Cancel).clicked.connect(self.reject)
        self.setWindowTitle("Enter new name:")

    def apply(self):
        self.parent.rename_tag(self.tag, self.line_edit.text())
        super(RenameTagDialog, self).accept()


class LabelledDropDown(QWidget):
    """
    parameter: main_window, labelText, *item_names
    first item will be checked by default
    """

    def __init__(self, main_window, key, labelText, *item_names, position=Qt.AlignLeft):
        super(LabelledDropDown, self).__init__(main_window)
        layout = QBoxLayout(QBoxLayout.LeftToRight if position == Qt.AlignLeft else QBoxLayout.TopToBottom)
        self.label = QLabel(labelText)
        layout.addWidget(self.label)
        self.comboBox = QComboBox()
        self.comboBox.addItems(item_names)
        self.comboBox.currentIndexChanged[str].connect(lambda: main_window.filter(key, self.comboBox.currentText()))
        layout.addWidget(self.comboBox, Qt.AlignLeft)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)


class LabelledButtonGroup(QWidget):
    """
    parameter: labelText, *button_names
    first button will be checked by default
    """

    def __init__(self, labelText, *button_names, position=Qt.AlignLeft, parent=None):
        super(LabelledButtonGroup, self).__init__(parent)
        layout = QBoxLayout(QBoxLayout.LeftToRight if position == Qt.AlignLeft else QBoxLayout.TopToBottom)
        self.label = QLabel(labelText)
        layout.addWidget(self.label)
        buttonGroup = QButtonGroup()
        for idx, button_name in enumerate(button_names):
            button = QRadioButton(button_name)
            button.setCheckable(True)
            if idx == 0:
                button.setChecked(True)  # check first button
            buttonGroup.addButton(button)
            layout.addWidget(button)
        self.setLayout(layout)


# changes the header text
class CustomHeaderView(QHeaderView):
    def __init__(self, text):
        super(CustomHeaderView, self).__init__(Qt.Horizontal)
        self.setSectionResizeMode(QHeaderView.Stretch)
        self.text = text

    def paintSection(self, painter, rect, logicalIndex):
        opt = QStyleOptionHeader()
        opt.rect = rect
        opt.text = self.text
        QApplication.style().drawControl(QStyle.CE_Header, opt, painter, self)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setApplicationName(QApplication.translate('main', 'TreeNote'))
    app.setWindowIcon(QIcon(':/icon.png'))

    app.setStyle("Fusion")
    dark_palette = QPalette()
    dark_palette.setColor(QPalette.Window, item_model.FOREGROUND_GRAY)
    dark_palette.setColor(QPalette.WindowText, item_model.TEXT_GRAY)
    dark_palette.setColor(QPalette.Base, item_model.BACKGROUND_GRAY)
    dark_palette.setColor(QPalette.AlternateBase, item_model.FOREGROUND_GRAY)
    dark_palette.setColor(QPalette.ToolTipBase, item_model.TEXT_GRAY)
    dark_palette.setColor(QPalette.ToolTipText, item_model.TEXT_GRAY)
    dark_palette.setColor(QPalette.Text, item_model.TEXT_GRAY)
    dark_palette.setColor(QPalette.Button, item_model.FOREGROUND_GRAY)
    dark_palette.setColor(QPalette.ButtonText, item_model.TEXT_GRAY)
    dark_palette.setColor(QPalette.BrightText, Qt.red)
    dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.Highlight, item_model.SELECTION_GRAY)
    dark_palette.setColor(QPalette.HighlightedText, item_model.TEXT_GRAY)
    app.setPalette(dark_palette)
    app.setStyleSheet('QToolTip { color: #ffffff; background-color: #2a82da; border: 1px solid white; }\
                      QHeaderView::section { padding-bottom: 5px;  padding-top: 2px;}')

    font = QFont('Arial', 16)
    app.setFont(font);

    form = MainWindow()
    form.show()
    app.exec_()