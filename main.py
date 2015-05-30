# -*- coding: utf-8 -*-
from PyQt5 import QtWidgets
import sys
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import qrc_resources
import model
import server_model
import tag_model
import socket
import webbrowser
import re
import time
import couchdb
from functools import partial

EDIT_BOOKMARK = 'Edit bookmark'
EDIT_QUICKLINK = 'Edit quick link shortcut'
EXPANDED_ITEMS = 'EXPANDED_ITEMS'
EXPANDED_QUICKLINKS = 'EXPANDED_QUICKLINKS'
SELECTED_ID = 'SELECTED_ID'
CREATE_DB = 'Create bookmark to a server database'
EDIT_DB = 'Edit selected database bookmark'
DEL_DB = 'Delete selected database bookmark'


class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()

        app.setStyle("Fusion")
        self.light_palette = app.palette()

        self.dark_palette = QPalette()
        self.dark_palette.setColor(QPalette.Window, model.FOREGROUND_GRAY)
        self.dark_palette.setColor(QPalette.WindowText, model.TEXT_GRAY)
        self.dark_palette.setColor(QPalette.Base, model.BACKGROUND_GRAY)
        self.dark_palette.setColor(QPalette.AlternateBase, model.FOREGROUND_GRAY)
        self.dark_palette.setColor(QPalette.ToolTipBase, model.TEXT_GRAY)
        self.dark_palette.setColor(QPalette.ToolTipText, model.TEXT_GRAY)
        self.dark_palette.setColor(QPalette.Text, model.TEXT_GRAY)
        self.dark_palette.setColor(QPalette.Button, model.FOREGROUND_GRAY)
        self.dark_palette.setColor(QPalette.ButtonText, model.TEXT_GRAY)
        self.dark_palette.setColor(QPalette.BrightText, Qt.red)
        self.dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
        self.dark_palette.setColor(QPalette.Highlight, model.SELECTION_GRAY)
        self.dark_palette.setColor(QPalette.HighlightedText, model.TEXT_GRAY)
        self.dark_palette.setColor(QPalette.ToolTipBase, model.FOREGROUND_GRAY)
        self.dark_palette.setColor(QPalette.ToolTipText, model.TEXT_GRAY)

        app.setPalette(self.dark_palette)

        font = QFont('Arial', 16)
        app.setFont(font)

        self.expanded_id_list = []  # for restoring the expanded state after a search
        self.removed_id_expanded_state_dict = {}  # remember expanded state when moving horizontally (removing then adding at other place)
        self.old_search_text = ''  # used to detect if user leaves "just focused" state. when that's the case, expanded states are saved

        self.server_model = server_model.ServerModel()

        # load databases
        settings = QSettings()
        servers = settings.value('databases', [('Local', '', 'local'), ('Jans Raspberry', 'http://192.168.178.42:5984/', 'jans_raspberry')])  # second value is loaded, if nothing was saved before in the settings
        for bookmark_name, url, db_name in servers:
            new_server = server_model.Server(bookmark_name, url, db_name)
            new_server.model.db_change_signal[dict, QAbstractItemModel].connect(self.db_change_signal)
            self.server_model.add_server(new_server)

        self.item_model = self.server_model.servers[0].model

        self.bookmark_model = model.TreeModel(server_model.get_db('', 'local_bookmarks'), header_list=['Bookmarks'])
        self.bookmark_model.db_change_signal[dict, QAbstractItemModel].connect(self.db_change_signal)

        self.mainSplitter = QSplitter(Qt.Horizontal)
        self.mainSplitter.setHandleWidth(0)  # thing to grab the splitter

        # first column

        self.servers_view = QTreeView()
        self.servers_view.setModel(self.server_model)
        self.servers_view.clicked.connect(self.change_active_database)
        self.servers_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.servers_view.customContextMenuRequested.connect(self.open_edit_server_contextmenu)
        top_most_index = self.server_model.index(0, 0, QModelIndex())
        self.servers_view.selectionModel().setCurrentIndex(top_most_index, QItemSelectionModel.ClearAndSelect)

        self.quicklinks_view = QTreeView()
        self.quicklinks_view.setModel(self.item_model)
        self.quicklinks_view.setItemDelegate(model.BookmarkDelegate(self, self.item_model))
        self.quicklinks_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.quicklinks_view.customContextMenuRequested.connect(self.open_edit_shortcut_contextmenu)
        self.quicklinks_view.clicked.connect(self.focus_index)
        self.quicklinks_view.setHeader(CustomHeaderView('Quick links'))
        self.quicklinks_view.header().setToolTip('Focus on the clicked row')
        self.quicklinks_view.hideColumn(1)
        self.quicklinks_view.hideColumn(2)
        quicklinks_holder = QWidget()  # needed to add space
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 11, 0, 0)  # left, top, right, bottom
        layout.addWidget(self.quicklinks_view)
        quicklinks_holder.setLayout(layout)

        self.bookmarks_view = QTreeView()
        self.bookmarks_view.setModel(self.bookmark_model)
        self.bookmarks_view.setItemDelegate(model.BookmarkDelegate(self, self.bookmark_model))
        self.bookmarks_view.clicked.connect(self.filter_bookmark_click)
        self.bookmarks_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.bookmarks_view.customContextMenuRequested.connect(self.open_edit_bookmark_contextmenu)
        self.bookmarks_view.hideColumn(1)
        self.bookmarks_view.hideColumn(2)
        bookmarks_holder = QWidget()  # needed to add space
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 11, 0, 0)  # left, top, right, bottom
        layout.addWidget(self.bookmarks_view)
        bookmarks_holder.setLayout(layout)

        self.first_column_splitter = QSplitter(Qt.Vertical)
        self.first_column_splitter.setHandleWidth(0)
        self.first_column_splitter.addWidget(self.servers_view)
        self.first_column_splitter.addWidget(quicklinks_holder)
        self.first_column_splitter.addWidget(bookmarks_holder)
        self.first_column_splitter.setContentsMargins(0, 11, 6, 0)  # left, top, right, bottom

        # second column

        self.item_views_splitter = QSplitter(Qt.Horizontal)
        self.item_views_splitter.setHandleWidth(0)  # thing to grab the splitter

        # third column

        filter_label = QLabel(self.tr('ADD FILTERS'))

        def init_dropdown(key, *item_names):
            comboBox = QComboBox()
            comboBox.addItems(item_names)
            comboBox.currentIndexChanged[str].connect(lambda: self.filter(key, comboBox.currentText()))
            return comboBox

        self.task_dropdown = init_dropdown('t=', self.tr('all'), model.NOTE, model.TASK, model.DONE_TASK)
        self.estimate_dropdown = init_dropdown('e', self.tr('all'), self.tr('<20'), self.tr('=60'), self.tr('>60'))
        self.color_dropdown = init_dropdown('c=', self.tr('all'), self.tr('green'), self.tr('yellow'), self.tr('blue'), self.tr('red'), self.tr('orange'), self.tr('no color'))

        self.flattenViewCheckBox = QCheckBox('Flatten view')
        self.flattenViewCheckBox.clicked.connect(self.filter_flatten_view)
        self.hideFutureStartdateCheckBox = QCheckBox('Hide rows with future start date')
        self.hideFutureStartdateCheckBox.clicked.connect(self.filter_hide_future_startdate)
        self.showOnlyStartdateCheckBox = QCheckBox('Show only rows with a start date')
        self.showOnlyStartdateCheckBox.clicked.connect(self.filter_show_only_startdate)

        bookmarks_holder = QWidget()  # needed to add space
        layout = QGridLayout()
        layout.setContentsMargins(0, 4, 6, 0)  # left, top, right, bottom
        layout.addWidget(filter_label, 0, 0, 1, 2)  # fromRow, fromColumn, rowSpan, columnSpan
        layout.addWidget(QLabel('Tasks:'), 1, 0, 1, 1)
        layout.addWidget(self.task_dropdown, 1, 1, 1, 1)
        layout.addWidget(QLabel('Estimate:'), 2, 0, 1, 1)
        layout.addWidget(self.estimate_dropdown, 2, 1, 1, 1)
        layout.addWidget(QLabel('Color:'), 3, 0, 1, 1)
        layout.addWidget(self.color_dropdown, 3, 1, 1, 1)
        layout.addWidget(self.flattenViewCheckBox, 4, 0, 1, 2)
        layout.addWidget(self.hideFutureStartdateCheckBox, 5, 0, 1, 2)
        layout.addWidget(self.showOnlyStartdateCheckBox, 6, 0, 1, 2)
        layout.setColumnStretch(1, 10)
        bookmarks_holder.setLayout(layout)

        self.tag_view = QTreeView()
        self.tag_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tag_view.customContextMenuRequested.connect(self.open_rename_tag_contextmenu)
        # self.tag_view.setSizePolicy(QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding))  # horizontal, vertical
        self.tag_view.setModel(tag_model.TagModel())
        self.tag_view.selectionModel().selectionChanged.connect(self.filter_tag)

        third_column = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(6, 6, 0, 0)  # left, top, right, bottom
        layout.addWidget(bookmarks_holder)
        layout.addWidget(self.tag_view)
        third_column.setLayout(layout)

        # add columns to main

        self.mainSplitter.addWidget(self.first_column_splitter)
        self.mainSplitter.addWidget(self.item_views_splitter)
        self.mainSplitter.addWidget(third_column)
        self.mainSplitter.setStretchFactor(0, 2)  # first column has a share of 2
        self.mainSplitter.setStretchFactor(1, 6)
        self.mainSplitter.setStretchFactor(2, 2)
        self.setCentralWidget(self.mainSplitter)

        self.actions = list()

        def add_action(name, qaction):
            setattr(self, name, qaction)
            self.actions.append(qaction)

        add_action('addDatabaseAct', QAction(self.tr(CREATE_DB), self, triggered=lambda: DatabaseDialog(self).exec_()))
        add_action('deleteDatabaseAct', QAction(self.tr(DEL_DB), self, triggered=lambda: self.server_model.delete_server(self.servers_view.selectionModel().currentIndex())))
        add_action('editDatabaseAct', QAction(self.tr(EDIT_DB), self, triggered=lambda: DatabaseDialog(self, index=self.servers_view.selectionModel().currentIndex()).exec_()))
        add_action('settingsAct', QAction(self.tr('Preferences'), self, shortcut='Ctrl+,', triggered=lambda: SettingsDialog(self).exec_()))
        add_action('aboutAct', QAction(self.tr('&About'), self, triggered=self.about))
        # add_action('unsplitWindowAct', QAction(self.tr('&Unsplit window'), self, shortcut='Ctrl+Shift+S', triggered=self.unsplit_window))
        # add_action('splitWindowAct', QAction(self.tr('&Split window'), self, shortcut='Ctrl+S', triggered=self.split_window))
        add_action('editRowAction', QAction(self.tr('&Edit row'), self, shortcut='Tab', triggered=self.edit_row))
        add_action('deleteSelectedRowsAction', QAction(self.tr('&Delete selected rows'), self, shortcut='delete', triggered=self.removeSelection))
        add_action('insertRowAction', QAction(self.tr('&Insert row'), self, shortcut='Return', triggered=self.insert_row))
        add_action('insertChildAction', QAction(self.tr('&Insert child'), self, shortcut='Shift+Return', triggered=self.insert_child))
        add_action('moveUpAction', QAction(self.tr('&Up'), self, shortcut='W', triggered=self.move_up))
        add_action('moveDownAction', QAction(self.tr('&Down'), self, shortcut='S', triggered=self.move_down))
        add_action('moveLeftAction', QAction(self.tr('&Left'), self, shortcut='A', triggered=self.move_left))
        add_action('moveRightAction', QAction(self.tr('&Right'), self, shortcut='D', triggered=self.move_right))
        add_action('expandAllChildrenAction', QAction(self.tr('&Expand all children'), self, shortcut='Alt+Right', triggered=self.expand_all_children_of_selected_rows))
        add_action('collapseAllChildrenAction', QAction(self.tr('&Collapse all children'), self, shortcut='Alt+Left', triggered=self.collapse_all_children_of_selected_rows))
        add_action('focusSearchBarAction', QAction(self.tr('&Focus search bar'), self, shortcut='Ctrl+F', triggered=lambda: self.focused_column().search_bar.setFocus()))
        add_action('colorGreenAction', QAction('&Green', self, shortcut='G', triggered=lambda: self.color_row('g')))
        add_action('colorYellowAction', QAction('&Yellow', self, shortcut='Y', triggered=lambda: self.color_row('y')))
        add_action('colorBlueAction', QAction('&Blue', self, shortcut='B', triggered=lambda: self.color_row('b')))
        add_action('colorRedAction', QAction('&Red', self, shortcut='R', triggered=lambda: self.color_row('r')))
        add_action('colorOrangeAction', QAction('&Orange', self, shortcut='O', triggered=lambda: self.color_row('o')))
        add_action('colorNoColorAction', QAction('&No color', self, shortcut='N', triggered=lambda: self.color_row('n')))
        add_action('toggleTaskAction', QAction(self.tr('&Toggle: note, todo, done'), self, shortcut='Space', triggered=self.toggle_task))
        add_action('openLinkAction', QAction(self.tr('&Open selected rows with URLs'), self, shortcut='L', triggered=self.open_links))
        add_action('renameTagAction', QAction(self.tr('&Rename tag'), self, triggered=lambda: RenameTagDialog(self, self.tag_view.currentIndex().data()).exec_()))
        add_action('editBookmarkAction', QAction(self.tr(EDIT_BOOKMARK), self, triggered=lambda: BookmarkDialog(self, index=self.bookmarks_view.selectionModel().currentIndex()).exec_()))
        add_action('moveBookmarkUpAction', QAction(self.tr('Move bookmark up'), self, triggered=self.move_up))
        add_action('moveBookmarkDownAction', QAction(self.tr('Move bookmark down'), self, triggered=self.move_down))
        add_action('deleteBookmarkAction', QAction(self.tr('Delete selected bookmarks'), self, triggered=self.removeBookmarkSelection))
        add_action('editShortcutAction', QAction(self.tr(EDIT_QUICKLINK), self, triggered=lambda: ShortcutDialog(self, self.quicklinks_view.selectionModel().currentIndex()).exec_()))
        add_action('resetViewAction', QAction(self.tr('&Reset view'), self, shortcut='esc', triggered=self.reset_view))
        add_action('toggleProjectAction', QAction(self.tr('&Toggle: note, sequential project, parallel project, paused project'), self, shortcut='P', triggered=self.toggle_project))
        add_action('appendRepeatAction', QAction(self.tr('&Repeat'), self, triggered=self.append_repeat))
        add_action('undoAction', self.item_model.undoStack.createUndoAction(self))
        self.undoAction.setShortcut('CTRL+Z')
        add_action('redoAction', self.item_model.undoStack.createRedoAction(self))
        self.redoAction.setShortcut('CTRL+Shift+Z')

        self.fileMenu = self.menuBar().addMenu(self.tr('Databases'))
        self.fileMenu.addAction(self.addDatabaseAct)
        self.fileMenu.addAction(self.deleteDatabaseAct)
        self.fileMenu.addAction(self.editDatabaseAct)

        self.fileMenu = self.menuBar().addMenu(self.tr('&File'))
        self.fileMenu.addAction(self.undoAction)
        self.fileMenu.addAction(self.redoAction)
        self.fileMenu.addAction(self.renameTagAction)
        self.fileMenu.addAction(self.editBookmarkAction)
        self.fileMenu.addAction(self.moveBookmarkUpAction)
        self.fileMenu.addAction(self.moveBookmarkDownAction)
        self.fileMenu.addAction(self.deleteBookmarkAction)
        self.fileMenu.addAction(self.editShortcutAction)
        self.fileMenu.addAction(self.settingsAct)

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
        # self.viewMenu.addAction(self.splitWindowAct)
        # self.viewMenu.addAction(self.unsplitWindowAct)
        self.viewMenu.addAction(self.focusSearchBarAction)
        self.viewMenu.addAction(self.openLinkAction)
        self.viewMenu.addAction(self.resetViewAction)

        self.bookmarkShortcutsMenu = self.menuBar().addMenu(self.tr('Bookmark shortcuts'))
        self.fill_bookmarkShortcutsMenu()

        self.helpMenu = self.menuBar().addMenu(self.tr('&Help'))
        self.helpMenu.addAction(self.aboutAct)

        # make single key menu shortcuts work on Mac OS X, too
        # source: http://thebreakfastpost.com/2014/06/03/single-key-menu-shortcuts-with-qt5-on-osx/
        if sys.platform == "darwin":
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
        self.reset_view()  # inits checkboxes
        self.focused_column().view.setFocus()
        self.updateActions()

        # restore previous position etc
        self.resize(settings.value('size', QSize(800, 600)))
        self.move(settings.value('pos', QPoint(200, 200)))

        mainSplitter_state = settings.value('mainSplitter')
        if mainSplitter_state is not None:
            self.mainSplitter.restoreState(mainSplitter_state)

        first_column_splitter_state = settings.value('first_column_splitter')
        if first_column_splitter_state is not None:
            self.first_column_splitter.restoreState(first_column_splitter_state)

        # restore expanded item states
        for item_id in settings.value(EXPANDED_ITEMS, []):
            if item_id in self.item_model.id_index_dict:
                index = self.item_model.id_index_dict[item_id]
                proxy_index = self.filter_proxy_index_from_model_index(QModelIndex(index))
                self.focused_column().view.expand(proxy_index)

        # restore expanded quick link states
        for item_id in settings.value(EXPANDED_QUICKLINKS, []):
            if item_id in self.item_model.id_index_dict:
                index = self.item_model.id_index_dict[item_id]
                self.quicklinks_view.expand(QModelIndex(index))

        # restore selection
        selection_item_id = settings.value(SELECTED_ID, None)
        if selection_item_id is not None and selection_item_id in self.item_model.id_index_dict:
            index = QModelIndex(self.item_model.id_index_dict[selection_item_id])
            self.set_selection(index, index)

    def fill_bookmarkShortcutsMenu(self):
        self.bookmarkShortcutsMenu.clear()
        map = "function(doc) { \
                    if (doc." + model.SHORTCUT + " != '' && doc." + model.DELETED + " == '') \
                        emit(doc, null); \
                }"
        res = self.bookmark_model.db.query(map)
        for row in res:
            db_item = self.bookmark_model.db[row.id]
            self.bookmarkShortcutsMenu.addAction(QAction(db_item[model.TEXT], self, shortcut=db_item[model.SHORTCUT],
                                                         triggered=partial(self.filter_bookmark, row.id)))

        res = self.item_model.db.query(map)
        for row in res:
            db_item = self.item_model.db[row.id]
            self.bookmarkShortcutsMenu.addAction(QAction(db_item[model.TEXT], self, shortcut=db_item[model.SHORTCUT],
                                                         triggered=partial(self.append_replace_to_searchbar, model.FOCUS, row.id)))

    def focused_column(self):  # returns focused item view holder
        for i in range(0, self.item_views_splitter.count()):
            if self.item_views_splitter.widget(i).hasFocus():
                return self.item_views_splitter.widget(i)
        return self.item_views_splitter.widget(0)

    def setup_tag_model(self):
        self.tag_view.model().setupModelData(self.item_model.get_tags_set())

        def expand_node(parent_index, bool_expand):
            self.tag_view.setExpanded(parent_index, bool_expand)
            for row_num in range(self.tag_view.model().rowCount(parent_index)):
                child_index = self.tag_view.model().index(row_num, 0, parent_index)
                self.tag_view.setExpanded(parent_index, bool_expand)
                expand_node(child_index, bool_expand)

        expand_node(self.tag_view.selectionModel().currentIndex(), True)

    def change_active_database(self, index):
        self.item_model = self.server_model.get_server(index).model
        self.focused_column().flat_proxy.setSourceModel(self.item_model)
        self.focused_column().filter_proxy.setSourceModel(self.item_model)


    def closeEvent(self, event):
        settings = QSettings()
        settings.setValue('pos', self.pos())
        settings.setValue('size', self.size())
        settings.setValue('mainSplitter', self.mainSplitter.saveState())
        settings.setValue('first_column_splitter', self.first_column_splitter.saveState())

        # save databases
        server_list = []
        for server in self.server_model.servers:
            server_list.append((server.bookmark_name, server.url, server.database_name))
        settings.setValue('databases', server_list)

        # save expanded items
        self.save_expanded_state()
        settings.setValue(EXPANDED_ITEMS, self.expanded_id_list)

        # save expanded quicklinks
        expanded_quicklinks_id_list = []
        for index in self.item_model.persistentIndexList():
            if self.quicklinks_view.isExpanded(index):
                expanded_quicklinks_id_list.append(self.item_model.getItem(index).id)
        settings.setValue(EXPANDED_QUICKLINKS, expanded_quicklinks_id_list)

        # save selection
        current_index = self.focused_column().view.selectionModel().currentIndex()
        settings.setValue(SELECTED_ID, self.focused_column().filter_proxy.getItem(current_index).id)

        self.item_model.updater.terminate()

        if not __debug__:  # This constant is true if Python was not started with an -O option. -O turns on basic optimizations.
            if sys.platform == "darwin":
                subprocess.call(['osascript', '-e', 'tell application "Apache CouchDB" to quit'])

    def evoke_singlekey_action(self, action_name):  # fix shortcuts for mac
        for action in self.actions:
            if action.text() == action_name and action.isEnabled():
                action.trigger()
                break

    def updateActions(self):
        pass  #
        # todo rename tag action just when a tag is selected

    def toggle_sorting(self, column):
        if column == 0:  # order manually
            self.filter(model.SORT, 'all')
        elif column == 1:  # order by start date
            order = model.DESC  # toggle between ASC and DESC
            if model.DESC in self.focused_column().search_bar.text():
                order = model.ASC
            self.append_replace_to_searchbar(model.SORT, model.STARTDATE + order)
        elif column == 2:  # order by estimate
            order = model.DESC
            if model.DESC in self.focused_column().search_bar.text():
                order = model.ASC
            self.append_replace_to_searchbar(model.SORT, model.ESTIMATE + order)

    def append_replace_to_searchbar(self, key, value):
        search_bar_text = self.focused_column().search_bar.text()
        new_text = re.sub(key + r'(\w|=)* ', key + '=' + value + ' ', search_bar_text)
        if key not in search_bar_text:
            new_text += ' ' + key + '=' + value + ' '
        self.set_searchbar_text_and_search(new_text)

    @pyqtSlot(bool)
    def filter_show_only_startdate(self, only_startdate):
        if only_startdate:
            self.append_replace_to_searchbar(model.ONLY_START_DATE, 'yes')
        else:
            self.filter(model.ONLY_START_DATE, 'all')  # todo: ugly to use two different methods for the same thing, append_replace_to_searchbar and filter

    @pyqtSlot(bool)
    def filter_hide_future_startdate(self, hide_future_startdate):
        if hide_future_startdate:
            self.append_replace_to_searchbar(model.HIDE_FUTURE_START_DATE, 'yes')
        else:
            self.filter(model.HIDE_FUTURE_START_DATE, 'all')

    @pyqtSlot(bool)
    def filter_flatten_view(self, flatten):
        if flatten:
            self.append_replace_to_searchbar(model.FLATTEN, 'yes')
        else:
            self.filter(model.FLATTEN, 'all')

    def filter_tag(self):
        current_index = self.tag_view.selectionModel().currentIndex()
        current_tag = self.tag_view.model().data(current_index, tag_model.FULL_PATH)
        if current_tag is not None:
            search_bar_text = self.focused_column().search_bar.text()
            new_text = re.sub(r':(\w|:)* ', current_tag + ' ', search_bar_text)  # matches a tag
            if ':' not in search_bar_text:
                new_text += ' ' + current_tag + ' '
            self.set_searchbar_text_and_search(new_text)

    # set the search bar text according to the selected bookmark
    def filter_bookmark(self, item_id):
        new_search_bar_text = self.bookmark_model.db[item_id][model.SEARCH_TEXT]
        self.focused_column().search_bar.setText(new_search_bar_text)
        # if shortcut was used: select bookmarks row for visual highlight
        index = self.bookmark_model.id_index_dict[item_id]
        self.set_selection(index, index)

    @pyqtSlot(QModelIndex)
    def filter_bookmark_click(self, index):
        item_id = self.bookmark_model.getItem(index).id
        self.filter_bookmark(item_id)

    # just for one character filters
    def filter(self, key, value):
        character = value[0]
        search_bar_text = self.focused_column().search_bar.text()
        # 'all' selected: remove existing same filter
        if value == 'all':
            search_bar_text = re.sub(key + r'(<|>|=|\w|\d)* ', '', search_bar_text)
        else:
            # key is a compare operator. estimate parameters are 'e' and '<20' instead of 't=' and 'n'
            if len(key) == 1:
                key += value[0]
                value = value[1:]
            # filter is already in the search bar: replace existing same filter
            if re.search(key[0] + r'(<|>|=)', search_bar_text):
                search_bar_text = re.sub(key[0] + r'(<|>|=|\w|\d)* ', key + value + ' ', search_bar_text)
            else:
                # add filter
                search_bar_text += ' ' + key + value + ' '
        self.set_searchbar_text_and_search(search_bar_text)

    def set_searchbar_text_and_search(self, search_bar_text):
        self.focused_column().search_bar.setText(search_bar_text)
        self.search(search_bar_text)

    def filter_proxy_index_from_model_index(self, model_index):
        if self.focused_column().filter_proxy.sourceModel() == self.focused_column().flat_proxy:
            model_index = self.focused_column().flat_proxy.mapFromSource(model_index)
        return self.focused_column().filter_proxy.mapFromSource(model_index)

    @pyqtSlot(dict, QAbstractItemModel)
    def db_change_signal(self, db_item, source_model):
        change_dict = db_item['change']
        my_edit = change_dict['user'] == socket.gethostname()
        method = change_dict['method']
        position = change_dict.get('position')
        count = change_dict.get('count')
        item_id = db_item['_id']

        # ignore cases when the 'update delete marker' change comes before the corresponding item is created
        if item_id not in source_model.id_index_dict:
            return
        index = QModelIndex(source_model.id_index_dict[item_id])

        item = source_model.getItem(index)

        if method == 'updated':
            item.update_attributes(db_item)
            if my_edit:
                self.set_selection(index, index)
            self.setup_tag_model()
            source_model.dataChanged.emit(index, index)

            # update next available task in a sequential project
            project_index = source_model.parent(index)
            project_parent_index = source_model.parent(project_index)
            available_index = source_model.get_next_available_task(project_index.row(), project_parent_index)
            if isinstance(available_index, QModelIndex):
                source_model.dataChanged.emit(available_index, available_index)

            # update the sort by changing the ordering
            sorted_column = self.focused_column().view.header().sortIndicatorSection()
            if sorted_column == 1 or sorted_column == 2:
                order = self.focused_column().view.header().sortIndicatorOrder()
                self.focused_column().view.sortByColumn(sorted_column, 1 - order)
                self.focused_column().view.sortByColumn(sorted_column, order)

        elif method == 'added':
            id_list = change_dict['id_list']
            source_model.beginInsertRows(index, position, position + len(id_list) - 1)
            for i, added_item_id in enumerate(id_list):
                item.add_child(position + i, added_item_id, index)
            source_model.endInsertRows()
            if my_edit:
                index_first_added = source_model.index(position, 0, index)
                index_last_added = source_model.index(position + len(id_list) - 1, 0, index)
                if not change_dict['set_edit_focus']:
                    self.set_selection(index_first_added, index_last_added)
                else:  # update selection_and_edit
                    if index_first_added.model() is self.item_model:
                        index_first_added = self.filter_proxy_index_from_model_index(index_first_added)
                        self.focusWidget().selectionModel().setCurrentIndex(index_first_added, QItemSelectionModel.ClearAndSelect)
                        self.focusWidget().edit(index_first_added)
                    else:  # bookmark
                        self.bookmarks_view.selectionModel().setCurrentIndex(index_first_added, QItemSelectionModel.ClearAndSelect)

                # restore horizontally moved items expanded states + expanded states of their childrens
                for child_id in self.removed_id_expanded_state_dict:
                    child_index = QModelIndex(source_model.id_index_dict[child_id])
                    proxy_index = self.filter_proxy_index_from_model_index(child_index)
                    expanded_state = self.removed_id_expanded_state_dict[child_id]
                    self.focused_column().view.setExpanded(proxy_index, expanded_state)
                self.removed_id_expanded_state_dict = {}

        elif method == 'removed':
            # for move horizontally: save expanded states of moved + children of moved
            if source_model is self.item_model:  # not for bookmarks
                self.removed_id_expanded_state_dict = {}
                # save and restore expanded state  todo performance
                def save_childs(parent, from_child, to_child):
                    for child_item in parent.childItems[from_child:to_child]:
                        child_item_index = QModelIndex(source_model.id_index_dict[child_item.id])
                        proxy_index = self.filter_proxy_index_from_model_index(child_item_index)
                        self.removed_id_expanded_state_dict[child_item.id] = self.focused_column().view.isExpanded(proxy_index)
                        save_childs(source_model.getItem(child_item_index), None, None)  # save expanded state of all childs

                save_childs(item, position, position + count)

            source_model.beginRemoveRows(index, position, position + count - 1)
            item.childItems[position:position + count] = []
            source_model.endRemoveRows()
            self.fill_bookmarkShortcutsMenu()
            if my_edit:
                # select the item below
                if position == len(item.childItems):  # there is no item below, so select the one above
                    position -= 1
                if len(item.childItems) > 0:
                    index_next_child = source_model.index(position, 0, index)
                    self.set_selection(index_next_child, index_next_child)
                else:  # all childs deleted, select parent
                    self.set_selection(index, index)

        elif method == 'moved_vertical':
            # save expanded states todo: save and restore the moved items only
            bool_moved_bookmark = source_model is self.bookmark_model  # but not for bookmarks
            id_expanded_state_dict = {}
            if not bool_moved_bookmark:
                for child_position, child_item in enumerate(item.childItems):
                    child_item_index = QModelIndex(source_model.id_index_dict[child_item.id])
                    proxy_index = self.filter_proxy_index_from_model_index(child_item_index)
                    id_expanded_state_dict[child_item.id] = self.focused_column().view.isExpanded(proxy_index)

            source_model.layoutAboutToBeChanged.emit([QPersistentModelIndex(index)])
            up_or_down = change_dict['up_or_down']
            if up_or_down == -1:
                # if we want to move several items up, we can move the item-above below the selection instead:
                item.childItems.insert(position + count - 1, item.childItems.pop(position - 1))
            elif up_or_down == +1:
                item.childItems.insert(position, item.childItems.pop(position + count))
            index_first_moved_item = source_model.index(position + up_or_down, 0, index)
            index_last_moved_item = source_model.index(position + up_or_down + count - 1, 0, index)
            source_model.layoutChanged.emit([QPersistentModelIndex(index)])

            if my_edit:
                # select first moved item
                self.set_selection(index_first_moved_item, index_last_moved_item)

                # restore expanded states
                if not bool_moved_bookmark:
                    for child_position, child_item in enumerate(item.childItems):
                        child_index = source_model.index(child_position, 0, index)

                        # update id_index_dict # todo for foreign edits, too. so move this out of 'if my_edit:'
                        source_model.id_index_dict[child_item.id] = QPersistentModelIndex(child_index)
                        source_model.pointer_set.add(child_index.internalId())

                        proxy_index = self.filter_proxy_index_from_model_index(child_index)
                        expanded_state = id_expanded_state_dict[child_item.id]
                        self.focused_column().view.setExpanded(proxy_index, expanded_state)



        elif method == model.DELETED:
            if source_model.db[item_id][model.DELETED] == '':
                source_model.pointer_set.add(index.internalId())
            else:
                source_model.pointer_set.remove(index.internalId())
            self.setup_tag_model()

    def set_selection(self, index_from, index_to):
        if self.focused_column().view.state() != QAbstractItemView.EditingState:
            view = self.focused_column().view
            if index_from.model() is self.item_model:
                index_to = self.filter_proxy_index_from_model_index(index_to)
                index_from = self.filter_proxy_index_from_model_index(index_from)
            elif index_from.model() is self.bookmark_model:
                view = self.bookmarks_view
                view.setFocus()
            index_from = index_from.sibling(index_from.row(), 0)
            index_to = index_to.sibling(index_to.row(), self.item_model.columnCount() - 1)
            view.selectionModel().setCurrentIndex(index_from, QItemSelectionModel.ClearAndSelect)
            view.selectionModel().select(QItemSelection(index_from, index_to), QItemSelectionModel.ClearAndSelect)

    def set_top_row_selected(self):
        current_root_index = self.focused_column().view.rootIndex()
        top_most_index = self.focused_column().filter_proxy.index(0, 0, current_root_index)
        self.set_selection(top_most_index, top_most_index)
        self.focused_column().view.setFocus()

    def reset_view(self):
        self.hideFutureStartdateCheckBox.setChecked(False)
        self.flattenViewCheckBox.setChecked(False)
        self.showOnlyStartdateCheckBox.setChecked(False)
        self.task_dropdown.setCurrentIndex(0)
        self.estimate_dropdown.setCurrentIndex(0)
        self.color_dropdown.setCurrentIndex(0)
        self.set_searchbar_text_and_search('')
        self.bookmarks_view.selectionModel().setCurrentIndex(QModelIndex(), QItemSelectionModel.ClearAndSelect)
        self.focused_column().view.setRootIndex(QModelIndex())

    def save_expanded_state(self):
        self.expanded_id_list = []
        for index in self.focused_column().filter_proxy.persistentIndexList():
            if self.focused_column().view.isExpanded(index):
                self.expanded_id_list.append(self.focused_column().filter_proxy.getItem(index).id)

    @pyqtSlot(str)
    def search(self, search_text):
        # before doing the search: save expanded states
        focus_pattern = re.compile(' ' + model.FOCUS + '\S* *$')  # '\S*' = any number of not Whitespaces. ' *' = any number of Whitespaces. '$' = end of string
        if self.old_search_text == '':
            self.save_expanded_state()
        elif focus_pattern.match(self.old_search_text):
            self.save_expanded_state()
        self.old_search_text = search_text

        # sort
        if model.SORT in search_text:
            if model.ASC in search_text:
                order = Qt.DescendingOrder  # it's somehow reverted :/
            elif model.DESC in search_text:
                order = Qt.AscendingOrder
            if model.STARTDATE in search_text:
                column = 1
            elif model.ESTIMATE in search_text:
                column = 2
            self.focused_column().view.setSortingEnabled(True)
            self.focused_column().view.sortByColumn(column, order)
        else:  # reset sorting
            self.focused_column().view.sortByColumn(-1, Qt.AscendingOrder)
            self.focused_column().view.setSortingEnabled(False)  # prevent sorting by text
            self.focused_column().view.header().setSectionsClickable(True)

        def apply_filter():
            self.focused_column().filter_proxy.filter = search_text
            self.focused_column().filter_proxy.invalidateFilter()
            # deselect tag if user changes the search string
            selected_tags = self.tag_view.selectionModel().selectedRows()
            if len(selected_tags) > 0 and selected_tags[0].data() not in search_text:
                self.tag_view.selectionModel().setCurrentIndex(QModelIndex(), QItemSelectionModel.Clear)
                # changing dropdown index accordingly is not that easy, because changing it fires "color_clicked" which edits search bar...

        # flatten + filter # todo just when not already flattened
        if model.FLATTEN in search_text:
            self.focused_column().filter_proxy.setSourceModel(self.focused_column().flat_proxy)
            apply_filter()
        else:
            apply_filter()  # filter must be refreshed before changing the model, otherwise exc because use of wrong model
            self.focused_column().filter_proxy.setSourceModel(self.item_model)

        # focus
        if model.FOCUS in search_text and model.FLATTEN not in search_text:
            item_id_with_space_behind = search_text.split(model.FOCUS)[1]  # second item is the one behind FOCUS
            item_id_with_equalsign_before = item_id_with_space_behind.split()
            item_id = item_id_with_equalsign_before[0][1:]
            idx = QModelIndex(self.item_model.id_index_dict[item_id])  # convert QPersistentModelIndex
            proxy_idx = self.filter_proxy_index_from_model_index(idx)
            self.focused_column().view.setRootIndex(proxy_idx)

        # expand
        if search_text == '' or focus_pattern.match(search_text):
            for item_id in self.expanded_id_list:
                index = self.item_model.id_index_dict[item_id]
                proxy_index = self.filter_proxy_index_from_model_index(QModelIndex(index))
                self.focused_column().view.expand(proxy_index)
        else:  # expand all items
            self.expand_or_collapse_children(QModelIndex(), True)

        # set selection
        if not self.focused_column().search_bar.isModified():  # only if text was set programmatically e.g. because the user selected a dropdown
            self.set_top_row_selected()

    def expand_or_collapse_children(self, parent_index, bool_expand):
        self.focused_column().view.setExpanded(parent_index, bool_expand)
        for row_num in range(self.focused_column().filter_proxy.rowCount(parent_index)):
            child_index = self.focused_column().filter_proxy.index(row_num, 0, parent_index)
            self.focused_column().view.setExpanded(parent_index, bool_expand)
            self.expand_or_collapse_children(child_index, bool_expand)

    def rename_tag(self, tag, new_name):
        map = "function(doc) {{ \
                    if (doc.text.indexOf('{}') != -1 ) \
                        emit(doc, null); \
                }}".format(tag)
        res = self.item_model.db.query(map)
        for row in res:
            db_item = self.item_model.db[row.id]
            db_item['text'] = db_item['text'].replace(tag, new_name)
            db_item['change'] = dict(method='updated', user=socket.gethostname())
            self.item_model.db[row.id] = db_item

    @pyqtSlot(QPoint)
    def open_rename_tag_contextmenu(self, point):
        index = self.tag_view.indexAt(point)
        if not index.isValid():  # show context menu only when clicked on an item, not when clicked on empty space
            return
        menu = QMenu()
        renameTagAction = menu.addAction(self.tr("Rename tag"))
        action = menu.exec_(self.tag_view.viewport().mapToGlobal(point))
        if action is not renameTagAction:
            return
        tag = index.data()
        RenameTagDialog(self, tag).exec_()

    @pyqtSlot(QPoint)
    def open_edit_bookmark_contextmenu(self, point):
        index = self.bookmarks_view.indexAt(point)
        if not index.isValid(): return
        menu = QMenu()
        editBookmarkAction = menu.addAction(self.tr(EDIT_BOOKMARK))
        deleteBookmarkAction = menu.addAction(self.tr('Delete bookmark'))
        action = menu.exec_(self.bookmarks_view.viewport().mapToGlobal(point))
        if action is editBookmarkAction:
            BookmarkDialog(self, index=index).exec_()
        elif action is deleteBookmarkAction:
            self.removeBookmarkSelection()

    @pyqtSlot(QPoint)
    def open_edit_shortcut_contextmenu(self, point):
        index = self.quicklinks_view.indexAt(point)
        if not index.isValid(): return
        menu = QMenu()
        editShortcutAction = menu.addAction(self.tr('Edit shortcut'))
        action = menu.exec_(self.quicklinks_view.viewport().mapToGlobal(point))
        if action is editShortcutAction:
            ShortcutDialog(self, index=index).exec_()

    @pyqtSlot(QPoint)
    def open_edit_server_contextmenu(self, point):
        menu = QMenu()
        menu.addAction(self.addDatabaseAct)
        index = self.servers_view.indexAt(point)
        if index.isValid():
            menu.addAction(self.editDatabaseAct)
            menu.addAction(self.deleteDatabaseAct)
        menu.exec_(self.servers_view.viewport().mapToGlobal(point))

    # structure menu actions

    def expand_all_children_of_selected_rows(self):
        self.expand_or_collapse_children(self.focused_column().view.selectionModel().selectedRows()[0], True)

    def collapse_all_children_of_selected_rows(self):
        self.expand_or_collapse_children(self.focused_column().view.selectionModel().selectedRows()[0], False)

    def move_up(self):
        indexes = self.focusWidget().selectionModel().selectedRows()
        indexes[0].model().move_vertical(indexes, -1)

    def move_down(self):
        indexes = self.focusWidget().selectionModel().selectedRows()
        indexes[0].model().move_vertical(indexes, +1)

    def move_left(self):
        if self.focusWidget() is self.focused_column().view:
            self.focused_column().filter_proxy.move_horizontal(self.focused_column().view.selectionModel().selectedRows(), -1)

    def move_right(self):
        if self.focusWidget() is self.focused_column().view:
            self.focused_column().filter_proxy.move_horizontal(self.focused_column().view.selectionModel().selectedRows(), +1)

    def insert_child(self):
        index = self.focused_column().view.selectionModel().currentIndex()
        if self.focused_column().view.state() == QAbstractItemView.EditingState:
            # save the edit of the yet open editor
            self.focused_column().view.selectionModel().currentChanged.emit(index, index)
        self.focused_column().filter_proxy.insert_row(0, index)

    def insert_row(self):
        index = self.focused_column().view.selectionModel().currentIndex()
        if self.focused_column().view.hasFocus():
            self.focused_column().filter_proxy.insert_row(index.row() + 1, index.parent())
        elif self.focused_column().view.state() == QAbstractItemView.EditingState:
            # commit data by changing the current selection
            self.focused_column().view.selectionModel().currentChanged.emit(index, index)

    def removeSelection(self):
        indexes = self.focusWidget().selectionModel().selectedRows()
        self.focused_column().filter_proxy.remove_rows(indexes)

    def removeBookmarkSelection(self):
        self.bookmarks_view.setFocus()
        indexes = self.focusWidget().selectionModel().selectedRows()
        self.bookmark_model.insert_remove_rows(indexes=indexes)

    # task menu actions

    def edit_row(self):
        current_index = self.focused_column().view.selectionModel().currentIndex()
        if self.focused_column().view.state() == QAbstractItemView.EditingState:  # change column with tab key
            next_column_number = (current_index.column() + 1) % 3
            sibling_index = current_index.sibling(current_index.row(), next_column_number)
            self.focused_column().view.selectionModel().setCurrentIndex(sibling_index, QItemSelectionModel.ClearAndSelect)
            self.focused_column().view.edit(sibling_index)
        elif self.focused_column().view.hasFocus():
            self.focused_column().view.edit(current_index)
        else:
            self.focused_column().view.setFocus()

    def toggle_task(self):
        if self.focused_column().view.hasFocus():
            for row_index in self.focused_column().view.selectionModel().selectedRows():
                self.focused_column().filter_proxy.toggle_task(row_index)

    def toggle_project(self):
        if self.focused_column().view.hasFocus():
            for row_index in self.focused_column().view.selectionModel().selectedRows():
                self.focused_column().filter_proxy.toggle_project(row_index)

    def append_repeat(self):
        current_index = self.focused_column().view.selectionModel().currentIndex()
        self.focused_column().filter_proxy.set_data(current_index.data() + ' repeat=1w', index=current_index)
        self.edit_row()

    @pyqtSlot(str)
    def color_row(self, color_character):
        if self.focused_column().view.hasFocus():  # todo not needed if action is only available when row selected
            for row_index in self.focused_column().view.selectionModel().selectedRows():
                self.focused_column().filter_proxy.set_data(model.CHAR_QCOLOR_DICT[color_character], index=row_index, field='color')

    # view menu actions

    @pyqtSlot(QModelIndex)
    def focus_index(self, index):
        search_bar_text = self.focused_column().search_bar.text()
        item_id = index.model().get_db_item(index)['_id']
        self.set_searchbar_text_and_search(model.FOCUS + '=' + item_id)

    def open_links(self):
        for row_index in self.focused_column().view.selectionModel().selectedRows():
            url_regex = r"""(?i)\b((?:https?:(?:/{1,3}|[a-z0-9%])|[a-z0-9.\-]+[.](?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)/)(?:[^\s()<>{}\[\]]+|\([^\s()]*?\([^\s()]+\)[^\s()]*?\)|\([^\s]+?\))+(?:\([^\s()]*?\([^\s()]+\)[^\s()]*?\)|\([^\s]+?\)|[^\s`!()\[\]{};:'".,<>?«»“”‘’])|(?:(?<!@)[a-z0-9]+(?:[.\-][a-z0-9]+)*[.](?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)\b/?(?!@)))"""  # source: http://daringfireball.net/2010/07/improved_regex_for_matching_urls
            url_list = re.findall(url_regex, row_index.data())
            for url in url_list:
                if not url.startswith('http://'):
                    url = 'http://' + url
                webbrowser.open(url)

    def split_window(self):  # creates another item_view
        new_column = QWidget()

        new_column.focus_button = QPushButton()
        new_column.focus_button.setToolTip('Focus on current row')
        new_column.focus_button.setIcon(QIcon(':/focus'))
        new_column.focus_button.setStyleSheet('QPushButton {\
            width: 22px;\
            height: 22px;\
            padding: 2px; }')
        new_column.focus_button.clicked.connect(lambda: self.focus_index(self.focused_column().view.selectionModel().currentIndex()))

        new_column.search_bar = SearchBarQLineEdit(self)
        new_column.search_bar.setPlaceholderText(self.tr('Search'))

        # search shall start not before the user completed typing
        filterDelay = DelayedExecutionTimer(self)
        new_column.search_bar.textEdited[str].connect(filterDelay.trigger)  # just triggered by user editing, not triggered by programmatically setting the search bar text
        filterDelay.triggered[str].connect(self.search)

        new_column.bookmark_button = QPushButton()
        new_column.bookmark_button.setToolTip('Bookmark current filters')
        new_column.bookmark_button.setIcon(QIcon(':/star'))
        new_column.bookmark_button.setStyleSheet('QPushButton {\
            width: 22px;\
            height: 22px;\
            padding: 2px; }')
        new_column.bookmark_button.clicked.connect(lambda: BookmarkDialog(self, search_bar_text=self.focused_column().search_bar.text()).exec_())

        search_holder = QWidget()
        layout = QHBoxLayout()
        layout.addWidget(new_column.focus_button)
        layout.addWidget(new_column.search_bar)
        layout.addWidget(new_column.bookmark_button)
        layout.setContentsMargins(0, 11, 0, 0)
        search_holder.setLayout(layout)

        new_column.view = QTreeView()
        new_column.view.setStyleSheet('QTreeView:focus { border: 1px solid #006080; }')
        new_column.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        new_column.view.setSelectionMode(QAbstractItemView.ExtendedSelection)

        new_column.flat_proxy = model.FlatProxyModel()
        new_column.flat_proxy.setSourceModel(self.item_model)

        new_column.filter_proxy = model.FilterProxyModel()
        new_column.filter_proxy.setSourceModel(self.item_model)
        new_column.filter_proxy.setDynamicSortFilter(True)  # re-sort and re-filter data whenever the original model changes
        new_column.filter_proxy.filter = ''

        new_column.view.setModel(new_column.filter_proxy)
        new_column.view.setItemDelegate(model.Delegate(self, new_column.filter_proxy))
        new_column.view.selectionModel().selectionChanged.connect(self.updateActions)
        new_column.view.header().sectionClicked[int].connect(self.toggle_sorting)
        new_column.view.header().setStretchLastSection(False)
        new_column.view.setColumnWidth(1, 105)
        new_column.view.setColumnWidth(2, 85)
        new_column.view.header().setSectionResizeMode(0, QHeaderView.Stretch)
        new_column.view.header().setSectionResizeMode(1, QHeaderView.Fixed)
        new_column.view.header().setSectionResizeMode(2, QHeaderView.Fixed)
        new_column.view.header().setSectionsClickable(True)

        layout = QVBoxLayout()
        layout.setContentsMargins(6, 0, 6, 0)  # left, top, right, bottom
        layout.addWidget(search_holder)
        layout.addWidget(new_column.view)
        new_column.setLayout(layout)

        self.item_views_splitter.addWidget(new_column)
        self.setup_tag_model()

        self.focused_column().view.setFocus()
        top_most_index = self.focused_column().filter_proxy.index(0, 0, QModelIndex())
        self.set_selection(top_most_index, top_most_index)
        self.bookmarks_view.selectionModel().setCurrentIndex(QModelIndex(), QItemSelectionModel.ClearAndSelect)

    def unsplit_window(self):
        index_last_widget = self.item_views_splitter.count() - 1
        self.item_views_splitter.widget(index_last_widget).setParent(None)
        if self.item_views_splitter.count() == 1:
            self.unsplitWindowAct.setEnabled(False)

    # help menu actions

    def about(self):
        QMessageBox.about(self, self.tr('About'), self.tr('teeeext'))


