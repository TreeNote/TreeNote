#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#################################################################################
# TreeNote
# A collaboratively usable outliner for personal knowledge and task management.
#
# Copyright (C) 2015 Jan Korte (j.korte@me.com)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3 of the License.
#################################################################################

import json
import logging
import os
import re
import socket
import subprocess
import sys
import textwrap
import time
import traceback
from functools import partial
#
import json
import threading
import requests
import sip  # needed for pyinstaller, get's removed with 'optimize imports'!
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from resources import qrc_resources  # get's removed with 'optimize imports'!
#
import model
import tag_model
import util
import version

HIDE_SHOW_THE_SIDEBARS = 'Hide / show the sidebars'

if __debug__:
    from pprint import pprint

COLUMNS_HIDDEN = 'columns_hidden'
EDIT_BOOKMARK = 'Edit selected bookmark'
EDIT_QUICKLINK = 'Edit selected quick link shortcut'
EXPANDED_ITEMS = 'EXPANDED_ITEMS'
EXPANDED_QUICKLINKS_INDEXES = 'EXPANDED_QUICKLINKS'
SELECTED_INDEX = 'SELECTED_ID'
IMPORT_DB = 'Import JSON file into a new  database'
APP_FONT_SIZE = 17 if sys.platform == "darwin" else 14
INITIAL_SIDEBAR_WIDTH = 200

RESOURCE_FOLDER = os.path.dirname(os.path.realpath(__file__)) + os.sep + 'resources' + os.sep

