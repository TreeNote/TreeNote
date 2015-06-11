# -*- coding: utf-8 -*-
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

import socket
import webbrowser
import re
import subprocess
import sys
from functools import partial
import json
import time

import sip # for pyinstaller
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import couchdb

import qrc_resources
import model
import server_model
import tag_model
import dump

EDIT_BOOKMARK = 'Edit bookmark'
EDIT_QUICKLINK = 'Edit quick link shortcut'
EXPANDED_ITEMS_DICT = 'EXPANDED_ITEMS'
EXPANDED_QUICKLINKS = 'EXPANDED_QUICKLINKS'
SELECTED_ID = 'SELECTED_ID'
CREATE_DB = 'Create bookmark to a database server'
EDIT_DB = 'Edit selected database bookmark'
DEL_DB = 'Delete selected database bookmark'
IMPORT_DB = 'Import into a new  database'


class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        try:  # catch db connect errors
            app.focusChanged.connect(self.update_actions)

            app.setStyle("Fusion")
            self.light_palette = app.palette()

            self.dark_palette = QPalette()
            self.dark_palette.setColor(QPalette.Window, model.FOREGROUND_GRAY)
            self.dark_palette.setColor(QPalette.WindowText, model.TEXT_GRAY)
            self.dark_palette.setColor(QPalette.Base, model.BACKGROUND_GRAY)
            self.dark_palette.setColor(QPalette.AlternateBase, model.ALTERNATE_BACKGROUND_GRAY)
            self.dark_palette.setColor(QPalette.ToolTipBase, model.TEXT_GRAY)
            self.dark_palette.setColor(QPalette.ToolTipText, model.TEXT_GRAY)
            self.dark_palette.setColor(QPalette.Text, model.TEXT_GRAY)
            self.dark_palette.setColor(QPalette.Button, model.FOREGROUND_GRAY)
            self.dark_palette.setColor(QPalette.ButtonText, model.TEXT_GRAY)
            self.dark_palette.setColor(QPalette.BrightText, Qt.red)
            self.dark_palette.setColor(QPalette.Link, QColor('#8A9ADD'))  # light blue
            self.dark_palette.setColor(QPalette.Highlight, model.SELECTION_GRAY)
            self.dark_palette.setColor(QPalette.HighlightedText, model.TEXT_GRAY)
            self.dark_palette.setColor(QPalette.ToolTipBase, model.FOREGROUND_GRAY)
            self.dark_palette.setColor(QPalette.ToolTipText, model.TEXT_GRAY)

            # font = QFont('Arial', 16)
            # app.setFont(font)

            self.expanded_ids_list_dict = {}  # for restoring the expanded state after a search
            self.removed_id_expanded_state_dict = {}  # remember expanded state when moving horizontally (removing then adding at other place)
            self.old_search_text = ''  # used to detect if user leaves "just focused" state. when that's the case, expanded states are saved

            self.server_model = server_model.ServerModel()

            # load databases
            settings = QSettings()
            servers = settings.value('databases')  # second value is loaded, if nothing was saved before in the settings

            def add_db(bookmark_name, url, db_name, db):
                new_server = server_model.Server(bookmark_name, url, db_name, db)
                new_server.model.db_change_signal[dict, QAbstractItemModel].connect(self.db_change_signal)
                self.server_model.add_server(new_server)

            if servers is None:
                def load_db_from_file(bookmark_name, db_name):
                    db = self.get_db('', db_name, create_root=False)
                    with open(db_name + '.txt', 'r') as file:
                        doc_list = json.load(file)
                        db.update(doc_list)
                    add_db(bookmark_name, '', db_name, db)

                load_db_from_file('Manual', 'manual')
                load_db_from_file('Local', 'local')

                db = self.get_db('', 'local_bookmarks', create_root=False)
                with open('local_bookmarks.txt', 'r') as file:
                    doc_list = json.load(file)
                    db.update(doc_list)
            else:
                for bookmark_name, url, db_name in servers:
                    add_db(bookmark_name, url, db_name, self.get_db(url, db_name, db_name))

            self.item_model = self.server_model.servers[0].model

            self.bookmark_model = model.TreeModel(self.get_db('', 'local_bookmarks'), header_list=['Bookmarks'])
            self.bookmark_model.db_change_signal[dict, QAbstractItemModel].connect(self.db_change_signal)

            self.mainSplitter = QSplitter(Qt.Horizontal)
            self.mainSplitter.setHandleWidth(0)  # thing to grab the splitter

            # first column

            self.servers_view = QTreeView()
            self.servers_view.setModel(self.server_model)
            self.servers_view.selectionModel().currentChanged.connect(self.change_active_database)
            self.servers_view.setContextMenuPolicy(Qt.CustomContextMenu)
            self.servers_view.customContextMenuRequested.connect(self.open_edit_server_contextmenu)

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
            self.hideTagsCheckBox = QCheckBox('Hide rows with a tag')
            self.hideTagsCheckBox.clicked.connect(self.filter_hide_tags)
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
            layout.addWidget(self.hideTagsCheckBox, 5, 0, 1, 2)
            layout.addWidget(self.hideFutureStartdateCheckBox, 6, 0, 1, 2)
            layout.addWidget(self.showOnlyStartdateCheckBox, 7, 0, 1, 2)
            layout.setColumnStretch(1, 10)
            bookmarks_holder.setLayout(layout)

            self.tag_view = QTreeView()
            self.tag_view.setContextMenuPolicy(Qt.CustomContextMenu)
            self.tag_view.customContextMenuRequested.connect(self.open_rename_tag_contextmenu)
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

            # list of actions which depend on a specific view
            self.item_view_actions = []
            self.tag_view_actions = []
            self.bookmark_view_actions = []
            self.quick_links_view_actions = []
            self.all_actions = []

            def add_action(name, qaction, list=None):
                setattr(self, name, qaction)
                self.all_actions.append(qaction)
                if list is not None:
                    list.append(qaction)

            add_action('addDatabaseAct', QAction(self.tr(CREATE_DB), self, triggered=lambda: DatabaseDialog(self).exec_()))
            add_action('deleteDatabaseAct', QAction(self.tr(DEL_DB), self, triggered=lambda: self.server_model.delete_server(self.servers_view.selectionModel().currentIndex())))
            add_action('editDatabaseAct', QAction(self.tr(EDIT_DB), self, triggered=lambda: DatabaseDialog(self, index=self.servers_view.selectionModel().currentIndex()).exec_()))
            add_action('exportDatabaseAct', QAction(self.tr('Export selected database'), self, triggered=self.export_db))
            add_action('importDatabaseAct', QAction(self.tr(IMPORT_DB), self, triggered=self.import_db))
            add_action('settingsAct', QAction(self.tr('Preferences'), self, shortcut='Ctrl+,', triggered=lambda: SettingsDialog(self).exec_()))
            add_action('aboutAct', QAction(self.tr('&About'), self, triggered=lambda: AboutBox().exec()))
            # add_action('unsplitWindowAct', QAction(self.tr('&Unsplit window'), self, shortcut='Ctrl+Shift+S', triggered=self.unsplit_window))
            # add_action('splitWindowAct', QAction(self.tr('&Split window'), self, shortcut='Ctrl+S', triggered=self.split_window))
            add_action('editRowAction', QAction(self.tr('&Edit row'), self, shortcut='Tab', triggered=self.edit_row), list=self.item_view_actions)
            add_action('deleteSelectedRowsAction', QAction(self.tr('&Delete selected rows'), self, shortcut='delete', triggered=self.removeSelection), list=self.item_view_actions)
            add_action('insertRowAction', QAction(self.tr('&Insert row'), self, shortcut='Return', triggered=self.insert_row), list=self.item_view_actions)
            add_action('insertChildAction', QAction(self.tr('&Insert child'), self, shortcut='Shift+Return', triggered=self.insert_child), list=self.item_view_actions)
            add_action('moveUpAction', QAction(self.tr('&Up'), self, shortcut='W', triggered=self.move_up), list=self.item_view_actions)
            add_action('moveDownAction', QAction(self.tr('&Down'), self, shortcut='S', triggered=self.move_down), list=self.item_view_actions)
            add_action('moveLeftAction', QAction(self.tr('&Left'), self, shortcut='A', triggered=self.move_left), list=self.item_view_actions)
            add_action('moveRightAction', QAction(self.tr('&Right'), self, shortcut='D', triggered=self.move_right), list=self.item_view_actions)
            add_action('expandAllChildrenAction', QAction(self.tr('&Expand all children'), self, shortcut='Alt+Right', triggered=self.expand_all_children_of_selected_rows), list=self.item_view_actions)
            add_action('collapseAllChildrenAction', QAction(self.tr('&Collapse all children'), self, shortcut='Alt+Left', triggered=self.collapse_all_children_of_selected_rows), list=self.item_view_actions)
            add_action('focusSearchBarAction', QAction(self.tr('&Focus search bar'), self, shortcut='Ctrl+F', triggered=lambda: self.focused_column().search_bar.setFocus()))
            add_action('colorGreenAction', QAction('&Green', self, shortcut='G', triggered=lambda: self.color_row('g')), list=self.item_view_actions)
            add_action('colorYellowAction', QAction('&Yellow', self, shortcut='Y', triggered=lambda: self.color_row('y')), list=self.item_view_actions)
            add_action('colorBlueAction', QAction('&Blue', self, shortcut='B', triggered=lambda: self.color_row('b')), list=self.item_view_actions)
            add_action('colorRedAction', QAction('&Red', self, shortcut='R', triggered=lambda: self.color_row('r')), list=self.item_view_actions)
            add_action('colorOrangeAction', QAction('&Orange', self, shortcut='O', triggered=lambda: self.color_row('o')), list=self.item_view_actions)
            add_action('colorNoColorAction', QAction('&No color', self, shortcut='N', triggered=lambda: self.color_row('n')), list=self.item_view_actions)
            add_action('toggleTaskAction', QAction(self.tr('&Toggle: note, todo, done'), self, shortcut='Space', triggered=self.toggle_task), list=self.item_view_actions)
            add_action('openLinkAction', QAction(self.tr('&Open selected rows with URLs'), self, shortcut='L', triggered=self.open_links), list=self.item_view_actions)
            add_action('renameTagAction', QAction(self.tr('&Rename tag'), self, triggered=lambda: RenameTagDialog(self, self.tag_view.currentIndex().data()).exec_()), list=self.tag_view_actions)
            add_action('editBookmarkAction', QAction(self.tr(EDIT_BOOKMARK), self, triggered=lambda: BookmarkDialog(self, index=self.bookmarks_view.selectionModel().currentIndex()).exec_()), list=self.bookmark_view_actions)
            add_action('moveBookmarkUpAction', QAction(self.tr('Move bookmark up'), self, triggered=self.move_bookmark_up), list=self.bookmark_view_actions)
            add_action('moveBookmarkDownAction', QAction(self.tr('Move bookmark down'), self, triggered=self.move_bookmark_down), list=self.bookmark_view_actions)
            add_action('deleteBookmarkAction', QAction(self.tr('Delete selected bookmarks'), self, triggered=self.removeBookmarkSelection), list=self.bookmark_view_actions)
            add_action('editShortcutAction', QAction(self.tr(EDIT_QUICKLINK), self, triggered=lambda: ShortcutDialog(self, self.quicklinks_view.selectionModel().currentIndex()).exec_()), list=self.quick_links_view_actions)
            add_action('resetViewAction', QAction(self.tr('&Reset view'), self, shortcut='esc', triggered=self.reset_view))
            add_action('toggleProjectAction', QAction(self.tr('&Toggle: note, sequential project, parallel project, paused project'), self, shortcut='P', triggered=self.toggle_project), list=self.item_view_actions)
            add_action('appendRepeatAction', QAction(self.tr('&Repeat'), self, triggered=self.append_repeat), list=self.item_view_actions)
            add_action('undoAction', self.item_model.undoStack.createUndoAction(self))
            self.undoAction.setShortcut('CTRL+Z')
            add_action('redoAction', self.item_model.undoStack.createRedoAction(self))
            self.redoAction.setShortcut('CTRL+Shift+Z')

            self.databasesMenu = self.menuBar().addMenu(self.tr('Databases list'))
            self.databasesMenu.addAction(self.addDatabaseAct)
            self.databasesMenu.addAction(self.deleteDatabaseAct)
            self.databasesMenu.addAction(self.editDatabaseAct)
            self.databasesMenu.addAction(self.exportDatabaseAct)
            self.databasesMenu.addAction(self.importDatabaseAct)

            self.fileMenu = self.menuBar().addMenu(self.tr('Current database'))
            self.fileMenu.addAction(self.undoAction)
            self.fileMenu.addAction(self.redoAction)
            self.fileMenu.addAction(self.editShortcutAction)
            self.fileMenu.addAction(self.editBookmarkAction)
            self.fileMenu.addAction(self.deleteBookmarkAction)
            self.fileMenu.addAction(self.moveBookmarkUpAction)
            self.fileMenu.addAction(self.moveBookmarkDownAction)
            self.fileMenu.addAction(self.renameTagAction)
            self.fileMenu.addAction(self.settingsAct)

            self.structureMenu = self.menuBar().addMenu(self.tr('&Edit structure'))
            self.structureMenu.addAction(self.insertRowAction)
            self.structureMenu.addAction(self.insertChildAction)
            self.structureMenu.addAction(self.deleteSelectedRowsAction)

            self.moveMenu = self.structureMenu.addMenu(self.tr('&Move selected rows'))
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
                for action in self.all_actions:
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
            self.update_actions()

            # restore previous position etc
            self.resize(settings.value('size', QSize(800, 600)))
            self.move(settings.value('pos', QPoint(200, 200)))

            mainSplitter_state = settings.value('mainSplitter')
            if mainSplitter_state is not None:
                self.mainSplitter.restoreState(mainSplitter_state)

            first_column_splitter_state = settings.value('first_column_splitter')
            if first_column_splitter_state is not None:
                self.first_column_splitter.restoreState(first_column_splitter_state)

            # restore selected database
            last_db_name = settings.value('database')
            if last_db_name is not None:
                for idx, server in enumerate(self.server_model.servers):
                    if server.bookmark_name == last_db_name:
                        server_index = self.server_model.index(idx, 0, QModelIndex())
                        break
            else:
                server_index = self.server_model.index(0, 0, QModelIndex())  # top_most_index
            self.servers_view.selectionModel().setCurrentIndex(server_index, QItemSelectionModel.ClearAndSelect)
            self.change_active_database(server_index)

            # restore expanded item states
            expanded_ids_list_dict = settings.value(EXPANDED_ITEMS_DICT)
            if expanded_ids_list_dict is not None:  # and last_db_name in self.expanded_ids_list_dict:
                self.expanded_ids_list_dict = expanded_ids_list_dict
                self.expand_saved()

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

            # restore palette
            palette = settings.value('theme')
            if palette is not None:
                palette = self.light_palette if palette == 'light' else self.dark_palette
            else:
                palette = self.dark_palette  # standard theme
            self.set_palette(palette)
        except Exception as e:
            print(e)  # exception handling is in get_db

    def expand_saved(self):
        current_server_name = self.get_current_server().bookmark_name
        if current_server_name in self.expanded_ids_list_dict:
            for item_id in self.expanded_ids_list_dict[current_server_name]:
                if item_id in self.item_model.id_index_dict:
                    index = self.item_model.id_index_dict[item_id]
                    proxy_index = self.filter_proxy_index_from_model_index(QModelIndex(index))
                    self.focused_column().view.expand(proxy_index)

    def set_palette(self, new_palette):
        QApplication.setPalette(new_palette)
        self.focused_column().focus_button.setPalette(new_palette)
        self.focused_column().bookmark_button.setPalette(new_palette)
        self.focused_column().search_bar.setPalette(new_palette)
        self.focused_column().view.setPalette(new_palette)
        self.focused_column().view.verticalScrollBar().setPalette(new_palette)
        self.focused_column().view.header().setPalette(new_palette)

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

    def export_db(self):
        proposed_file_name = self.get_current_server().database_name + '_' + QDate.currentDate().toString('yyyy-MM-dd')
        file_name = QFileDialog.getSaveFileName(self, "Save", proposed_file_name + ".txt", "*.txt")
        with open(file_name[0], 'w') as file:
            row_list = []
            map = "function(doc) { \
            if (doc." + model.DELETED + " == '') \
                emit(doc, null); }"
            res = self.item_model.db.query(map, include_docs=True)
            file.write(json.dumps([row.doc for row in res], indent=4))

    def import_db(self):
        self.file_name = QFileDialog.getOpenFileName(self, "Open", "", "*.txt")
        if self.file_name[0] != '':
            DatabaseDialog(self, import_file_name=self.file_name[0]).exec_()

    def get_db(self, url, database_name, create_root=True):
        def get_create_db(self, url, new_db_name, connection_attempts=0):
            if url != '':
                server = couchdb.Server(url)
            else:  # local db
                server = couchdb.Server()
            try:
                return server, server[new_db_name]
            except couchdb.http.ResourceNotFound:
                new_db = server.create(new_db_name)
                if create_root:
                    new_db[model.ROOT_ID] = (model.NEW_DB_ITEM.copy())
                print("Database does not exist. Created the database.")
                return server, new_db
            except couchdb.http.Unauthorized as err:
                QMessageBox.warning(self, 'Unauthorized', '')
            except couchdb.http.ServerError as err:
                QMessageBox.warning(self, 'ServerError', '')
            except ConnectionRefusedError:
                print('couchdb ist not started yet, so wait and try to connect again')
                connection_attempts += 1
                if connection_attempts < 9:
                    time.sleep(0.3)
                    return get_create_db(self, url, new_db_name, connection_attempts=connection_attempts)
                else:
                    QMessageBox.warning(self, '', 'Could not connect to the server. Is the url correct?')
            except OSError:
                QMessageBox.warning(self, '', 'Could not connect to the server. Synchronisation is disabled. Local changes will be merged when you go online again.')
            except Exception as err:
                QMessageBox.warning(self, '', 'Unknown Error: Contact the developer.')

        local_server, local_db = get_create_db(self, '', database_name)

        # if new db is also on a server: enable replication
        if url != '':
            success = get_create_db(self, url, database_name)
            if success:
                local_server.replicate(database_name, url + database_name, continuous=True)
                local_server.replicate(url + database_name, database_name, continuous=True)
        return local_db

    def change_active_database(self, new_index, old_index=None):
        self.save_expanded_state(old_index)
        self.item_model = self.server_model.get_server(new_index).model
        self.focused_column().flat_proxy.setSourceModel(self.item_model)
        self.focused_column().filter_proxy.setSourceModel(self.item_model)
        self.quicklinks_view.setModel(self.item_model)
        self.quicklinks_view.setItemDelegate(model.BookmarkDelegate(self, self.item_model))
        self.old_search_text = 'dont save expanded states of next db when switching to next db'
        self.setup_tag_model()
        self.reset_view()

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
        settings.setValue(EXPANDED_ITEMS_DICT, self.expanded_ids_list_dict)

        # save expanded quicklinks
        expanded_quicklinks_id_list = []
        for index in self.item_model.persistentIndexList():
            if self.quicklinks_view.isExpanded(index):
                expanded_quicklinks_id_list.append(self.item_model.getItem(index).id)
        settings.setValue(EXPANDED_QUICKLINKS, expanded_quicklinks_id_list)

        # save selection
        current_index = self.focused_column().view.selectionModel().currentIndex()
        settings.setValue(SELECTED_ID, self.focused_column().filter_proxy.getItem(current_index).id)

        # save theme
        theme = 'light' if app.palette() == self.light_palette else 'dark'
        settings.setValue('theme', theme)

        # save selected database
        settings.setValue('database', self.get_current_server().bookmark_name)

        self.item_model.updater.terminate()

        if not __debug__:  # This constant is true if Python was not started with an -O option. -O turns on basic optimizations.
            if sys.platform == "darwin":
                subprocess.call(['osascript', '-e', 'tell application "Apache CouchDB" to quit'])

    def get_current_server(self, index=None):
        if index is None:
            index = self.servers_view.selectionModel().currentIndex()
        return self.server_model.get_server(index)

    def evoke_singlekey_action(self, action_name):  # fix shortcuts for mac
        for action in self.all_actions:
            if action.text() == action_name and action.isEnabled():
                action.trigger()
                break

    def update_actions(self):  # enable / disable menu items whether they are doable right now
        def toggle_actions(bool_focused, actions_list):
            for action in actions_list:
                action.setEnabled(bool_focused)

        toggle_actions(len(self.bookmarks_view.selectedIndexes()) > 0, self.bookmark_view_actions)
        toggle_actions(len(self.tag_view.selectedIndexes()) > 0, self.tag_view_actions)
        toggle_actions(len(self.quicklinks_view.selectedIndexes()) > 0, self.quick_links_view_actions)

        # focus is either in a dialog, in item_view or in the search bar
        # item actions should be enabled while editing a row, so:
        bool_item_view_focused = not self.focused_column().search_bar.hasFocus()
        for action in self.item_view_actions:
            action.setEnabled(bool_item_view_focused)

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
            self.filter(model.ONLY_START_DATE, 'all')

    @pyqtSlot(bool)
    def filter_hide_tags(self, filter_hide_tags):
        if filter_hide_tags:
            self.append_replace_to_searchbar(model.HIDE_TAGS, 'no')
        else:
            self.filter(model.HIDE_TAGS, 'all')

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
        self.set_searchbar_text_and_search(new_search_bar_text)
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
            search_bar_text = re.sub(' ' + key + r'(<|>|=|\w|\d)* ', '', search_bar_text)
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
        try:
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
                    # save and restore expanded state
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
                if my_edit:  # save expanded states
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

                # update id_index_dict
                child_index_list = []
                for child_position, child_item in enumerate(item.childItems):
                    child_index = source_model.index(child_position, 0, index)
                    source_model.id_index_dict[child_item.id] = QPersistentModelIndex(child_index)
                    source_model.pointer_set.add(child_index.internalId())
                    child_index_list.append((child_index, child_item.id))

                if my_edit:
                    # select first moved item
                    self.set_selection(index_first_moved_item, index_last_moved_item)

                    # restore expanded states
                    if not bool_moved_bookmark:
                        for child_index, child_item_id in child_index_list:
                            proxy_index = self.filter_proxy_index_from_model_index(child_index)
                            expanded_state = id_expanded_state_dict[child_item_id]
                            self.focused_column().view.setExpanded(proxy_index, expanded_state)

            elif method == model.DELETED:
                if source_model.db[item_id][model.DELETED] == '':
                    source_model.pointer_set.add(index.internalId())
                else:
                    source_model.pointer_set.remove(index.internalId())
                self.setup_tag_model()
        except Exception as e:
            QMessageBox.warning(self, '', 'Error when receiving changes: ' + str(e))

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
            self.focused_column().view.setFocus()  # after editing a date, the focus is lost

    def set_top_row_selected(self):
        current_root_index = self.focused_column().view.rootIndex()
        top_most_index = self.focused_column().filter_proxy.index(0, 0, current_root_index)
        self.set_selection(top_most_index, top_most_index)
        self.focused_column().view.setFocus()

    def reset_view(self):
        self.hideFutureStartdateCheckBox.setChecked(False)
        self.hideTagsCheckBox.setChecked(False)
        self.flattenViewCheckBox.setChecked(False)
        self.showOnlyStartdateCheckBox.setChecked(False)
        self.task_dropdown.setCurrentIndex(0)
        self.estimate_dropdown.setCurrentIndex(0)
        self.color_dropdown.setCurrentIndex(0)
        self.set_searchbar_text_and_search('')
        self.bookmarks_view.selectionModel().setCurrentIndex(QModelIndex(), QItemSelectionModel.ClearAndSelect)
        self.quicklinks_view.selectionModel().setCurrentIndex(QModelIndex(), QItemSelectionModel.ClearAndSelect)
        self.focused_column().view.setRootIndex(QModelIndex())

    def save_expanded_state(self, index=None):
        expanded_list_current_view = []
        current_server_name = self.get_current_server(index).bookmark_name
        for index in self.focused_column().filter_proxy.persistentIndexList():
            if self.focused_column().view.isExpanded(index):
                expanded_list_current_view.append(self.focused_column().filter_proxy.getItem(index).id)
        self.expanded_ids_list_dict[current_server_name] = expanded_list_current_view

    @pyqtSlot(str)
    def search(self, search_text):
        # before doing the search: save expanded states
        focus_pattern = re.compile(' ' + model.FOCUS + '\S* *$')  # '\S*' = any number of not Whitespaces. ' *' = any number of Whitespaces. '$' = end of string
        if self.old_search_text == '' or focus_pattern.match(self.old_search_text):
            self.save_expanded_state()
        self.old_search_text = search_text

        # sort
        if model.SORT in search_text:
            if model.ASC in search_text:
                order = Qt.DescendingOrder  # it's somehow reverted
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
                # changing dropdown index accordingly is not that easy, because changing it fires "color_clicked" which edits search bar

        # flatten + filter
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
            self.expand_saved()
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
        # show context menu only when clicked on an item, not when clicked on empty space
        if not index.isValid(): return
        menu = QMenu()
        menu.addAction(self.renameTagAction)
        menu.exec_(self.tag_view.viewport().mapToGlobal(point))

    @pyqtSlot(QPoint)
    def open_edit_bookmark_contextmenu(self, point):
        index = self.bookmarks_view.indexAt(point)
        if not index.isValid(): return
        menu = QMenu()
        menu.addAction(self.editBookmarkAction)
        menu.addAction(self.deleteBookmarkAction)
        menu.addAction(self.moveBookmarkUpAction)
        menu.addAction(self.moveBookmarkDownAction)
        menu.exec_(self.bookmarks_view.viewport().mapToGlobal(point))

    @pyqtSlot(QPoint)
    def open_edit_shortcut_contextmenu(self, point):
        index = self.quicklinks_view.indexAt(point)
        if not index.isValid(): return
        menu = QMenu()
        menu.addAction(self.editShortcutAction)
        menu.exec_(self.quicklinks_view.viewport().mapToGlobal(point))

    @pyqtSlot(QPoint)
    def open_edit_server_contextmenu(self, point):
        menu = QMenu()
        menu.addAction(self.addDatabaseAct)
        index = self.servers_view.indexAt(point)
        if index.isValid():
            menu.addAction(self.editDatabaseAct)
            menu.addAction(self.deleteDatabaseAct)
            menu.addAction(self.exportDatabaseAct)
        menu.addAction(self.importDatabaseAct)
        menu.exec_(self.servers_view.viewport().mapToGlobal(point))

    # structure menu actions

    def expand_all_children_of_selected_rows(self):
        self.expand_or_collapse_children(self.focused_column().view.selectionModel().selectedRows()[0], True)

    def collapse_all_children_of_selected_rows(self):
        self.expand_or_collapse_children(self.focused_column().view.selectionModel().selectedRows()[0], False)

    def move_bookmark_up(self):
        self.bookmark_model.move_vertical(self.bookmarks_view.selectedIndexes(), -1)

    def move_bookmark_down(self):
        self.bookmark_model.move_vertical(self.bookmarks_view.selectedIndexes(), 1)

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
        for row_index in self.focused_column().view.selectionModel().selectedRows():
            self.focused_column().filter_proxy.toggle_task(row_index)

    def toggle_project(self):
        for row_index in self.focused_column().view.selectionModel().selectedRows():
            self.focused_column().filter_proxy.toggle_project(row_index)

    def append_repeat(self):
        current_index = self.focused_column().view.selectionModel().currentIndex()
        self.focused_column().filter_proxy.set_data(current_index.data() + ' repeat=1w', index=current_index)
        self.edit_row()

    @pyqtSlot(str)
    def color_row(self, color_character):
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
            if url_list != []:
                for url in url_list:
                    if not url.startswith('http://'):
                        url = 'http://' + url
                    webbrowser.open(url)
            else:  # no urls found: search the web for the selected entry
                webbrowser.open('https://www.google.de/search?q=' + row_index.data())

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
        new_column.view.setAlternatingRowColors(True)
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
        new_column.view.selectionModel().selectionChanged.connect(self.update_actions)
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