class SearchBarQLineEdit(QLineEdit):
    def __init__(self, main):
        super(QLineEdit, self).__init__()
        self.main = main
        self.setStyleSheet('QLineEdit {\
        padding-left: 22px;\
        padding-top: 3px;\
        padding-right: 3px;\
        padding-bottom: 3px;\
        background: url(:/search);\
        background-position: left;\
        background-repeat: no-repeat;\
        border-radius: 2px;\
        height: 22px;}')
        self.setStyleSheet('QLineEdit:focus {\
        border: 1px solid #006080;\
        border-radius: 2px;\
        height: 24px; }')

    def keyPressEvent(self, event):
        # arror key down: select first child
        if event.key() == Qt.Key_Down:
            index = self.main.focused_column().filter_proxy.index(0, 0, QModelIndex())
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
        self.setMinimumWidth(600)
        self.parent = parent
        self.search_bar_text = search_bar_text
        self.index = index
        if index is not None:
            item = parent.bookmark_model.getItem(index)
            db_item = parent.bookmark_model.db[item.id]

        name = '' if index is None else db_item[model.TEXT]
        self.name_edit = QLineEdit(name)

        if search_bar_text is None:
            search_bar_text = db_item[model.SEARCH_TEXT]
        self.search_bar_text_edit = QLineEdit(search_bar_text)

        shortcut = '' if index is None else db_item[model.SHORTCUT]
        self.shortcut_edit = QKeySequenceEdit()
        self.shortcut_edit.setKeySequence(QKeySequence(shortcut))
        clearButton = QPushButton('Clear')
        clearButton.clicked.connect(self.shortcut_edit.clear)

        buttonBox = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Cancel)

        grid = QGridLayout()
        grid.addWidget(QLabel('Bookmark name:'), 0, 0)  # row, column
        grid.addWidget(QLabel('Saved filters:'), 1, 0)
        grid.addWidget(QLabel('Shortcut (optional):'), 2, 0)
        grid.addWidget(self.name_edit, 0, 1)
        grid.addWidget(self.search_bar_text_edit, 1, 1)
        grid.addWidget(self.shortcut_edit, 2, 1)
        grid.addWidget(clearButton, 2, 2)
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
            self.parent.bookmark_model.insert_remove_rows(new_item_position, model.ROOT_ID)
            children_list = self.parent.bookmark_model.db[model.ROOT_ID]['children'].split()
            item_id = children_list[-1]
        else:
            item_id = self.parent.bookmark_model.get_db_item(self.index)['_id']
        self.parent.bookmark_model.set_data(self.name_edit.text(), item_id=item_id, column=0, field='text')
        self.parent.bookmark_model.set_data(self.search_bar_text_edit.text(), item_id=item_id, column=0, field=model.SEARCH_TEXT)
        self.parent.bookmark_model.set_data(self.shortcut_edit.keySequence().toString(), item_id=item_id, column=0, field=model.SHORTCUT)
        self.parent.fill_bookmarkShortcutsMenu()
        super(BookmarkDialog, self).accept()