logging.basicConfig(filename=os.path.dirname(os.path.realpath(__file__)) + os.sep + 'treenote.log',
                    format='%(asctime)s - %(levelname)s - %(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)


def git_tag_to_versionnr(git_tag):
    return int(re.sub(r'\.|v', '', git_tag))


class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        app.setStyle("Fusion")
        self.light_palette = app.palette()
        self.light_palette.setColor(QPalette.Highlight, model.SELECTION_LIGHT_BLUE)
        self.light_palette.setColor(QPalette.AlternateBase, model.ALTERNATE_BACKGROUND_GRAY_LIGHT)

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

        # used to detect if user leaves "just focused" state. when that's the case, expanded states are saved
        self.old_search_text = ''

        self.flatten = False

        # load databases
        settings = self.getQSettings()

        last_opened_file_path = settings.value('last_opened_file_path', os.path.dirname(os.path.realpath(__file__))
                                               + os.sep + 'example_tree.json')
        self.open_file(last_opened_file_path)

        app.focusChanged.connect(self.update_actions)

        # set font-size and padding
        # second value is loaded, if nothing was saved before in the settings
        self.interface_fontsize = int(settings.value('interface_fontsize', APP_FONT_SIZE))
        app.setFont(QFont(model.FONT, self.interface_fontsize))
        # second value is loaded, if nothing was saved before in the settings
        self.fontsize = int(settings.value('fontsize', APP_FONT_SIZE))
        self.padding = int(settings.value('padding', 2))

        self.mainSplitter = QSplitter(Qt.Horizontal)
        self.mainSplitter.setHandleWidth(0)  # thing to grab the splitter

        # first column

        self.quicklinks_view = QTreeView()
        self.quicklinks_view.setModel(self.item_model)
        self.quicklinks_view.setItemDelegate(model.BookmarkDelegate(self, self.item_model))
        self.quicklinks_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.quicklinks_view.customContextMenuRequested.connect(self.open_edit_shortcut_contextmenu)
        self.quicklinks_view.clicked.connect(lambda i: self.focus_index(self.filter_proxy_index_from_model_index(i)))
        self.quicklinks_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.quicklinks_view.setHeader(CustomHeaderView('Quick links'))
        self.quicklinks_view.header().setToolTip('Focus on the clicked row')
        self.quicklinks_view.hideColumn(1)
        self.quicklinks_view.hideColumn(2)
        self.quicklinks_view.setUniformRowHeights(True)  # improves performance
        self.quicklinks_view.setAnimated(True)

        self.bookmarks_view = QTreeView()
        self.bookmarks_view.setModel(self.bookmark_model)
        self.bookmarks_view.setItemDelegate(model.BookmarkDelegate(self, self.bookmark_model))
        self.bookmarks_view.clicked.connect(self.filter_bookmark)
        self.bookmarks_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.bookmarks_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.bookmarks_view.customContextMenuRequested.connect(self.open_edit_bookmark_contextmenu)
        self.bookmarks_view.hideColumn(1)
        self.bookmarks_view.hideColumn(2)
        self.bookmarks_view.setUniformRowHeights(True)  # improves performance
        filters_holder = QWidget()  # needed to add space
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 11, 0, 0)  # left, top, right, bottom
        layout.addWidget(self.bookmarks_view)
        filters_holder.setLayout(layout)

        self.first_column_splitter = QSplitter(Qt.Vertical)
        self.first_column_splitter.setHandleWidth(0)
        self.first_column_splitter.setChildrenCollapsible(False)
        self.first_column_splitter.addWidget(self.quicklinks_view)
        self.first_column_splitter.addWidget(filters_holder)
        self.first_column_splitter.setContentsMargins(0, 11, 6, 0)  # left, top, right, bottom
        self.first_column_splitter.setStretchFactor(0, 6)  # when the window is resized, only quick links shall grow
        self.first_column_splitter.setStretchFactor(1, 0)
        self.first_column_splitter.setSizes([100, 200])

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
        self.color_dropdown = init_dropdown('c=', self.tr('all'), self.tr('green'), self.tr('yellow'),
                                            self.tr('blue'), self.tr('red'), self.tr('orange'), self.tr('no color'))

        self.flattenViewCheckBox = QCheckBox('Flatten view')
        self.flattenViewCheckBox.clicked.connect(self.filter_flatten_view)
        self.hideTagsCheckBox = QCheckBox('Hide rows with a tag')
        self.hideTagsCheckBox.clicked.connect(self.filter_hide_tags)
        self.hideFutureStartdateCheckBox = QCheckBox('Hide rows with future start date')
        self.hideFutureStartdateCheckBox.clicked.connect(self.filter_hide_future_startdate)
        self.showOnlyStartdateCheckBox = QCheckBox('Show only rows with a start date')
        self.showOnlyStartdateCheckBox.clicked.connect(self.filter_show_only_startdate)

        filters_holder = QWidget()  # needed to add space
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
        filters_holder.setLayout(layout)

        self.tag_view = QTreeView()
        self.tag_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tag_view.customContextMenuRequested.connect(self.open_rename_tag_contextmenu)
        self.tag_view.setModel(tag_model.TagModel())
        self.tag_view.selectionModel().selectionChanged.connect(self.filter_tag)
        self.tag_view.setUniformRowHeights(True)  # improves performance
        self.tag_view.setStyleSheet('QTreeView:item { padding: ' + str(
            model.SIDEBARS_PADDING + model.SIDEBARS_PADDING_EXTRA_SPACE) + 'px; }')
        self.tag_view.setAnimated(True)

        third_column = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(6, 6, 0, 0)  # left, top, right, bottom
        layout.addWidget(filters_holder)
        layout.addWidget(self.tag_view)
        third_column.setLayout(layout)

        # add columns to main

        self.mainSplitter.addWidget(self.first_column_splitter)
        self.mainSplitter.addWidget(self.item_views_splitter)
        self.mainSplitter.addWidget(third_column)
        self.mainSplitter.setStretchFactor(0, 0)  # first column has a share of 2
        self.mainSplitter.setStretchFactor(1, 6)
        self.mainSplitter.setStretchFactor(2, 0)
        self.mainSplitter.setSizes([INITIAL_SIDEBAR_WIDTH, 500, 1])
        self.setCentralWidget(self.mainSplitter)

        # list of actions which depend on a specific view
        self.item_view_actions = []
        self.item_view_not_editing_actions = []
        self.tag_view_actions = []
        self.bookmark_view_actions = []
        self.quick_links_view_actions = []
        self.all_actions = []

        def add_action(name, qaction, list=None):
            setattr(self, name, qaction)
            self.all_actions.append(qaction)
            if list is not None:
                list.append(qaction)

        add_action('exportDatabaseAct', QAction(self.tr('as JSON file'), self, triggered=self.export_db))
        add_action('importDatabaseAct', QAction(self.tr(IMPORT_DB), self, triggered=self.import_db))
        add_action('settingsAct', QAction(self.tr('Preferences...'), self, shortcut='Ctrl+,',
                                          triggered=lambda: SettingsDialog(self).exec_()))
        add_action('updateAct',
                   QAction(self.tr('Check for Updates...'), self, triggered=lambda: UpdateDialog(self).exec()))
        add_action('aboutAct', QAction(self.tr('About...'), self, triggered=lambda: AboutBox(self).exec()))
        # add_action('unsplitWindowAct', QAction(self.tr('Unsplit window'),
        #            self, shortcut='Ctrl+Shift+S', triggered=self.unsplit_window))
        # add_action('splitWindowAct', QAction(self.tr('Split window'),
        #            self, shortcut='Ctrl+S', triggered=self.split_window))
        add_action('editRowAction', QAction(self.tr('Edit row'), self, shortcut='Tab', triggered=self.edit_row),
                   list=self.item_view_actions)
        add_action('deleteSelectedRowsAction', QAction(self.tr('Delete selected rows'), self, shortcut='delete',
                                                       triggered=self.remove_selection),
                   list=self.item_view_actions)
        add_action('insertRowAction',
                   QAction(self.tr('Insert row'), self, shortcut='Return', triggered=self.insert_row))
        add_action('insertChildAction',
                   QAction(self.tr('Insert child'), self, shortcut='Shift+Return', triggered=self.insert_child),
                   list=self.item_view_actions)
        add_action('moveUpAction', QAction(self.tr('Up'), self, shortcut='W', triggered=self.move_up),
                   list=self.item_view_actions)
        add_action('moveDownAction', QAction(self.tr('Down'), self, shortcut='S', triggered=self.move_down),
                   list=self.item_view_actions)
        add_action('moveLeftAction', QAction(self.tr('Left'), self, shortcut='A', triggered=self.move_left),
                   list=self.item_view_actions)
        add_action('moveRightAction', QAction(self.tr('Right'), self, shortcut='D', triggered=self.move_right),
                   list=self.item_view_actions)
        add_action('expandAllChildrenAction', QAction(self.tr('Expand all children'), self, shortcut='Alt+Right',
                                                      triggered=lambda: self.expand_or_collapse_children_selected(
                                                          True)), list=self.item_view_not_editing_actions)
        add_action('collapseAllChildrenAction', QAction(self.tr('Collapse all children'), self, shortcut='Alt+Left',
                                                        triggered=lambda: self.expand_or_collapse_children_selected(
                                                            False)), list=self.item_view_not_editing_actions)
        add_action('focusSearchBarAction', QAction(self.tr('Focus search bar'), self, shortcut='Ctrl+F',
                                                   triggered=lambda: self.focused_column().search_bar.setFocus()))
        add_action('colorGreenAction', QAction('Green', self, shortcut='G', triggered=lambda: self.color_row('g')),
                   list=self.item_view_actions)
        add_action('colorYellowAction',
                   QAction('Yellow', self, shortcut='Y', triggered=lambda: self.color_row('y')),
                   list=self.item_view_actions)
        add_action('colorBlueAction', QAction('Blue', self, shortcut='B', triggered=lambda: self.color_row('b')),
                   list=self.item_view_actions)
        add_action('colorRedAction', QAction('Red', self, shortcut='R', triggered=lambda: self.color_row('r')),
                   list=self.item_view_actions)
        add_action('colorOrangeAction',
                   QAction('Orange', self, shortcut='O', triggered=lambda: self.color_row('o')),
                   list=self.item_view_actions)
        add_action('colorNoColorAction',
                   QAction('No color', self, shortcut='N', triggered=lambda: self.color_row('n')),
                   list=self.item_view_actions)
        add_action('toggleTaskAction',
                   QAction(self.tr('Toggle: note, todo, done'), self, shortcut='Space', triggered=self.toggle_task),
                   list=self.item_view_actions)
        add_action('openLinkAction', QAction(self.tr('Open selected rows containing URLs'), self, shortcut='L',
                                             triggered=self.open_links), list=self.item_view_actions)
        add_action('renameTagAction',
                   QAction(self.tr('Rename selected tag'), self, triggered=lambda: RenameTagDialog(
                       self, self.tag_view.currentIndex().data()).exec_()), list=self.tag_view_actions)
        add_action('editBookmarkAction',
                   QAction(self.tr(EDIT_BOOKMARK), self, triggered=lambda: BookmarkDialog(
                       self, index=self.bookmarks_view.selectionModel().currentIndex()).exec_()),
                   list=self.bookmark_view_actions)
        add_action('moveBookmarkUpAction',
                   QAction(self.tr('Move selected bookmark up'), self, triggered=self.move_bookmark_up),
                   list=self.bookmark_view_actions)
        add_action('moveBookmarkDownAction',
                   QAction(self.tr('Move selected bookmark down'), self, triggered=self.move_bookmark_down),
                   list=self.bookmark_view_actions)
        add_action('deleteBookmarkAction',
                   QAction(self.tr('Delete selected bookmark'), self, triggered=self.remove_bookmark_selection),
                   list=self.bookmark_view_actions)
        add_action('editShortcutAction',
                   QAction(self.tr(EDIT_QUICKLINK), self, triggered=lambda: ShortcutDialog(
                       self, self.quicklinks_view.selectionModel().currentIndex()).exec_()),
                   list=self.quick_links_view_actions)
        add_action('resetViewAction',
                   QAction(self.tr('Reset search filter'), self, shortcut='esc', triggered=self.reset_view))
        add_action('toggleSideBarsAction',
                   QAction(HIDE_SHOW_THE_SIDEBARS, self, shortcut='Ctrl+S', triggered=self.toggle_sidebars))
        add_action('toggleProjectAction',
                   QAction(self.tr('Toggle: note, sequential project, parallel project, paused project'), self,
                           shortcut='P', triggered=self.toggle_project), list=self.item_view_actions)
        add_action('appendRepeatAction',
                   QAction(self.tr('Repeat'), self, shortcut='Ctrl+R', triggered=self.append_repeat),
                   list=self.item_view_actions)
        add_action('goDownAction', QAction(self.tr('Set selected row as root'), self, shortcut='Ctrl+Down',
                                           triggered=lambda: self.focus_index(self.current_index())),
                   list=self.item_view_actions)
        add_action('goUpAction', QAction(self.tr('Set parent of current root as root'), self, shortcut='Ctrl+Up',
                                         triggered=self.focus_parent_of_focused), list=self.item_view_actions)
        add_action('increaseInterFaceFontAction', QAction(self.tr('Increase interface font-size'), self,
                                                          shortcut=QKeySequence(Qt.ALT + Qt.Key_Plus),
                                                          triggered=lambda: self.change_interface_font_size(+1)))
        add_action('decreaseInterFaceFontAction', QAction(self.tr('Decrease interface font-size'), self,
                                                          shortcut=QKeySequence(Qt.ALT + Qt.Key_Minus),
                                                          triggered=lambda: self.change_interface_font_size(-1)))
        add_action('increaseFontAction', QAction(self.tr('Increase font-size'), self, shortcut='Ctrl++',
                                                 triggered=lambda: self.change_font_size(+1)))
        add_action('decreaseFontAction', QAction(self.tr('Decrease font-size'), self, shortcut='Ctrl+-',
                                                 triggered=lambda: self.change_font_size(-1)))
        add_action('increasePaddingAction', QAction(self.tr('Increase padding'), self, shortcut='Ctrl+Shift++',
                                                    triggered=lambda: self.change_padding(+1)))
        add_action('decreasePaddingAction', QAction(self.tr('Decrease padding'), self, shortcut='Ctrl+Shift+-',
                                                    triggered=lambda: self.change_padding(-1)))
        add_action('cutAction', QAction(self.tr('Cut'), self, shortcut='Ctrl+X', triggered=self.cut),
                   list=self.item_view_actions)
        add_action('copyAction', QAction(self.tr('Copy'), self, shortcut='Ctrl+C', triggered=self.copy),
                   list=self.item_view_actions)
        add_action('pasteAction', QAction(self.tr('Paste'), self, shortcut='Ctrl+V', triggered=self.paste),
                   list=self.item_view_actions)
        add_action('exportPlainTextAction',
                   QAction(self.tr('as a plain text file...'), self, triggered=self.export_plain_text))
        add_action('expandAction',
                   QAction('Expand selected rows / add children to selection', self, shortcut='Right',
                           triggered=self.expand), list=self.item_view_not_editing_actions)
        add_action('collapseAction', QAction('Collapse selected rows / jump to parent', self, shortcut='Left',
                                             triggered=self.collapse), list=self.item_view_not_editing_actions)
        add_action('quitAction',
                   QAction(self.tr('Quit TreeNote'), self, shortcut='Ctrl+Q', triggered=self.close))
        add_action('openFileAction',
                   QAction(self.tr('Open file...'), self, shortcut='Ctrl+O', triggered=self.start_open_file))
        add_action('newFileAction',
                   QAction(self.tr('New file...'), self, shortcut='Ctrl+N', triggered=self.new_file))

        self.fileMenu = self.menuBar().addMenu(self.tr('File'))
        self.fileMenu.addAction(self.newFileAction)
        self.fileMenu.addAction(self.openFileAction)
        self.exportMenu = self.fileMenu.addMenu(self.tr('Export tree'))
        self.fileMenu.addSeparator()
        self.fileMenu.addAction(self.editShortcutAction)
        self.fileMenu.addAction(self.editBookmarkAction)
        self.fileMenu.addAction(self.deleteBookmarkAction)
        self.fileMenu.addAction(self.renameTagAction)
        self.fileMenu.addSeparator()
        self.exportMenu.addAction(self.exportPlainTextAction)
        self.fileMenu.addAction(self.settingsAct)
        if sys.platform != "darwin":
            self.fileMenu.addSeparator()
            self.fileMenu.addAction(self.quitAction)

        self.structureMenu = self.menuBar().addMenu(self.tr('Edit structure'))
        self.structureMenu.addAction(self.insertRowAction)
        self.structureMenu.addAction(self.insertChildAction)
        self.structureMenu.addAction(self.deleteSelectedRowsAction)
        self.moveMenu = self.structureMenu.addMenu(self.tr('Move selected rows'))
        self.moveMenu.addAction(self.moveUpAction)
        self.moveMenu.addAction(self.moveDownAction)
        self.moveMenu.addAction(self.moveLeftAction)
        self.moveMenu.addAction(self.moveRightAction)
        self.structureMenu.addSeparator()
        self.structureMenu.addAction(self.cutAction)
        self.structureMenu.addAction(self.copyAction)
        self.structureMenu.addAction(self.pasteAction)

        self.editRowMenu = self.menuBar().addMenu(self.tr('Edit row'))
        self.editRowMenu.addAction(self.editRowAction)
        self.editRowMenu.addAction(self.toggleTaskAction)
        self.editRowMenu.addAction(self.toggleProjectAction)
        self.editRowMenu.addAction(self.appendRepeatAction)
        self.colorMenu = self.editRowMenu.addMenu(self.tr('Color selected rows'))
        self.colorMenu.addAction(self.colorGreenAction)
        self.colorMenu.addAction(self.colorYellowAction)
        self.colorMenu.addAction(self.colorBlueAction)
        self.colorMenu.addAction(self.colorRedAction)
        self.colorMenu.addAction(self.colorOrangeAction)
        self.colorMenu.addAction(self.colorNoColorAction)

        self.viewMenu = self.menuBar().addMenu(self.tr('View'))
        self.viewMenu.addAction(self.goDownAction)
        self.viewMenu.addAction(self.goUpAction)
        self.viewMenu.addAction(self.resetViewAction)
        self.viewMenu.addSeparator()
        self.viewMenu.addAction(self.expandAction)
        self.viewMenu.addAction(self.collapseAction)
        self.viewMenu.addAction(self.expandAllChildrenAction)
        self.viewMenu.addAction(self.collapseAllChildrenAction)
        self.viewMenu.addSeparator()
        # self.viewMenu.addAction(self.splitWindowAct)
        # self.viewMenu.addAction(self.unsplitWindowAct)
        self.viewMenu.addAction(self.openLinkAction)
        self.viewMenu.addAction(self.focusSearchBarAction)
        self.viewMenu.addAction(self.toggleSideBarsAction)
        self.viewMenu.addSeparator()
        self.viewMenu.addAction(self.increaseFontAction)
        self.viewMenu.addAction(self.decreaseFontAction)
        self.viewMenu.addAction(self.increasePaddingAction)
        self.viewMenu.addAction(self.decreasePaddingAction)
        self.viewMenu.addSeparator()
        self.viewMenu.addAction(self.increaseInterFaceFontAction)
        self.viewMenu.addAction(self.decreaseInterFaceFontAction)

        self.bookmarkShortcutsMenu = self.menuBar().addMenu(self.tr('My shortcuts'))
        self.fill_bookmarkShortcutsMenu()

        self.helpMenu = self.menuBar().addMenu(self.tr('Help'))
        self.helpMenu.addAction(self.updateAct)
        self.helpMenu.addAction(self.aboutAct)

        self.make_single_key_menu_shortcuts_work_on_mac(self.all_actions)

        self.split_window()

        # restore previous position
        size = settings.value('size')
        if size is not None:
            self.resize(size)
            self.move(settings.value('pos'))
        else:
            self.showMaximized()

        mainSplitter_state = settings.value('mainSplitter')
        if mainSplitter_state is not None:
            self.mainSplitter.restoreState(mainSplitter_state)

        first_column_splitter_state = settings.value('first_column_splitter')
        if first_column_splitter_state is not None:
            self.first_column_splitter.restoreState(first_column_splitter_state)

        # first (do this before the label 'second')
        self.change_active_database()
        # self.expand_saved_quicklinks() todo

        self.reset_view()  # inits checkboxes
        self.focused_column().view.setFocus()
        self.update_actions()

        # second
        # restore selection
        # second value is loaded, if nothing was saved before in the settings
        selected_index = settings.value(SELECTED_INDEX, None)
        if selected_index is not None:
            self.set_selection(QModelIndex(selected_index), QModelIndex(selected_index))

        # restore palette
        palette = settings.value('theme')
        if palette is not None:
            palette = self.light_palette if palette == 'light' else self.dark_palette
        else:  # set standard theme
            palette = self.dark_palette
        self.set_palette(palette)

        # restore splitters
        splitter_sizes = settings.value('splitter_sizes')
        if splitter_sizes is not None:
            self.mainSplitter.restoreState(splitter_sizes)
        else:
            self.toggle_sidebars()

        # restore columns
        columns_hidden = settings.value(COLUMNS_HIDDEN)
        if columns_hidden or columns_hidden is None:
            self.toggle_columns()

        self.backup_timer = QTimer()
        self.backup_timer.timeout.connect(self.backup_all_db_with_changes)
        self.start_backup_service(settings.value('backup_interval', 10))

        self.set_indentation(settings.value('indentation', 40))
        self.check_for_software_update()

    def backup_all_db_with_changes(self):
        # todo
        pass
        # for server in self.server_model.servers:
        #     if server.model.changed:
        #         server.model.changed = False
        #         self.backup_db(server)

    def start_backup_service(self, minutes):
        self.backup_interval = int(minutes)
        self.backup_timer.stop()
        if minutes != 0:
            self.backup_timer.start(self.backup_interval * 1000 * 60)  # time specified in ms

    def check_for_software_update(self):
        self.new_version_data = requests.get('https://api.github.com/repos/treenote/treenote/releases/latest').json()
        skip_this_version = self.getQSettings().value('skip_version') is not None and \
                            self.getQSettings().value('skip_version') == self.new_version_data['tag_name']
        is_newer_version = git_tag_to_versionnr(version.version_nr) < \
                           git_tag_to_versionnr(self.new_version_data['tag_name'])
        if not skip_this_version and is_newer_version:
            UpdateDialog(self).exec_()
        return is_newer_version

    def make_single_key_menu_shortcuts_work_on_mac(self, actions):
        # source: http://thebreakfastpost.com/2014/06/03/single-key-menu-shortcuts-with-qt5-on-osx/
        if sys.platform == "darwin":
            # This class collects a set of parameterless signals, and re-emits
            # them with a string corresponding to the object that sent the signal.
            self.signalMapper = QSignalMapper(self)
            self.signalMapper.mapped[str].connect(self.evoke_singlekey_action)
            for action in actions:
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

    def expand_saved(self):
        self.item_model.expand_saved(QModelIndex())

    def expand_saved_quicklinks(self):  # todo
        pass

    def get_widgets(self):
        return [QApplication,
                self.focused_column().toggle_sidebars_button,
                self.focused_column().toggle_columns_button,
                self.focused_column().bookmark_button,
                self.focused_column().search_bar,
                self.focused_column().view,
                self.focused_column().view.verticalScrollBar(),
                self.focused_column().view.header(),
                self.tag_view,
                self.tag_view.header()]

    def set_palette(self, new_palette):
        for widget in self.get_widgets():
            widget.setPalette(new_palette)

    def fill_bookmarkShortcutsMenu(self):
        self.bookmarkShortcutsMenu.clear()
        for index in self.item_model.indexes():
            item = self.bookmark_model.getItem(index)
            if item.shortcut:
                self.bookmarkShortcutsMenu.addAction(QAction(item.text, self, shortcut=item.shortcut,
                                                             triggered=partial(self.open_quicklink_shortcut, index)))
        self.bookmarkShortcutsMenu.addSeparator()
        for index in self.bookmark_model.indexes():
            item = self.bookmark_model.getItem(index)
            if item.shortcut:
                self.bookmarkShortcutsMenu.addAction(QAction(item.text, self, shortcut=item.shortcut,
                                                             triggered=partial(self.filter_bookmark, index)))

    def open_quicklink_shortcut(self, real_index):
        index = self.filter_proxy_index_from_model_index(real_index)
        self.focus_index(index)
        # select row for visual highlight
        self.quicklinks_view.selectionModel().select(QItemSelection(index, index), QItemSelectionModel.ClearAndSelect)

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
        with open(self.filename_from_dialog('.json'), 'w', encoding='utf-8') as file:
            row_list = []
            map = "function(doc) { \
            if (doc." + model.DELETED + " == '') \
                emit(doc, null); }"
            res = self.item_model.db.query(map, include_docs=True)
            file.write(json.dumps([row.doc for row in res], indent=4))

    def filename_from_dialog(self, file_type):
        proposed_file_name = self.get_current_server().database_name + '_' + QDate.currentDate().toString('yyyy-MM-dd')
        file_name = QFileDialog.getSaveFileName(self, "Save", proposed_file_name + file_type, "*" + file_type)
        return file_name[0]

    def export_plain_text(self):
        with open(self.filename_from_dialog('.txt'), 'w', encoding='utf-8') as file:
            file.write(self.tree_as_string(self.item_model))

    def import_db(self):
        self.file_name = QFileDialog.getOpenFileName(self, "Open", "", "*.json")
        if self.file_name[0] != '':
            DatabaseDialog(self, import_file_name=self.file_name[0]).exec_()

    def change_active_database(self):
        if not hasattr(self, 'item_views_splitter'):
            return
        self.save_expanded_quicklinks_state()
        self.focused_column().flat_proxy.setSourceModel(self.item_model)
        self.focused_column().filter_proxy.setSourceModel(self.item_model)
        self.quicklinks_view.setModel(self.item_model)
        self.quicklinks_view.setItemDelegate(model.BookmarkDelegate(self, self.item_model))
        self.set_undo_actions()
        self.old_search_text = 'dont save expanded states of next db when switching to next db'
        self.setup_tag_model()
        self.expand_saved_quicklinks()
        self.reset_view()

    def set_undo_actions(self):
        if hasattr(self, 'undoAction'):
            self.fileMenu.removeAction(self.undoAction)
            self.fileMenu.removeAction(self.redoAction)
        self.undoAction = self.item_model.undoStack.createUndoAction(self)
        self.undoAction.setShortcut('CTRL+Z')
        self.redoAction = self.item_model.undoStack.createRedoAction(self)
        self.redoAction.setShortcut('CTRL+Shift+Z')
        self.make_single_key_menu_shortcuts_work_on_mac([self.undoAction, self.redoAction])
        self.fileMenu.insertAction(self.editShortcutAction, self.undoAction)
        self.fileMenu.insertAction(self.editShortcutAction, self.redoAction)
        self.fileMenu.insertAction(self.editShortcutAction, self.fileMenu.addSeparator())

    def closeEvent(self, event):
        settings = self.getQSettings()
        settings.setValue('pos', self.pos())
        settings.setValue('size', self.size())
        settings.setValue('mainSplitter', self.mainSplitter.saveState())
        settings.setValue('first_column_splitter', self.first_column_splitter.saveState())
        settings.setValue('fontsize', self.fontsize)
        settings.setValue('interface_fontsize', self.interface_fontsize)
        settings.setValue('padding', self.padding)
        settings.setValue('splitter_sizes', self.mainSplitter.saveState())
        settings.setValue('indentation', self.focused_column().view.indentation())
        settings.setValue('backup_interval', self.backup_interval)
        settings.setValue('last_opened_file_path', self.path)
        settings.setValue(COLUMNS_HIDDEN, self.focused_column().view.isHeaderHidden())

        # save expanded quicklinks
        self.save_expanded_quicklinks_state()
        settings.setValue(EXPANDED_QUICKLINKS_INDEXES, self.expanded_quicklink_indexes)

        # save selection
        settings.setValue(SELECTED_INDEX, QPersistentModelIndex(self.current_index()))

        # save theme
        theme = 'light' if app.palette() == self.light_palette else 'dark'
        settings.setValue('theme', theme)

        # __debug__ is true if Python was not started with an -O option. -O turns on basic optimizations.
        if not __debug__:
            if sys.platform == "darwin":
                subprocess.call(['osascript', '-e', 'tell application "Apache CouchDB" to quit'])

    def getQSettings(self):
        settings_file = 'treenote_settings.ini'
        return QSettings(os.path.dirname(os.path.realpath(__file__)) + os.sep + settings_file, QSettings.IniFormat)

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
        toggle_actions(not self.focused_column().search_bar.hasFocus(), self.item_view_actions)

        toggle_actions(self.focused_column().view.state() != QAbstractItemView.EditingState,
                       self.item_view_not_editing_actions)

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
        self.flatten = flatten
        if flatten:
            self.append_replace_to_searchbar(model.FLATTEN, 'yes')
        else:
            self.filter(model.FLATTEN, 'all')

    def filter_tag(self):
        current_index = self.tag_view.selectionModel().currentIndex()
        current_tag = self.tag_view.model().data(current_index, tag_model.FULL_PATH)
        if current_tag is not None:
            search_bar_text = self.focused_column().search_bar.text()
            new_text = re.sub(r':\S* ', current_tag + ' ', search_bar_text)  # matches a tag
            if ':' not in search_bar_text:
                new_text += ' ' + current_tag + ' '
            self.set_searchbar_text_and_search(new_text)

    # set the search bar text according to the selected bookmark
    def filter_bookmark(self, index):
        new_search_bar_text = self.bookmark_model.getItem(index).search_text
        self.set_searchbar_text_and_search(new_search_bar_text)
        # if shortcut was used: select bookmarks row for visual highlight
        self.set_selection(index, index)

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

    def change_interface_font_size(self, step):
        self.new_if_size = self.interface_fontsize + step
        if self.new_if_size <= 25 and self.new_if_size >= 8:
            self.interface_fontsize += step
            for widget in self.get_widgets():
                widget.setFont(QFont(model.FONT, self.interface_fontsize))

    def change_font_size(self, step):
        self.fontsize += step
        self.focused_column().view.itemDelegate().sizeHintChanged.emit(QModelIndex())

    def change_padding(self, step):
        if not (step == -1 and self.padding == 2):
            self.padding += step
            self.focused_column().view.itemDelegate().sizeHintChanged.emit(QModelIndex())

    def toggle_sidebars(self):
        sidebar_shown = self.mainSplitter.widget(0).size().width() > 0 or self.mainSplitter.widget(2).size().width() > 0
        if sidebar_shown:  # hide
            self.mainSplitter.moveSplitter(0, 1)
            self.mainSplitter.moveSplitter(self.width(), 2)
        else:
            self.mainSplitter.moveSplitter(INITIAL_SIDEBAR_WIDTH, 1)
            self.mainSplitter.moveSplitter(self.width() - INITIAL_SIDEBAR_WIDTH, 2)

    def toggle_columns(self):
        if self.focused_column().view.isHeaderHidden():
            self.focused_column().view.showColumn(1)
            self.focused_column().view.showColumn(2)
            self.focused_column().view.setHeaderHidden(False)
        else:
            self.focused_column().view.hideColumn(1)
            self.focused_column().view.hideColumn(2)
            self.focused_column().view.setHeaderHidden(True)

    def save_expanded_quicklinks_state(self):
        self.expanded_quicklink_indexes = []
        for index in self.item_model.persistentIndexList():
            if self.quicklinks_view.isExpanded(index):
                self.expanded_quicklink_indexes.append(index)

    @pyqtSlot(str)
    def search(self, search_text):
        self.old_search_text = search_text  # needed by the line above next time this method is called

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
                # changing dropdown index accordingly is not that easy,
                # because changing it fires "color_clicked" which edits search bar

        def set_model(new_model):
            if self.focused_column().filter_proxy.sourceModel() != new_model:
                self.focused_column().filter_proxy.setSourceModel(new_model)

        # flatten + filter
        if model.FLATTEN in search_text:
            set_model(self.focused_column().flat_proxy)
            apply_filter()
        else:
            # filter must be refreshed before changing the model,
            # otherwise exc because use of wrong model
            apply_filter()
            set_model(self.item_model)

        # expand
        if search_text == '':
            self.expand_or_collapse_children(QModelIndex(), False)
            self.expand_saved()
        else:  # expand all items
            self.expand_or_collapse_children(QModelIndex(), True)

        # set selection
        # ( the selection is also set after pressing Enter, in SearchBarQLineEdit and insert_row() )
        # Set only if text was set programmatically e.g. because the user selected a dropdown,
        # and if the previous selected row was filtered out by the search.
        if not self.focused_column().search_bar.isModified() and not self.is_selection_visible():
            self.set_top_row_selected()

    def is_selection_visible(self):
        if not self.focused_column().view.selectionModel().selectedRows():
            return False

        # check if the parent of the selection is the current root
        # if not, the check if one of it's parent is the current root - then the selection is visible
        # if we dont find the current root but the root of the whole tree, the selection is not visible
        def check_parents(index):
            if index == self.focused_column().view.rootIndex():
                return True
            elif index == QModelIndex():
                return False
            else:
                return check_parents(index.parent())

        return check_parents(self.current_index().parent())

    def expand_or_collapse_children_selected(self, bool_expand):
        for index in self.selected_indexes():
            self.expand_or_collapse_children(index, bool_expand)

    def expand_or_collapse_children(self, parent_index, bool_expand):
        self.focused_column().view.setExpanded(parent_index, bool_expand)  # for recursion
        for row_num in range(self.focused_column().filter_proxy.rowCount(parent_index)):
            child_index = self.focused_column().filter_proxy.index(row_num, 0, parent_index)
            self.focused_column().view.setExpanded(parent_index, bool_expand)
            self.expand_or_collapse_children(child_index, bool_expand)

    def expand(self):
        for index in self.selected_indexes():
            if self.focused_column().view.isExpanded(index):  # select all children
                for row_num in range(self.focused_column().filter_proxy.rowCount(index)):
                    child_index = self.focused_column().filter_proxy.index(row_num, 0, index)
                    child_index_to = child_index.sibling(child_index.row(), self.item_model.columnCount() - 1)
                    self.focused_column().view.selectionModel().setCurrentIndex(child_index_to,
                                                                                QItemSelectionModel.Select)
                    self.focused_column().view.selectionModel().select(QItemSelection(child_index, child_index_to),
                                                                       QItemSelectionModel.Select)
            else:
                self.focused_column().filter_proxy.getItem(index).expanded = True
                self.focused_column().view.setExpanded(index, True)
                self.save_file()

    def collapse(self):
        for index in self.selected_indexes():
            # jump to parent
            if not self.focused_column().view.isExpanded(index) or \
                    not self.item_model.hasChildren(self.focused_column().filter_proxy.mapToSource(index)):
                index_parent_to = index.parent().sibling(index.parent().row(), self.item_model.columnCount() - 1)
                if index_parent_to != QModelIndex():  # dont select root (because its not visible)
                    self.focused_column().view.selectionModel().setCurrentIndex(index.parent(),
                                                                                QItemSelectionModel.Select)
                    self.focused_column().view.selectionModel().select(QItemSelection(index.parent(), index_parent_to),
                                                                       QItemSelectionModel.Select)

                    index_to = index.sibling(index.row(), self.item_model.columnCount() - 1)
                    self.focused_column().view.selectionModel().select(QItemSelection(index, index_to),
                                                                       QItemSelectionModel.Deselect)
            else:
                self.focused_column().filter_proxy.getItem(index).expanded = False
                self.focused_column().view.setExpanded(index, False)
                self.save_file()

    def rename_tag(self, tag, new_name):
        for item in self.item_model.items():
            if tag in item.text:
                item.text = item.text.replace(tag, new_name)

    @pyqtSlot(QPoint)
    def open_rename_tag_contextmenu(self, point):
        index = self.tag_view.indexAt(point)
        # show context menu only when clicked on an item, not when clicked on empty space
        if not index.isValid():
            return
        menu = QMenu()
        menu.addAction(self.renameTagAction)
        menu.exec_(self.tag_view.viewport().mapToGlobal(point))

    @pyqtSlot(QPoint)
    def open_edit_bookmark_contextmenu(self, point):
        index = self.bookmarks_view.indexAt(point)
        if not index.isValid():
            return
        menu = QMenu()
        menu.addAction(self.editBookmarkAction)
        menu.addAction(self.deleteBookmarkAction)
        menu.addAction(self.moveBookmarkUpAction)
        menu.addAction(self.moveBookmarkDownAction)
        menu.exec_(self.bookmarks_view.viewport().mapToGlobal(point))

    @pyqtSlot(QPoint)
    def open_edit_shortcut_contextmenu(self, point):
        index = self.quicklinks_view.indexAt(point)
        if not index.isValid():
            return
        menu = QMenu()
        menu.addAction(self.editShortcutAction)
        menu.exec_(self.quicklinks_view.viewport().mapToGlobal(point))

    # structure menu actions
    def move_bookmark_up(self):
        self.bookmark_model.move_vertical(self.bookmarks_view.selectedIndexes(), -1)

    def move_bookmark_down(self):
        self.bookmark_model.move_vertical(self.bookmarks_view.selectedIndexes(), 1)

    def move_up(self):
        indexes = self.selected_indexes()
        indexes[0].model().move_vertical(indexes, -1)

    def move_down(self):
        indexes = self.selected_indexes()
        indexes[0].model().move_vertical(indexes, +1)

    def move_left(self):
        if self.focusWidget() is self.focused_column().view:
            self.focused_column().filter_proxy.move_horizontal(self.focused_column().view.
                                                               selectionModel().selectedRows(), -1)

    def move_right(self):
        if self.focusWidget() is self.focused_column().view:
            selected_indexes = self.focused_column().view.selectionModel().selectedRows()
            self.focused_column().view.setAnimated(False)
            self.focused_column().view.setExpanded(selected_indexes[0].sibling(selected_indexes[0].row() - 1, 0), True)
            self.focused_column().view.setAnimated(True)
            self.focused_column().filter_proxy.move_horizontal(selected_indexes, +1)

    def insert_child(self):
        index = self.current_index()
        if self.focused_column().view.state() == QAbstractItemView.EditingState:
            # save the edit of the yet open editor
            self.focused_column().view.selectionModel().currentChanged.emit(index, index)
        self.focused_column().filter_proxy.insert_row(0, index)

    def insert_row(self):
        index = self.current_index()
        # if the user sees not entries, pressing enter shall create a child of the current root entry
        if index == QModelIndex():
            self.focused_column().filter_proxy.insert_row(0, self.focused_column().view.rootIndex())
        else:
            if self.focused_column().view.hasFocus():
                # if selection has childs and is expanded: create top child instead of sibling
                if self.focused_column().view.isExpanded(self.current_index()) and \
                                self.focused_column().filter_proxy.rowCount(self.current_index()) > 0:
                    self.insert_child()
                else:
                    self.focused_column().filter_proxy.insert_row(index.row() + 1, index.parent())
            elif self.focused_column().view.state() == QAbstractItemView.EditingState:
                # todo irgendwann: this is never called?
                # commit data by changing the current selection
                self.focused_column().view.selectionModel().currentChanged.emit(index, index)
            else:
                self.focused_column().view.setFocus()  # focus view after search with enter
                if not self.selected_indexes():
                    self.set_top_row_selected()

    def remove_selection(self):
        # workaround against data loss due to crashes: backup db as txt file before delete operations
        # self.backup_db(self.get_current_server()) # todo
        self.focused_column().filter_proxy.remove_rows(self.selected_indexes())

    def backup_db(self, server):
        proposed_file_name = server.database_name + '_' + QDate.currentDate().toString('yyyy-MM-dd') + '-' \
                             + QTime.currentTime().toString('hh-mm-ss-zzz') + '.txt'
        with open(os.path.dirname(os.path.realpath(__file__)) + os.sep + 'backups' + os.sep +
                          proposed_file_name, 'w', encoding='utf-8') as file:
            file.write(self.tree_as_string(server.model))

    def tree_as_string(self, item_model, index=QModelIndex(), rows_string=''):
        indention_string = (model.indention_level(index) - 1) * '\t'
        if index.data() is not None:
            rows_string += indention_string + '- ' + index.data().replace('\n', '\n' + indention_string + '\t') + '\n'
        for child_nr in range(item_model.rowCount(index)):
            rows_string = self.tree_as_string(item_model, item_model.index(child_nr, 0, index), rows_string)
        return rows_string

    def selected_indexes(self):
        return self.focusWidget().selectionModel().selectedRows()

    def remove_bookmark_selection(self):
        reply = QMessageBox.question(self, '', 'Delete this bookmark?', QMessageBox.Yes, QMessageBox.Cancel)
        if reply == QMessageBox.Yes:
            self.bookmarks_view.setFocus()
            self.bookmark_model.insert_remove_rows(indexes=self.selected_indexes())

    def cut(self):
        print("cut")

    def copy(self):
        if len(self.selected_indexes()) == 1:
            rows_string = self.selected_indexes()[0].data()
        elif self.flatten:
            rows_string = '\r\n'.join(['- ' + index.data().replace('\n', '\r\n\t')
                                       for index in self.selected_indexes()])
        else:
            selected_source_indexes = [self.focused_column().filter_proxy.mapToSource(index)
                                       for index in self.selected_indexes()]

            def tree_as_string(index, rows_string=''):
                indention_string = (model.indention_level(index) - 1) * '\t'
                if index.data() is not None and index in selected_source_indexes:
                    rows_string += indention_string + '- ' + \
                                   index.data().replace('\n', '\r\n' + indention_string + '\t') + '\r\n'
                for child_nr in range(self.item_model.rowCount(index)):
                    child_index = self.item_model.index(child_nr, 0, index)
                    rows_string = tree_as_string(child_index, rows_string)
                return rows_string

            rows_string = tree_as_string(QModelIndex())

            # if a child is in the selection but not the parent: flatten
            indention_level, left_most_index = min((model.indention_level(index), index)
                                                   for index in selected_source_indexes)
            for index in selected_source_indexes:
                if index.parent() not in selected_source_indexes + [left_most_index.parent()]:
                    lines = []
                    for line in rows_string.split('\n'):
                        line = line.strip()
                        if not line.startswith('-'):
                            line = '\t' + line
                        lines.append(line)
                    rows_string = '\r\n'.join(lines)
                    break

            rows_string = textwrap.dedent(rows_string)  # strip spaces in front of all rows until equal
            rows_string = rows_string.strip()  # strip the line break at the end
        QApplication.clipboard().setText(rows_string)

    def paste(self):
        # builds a tree structure out of indented rows
        # idea: insert new rows from top to bottom.
        # depending on the indention, the parent will be the last inserted row with one lower indention
        # we count the row position to know where to insert the next row
        start_index = self.current_index()
        # \r ist for windows compatibility. strip is to remove the last linebreak
        text = QApplication.clipboard().text().replace('\r\n', '\n').strip('\n')
        # which format style has the text?
        if re.search(r'(\n|^)(\t*-)', text):  # each item starts with a dash
            text = re.sub(r'\n(\t*-)', r'\r\1', text)  # replaces \n which produce a new item with \r
        else:  # each row is an item
            text = re.sub(r'\n(\t*)', r'\r\1', text)  # replaces \n which produce a new item with \r
        lines = re.split(r'\r', text)
        source_index = self.focused_column().filter_proxy.mapToSource(start_index)
        indention_insert_position_dict = {0: source_index.row() + 1}
        indention_parent_id_dict = {-1: self.item_model.getItem(source_index.parent()).id}
        for line in lines:
            stripped_line = line.lstrip('\t')
            indention = len(line) - len(stripped_line)
            # remove -, *, spaces and tabs from the beginning of the line
            cleaned_line = re.sub(r'^(-|\*)? *|\t*', '', stripped_line)
            if indention not in indention_insert_position_dict:
                indention_insert_position_dict[indention] = 0
            child_id = self.paste_row_with_id(indention_insert_position_dict[indention],
                                              indention_parent_id_dict[indention - 1], cleaned_line)
            indention_insert_position_dict[indention] += 1
            for key in indention_insert_position_dict.keys():
                if key > indention:
                    indention_insert_position_dict[key] = 0
            indention_parent_id_dict[indention] = child_id

    def paste_row_with_id(self, new_position, parent_item_id, text):
        self.item_model.insert_remove_rows(new_position, parent_item_id, set_edit_focus=False)
        children_list = self.item_model.db[parent_item_id]['children'].split()
        item_id = children_list[new_position]
        self.item_model.set_data_with_id(text, item_id, 0)
        return item_id

    # task menu actions

    def edit_row(self):
        # workaround to fix a weird bug, where the second column is skipped
        if sys.platform == "darwin" or self.current_index().column() != 1:
            self.edit_row_without_check()

    def edit_row_without_check(self):
        current_index = self.current_index()
        if self.focused_column().view.state() == QAbstractItemView.EditingState:  # change column with tab key
            next_column_number = (current_index.column() + 1) % 3
            sibling_index = current_index.sibling(current_index.row(), next_column_number)
            self.focused_column().view.selectionModel().setCurrentIndex(sibling_index,
                                                                        QItemSelectionModel.ClearAndSelect)
            self.focused_column().view.edit(sibling_index)
        elif self.focused_column().view.hasFocus():
            self.focused_column().view.edit(current_index)
        else:
            self.focused_column().view.setFocus()

    def edit_estimate(self):
        current_index = self.current_index()
        sibling_index = current_index.sibling(current_index.row(), 2)
        self.focused_column().view.selectionModel().setCurrentIndex(sibling_index, QItemSelectionModel.ClearAndSelect)
        self.focused_column().view.edit(sibling_index)

    def current_index(self):
        return self.focused_column().view.selectionModel().currentIndex()

    def toggle_task(self):
        for row_index in self.focused_column().view.selectionModel().selectedRows():
            self.focused_column().filter_proxy.toggle_task(row_index)

    def toggle_project(self):
        for row_index in self.focused_column().view.selectionModel().selectedRows():
            self.focused_column().filter_proxy.toggle_project(row_index)

    def append_repeat(self):
        index = self.current_index()
        self.focused_column().filter_proxy.set_data(model.TASK, index=index, field='type')
        self.focused_column().filter_proxy.set_data(QDate.currentDate().toString('dd.MM.yy'), index=index, field='date')
        self.focused_column().filter_proxy.set_data(index.data() + ' repeat=1w', index=index)
        self.edit_row()

    @pyqtSlot(str)
    def color_row(self, color_character):
        for row_index in self.focused_column().view.selectionModel().selectedRows():
            self.focused_column().filter_proxy.set_data(model.CHAR_QCOLOR_DICT[color_character],
                                                        index=row_index, field='color')

    # view menu actions

    @pyqtSlot(QModelIndex)
    def focus_index(self, index):
        self.focused_column().view.setRootIndex(index)
        if not self.focused_column().search_bar.isModified() and not self.is_selection_visible():
            self.set_top_row_selected()

    def focus_parent_of_focused(self):
        self.focused_column().view.selectionModel().clear()
        root_index = self.focused_column().view.rootIndex()
        self.focus_index(root_index.parent())
        self.set_selection(root_index, root_index)

    def open_links(self):
        for row_index in self.focused_column().view.selectionModel().selectedRows():
            url_list = re.findall(util.url_regex, row_index.data())
            for url in url_list:
                if not re.search(r'https?://', url):
                    url = 'http://' + url
                QDesktopServices.openUrl(QUrl(url))
            else:  # no urls found: search the web for the selected entry
                text_without_tags = re.sub(r':(\w|:)*', '', row_index.data())
                QDesktopServices.openUrl(QUrl('https://www.google.de/search?q=' + text_without_tags))

    def split_window(self):  # creates another item_view
        new_column = QWidget()

        new_column.toggle_sidebars_button = QPushButton()
        new_column.toggle_sidebars_button.setToolTip(HIDE_SHOW_THE_SIDEBARS)
        new_column.toggle_sidebars_button.setIcon(QIcon(':/toggle_sidebars'))
        new_column.toggle_sidebars_button.setStyleSheet('QPushButton {\
            width: 22px;\
            height: 22px;\
            padding: 2px; }')
        new_column.toggle_sidebars_button.clicked.connect(self.toggle_sidebars)

        new_column.toggle_columns_button = QPushButton()
        new_column.toggle_columns_button.setToolTip("Hide / show the columns 'Start date' and 'Estimate'")
        new_column.toggle_columns_button.setIcon(QIcon(':/toggle_columns'))
        new_column.toggle_columns_button.setStyleSheet('QPushButton {\
            width: 22px;\
            height: 22px;\
            padding: 2px; }')
        new_column.toggle_columns_button.clicked.connect(self.toggle_columns)

        new_column.search_bar = SearchBarQLineEdit(self)
        new_column.search_bar.setPlaceholderText(self.tr('Search'))

        # search shall start not before the user completed typing
        filter_delay = DelayedExecutionTimer(self)
        # just triggered by user editing, not triggered by programmatically setting the search bar text
        new_column.search_bar.textEdited[str].connect(filter_delay.trigger)
        filter_delay.triggered[str].connect(self.search)

        new_column.bookmark_button = QPushButton()
        new_column.bookmark_button.setToolTip('Bookmark current filters')
        new_column.bookmark_button.setIcon(QIcon(':/star'))
        new_column.bookmark_button.setStyleSheet('QPushButton {\
            width: 22px;\
            height: 22px;\
            padding: 2px; }')
        new_column.bookmark_button.clicked.connect(
            lambda: BookmarkDialog(self, search_bar_text=self.focused_column().search_bar.text()).exec_())

        search_holder = QWidget()
        layout = QHBoxLayout()
        layout.addWidget(new_column.toggle_sidebars_button)
        layout.addWidget(new_column.toggle_columns_button)
        layout.addWidget(new_column.search_bar)
        layout.addWidget(new_column.bookmark_button)
        layout.setContentsMargins(0, 11, 0, 0)
        search_holder.setLayout(layout)

        new_column.view = ResizeTreeView()
        new_column.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        new_column.view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        new_column.view.setAnimated(True)
        new_column.view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)

        new_column.flat_proxy = model.FlatProxyModel()
        new_column.flat_proxy.setSourceModel(self.item_model)

        new_column.filter_proxy = model.FilterProxyModel()
        new_column.filter_proxy.setSourceModel(self.item_model)
        # re-sort and re-filter data whenever the original model changes
        new_column.filter_proxy.setDynamicSortFilter(True)
        new_column.filter_proxy.filter = ''

        new_column.view.setModel(new_column.filter_proxy)
        new_column.view.setItemDelegate(model.Delegate(self, new_column.filter_proxy, new_column.view.header()))
        new_column.view.selectionModel().selectionChanged.connect(self.update_actions)
        new_column.view.header().sectionClicked[int].connect(self.toggle_sorting)
        new_column.view.header().setStretchLastSection(False)
        new_column.view.setColumnWidth(1, 130)
        new_column.view.setColumnWidth(2, 85)
        new_column.view.header().setSectionResizeMode(0, QHeaderView.Stretch)
        new_column.view.header().setSectionResizeMode(1, QHeaderView.Fixed)
        new_column.view.header().setSectionResizeMode(2, QHeaderView.Fixed)
        new_column.view.header().setSectionsClickable(True)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)  # left, top, right, bottom
        layout.addWidget(search_holder)
        layout.addWidget(new_column.view)
        new_column.setLayout(layout)

        self.item_views_splitter.addWidget(new_column)
        self.setup_tag_model()

        self.focused_column().view.setFocus()
        self.style_tree()
        top_most_index = self.focused_column().filter_proxy.index(0, 0, QModelIndex())
        self.set_selection(top_most_index, top_most_index)
        self.bookmarks_view.selectionModel().setCurrentIndex(QModelIndex(), QItemSelectionModel.ClearAndSelect)

    def unsplit_window(self):
        index_last_widget = self.item_views_splitter.count() - 1
        self.item_views_splitter.widget(index_last_widget).setParent(None)
        if self.item_views_splitter.count() == 1:
            self.unsplitWindowAct.setEnabled(False)

    def set_indentation(self, i):
        self.focused_column().view.setIndentation(int(i))
        self.style_tree()

    def style_tree(self):
        padding = str(self.focused_column().view.indentation() - 30)
        self.focused_column().view.setStyleSheet(
            'QTreeView:focus { border: 1px solid #006080; }'  # blue glow around the view
            'QTreeView:branch:open:has-children  {'
            'image: url(:/open);'
            'padding-top: 10px;'
            'padding-bottom: 10px;'
            'padding-left: ' + padding + 'px;}'
                                         'QTreeView:branch:closed:has-children {'
                                         'image: url(:/closed);'
                                         'padding-top: 10px;'
                                         'padding-bottom: 10px;'
                                         'padding-left: ' + padding + 'px;}')

    def new_file(self):
        path = QFileDialog.getSaveFileName(self, "Save", '.json', "*.json")[0]
        if len(path) > 0:
            self.path = path
            self.item_model = model.TreeModel(self, header_list=['Text', 'Start date', 'Estimate'])
            self.bookmark_model = model.TreeModel(self, header_list=['Bookmarks'])
            self.setWindowTitle(self.path + ' - TreeNote')
            self.change_active_database()
            self.save_file()

    def save_file(self):
        def save():
            if hasattr(self, 'bookmark_model'):
                def json_encoder(obj):
                    dic = obj.__dict__.copy()
                    del dic['parentItem']
                    return dic

                json.dump((self.item_model.rootItem, self.bookmark_model.rootItem), open(self.path, 'w'),
                          default=json_encoder, indent=4)

        thread = threading.Thread(target=save)
        thread.start()

    def start_open_file(self):
        path = self.open_file(QFileDialog.getOpenFileName(self, "Open", filter="*.json")[0])
        if path and len(path) > 0:
            self.open_file(path)

    def open_file(self, path):
        self.path = path
        self.setWindowTitle(path + ' - TreeNote')
        self.item_model = model.TreeModel(self, header_list=['Text', 'Start date', 'Estimate'])
        self.bookmark_model = model.TreeModel(self, header_list=['Bookmarks'])

        def json_decoder(obj):
            if 'text' in obj:
                item = model.Tree_item()
                item.__dict__.update(obj)
                item.childItems = obj['childItems']
                return item
            return obj

        self.item_model.rootItem, self.bookmark_model.rootItem = json.load(open(path, 'r'), object_hook=json_decoder)

        def set_parents(parent_item):
            for child_item in parent_item.childItems:
                child_item.parentItem = parent_item
                set_parents(child_item)

        set_parents(self.item_model.rootItem)
        set_parents(self.bookmark_model.rootItem)

        self.change_active_database()

        # todo: expand saved