class AboutBox(QDialog):
    def __init__(self):
        super(AboutBox, self).__init__()
        label = QLabel(self.tr('\
            TreeNote is a collaboratively usable outliner for personal knowledge and task management.<br>\
            <br>\
            Copyright (C) 2015 Jan Korte<br>\
            <br>\
            Contact me through <a href="http://www.treenote.de/">www.treenote.de</a> if you have ideas or problems!<br>\
            <br>\
            This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, version 3 of the License.<br>\
            <br>\
            I hope you enjoy this application. Consider a donation to my freedom-loving hoster <a href="http://www.wissenschaftsladen-dortmund.de/spenden/">Wissenschaftsladen Dortmund</a>.'))
        label.setOpenExternalLinks(True)
        label.setTextFormat(Qt.RichText)
        label.setWordWrap(True)
        buttonBox = QDialogButtonBox(QDialogButtonBox.Ok)
        buttonBox.button(QDialogButtonBox.Ok).clicked.connect(self.reject)
        grid = QGridLayout()
        grid.setContentsMargins(20, 20, 20, 20)
        grid.setSpacing(20)
        grid.addWidget(label, 0, 0)  # row, column
        grid.addWidget(buttonBox, 1, 0, 1, 1, Qt.AlignCenter)  # fromRow, fromColumn, rowSpan, columnSpan.
        self.setLayout(grid)


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
        self.parent.bookmark_model.set_data_with_id(self.name_edit.text(), item_id=item_id, column=0, field='text')
        self.parent.bookmark_model.set_data_with_id(self.search_bar_text_edit.text(), item_id=item_id, column=0, field=model.SEARCH_TEXT)
        self.parent.bookmark_model.set_data_with_id(self.shortcut_edit.keySequence().toString(), item_id=item_id, column=0, field=model.SHORTCUT)
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
        self.parent.item_model.set_data_with_id(self.shortcut_edit.keySequence().toString(), item_id=self.item.id, column=0, field=model.SHORTCUT)
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
        buttonBox = QDialogButtonBox(QDialogButtonBox.Close)
        buttonBox.button(QDialogButtonBox.Close).clicked.connect(self.close)

        grid = QGridLayout()
        grid.addWidget(QLabel('UI Theme:'), 0, 0)  # row, column
        grid.addWidget(theme_dropdown, 0, 1)
        grid.addWidget(buttonBox, 1, 0, 1, 2, Qt.AlignCenter)  # fromRow, fromColumn, rowSpan, columnSpan.
        grid.setContentsMargins(20, 20, 20, 20)
        grid.setSpacing(20)
        self.setLayout(grid)
        self.setWindowTitle(self.tr('Preferences'))

    def change_theme(self, current_palette_index):
        if current_palette_index == 0:
            new_palette = self.parent.light_palette
        else:
            new_palette = self.parent.dark_palette
        self.parent.set_palette(new_palette)