class ShortcutDialog(QDialog):
    def __init__(self, parent, index):
        super(QDialog, self).__init__(parent)
        self.setMinimumWidth(340)
        self.parent = parent
        self.item = parent.item_model.getItem(index)
        db_item = parent.item_model.db[self.item.id]
        self.shortcut_edit = QKeySequenceEdit()
        self.shortcut_edit.setKeySequence(QKeySequence(db_item[model.SHORTCUT]))
        clearButton = QPushButton('Clear')
        clearButton.clicked.connect(self.shortcut_edit.clear)
        buttonBox = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Cancel)
        buttonBox.button(QDialogButtonBox.Apply).clicked.connect(self.apply)
        buttonBox.button(QDialogButtonBox.Cancel).clicked.connect(self.reject)

        grid = QGridLayout()
        grid.addWidget(QLabel('Shortcut:'), 0, 0)  # row, column
        grid.addWidget(self.shortcut_edit, 0, 1)
        grid.addWidget(clearButton, 0, 2)
        grid.addWidget(buttonBox, 1, 0, 1, 2, Qt.AlignRight)  # fromRow, fromColumn, rowSpan, columnSpan.
        self.setLayout(grid)
        self.setWindowTitle(EDIT_QUICKLINK)

    def apply(self):
        self.parent.item_model.set_data(self.shortcut_edit.keySequence().toString(), item_id=self.item.id, column=0, field=model.SHORTCUT)
        self.parent.fill_bookmarkShortcutsMenu()
        super(ShortcutDialog, self).accept()