class AboutBox(QDialog):
    def __init__(self, parent):
        super(AboutBox, self).__init__()
        headline = QLabel('TreeNote')
        headline.setFont(QFont(model.FONT, 25))
        label = QLabel(
            self.tr(
                'Version ' + version.version_nr.replace('v', '') +
                '<br><br>'
                'TreeNote is an easy outliner for personal knowledge and task management.'
                'More info at <a href="http://www.treenote.de/">www.treenote.de</a>.<br>'
                '<br>'
                'Contact me at j.korte@me.com if you have an idea or issue!<br>'
                '<br>'
                'This program is free software: you can redistribute it and/or modify it under the terms of the'
                'GNU General Public License as published by the Free Software Foundation, version 3 of the License.'))
        label.setOpenExternalLinks(True)
        label.setTextFormat(Qt.RichText)
        label.setWordWrap(True)
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.button(QDialogButtonBox.Ok).clicked.connect(self.reject)
        grid = QGridLayout()
        grid.setContentsMargins(20, 20, 20, 20)
        grid.setSpacing(20)
        grid.addWidget(headline, 0, 0)  # row, column
        grid.addWidget(label, 1, 0)  # row, column
        grid.addWidget(button_box, 2, 0, 1, 1, Qt.AlignCenter)  # fromRow, fromColumn, rowSpan, columnSpan.
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
        if event.key() == Qt.Key_Down or event.key() == Qt.Key_Up:
            self.main.focused_column().view.setFocus()
            if self.main.selected_indexes():  # if the selection remains valid after the search
                QApplication.sendEvent(self.main.focused_column().view, event)
            else:
                self.main.set_top_row_selected()
        else:
            QLineEdit.keyPressEvent(self, event)