class DatabaseDialog(QDialog):
    # if index is set: edit existing database. else: create new database
    def __init__(self, parent, index=None, import_file_name=None):
        super(DatabaseDialog, self).__init__(parent)
        self.setMinimumWidth(910)
        self.parent = parent
        self.index = index
        self.import_file_name = import_file_name
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
        self.url_edit.setPlaceholderText('Leave empty for a local database.')
        self.database_name_edit = QLineEdit(database_name)
        self.database_name_edit.setPlaceholderText('Different to existing database names. Only lowercase characters (a-z), digits (0-9) or _ allowed.')

        buttonBox = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Cancel)

        grid = QGridLayout()
        grid.addWidget(QLabel('Database bookmark name:'), 0, 0)  # row, column
        grid.addWidget(QLabel('URL:'), 1, 0)
        grid.addWidget(QLabel('Database name:'), 2, 0)
        grid.addWidget(self.bookmark_name_edit, 0, 1)
        if index is None:
            grid.addWidget(self.url_edit, 1, 1)
            grid.addWidget(self.database_name_edit, 2, 1)
        else:  # don't allow edit of existing databases
            url_label = QLabel(url)
            url_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            grid.addWidget(url_label, 1, 1)
            database_label = QLabel(database_name)
            database_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            grid.addWidget(database_label, 2, 1)
        grid.addWidget(buttonBox, 3, 0, 1, 2, Qt.AlignRight)  # fromRow, fromColumn, rowSpan, columnSpan.
        self.setLayout(grid)
        buttonBox.button(QDialogButtonBox.Apply).clicked.connect(self.apply)
        buttonBox.button(QDialogButtonBox.Cancel).clicked.connect(self.reject)
        if import_file_name:
            self.setWindowTitle(IMPORT_DB)
        elif self.index is None:
            self.setWindowTitle(CREATE_DB)
        else:
            self.setWindowTitle(EDIT_DB)

    def apply(self):
        if self.index is None:
            url = self.url_edit.text()
            db_name = self.database_name_edit.text()
            if not re.search('^[a-z0-9_]+$', db_name):  # ^ is start of string, [] is a character class, + is preceding expression  one or more times, $ is end of string
                QMessageBox.warning(self, '', 'Only lowercase characters (a-z), digits (0-9) or _ allowed.')
                return
            if self.import_file_name:
                db = self.parent.get_db(url, db_name, create_root=False)
                with open(self.import_file_name, 'r') as file:
                    doc_list = json.load(file)
                    db.update(doc_list)
            else:
                db = self.parent.get_db(url, db_name)
            new_server = server_model.Server(self.bookmark_name_edit.text(), url, db_name, db)
            new_server.model.db_change_signal[dict, QAbstractItemModel].connect(self.parent.db_change_signal)
            self.parent.server_model.add_server(new_server)
            new_index = self.parent.server_model.index(len(self.parent.server_model.servers) - 1, 0, QModelIndex())
            self.parent.servers_view.selectionModel().setCurrentIndex(new_index, QItemSelectionModel.ClearAndSelect)
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
    if sys.platform == "darwin":
        subprocess.call(['/usr/bin/open', '/Applications/Apache CouchDB.app'])

    app = QApplication(sys.argv)
    app.setApplicationName(QApplication.translate('main', 'TreeNote'))
    app.setWindowIcon(QIcon(':/icon'))

    form = MainWindow()
    form.show()
    app.exec_()