class RenameTagDialog(QDialog):
    def __init__(self, parent, tag):
        super(RenameTagDialog, self).__init__(parent)
        self.parent = parent
        self.tag = tag
        self.line_edit = QLineEdit(tag)
        buttonBox = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Cancel)

        grid = QGridLayout()
        grid.addWidget(QLabel('Enter new tag name:'), 0, 0)  # row, column
        grid.addWidget(self.line_edit, 0, 1)
        grid.addWidget(buttonBox, 1, 0, 1, 2, Qt.AlignRight)  # fromRow, fromColumn, rowSpan, columnSpan.
        self.setLayout(grid)
        buttonBox.button(QDialogButtonBox.Apply).clicked.connect(self.apply)
        buttonBox.button(QDialogButtonBox.Cancel).clicked.connect(self.reject)
        self.setWindowTitle(self.tr('Rename tag'))

    def apply(self):
        self.parent.rename_tag(self.tag, self.line_edit.text())
        super(RenameTagDialog, self).accept()


class SettingsDialog(QDialog):
    def __init__(self, parent):
        super(SettingsDialog, self).__init__(parent)
        self.parent = parent
        theme_dropdown = QComboBox()
        theme_dropdown.addItems(['Light', 'Dark'])
        current_palette_index = 0 if QApplication.palette() == self.parent.light_palette else 1
        theme_dropdown.setCurrentIndex(current_palette_index)
        theme_dropdown.currentIndexChanged[int].connect(self.change_theme)

        grid = QGridLayout()
        grid.addWidget(QLabel('UI Theme:'), 0, 0)  # row, column
        grid.addWidget(theme_dropdown, 0, 1)
        grid.setContentsMargins(20, 20, 20, 20)
        self.setLayout(grid)
        self.setWindowTitle(self.tr('Preferences'))

    def change_theme(self, current_palette_index):
        if current_palette_index == 0:
            new_palette = self.parent.light_palette
        else:
            new_palette = self.parent.dark_palette
        QApplication.setPalette(new_palette)
        self.parent.focused_column().focus_button.setPalette(new_palette)
        self.parent.focused_column().bookmark_button.setPalette(new_palette)
        self.parent.focused_column().search_bar.setPalette(new_palette)
        self.parent.focused_column().view.setPalette(new_palette)
        self.parent.focused_column().view.verticalScrollBar().setPalette(new_palette)
        self.parent.focused_column().view.header().setPalette(new_palette)