class BookmarkDialog(QDialog):
    # init it with either search_bar_text or index set
    # search_bar_text is set: create new bookmark
    # index is set: edit existing bookmark

    def __init__(self, main_window, search_bar_text=None, index=None):
        super(BookmarkDialog, self).__init__(main_window)
        self.setMinimumWidth(600)
        self.main_window = main_window
        self.search_bar_text = search_bar_text
        self.index = index
        if index is not None:
            item = main_window.bookmark_model.getItem(index)

        name = '' if index is None else item.text
        self.name_edit = QLineEdit(name)

        if search_bar_text is None:
            search_bar_text = item.search_text
        self.search_bar_text_edit = QLineEdit(search_bar_text)

        shortcut = '' if index is None else item.shortcut
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
            new_item_position = len(self.main_window.bookmark_model.rootItem.childItems)
            self.main_window.bookmark_model.insert_remove_rows(new_item_position, QModelIndex())
            self.index = self.main_window.bookmark_model.index(new_item_position, 0, QModelIndex())
        self.main_window.bookmark_model.set_data(self.name_edit.text(), index=self.index, field='text')
        self.main_window.bookmark_model.set_data(self.search_bar_text_edit.text(), index=self.index,
                                                 field=model.SEARCH_TEXT)
        self.main_window.bookmark_model.set_data(self.shortcut_edit.keySequence().toString(), index=self.index,
                                                 field=model.SHORTCUT)
        self.main_window.fill_bookmarkShortcutsMenu()
        self.main_window.save_file()
        super(BookmarkDialog, self).accept()


class ShortcutDialog(QDialog):
    def __init__(self, main_window, index):
        super(QDialog, self).__init__(main_window)
        self.setMinimumWidth(340)
        self.main_window = main_window
        self.index = index
        item = main_window.item_model.getItem(index)
        self.shortcut_edit = QKeySequenceEdit()
        self.shortcut_edit.setKeySequence(QKeySequence(item.shortcut))
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
        self.main_window.item_model.set_data(self.shortcut_edit.keySequence().toString(), index=self.index,
                                             field=model.SHORTCUT)
        self.main_window.fill_bookmarkShortcutsMenu()
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


class UpdateDialog(QDialog):
    def __init__(self, parent):
        super(UpdateDialog, self).__init__(parent)
        releaseNotesEdit = QPlainTextEdit(parent.new_version_data['body'])
        releaseNotesEdit.setReadOnly(True)
        releaseNotesEdit.setMinimumHeight(400)
        skipButton = QPushButton('Skip this version')
        skipButton.clicked.connect(self.skip)
        ignoreButton = QPushButton('Ignore for now')
        ignoreButton.clicked.connect(self.close)
        downloadButton = QPushButton('Download')
        downloadButton.setDefault(True)
        downloadButton.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('http://www.treenote.de/download/')))

        grid = QGridLayout()  # fromRow, fromColumn, rowSpan, columnSpan
        grid.addWidget(QLabel(self.tr('Treenote ' + parent.new_version_data['tag_name'][1:] +
                                      ' is now available - you have ' + version.version_nr[1:])), 0, 0, 1, -1)
        grid.addItem(QSpacerItem(-1, 10), 1, 0, 1, 1)
        grid.addWidget(QLabel(self.tr('Release notes:')), 2, 0, 1, -1)
        grid.addWidget(releaseNotesEdit, 3, 0, 1, -1)
        grid.addItem(QSpacerItem(-1, 10), 4, 0, 1, 1)
        grid.addWidget(QLabel(self.tr('Just extract the downloaded .zip file into your current treenote folder.\n'
                                      'Your data and settings will be kept.')), 5, 0, 1, -1)
        grid.addItem(QSpacerItem(-1, 10), 6, 0, 1, 1)

        row = QWidget()
        rowLayout = QHBoxLayout()
        rowLayout.addWidget(ignoreButton)
        rowLayout.addWidget(skipButton)
        rowLayout.addWidget(downloadButton)
        row.setLayout(rowLayout)
        grid.addWidget(row, 7, 2, 1, -1, Qt.AlignLeft)
        grid.setContentsMargins(20, 20, 20, 20)
        self.setLayout(grid)
        self.setWindowTitle(self.tr('Software Update'))

    def skip(self):
        self.parent().getQSettings().setValue('skip_version', self.parent().new_version_data['tag_name'])
        self.reject()