class DatabaseDialog(QDialog):
    # if index is set: edit existing database. else: create new database
    def __init__(self, parent, index=None):
        super(DatabaseDialog, self).__init__(parent)
        self.setMinimumWidth(910)
        self.parent = parent
        self.index = index
        name = ''
        url = ''
        database_name = ''
        if index is not None:
            server = parent.server_model.get_server(index)
            name = server.bookmark_name
            url = server.url
            database_name = server.database_name
        self.bookmark_name_edit = QLineEdit(name)
        self.url_edit = QLineEdit(url)
        self.database_name_edit = QLineEdit(database_name)
        self.database_name_edit.setPlaceholderText('Different to existing database names. Only lowercase characters (a-z), digits (0-9) or _ allowed.')

        buttonBox = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Cancel)

        grid = QGridLayout()
        grid.addWidget(QLabel('Database bookmark name:'), 0, 0)  # row, column
        grid.addWidget(QLabel('URL:'), 1, 0)
        grid.addWidget(QLabel('Database name:'), 2, 0)
        grid.addWidget(self.bookmark_name_edit, 0, 1)
        grid.addWidget(self.url_edit, 1, 1)
        grid.addWidget(self.database_name_edit, 2, 1)
        grid.addWidget(buttonBox, 3, 0, 1, 2, Qt.AlignRight)  # fromRow, fromColumn, rowSpan, columnSpan.
        self.setLayout(grid)
        buttonBox.button(QDialogButtonBox.Apply).clicked.connect(self.apply)
        buttonBox.button(QDialogButtonBox.Cancel).clicked.connect(self.reject)
        if self.index is None:
            self.setWindowTitle(CREATE_DB)
        else:
            self.setWindowTitle(EDIT_DB)

    def apply(self):
        if self.index is None:
            new_server = server_model.Server(self.bookmark_name_edit.text(), self.url_edit.text(), self.database_name_edit.text())
            self.parent.server_model.add_server(new_server)
        else:
            self.parent.server_model.set_data(self.index, self.bookmark_name_edit.text(), self.url_edit.text(), self.database_name_edit.text())
        super(DatabaseDialog, self).accept()