class SettingsDialog(QDialog):
    def __init__(self, parent):
        super(SettingsDialog, self).__init__(parent)
        self.parent = parent
        theme_dropdown = QComboBox()
        theme_dropdown.addItems(['Light', 'Dark'])
        current_palette_index = 0 if QApplication.palette() == self.parent.light_palette else 1
        theme_dropdown.setCurrentIndex(current_palette_index)
        theme_dropdown.currentIndexChanged[int].connect(self.change_theme)
        indentation_spinbox = QSpinBox()
        indentation_spinbox.setValue(parent.focused_column().view.indentation())
        indentation_spinbox.setRange(30, 100)
        indentation_spinbox.valueChanged[int].connect(lambda: parent.set_indentation(indentation_spinbox.value()))
        buttonBox = QDialogButtonBox(QDialogButtonBox.Close)
        buttonBox.button(QDialogButtonBox.Close).clicked.connect(self.close)
        backup_interval_spinbox = QSpinBox()
        backup_interval_spinbox.setValue(parent.backup_interval)
        backup_interval_spinbox.setRange(0, 10000)
        backup_interval_spinbox.valueChanged[int].connect(
            lambda: parent.start_backup_service(backup_interval_spinbox.value()))

        layout = QFormLayout()
        layout.addRow('Theme:', theme_dropdown)
        layout.addRow('Indentation of children in the tree:', indentation_spinbox)
        backup_label = QLabel("Create a plain text export of all databases which have changes to the folder 'backups' "
                              "every ... minutes (0 minutes disables this feature):")
        backup_label.setWordWrap(True)
        backup_label.setAlignment(Qt.AlignRight)
        backup_label.setMinimumSize(550, 0)
        layout.addRow(backup_label, backup_interval_spinbox)
        layout.addRow(buttonBox)
        layout.setLabelAlignment(Qt.AlignRight)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setVerticalSpacing(30)
        self.setLayout(layout)
        self.setWindowTitle(self.tr('Preferences'))

    def change_theme(self, current_palette_index):
        if current_palette_index == 0:
            new_palette = self.parent.light_palette
        else:
            new_palette = self.parent.dark_palette
        self.parent.set_palette(new_palette)


class DelayedExecutionTimer(QObject):  # source: https://wiki.qt.io/Delay_action_to_wait_for_user_interaction
    triggered = pyqtSignal(str)

    def __init__(self, parent):
        super(DelayedExecutionTimer, self).__init__(parent)
        # The minimum delay is the time the class will wait after being triggered before emitting the triggered() signal
        self.minimumDelay = 200
        # The maximum delay is the maximum time that will pass before a call to
        # the trigger() slot leads to a triggered() signal.
        self.maximumDelay = 500
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

    def paintSection(self, painter, rect, logical_index):
        opt = QStyleOptionHeader()
        opt.rect = rect
        opt.text = self.text
        QApplication.style().drawControl(QStyle.CE_Header, opt, painter, self)


class ResizeTreeView(QTreeView):
    def resizeEvent(self, event):
        self.itemDelegate().sizeHintChanged.emit(QModelIndex())


if __name__ == '__main__':
    if sys.platform == "darwin":
        subprocess.call(['/usr/bin/open', '/Applications/Apache CouchDB.app'])

    app = QApplication(sys.argv)
    app.setApplicationName('TreeNote')
    app.setOrganizationName('Jan Korte')
    app.setWindowIcon(QIcon(':/logo'))
    QFontDatabase.addApplicationFont(RESOURCE_FOLDER + 'SourceSansPro-Regular.otf')

    form = MainWindow()
    form.show()
    app.exec_()