class DelayedExecutionTimer(QObject):  # source: https://wiki.qt.io/Delay_action_to_wait_for_user_interaction
    triggered = pyqtSignal(str)

    def __init__(self, parent):
        super(DelayedExecutionTimer, self).__init__(parent)
        self.minimumDelay = 200  # The minimum delay is the time the class will wait after being triggered before emitting the triggered() signal
        self.maximumDelay = 500  # The maximum delay is the maximum time that will pass before a call to the trigger() slot leads to a triggered() signal.
        self.minimumTimer = QTimer(self)
        self.maximumTimer = QTimer(self)
        self.minimumTimer.timeout.connect(self.timeout)
        self.maximumTimer.timeout.connect(self.timeout)

    def timeout(self):
        self.minimumTimer.stop()
        self.maximumTimer.stop()
        self.triggered.emit(self.string)

    def trigger(self, string):
        self.string = string
        if not self.maximumTimer.isActive():
            self.maximumTimer.start(self.maximumDelay)
        self.minimumTimer.stop()
        self.minimumTimer.start(self.minimumDelay)


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
    app.setApplicationName(QApplication.translate('main', 'TreeNoteeee'))
    app.setWindowIcon(QIcon(':/icon.png'))

    form = MainWindow()
    form.show()
    app.exec_()
