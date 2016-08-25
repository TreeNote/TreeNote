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

import copy
import json
import logging
import os
import pickle
import plistlib
import re
import sys
import textwrap
from functools import partial
from traceback import format_exception
#
import requests
import sip  # needed for pyinstaller, get's removed with 'optimize imports'!
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtPrintSupport import *
#
import model
import tag_model
import planned_model
import util
import version
from resources import qrc_resources  # get's removed with 'optimize imports'!

BOOKMARKS_HEADER = ['Bookmarks']
TREE_HEADER = ['Text', 'Estimate', 'Start date']
HIDE_SHOW_THE_SIDEBARS = 'Hide / show the sidebars'
HIDE_SHOW_COLUMNS = "Hide / show the columns 'Estimate' and 'Start date'"
COLUMNS_HIDDEN = 'columns_hidden'
EDIT_BOOKMARK = 'Edit selected bookmark'
EDIT_QUICKLINK = 'Edit selected quick link shortcut'
EXPANDED_ITEMS = 'EXPANDED_ITEMS'
EXPANDED_QUICKLINKS_INDEXES = 'EXPANDED_QUICKLINKS'
SELECTED_INDEX = 'SELECTED_ID'
APP_FONT_SIZE = 17 if sys.platform == "darwin" else 14
INITIAL_SIDEBAR_WIDTH = 200
ESTIMATE_COLUMN_WIDTH = 85
TOOLBAR_MARGIN = 6
RESOURCE_FOLDER = os.path.dirname(os.path.realpath(__file__)) + os.sep + 'resources' + os.sep

logging.getLogger("requests").setLevel(logging.WARNING)
logging.basicConfig(filename=os.path.dirname(os.path.realpath(__file__)) + os.sep + 'treenote.log',
                    format='%(asctime)s - %(levelname)s - %(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)


def exception_handler(type_, text, traceback):
    print(''.join(format_exception(type_, text, traceback)))
    logger.exception('Uncaught exception:', exc_info=(type_, text, traceback))


sys.excepthook = exception_handler


def git_tag_to_versionnr(git_tag):
    return int(re.sub(r'\.|v', '', git_tag))


def time_stamp():
    return QDate.currentDate().toString('yyyy-MM-dd') + '-' + QTime.currentTime().toString('hh-mm-ss-zzz')


class ExportThread(QThread):
    def run(self):
        path = os.path.dirname(os.path.realpath(__file__)) + os.sep + 'backups' + os.sep + \
               self.main_window.save_path.split(os.sep)[-1].replace('.treenote', '') + '_' + time_stamp()
        self.main_window.save_json(path + '.json')


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

        self.item_model = model.TreeModel(self, header_list=TREE_HEADER)
        self.bookmark_model = model.TreeModel(self, header_list=BOOKMARKS_HEADER)

        settings = self.getQSettings()

        last_opened_file_path = settings.value('last_opened_file_path')
        if last_opened_file_path:
            try:
                self.open_file(last_opened_file_path)
            except Exception as e:
                QMessageBox.information(self, '', '{} \n\n Did not find last Treenote '
                                                  'file. Creating a new treenote file...'.format(e), QMessageBox.Ok)
                self.new_file()
        else:
            self.import_backup(RESOURCE_FOLDER + 'example_tree.json', 'example_tree_{}.treenote'.format(time_stamp()))

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
        self.quicklinks_view.setHeader(CustomHeaderView('Quick tree'))
        self.quicklinks_view.header().setToolTip('Focus on the clicked row')
        self.quicklinks_view.hideColumn(1)
        self.quicklinks_view.hideColumn(2)
        self.quicklinks_view.setUniformRowHeights(True)  # improves performance
        self.quicklinks_view.setAnimated(True)
        self.quicklinks_view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)

        quicklinks_view_holder = QWidget()  # needed to add space
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 6, 0)  # left, top, right, bottom
        layout.addWidget(self.quicklinks_view)
        quicklinks_view_holder.setLayout(layout)

        # second column

        self.item_views_splitter = QSplitter(Qt.Horizontal)
        self.item_views_splitter.setHandleWidth(0)  # thing to grab the splitter

        # third column

        def init_dropdown(key, *item_names):
            comboBox = QComboBox()
            comboBox.addItems(item_names)
            comboBox.currentIndexChanged[str].connect(lambda: self.filter(key, comboBox.currentText()))
            return comboBox

        self.task_dropdown = init_dropdown('t=', self.tr('all'), model.NOTE, model.TASK, model.DONE_TASK)
        self.estimate_dropdown = init_dropdown('e', self.tr('all'), self.tr('<20'), self.tr('=60'), self.tr('>60'))
        self.color_dropdown = init_dropdown('c=', self.tr('all'), self.tr('green'), self.tr('yellow'), self.tr('red'),
                                            self.tr('orange'), self.tr('blue'), self.tr('violet'), self.tr('no color'))
        self.hideTagsCheckBox = QCheckBox('Hide rows\nwith a tag')
        self.hideTagsCheckBox.clicked.connect(self.filter_hide_tags)
        self.hideFutureStartdateCheckBox = QCheckBox('Hide rows with\nfuture start date')
        self.hideFutureStartdateCheckBox.clicked.connect(self.filter_hide_future_startdate)
        self.showOnlyStartdateCheckBox = QCheckBox('Show only rows\nwith a start date')
        self.showOnlyStartdateCheckBox.clicked.connect(self.filter_show_only_startdate)

        layout = QGridLayout()
        layout.setContentsMargins(2 + 10, 0, 6, 0)  # left, top, right, bottom
        layout.addWidget(QLabel('Tasks:'), 1, 0, 1, 1)
        layout.addWidget(self.task_dropdown, 1, 1, 1, 1)
        layout.addWidget(QLabel('Estimate:'), 2, 0, 1, 1)
        layout.addWidget(self.estimate_dropdown, 2, 1, 1, 1)
        layout.addWidget(QLabel('Color:'), 3, 0, 1, 1)
        layout.addWidget(self.color_dropdown, 3, 1, 1, 1)
        layout.addWidget(self.hideTagsCheckBox, 5, 0, 1, 2)
        layout.addWidget(self.hideFutureStartdateCheckBox, 6, 0, 1, 2)
        layout.addWidget(self.showOnlyStartdateCheckBox, 7, 0, 1, 2)
        layout.setColumnStretch(1, 10)
        self.filter_spoiler = Spoiler(self, 'Available filters')
        self.filter_spoiler.setContentLayout(layout)

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
        self.bookmarks_view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)

        self.tag_view = QTreeView()
        self.tag_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tag_view.customContextMenuRequested.connect(self.open_rename_tag_contextmenu)
        self.tag_view.setModel(tag_model.TagModel())
        self.tag_view.selectionModel().selectionChanged.connect(self.filter_tag)
        self.tag_view.setUniformRowHeights(True)  # improves performance
        self.tag_view.setStyleSheet('QTreeView:item { padding: ' + str(
            model.SIDEBARS_PADDING + model.SIDEBARS_PADDING_EXTRA_SPACE) + 'px; }')
        self.tag_view.setAnimated(True)
        self.tag_view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)

        self.third_column_splitter = QSplitter(Qt.Vertical)
        self.third_column_splitter.setHandleWidth(0)
        self.third_column_splitter.setChildrenCollapsible(False)
        self.third_column_splitter.addWidget(self.filter_spoiler)
        self.third_column_splitter.addWidget(self.bookmarks_view)
        self.third_column_splitter.addWidget(self.tag_view)
        self.third_column_splitter.setContentsMargins(6, 0, 0, 0)  # left, top, right, bottom
        self.third_column_splitter.setStretchFactor(0, 0)
        self.third_column_splitter.setStretchFactor(1, 0)
        self.third_column_splitter.setStretchFactor(2, 1)  # when the window is resized, only tags shall grow

        # add columns to main

        self.mainSplitter.addWidget(quicklinks_view_holder)
        self.mainSplitter.addWidget(self.item_views_splitter)
        self.mainSplitter.addWidget(self.third_column_splitter)
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
            return qaction

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
        add_action('fileSelectedRows',
                   QAction(self.tr('File selected rows...'), self, shortcut='F', triggered=self.file),
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
        add_action('colorVioletAction',
                   QAction('Violet', self, shortcut='V', triggered=lambda: self.color_row('v')),
                   list=self.item_view_actions)
        add_action('colorGreyAction',
                   QAction('Grey', self, shortcut='E', triggered=lambda: self.color_row('e')),
                   list=self.item_view_actions)
        add_action('colorNoColorAction',
                   QAction('No color', self, shortcut='N', triggered=lambda: self.color_row('n')),
                   list=self.item_view_actions)
        add_action('noEstimateAction', QAction('No estimate', self, shortcut='0', triggered=partial(self.estimate, '')),
                   list=self.item_view_actions)
        add_action('increaseEstimateAction',
                   QAction('Increase estimate', self, shortcut='+', triggered=partial(self.adjust_estimate, 10)),
                   list=self.item_view_actions)
        add_action('decreaseEstimateAction',
                   QAction('Decrease estimate', self, shortcut='-', triggered=partial(self.adjust_estimate, -10)),
                   list=self.item_view_actions)
        add_action('toggleTaskAction',
                   QAction(self.tr('Toggle: note, todo, done'), self, shortcut='Space', triggered=self.toggle_task),
                   list=self.item_view_actions)
        add_action('openLinkAction',
                   QAction(self.tr('Open URLs of selected rows in the web browser'), self, shortcut='L',
                           triggered=self.open_links), list=self.item_view_actions)
        add_action('openInternalLinkAction',
                   QAction(self.tr('Set internal link of selected row as root'), self, shortcut='I',
                           triggered=self.open_internal_link), list=self.item_view_actions)
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
                   QAction(HIDE_SHOW_THE_SIDEBARS, self, shortcut='Shift+S', triggered=self.toggle_sidebars))
        add_action('toggleFullScreenAction',
                   QAction('Toggle fullscreen mode', self, shortcut='Shift+F', triggered=self.toggle_fullscreen))
        add_action('toggleColumnsAction',
                   QAction(HIDE_SHOW_COLUMNS, self, shortcut='Shift+C', triggered=self.toggle_columns))
        add_action('toggleProjectAction',
                   QAction(self.tr('Toggle: note, sequential project, parallel project, paused project'), self,
                           shortcut='P', triggered=self.toggle_project), list=self.item_view_actions)
        add_action('appendRepeatAction',
                   QAction(self.tr("Append 'repeat=1w'"), self, shortcut='Ctrl+R', triggered=self.append_repeat),
                   list=self.item_view_actions)
        add_action('appendRepeatAction',
                   QAction(self.tr("Append 'repeat=1w'"), self, shortcut='Ctrl+R', triggered=self.append_repeat),
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
        add_action('exportJSONAction',
                   QAction(self.tr('as a TreeNote JSON file...'), self, triggered=self.export_json))
        add_action('exportPlainTextAction',
                   QAction(self.tr('as a plain text file...'), self, triggered=self.export_plain_text))
        add_action('printAction', QAction(self.tr('&Print'), self, shortcut=QKeySequence.Print, triggered=self.print))
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
        add_action('importHitListAction',
                   QAction(self.tr('from The Hit List (Mac)...'), self, triggered=lambda: ImportDialog(
                       self, "*.thlbackup", "Import from The Hit List",
                       "Preparation in The Hit List: Move all tasks in a single list and there below a single"
                       "item called 'ROOT'.\n"
                       "Backup the database (this creates a .thlbackup file).\n"
                       "Task notes, creation date and modification date will get lost.\n"
                       "Tags won't be converted. You may replace their '@' with ':' manually before exporting.").exec()))
        add_action('importJSONAction',
                   QAction(self.tr('from TreeNote JSON export...'), self, triggered=lambda: ImportDialog(
                       self, "*.json", "Import from TreeNote Backup", None).exec()))

        self.fileMenu = self.menuBar().addMenu(self.tr('File'))
        self.fileMenu.addAction(self.newFileAction)
        self.fileMenu.addAction(self.openFileAction)
        self.importMenu = self.fileMenu.addMenu(self.tr('Import'))
        self.importMenu.addAction(self.importJSONAction)
        self.importMenu.addAction(self.importHitListAction)
        self.exportMenu = self.fileMenu.addMenu(self.tr('Export'))
        self.exportMenu.addAction(self.exportJSONAction)
        self.exportMenu.addAction(self.exportPlainTextAction)
        self.fileMenu.addAction(self.printAction)
        self.fileMenu.addSeparator()
        self.fileMenu.addAction(self.editShortcutAction)
        self.fileMenu.addAction(self.editBookmarkAction)
        self.fileMenu.addAction(self.deleteBookmarkAction)
        self.fileMenu.addAction(self.renameTagAction)
        self.fileMenu.addSeparator()
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
        self.structureMenu.addAction(self.fileSelectedRows)
        self.structureMenu.addSeparator()
        self.structureMenu.addAction(self.cutAction)
        self.structureMenu.addAction(self.copyAction)
        self.structureMenu.addAction(self.pasteAction)

        self.editRowMenu = self.menuBar().addMenu(self.tr('Edit row'))
        self.editRowMenu.addAction(self.editRowAction)
        self.editRowMenu.addAction(self.toggleTaskAction)
        self.editRowMenu.addAction(self.toggleProjectAction)
        self.colorMenu = self.editRowMenu.addMenu(self.tr('Color selected rows'))
        self.colorMenu.addAction(self.colorGreenAction)
        self.colorMenu.addAction(self.colorYellowAction)
        self.colorMenu.addAction(self.colorBlueAction)
        self.colorMenu.addAction(self.colorRedAction)
        self.colorMenu.addAction(self.colorOrangeAction)
        self.colorMenu.addAction(self.colorVioletAction)
        self.colorMenu.addAction(self.colorGreyAction)
        self.colorMenu.addAction(self.colorNoColorAction)
        self.estimateMenu = self.editRowMenu.addMenu(self.tr('Set estimate of selected rows'))
        self.estimateMenu.addAction(self.noEstimateAction)
        for i in [10, 15, 30, 45, 60, 90, 120, 180]:
            action = add_action('',
                                QAction('{} minutes'.format(i), self, shortcut=','.join(number for number in str(i)),
                                        triggered=partial(self.estimate, i)), list=self.item_view_actions)
            self.estimateMenu.addAction(action)

            shortcut_numpad = ''
            for number in str(i):
                shortcut_numpad += 'Num+' + number + ','
            shortcut = QShortcut(QKeySequence(shortcut_numpad[:-1]), self)
            shortcut.setContext(Qt.ApplicationShortcut)
            shortcut.activated.connect(partial(self.estimate, i))
        self.estimateMenu.addAction(self.increaseEstimateAction)
        self.estimateMenu.addAction(self.decreaseEstimateAction)
        self.remindInMenu = self.editRowMenu.addMenu(self.tr('Set start date of selected rows'))
        self.remindInMenu.addAction(
            add_action('', QAction('No start date', self, shortcut='.,D',
                                   triggered=partial(self.remindIn, 0)), list=self.item_view_actions))
        for time_unit, value, max in [('days', 1, 7), ('weeks', 7, 4), ('months', 30, 10), ('years', 365, 4)]:
            for i in range(1, max):
                self.remindInMenu.addAction(
                    add_action('', QAction('Remind in {} {}'.format(i, time_unit), self,
                                           shortcut='{},{}'.format(i, time_unit[0]),
                                           triggered=partial(self.remindIn, i * value)), list=self.item_view_actions))
                shortcut = QShortcut(QKeySequence('Num+{},{}'.format(i, time_unit[0])), self)
                shortcut.setContext(Qt.ApplicationShortcut)
                shortcut.activated.connect(partial(self.remindIn, i * value))
        self.editRowMenu.addAction(self.appendRepeatAction)
        self.setPlanMenu = self.editRowMenu.addMenu(self.tr('Set plan of selected rows'))
        for i in range(6):
            self.setPlanMenu.addAction(
                add_action('', QAction(model.NUMBER_PLAN_DICT[i], self, shortcut='Shift+{}'.format(i),
                                       triggered=partial(self.set_plan, i)), list=self.item_view_actions))

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
        self.viewMenu.addAction(self.openInternalLinkAction)
        self.viewMenu.addAction(self.focusSearchBarAction)
        self.viewMenu.addAction(self.toggleSideBarsAction)
        self.viewMenu.addAction(self.toggleColumnsAction)
        self.viewMenu.addAction(self.toggleFullScreenAction)
        self.viewMenu.addSeparator()
        self.viewMenu.addAction(self.increaseFontAction)
        self.viewMenu.addAction(self.decreaseFontAction)
        self.viewMenu.addAction(self.increasePaddingAction)
        self.viewMenu.addAction(self.decreasePaddingAction)
        self.viewMenu.addSeparator()
        self.viewMenu.addAction(self.increaseInterFaceFontAction)
        self.viewMenu.addAction(self.decreaseInterFaceFontAction)

        self.bookmarkShortcutsMenu = self.menuBar().addMenu(self.tr('My shortcuts'))

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

        third_column_splitter_state = settings.value('third_column_splitter')
        if third_column_splitter_state is not None:
            self.third_column_splitter.restoreState(third_column_splitter_state)

        # first (do this before the label 'second')
        self.change_active_tree()

        self.reset_view()  # inits checkboxes
        self.focused_column().view.setFocus()
        self.update_actions()

        # second
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
            margin = 0 if self.is_sidebar_shown() else TOOLBAR_MARGIN
            self.set_toolbar_margins(margin)
        else:
            self.toggle_sidebars()

        QTimer().singleShot(200, self.reset_view)

        # restore columns
        columns_hidden = settings.value(COLUMNS_HIDDEN, 'true')
        if columns_hidden == 'true':
            self.toggle_columns()

        self.backup_timer = QTimer()
        self.backup_timer.timeout.connect(self.backup_tree_if_changed)
        self.start_backup_service(settings.value('backup_interval', 10))

        self.print_size = float(settings.value('print_size', 1))
        self.new_rows_plan_item_creation_date = settings.value('new_rows_plan_item_creation_date')
        self.set_indentation_and_style_tree(settings.value('indentation', 40))
        self.check_for_software_update()

    def backup_tree_if_changed(self):
        if self.item_model.changed:
            self.item_model.changed = False
            self.worker = ExportThread()
            self.worker.main_window = self
            self.worker.start()

    def start_backup_service(self, minutes):
        self.backup_interval = int(minutes)
        self.backup_timer.stop()
        if minutes != 0:
            self.backup_timer.start(self.backup_interval * 1000 * 60)  # time specified in ms

    def check_for_software_update(self):
        try:
            self.new_version_data = requests.get(
                'https://api.github.com/repos/treenote/treenote/releases/latest').json()
            skip_this_version = self.getQSettings().value('skip_version') is not None and \
                                self.getQSettings().value('skip_version') == self.new_version_data['tag_name']
            is_newer_version = git_tag_to_versionnr(version.version_nr) < \
                               git_tag_to_versionnr(self.new_version_data['tag_name'])
            if not skip_this_version and is_newer_version:
                UpdateDialog(self).exec_()
        except:
            pass

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

    def get_widgets(self):
        return [QApplication,
                self.focused_column().toggle_sidebars_button,
                self.focused_column().bookmark_button,
                self.focused_column().search_bar,
                self.focused_column().view,
                self.focused_column().view.verticalScrollBar(),
                self.focused_column().view.header(),
                self.tag_view,
                self.tag_view.header(),
                self.tag_view.verticalScrollBar(),
                self.filter_spoiler.toggleButton,
                self.filter_spoiler.contentArea]

    def set_palette(self, new_palette):
        for widget in self.get_widgets():
            widget.setPalette(new_palette)
            self.filter_spoiler.contentArea.setStyleSheet("QScrollArea { border: none; }")

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
        self.quicklinks_view.selectionModel().select(QItemSelection(real_index, real_index),
                                                     QItemSelectionModel.ClearAndSelect)

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

    def change_active_tree(self):
        if not hasattr(self, 'item_views_splitter'):
            return
        self.focused_column().filter_proxy.setSourceModel(self.item_model)
        self.quicklinks_view.setModel(self.item_model)
        self.quicklinks_view.setItemDelegate(model.BookmarkDelegate(self, self.item_model))
        self.set_undo_actions()
        self.old_search_text = 'dont save expanded states of last tree when switching to next tree'
        self.setup_tag_model()
        self.reset_view()
        for index in self.item_model.indexes():
            if self.item_model.getItem(index) == self.item_model.selected_item:
                self.set_selection(index, index)
                QTimer().singleShot(100, lambda: self.focused_column().view.scrollTo(
                    self.filter_proxy_index_from_model_index(index)))
                break
        self.fill_bookmarkShortcutsMenu()
        self.setWindowTitle(self.save_path + ' - TreeNote')

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
        settings.setValue('first_column_splitter', self.third_column_splitter.saveState())
        settings.setValue('fontsize', self.fontsize)
        settings.setValue('interface_fontsize', self.interface_fontsize)
        settings.setValue('padding', self.padding)
        settings.setValue('splitter_sizes', self.mainSplitter.saveState())
        settings.setValue('indentation', self.focused_column().view.indentation())
        settings.setValue('backup_interval', self.backup_interval)
        settings.setValue('last_opened_file_path', self.save_path)
        settings.setValue('print_size', self.print_size)
        settings.setValue('new_rows_plan_item_creation_date', self.new_rows_plan_item_creation_date)
        settings.setValue(COLUMNS_HIDDEN, self.focused_column().view.isHeaderHidden())

        # save theme
        theme = 'light' if app.palette() == self.light_palette else 'dark'
        settings.setValue('theme', theme)
        self.save_file(save_expanded_states=True)

    def getQSettings(self):
        settings_file = 'treenote_settings.ini'
        if len(sys.argv) > 1 and sys.argv[1] == 'develop':
            settings_file = 'treenote_settings_for_developing.ini'
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

    def filter_tag(self):
        current_index = self.tag_view.selectionModel().currentIndex()
        current_tag = self.tag_view.model().data(current_index, tag_model.FULL_PATH)
        if current_tag is not None:
            search_bar_text = self.focused_column().search_bar.text()
            new_text = re.sub(r':\S* ', current_tag + ' ', search_bar_text)  # matches a tag
            if ':' not in search_bar_text:
                new_text += ' ' + current_tag + ' '
            self.set_searchbar_text_and_search(new_text)

    def get_index_by_creation_date(self, creation_date):
        for index in self.item_model.indexes():
            if str(self.item_model.getItem(index).creation_date_time) == str(creation_date):
                return index

    # set the search bar text according to the selected bookmark
    def filter_bookmark(self, bookmark_index):
        bookmark_item = self.bookmark_model.getItem(bookmark_index)

        if bookmark_item.saved_root_item_creation_date_time:
            focus_index = self.get_index_by_creation_date(bookmark_item.saved_root_item_creation_date_time)
            if focus_index:
                self.focus_index(self.filter_proxy_index_from_model_index(focus_index))

        new_search_bar_text = bookmark_item.search_text
        self.set_searchbar_text_and_search(new_search_bar_text)
        # if shortcut was used: select bookmarks row for visual highlight
        self.set_selection(bookmark_index, bookmark_index)

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
        return self.focused_column().filter_proxy.mapFromSource(model_index)

    def set_selection(self, index_from, index_to):
        if self.focused_column().view.state() != QAbstractItemView.EditingState:
            view = self.current_view()
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
        current_root_index = self.current_view().rootIndex()
        top_most_index = self.focused_column().filter_proxy.index(0, 0, current_root_index)
        self.set_selection(top_most_index, top_most_index)
        self.current_view().setFocus()

    def reset_view(self):
        self.hideFutureStartdateCheckBox.setChecked(False)
        self.hideTagsCheckBox.setChecked(False)
        self.showOnlyStartdateCheckBox.setChecked(False)
        self.task_dropdown.setCurrentIndex(0)
        self.estimate_dropdown.setCurrentIndex(0)
        self.color_dropdown.setCurrentIndex(0)
        self.bookmarks_view.selectionModel().setCurrentIndex(QModelIndex(), QItemSelectionModel.ClearAndSelect)
        self.quicklinks_view.selectionModel().setCurrentIndex(QModelIndex(), QItemSelectionModel.ClearAndSelect)
        self.focus_index(QModelIndex())
        self.set_searchbar_text_and_search('')
        self.setup_tag_model()

    def change_interface_font_size(self, step):
        self.new_if_size = self.interface_fontsize + step
        if self.new_if_size <= 25 and self.new_if_size >= 8:
            self.interface_fontsize += step
            for widget in self.get_widgets():
                widget.setFont(QFont(model.FONT, self.interface_fontsize))

    def change_font_size(self, step):
        if step > 0 or self.fontsize > 1:
            self.fontsize += step
            self.focused_column().view.itemDelegate().sizeHintChanged.emit(QModelIndex())

    def change_padding(self, step):
        if not (step == -1 and self.padding == 2):
            self.padding += step
            self.focused_column().view.itemDelegate().sizeHintChanged.emit(QModelIndex())

    def toggle_fullscreen(self):
        if self.windowState() != Qt.WindowFullScreen:
            self.showFullScreen()
            self.search_holder.hide()
            self.menuBar().setMaximumHeight(0)
        else:
            self.showMaximized()
            self.search_holder.show()
            self.menuBar().setMaximumHeight(99)

    def is_sidebar_shown(self):
        return self.mainSplitter.widget(0).size().width() > 0 or self.mainSplitter.widget(2).size().width() > 0

    def toggle_sidebars(self):
        self.path_bar.setMaximumWidth(0)
        if self.is_sidebar_shown():  # hide
            self.mainSplitter.moveSplitter(0, 1)
            self.mainSplitter.moveSplitter(self.width(), 2)
            margin = TOOLBAR_MARGIN
        else:
            self.mainSplitter.moveSplitter(INITIAL_SIDEBAR_WIDTH, 1)
            self.mainSplitter.moveSplitter(self.width() - INITIAL_SIDEBAR_WIDTH, 2)
            margin = 0
        self.set_toolbar_margins(margin)
        self.set_path_bar_width()

    def set_toolbar_margins(self, margin):
        self.search_holder.layout().setContentsMargins(margin, TOOLBAR_MARGIN, margin, 0)

    def toggle_columns(self):
        if self.focused_column().view.isHeaderHidden():
            self.focused_column().view.showColumn(1)
            self.focused_column().view.showColumn(2)
            self.focused_column().view.setHeaderHidden(False)
        else:
            self.focused_column().view.hideColumn(1)
            self.focused_column().view.hideColumn(2)
            self.focused_column().view.setHeaderHidden(True)

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

        # apply filter
        self.focused_column().filter_proxy.filter = search_text
        self.focused_column().filter_proxy.invalidateFilter()
        # deselect tag if user changes the search string
        selected_tags = self.tag_view.selectionModel().selectedRows()
        if len(selected_tags) > 0 and selected_tags[0].data() not in search_text:
            self.tag_view.selectionModel().setCurrentIndex(QModelIndex(), QItemSelectionModel.Clear)
            # changing dropdown index accordingly is not that easy,
            # because changing it fires "color_clicked" which edits search bar

        # restore expanded state when we are now in normal mode again after a text search
        if self.is_no_text_search(search_text):
            self.item_model.expand_saved()
        # expand all items when doing a text search
        else:
            self.expand_or_collapse_children(QModelIndex(), True)

        # set selection
        # ( the selection is also set after pressing Enter, in SearchBarQLineEdit and insert_row() )
        # Set only if text was set programmatically e.g. because the user selected a dropdown,
        # and if the previous selected row was filtered out by the search.
        if not self.focused_column().search_bar.isModified() and not self.is_selection_visible():
            self.set_top_row_selected()

        self.planned_view.model().refresh_model()

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
                self.focused_column().view.setExpanded(index, True)
                # save expanded state only when in normal mode,
                # not when doing a text search and therefore having everything expanded
                if self.is_no_text_search(self.focused_column().search_bar.text()):
                    self.focused_column().filter_proxy.getItem(index).expanded = True

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
                self.focused_column().view.setExpanded(index, False)
                if self.is_no_text_search(self.focused_column().search_bar.text()):
                    self.focused_column().filter_proxy.getItem(index).expanded = False

    def is_no_text_search(self, text):
        def is_filter_keyword(token):
            return token.startswith(model.SORT) or token.startswith('c=') or token.startswith('t=') or \
                   re.match(r'e(<|>|=)', token) or token.startswith(model.ONLY_START_DATE) or \
                   token.startswith(model.HIDE_TAGS) or token.startswith(model.HIDE_FUTURE_START_DATE)

        # it is no text search, if it is empty or all tokens are a filter keyword
        return text == '' or all(is_filter_keyword(token) for token in text.split())

    def rename_tag(self, tag, new_name):
        for item in self.item_model.items():
            if tag in item.text:
                item.text = item.text.replace(tag, new_name)
        self.setup_tag_model()

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

    def file(self):
        popup = QFrame(self, Qt.Window | Qt.FramelessWindowHint)
        edit = FileLineEdit(self, popup)
        rect = self.focused_column().view.visualRect(self.selected_indexes()[-1])
        rect = self.mapToGlobal(rect.bottomLeft())
        popup.move(rect.x() + 100, rect.y() + 40)
        popup.show()

    def insert_child(self):
        index = self.current_index()
        if self.focused_column().view.state() == QAbstractItemView.EditingState:
            # save the edit of the yet open editor
            self.focused_column().view.selectionModel().currentChanged.emit(index, index)
        self.focused_column().filter_proxy.insert_row(0, index)

    def insert_row(self):
        # focus view after search with enter
        if self.focused_column().search_bar.hasFocus():
            self.current_view().setFocus()
            if not self.selected_indexes():
                self.set_top_row_selected()
        elif self.current_view().hasFocus() and isinstance(self.current_view().model(), planned_model.PlannedModel):
            selected = self.selected_indexes()
            planned_level = self.current_view().model().getItem(selected[0]).planned if selected else 1
            parent_index = self.get_index_by_creation_date(self.new_rows_plan_item_creation_date)
            parent_filter_proxy_index = self.filter_proxy_index_from_model_index(
                parent_index) if parent_index else self.focused_column().view.rootIndex()
            self.focused_column().filter_proxy.insert_row(0, parent_filter_proxy_index)
            new_item_index = self.item_model.index(0, 0, parent_index)
            filter_proxy_index = self.filter_proxy_index_from_model_index(new_item_index)
            self.focused_column().filter_proxy.set_data(planned_level, index=filter_proxy_index, field='planned')
            planned_index = self.planned_view.model().map_to_planned_index(new_item_index)
            self.focusWidget().edit(planned_index)
            self.set_selection(planned_index, planned_index)
        # if there are no entries, pressing enter shall create a child of the current root entry
        elif len(self.item_model.rootItem.childItems) == 0:
            self.focused_column().filter_proxy.insert_row(0, self.focused_column().view.rootIndex())
        elif self.current_view().hasFocus():
            index = self.current_index()
            # if selection has childs and is expanded: create top child
            if self.current_view().isExpanded(self.current_index()) and \
                            self.focused_column().filter_proxy.rowCount(self.current_index()) > 0:
                self.insert_child()
            # create new entry below selection
            else:
                self.focused_column().filter_proxy.insert_row(index.row() + 1, index.parent())
        elif self.current_view().state() == QAbstractItemView.EditingState:
            # commit data by changing the current selection
            index = self.current_index()
            self.current_view().selectionModel().currentChanged.emit(index, index)

    def remove_selection(self):
        self.focused_column().filter_proxy.remove_rows(self.selected_indexes())

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
        self.copy()
        self.remove_selection()

    def copy(self):
        if len(self.selected_indexes()) == 1:
            rows_string = self.selected_indexes()[0].data()
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

        # remove children of items in the selection, otherwise there will be paste errors
        indexes = self.selected_indexes()

        def remove_if_parent(idx):
            if idx.parent() != QModelIndex():
                if idx.parent() in indexes:
                    indexes.remove(idx)
                else:
                    remove_if_parent(idx.parent())

        for index in self.selected_indexes():
            remove_if_parent(index)
        mime_data = ItemMimeData([self.focused_column().filter_proxy.getItem(index) for index in indexes])
        mime_data.setText(rows_string)
        QApplication.clipboard().setMimeData(mime_data)

    def paste(self):
        if isinstance(QApplication.clipboard().mimeData(), ItemMimeData):
            self.item_model.insert_remove_rows(position=self.current_index().row() + 1,
                                               parent_index=self.focused_column().filter_proxy.mapToSource(
                                                   self.current_index().parent()), set_edit_focus=False,
                                               items=copy.deepcopy(QApplication.clipboard().mimeData().items))
        else:
            # paste from plain text
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
            indention_parent_index_dict = {-1: source_index.parent()}
            for line in lines:
                stripped_line = line.lstrip('\t')
                indention = len(line) - len(stripped_line)
                # remove -, *, spaces and tabs from the beginning of the line
                cleaned_line = re.sub(r'^(-|\*)? *|\t*', '', stripped_line)
                if indention not in indention_insert_position_dict:
                    indention_insert_position_dict[indention] = 0
                child_index = self.paste_row(indention_insert_position_dict[indention],
                                             indention_parent_index_dict[indention - 1], cleaned_line)
                indention_insert_position_dict[indention] += 1
                for key in indention_insert_position_dict.keys():
                    if key > indention:
                        indention_insert_position_dict[key] = 0
                indention_parent_index_dict[indention] = child_index

    def paste_row(self, new_position, parent_index, text):
        self.item_model.insert_remove_rows(new_position, parent_index, set_edit_focus=False)
        child_index = self.item_model.index(new_position, 0, parent_index)
        self.item_model.set_data(text, child_index)
        return child_index

    # task menu actions

    def edit_row(self):
        # workaround to fix a weird bug, where the second column is skipped
        if sys.platform == "darwin" or self.current_index().column() != 1:
            self.edit_row_without_check()

    def edit_row_without_check(self):
        current_index = self.current_index()
        if self.focused_column().view.state() == QAbstractItemView.EditingState:  # change column with tab key
            next_column_number = (current_index.column() + 2)
            if next_column_number == 0 or next_column_number == 2:
                sibling_index = current_index.sibling(current_index.row(), next_column_number)
                self.focused_column().view.selectionModel().setCurrentIndex(sibling_index,
                                                                            QItemSelectionModel.ClearAndSelect)
                self.focused_column().view.edit(sibling_index)
            else:
                self.focused_column().view.setFocus()
        elif self.focused_column().view.hasFocus():
            self.focused_column().view.edit(current_index)
        else:
            self.focused_column().view.setFocus()

    def current_index(self):
        return self.current_view().selectionModel().currentIndex()

    def current_view(self):
        return self.focused_column().stacked_widget.currentWidget()

    def toggle_task(self):
        for row_index in self.focused_column().view.selectionModel().selectedRows():
            self.focused_column().filter_proxy.toggle_task(row_index)

    def toggle_project(self):
        for row_index in self.focused_column().view.selectionModel().selectedRows():
            self.focused_column().filter_proxy.toggle_project(row_index)

    def remindIn(self, days):
        date = '' if days == 0 else QDate.currentDate().addDays(days).toString('dd.MM.yy')
        self.focused_column().filter_proxy.set_data(date, index=self.current_index(), field='date')

    def append_repeat(self):
        index = self.current_index()
        self.focused_column().filter_proxy.set_data(model.TASK, index=index, field='type')
        self.focused_column().filter_proxy.set_data(QDate.currentDate().toString('dd.MM.yy'), index=index, field='date')
        self.focused_column().filter_proxy.set_data(index.data() + ' repeat=1w', index=index)
        self.edit_row()

    def estimate(self, number):
        for row_index in self.focused_column().view.selectionModel().selectedRows():
            self.focused_column().filter_proxy.set_data(str(number), index=row_index, field=model.ESTIMATE)

    def adjust_estimate(self, adjustment):
        for row_index in self.focused_column().view.selectionModel().selectedRows():
            old_estimate = self.focused_column().filter_proxy.getItem(row_index).estimate
            if old_estimate == '':
                old_estimate = 0
            new_estimate = int(old_estimate) + adjustment
            if new_estimate < 1:
                new_estimate = ''
            self.focused_column().filter_proxy.set_data(str(new_estimate), index=row_index, field=model.ESTIMATE)

    def set_plan(self, i):
        for row_index in self.focused_column().view.selectionModel().selectedRows():
            self.focused_column().filter_proxy.set_data(i, index=row_index, field='planned')

    @pyqtSlot(str)
    def color_row(self, color_character):
        for row_index in self.focused_column().view.selectionModel().selectedRows():
            self.focused_column().filter_proxy.set_data(model.CHAR_QCOLOR_DICT[color_character],
                                                        index=row_index, field='color')

    # view menu actions

    @pyqtSlot(QModelIndex)
    def focus_index(self, index):
        self.focused_column().view.setRootIndex(index)
        self.set_searchbar_text_and_search('')
        real_index = self.focused_column().filter_proxy.mapToSource(index)
        self.quicklinks_view.selectionModel().select(QItemSelection(real_index, real_index),
                                                     QItemSelectionModel.ClearAndSelect)
        if not self.focused_column().search_bar.isModified() and not self.is_selection_visible():
            self.set_top_row_selected()
        self.setup_tag_model()

        # refresh path bar
        while self.path_bar.layout().itemAt(0):
            self.path_bar.layout().itemAt(0).widget().setParent(None)

        widgets_to_add = []

        def add_parents(current_index):
            item = self.focused_column().filter_proxy.getItem(current_index)
            text = item.text.replace('\n', '')
            button = QPushButton(text)
            button.setStyleSheet('Text-align: left; padding-left: 2px; padding-right: 2px;'
                                 'padding-top: 3px; padding-bottom: 3px;')
            button.clicked.connect(lambda: self.focus_index(current_index))
            button.setMaximumWidth(button.fontMetrics().boundingRect(text).width() + 8)
            widgets_to_add.append(button)
            if item.parentItem:
                add_parents(self.focused_column().filter_proxy.parent(current_index))

        add_parents(self.focused_column().view.rootIndex())
        self.set_path_bar_width()
        for widget in reversed(widgets_to_add):
            self.path_bar.layout().addWidget(widget)

    def set_path_bar_width(self):
        margin_count_between_toolbar_widgets = 4 if self.is_sidebar_shown() else 6
        self.path_bar.setMaximumWidth(self.item_views_splitter.width() - self.tab_bar.sizeHint().width()
                                      - self.focused_column().search_bar.width()
                                      - 2 * self.focused_column().bookmark_button.sizeHint().width()
                                      - margin_count_between_toolbar_widgets * TOOLBAR_MARGIN)

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
                break
            else:  # no urls found: search the web for the selected entry
                text_without_tags = re.sub(r':(\w|:)*', '', row_index.data())
                QDesktopServices.openUrl(QUrl('https://www.google.de/search?q=' + text_without_tags))

    def open_internal_link(self):
        match = re.search(model.FIND_INTERNAL_LINK,
                          self.focused_column().view.selectionModel().selectedRows()[0].data())
        if match:
            text_to_find = match.group(1)[1:].strip(model.INTERNAL_LINK_DELIMITER)
            for index in self.item_model.indexes():
                if self.item_model.getItem(index).text == text_to_find:
                    self.focus_index(self.filter_proxy_index_from_model_index(index))
                    break

    def split_window(self):  # creates another item_view
        new_column = QWidget()

        new_column.toggle_sidebars_button = QPushButton()
        new_column.toggle_sidebars_button.setToolTip(HIDE_SHOW_THE_SIDEBARS)
        new_column.toggle_sidebars_button.setIcon(QIcon(':/toggle_sidebars'))
        new_column.toggle_sidebars_button.setStyleSheet('QPushButton {\
            width: 22px;\
            height: 22px;\
            padding: 5px; }')
        new_column.toggle_sidebars_button.clicked.connect(self.toggle_sidebars)

        new_column.search_bar = SearchBarQLineEdit(self)
        new_column.search_bar.setPlaceholderText(self.tr('Search'))
        new_column.search_bar.setMaximumWidth(300)
        new_column.search_bar.setMaximumHeight(32)
        new_column.search_bar.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Minimum)

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
            padding: 5px; }')
        new_column.bookmark_button.clicked.connect(
            lambda: BookmarkDialog(self, search_bar_text=self.focused_column().search_bar.text()).exec_())

        self.tab_bar = QTabBar()
        self.tab_bar.setUsesScrollButtons(False)
        self.tab_bar.setDrawBase(False)
        self.tab_bar.addTab('Tree')
        self.tab_bar.addTab('Calendar')
        self.tab_bar.addTab('Plan')
        for i in range(3):
            self.tab_bar.setTabToolTip(i, 'Press Ctrl+{} to select this tab'.format(i + 1))
            shortcut = QShortcut(QKeySequence('Ctrl+{}'.format(i + 1)), self)
            shortcut.setContext(Qt.ApplicationShortcut)
            shortcut.activated.connect(partial(self.tab_bar.setCurrentIndex, i))

        self.path_bar = QWidget()
        layout = QHBoxLayout()
        layout.setAlignment(Qt.AlignLeft)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)
        self.path_bar.setLayout(layout)

        self.search_holder = QWidget()
        layout = QHBoxLayout()
        layout.addWidget(self.tab_bar)
        layout.addWidget(self.path_bar)
        layout.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Expanding))
        layout.addWidget(new_column.search_bar)
        layout.addWidget(new_column.bookmark_button)
        layout.addWidget(new_column.toggle_sidebars_button)
        layout.setStretchFactor(new_column.search_bar, 1)
        self.search_holder.setLayout(layout)
        self.set_toolbar_margins(TOOLBAR_MARGIN)

        new_column.filter_proxy = model.FilterProxyModel()
        new_column.filter_proxy.setSourceModel(self.item_model)
        # re-sort and re-filter data whenever the original model changes
        new_column.filter_proxy.setDynamicSortFilter(True)
        new_column.filter_proxy.filter = ''

        new_column.view = ResizeTreeView(new_column.filter_proxy)
        new_column.view.setItemDelegate(model.Delegate(self, new_column.filter_proxy, new_column.view.header()))
        new_column.view.selectionModel().selectionChanged.connect(self.update_actions)
        new_column.view.header().sectionClicked[int].connect(self.toggle_sorting)
        new_column.view.header().setSectionsClickable(True)

        plan_model = planned_model.PlannedModel(self.item_model, new_column.filter_proxy)
        self.planned_view = ResizeTreeView(plan_model)
        self.planned_view.setItemDelegate(model.Delegate(self, plan_model, self.planned_view.header()))

        new_column.stacked_widget = QStackedWidget()
        new_column.stacked_widget.addWidget(new_column.view)
        new_column.stacked_widget.addWidget(QLabel('Coming soon :)'))
        new_column.stacked_widget.addWidget(self.planned_view)

        def change_tab(i):
            self.path_bar.setVisible(i == 0)
            new_column.stacked_widget.setCurrentIndex(i)

        self.tab_bar.currentChanged.connect(change_tab)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)  # left, top, right, bottom
        layout.addWidget(self.search_holder)
        layout.addWidget(new_column.stacked_widget)
        new_column.setLayout(layout)

        self.item_views_splitter.addWidget(new_column)
        self.setup_tag_model()

        self.focused_column().view.setFocus()
        self.set_indentation_and_style_tree(self.focused_column().view.indentation())
        top_most_index = self.focused_column().filter_proxy.index(0, 0, QModelIndex())
        self.set_selection(top_most_index, top_most_index)
        self.bookmarks_view.selectionModel().setCurrentIndex(QModelIndex(), QItemSelectionModel.ClearAndSelect)

    def unsplit_window(self):
        index_last_widget = self.item_views_splitter.count() - 1
        self.item_views_splitter.widget(index_last_widget).setParent(None)
        if self.item_views_splitter.count() == 1:
            self.unsplitWindowAct.setEnabled(False)

    def set_indentation_and_style_tree(self, i, view=None):
        space_left_of_arrow = str(int(i) - 30 * 2)
        if not view:
            space_left_of_arrow = str(int(i) - 30)
            view = self.focused_column().view
        view.setIndentation(int(i))
        padding_vertical = '8'
        view.setStyleSheet(
            'QTreeView:focus { border: 1px solid #006080; }'  # blue glow around the view
            'QTreeView:branch:open:has-children  {'
            'image: url(:/open);'
            'padding-top: ' + padding_vertical + 'px;\
            padding-bottom: ' + padding_vertical + 'px;\
            padding-left: ' + space_left_of_arrow + 'px;}\
            QTreeView:branch:closed:has-children {\
            image: url(:/closed);\
            padding-top: ' + padding_vertical + 'px;\
            padding-bottom: ' + padding_vertical + 'px;\
            padding-left: ' + space_left_of_arrow + 'px;}')

    def new_file(self):
        path = QFileDialog.getSaveFileName(self, "Save", 'my_tree.treenote', "*.treenote")[0]
        if len(path) > 0:
            self.save_path = path
            self.item_model = model.TreeModel(self, header_list=TREE_HEADER)
            self.bookmark_model = model.TreeModel(self, header_list=BOOKMARKS_HEADER)
            self.change_active_tree()

    def save_file(self, save_expanded_states=False):
        # this method is called everytime a change is done.
        # therefore it is the right place to set the model changed for backup purposes
        self.planned_view.model().refresh_model()
        self.item_model.changed = True
        self.item_model.selected_item = self.focused_column().filter_proxy.getItem(self.current_index())
        if save_expanded_states:
            for index in self.item_model.indexes():
                proxy_index = self.filter_proxy_index_from_model_index(index)
                self.item_model.getItem(index).expanded = self.focused_column().view.isExpanded(proxy_index)
                self.item_model.getItem(index).quicklink_expanded = self.quicklinks_view.isExpanded(index)
        pickle.dump((self.item_model.selected_item, self.item_model.rootItem, self.bookmark_model.rootItem),
                    open(self.save_path, 'wb'),
                    protocol=pickle.HIGHEST_PROTOCOL)

    def export_plain_text(self):
        path = QFileDialog.getSaveFileName(self, "Export", 'treenote_export.txt', "*.txt")[0]
        if len(path) > 0:
            with open(path, 'w', encoding='utf-8') as file:
                file.write(self.tree_as_string(self.item_model))
                QMessageBox(QMessageBox.NoIcon, ' ', 'Export successful!').exec()

    def export_json(self):
        path = QFileDialog.getSaveFileName(self, "Export", 'treenote_export.json', "*.json")[0]
        if len(path) > 0:
            self.save_json(path)
            QMessageBox(QMessageBox.NoIcon, ' ', 'Export successful!').exec()

    def save_json(self, path):
        def json_encoder(obj):
            app.processEvents()
            dic = obj.__dict__.copy()
            del dic['parentItem']
            return dic

        json.dump((self.item_model.rootItem, self.bookmark_model.rootItem), open(path, 'w'),
                  default=json_encoder)

    def start_open_file(self):
        path = QFileDialog.getOpenFileName(self, "Open", filter="*.treenote")[0]
        if path and len(path) > 0:
            self.open_file(path)

    def import_backup(self, open_path, save_path):
        self.item_model = model.TreeModel(self, header_list=TREE_HEADER)
        self.bookmark_model = model.TreeModel(self, header_list=BOOKMARKS_HEADER)
        if 'json' in open_path:
            if 'json' in open_path:
                def json_decoder(obj):
                    if 'text' in obj:
                        item = model.Tree_item()
                        item.__dict__.update(obj)
                        item.childItems = obj['childItems']
                        return item
                    return obj

                self.item_model.rootItem, self.bookmark_model.rootItem = json.load(open(open_path, 'r'),
                                                                                   object_hook=json_decoder)
        else:
            hit_list_dict = plistlib.load(open(open_path, 'rb'))
            id_item_dict = {}
            for task_dict in hit_list_dict['PFEntities']['Task'].values():
                item = model.Tree_item()
                item.text = task_dict['title']
                date = task_dict.get('startDate')
                if date:
                    item.date = date.strftime('%d.%m.%y')
                if item.text == 'ROOT':
                    item.header_list = TREE_HEADER
                    self.item_model.rootItem = item
                item.child_id_list = task_dict.get('subtasks', [])
                item.estimate = str(task_dict.get('priority', item.estimate))
                id_item_dict[task_dict['uid']] = item

            for item in id_item_dict.values():
                for child_id in item.child_id_list:
                    item.childItems.append(id_item_dict[child_id])
                del item.child_id_list

        def set_parents(parent_item):
            for child_item in parent_item.childItems:
                child_item.parentItem = parent_item
                set_parents(child_item)

        self.item_model.rootItem.parentItem = None
        set_parents(self.item_model.rootItem)
        self.bookmark_model.rootItem.parentItem = None
        set_parents(self.bookmark_model.rootItem)
        self.save_path = save_path
        self.change_active_tree()

    def open_file(self, open_path):
        self.item_model.selected_item, self.item_model.rootItem, self.bookmark_model.rootItem = pickle.load(
            open(open_path, 'rb'))
        self.save_path = open_path
        self.change_active_tree()

    def print(self):
        dialog = QPrintPreviewDialog()
        view = PrintTreeView(self, dialog.findChildren(QPrintPreviewWidget)[0])
        toolbar = dialog.findChildren(QToolBar)[0]
        toolbar.addAction(QIcon(':/plus'), self.tr('Increase print size'), lambda: view.change_print_size(0.1))
        toolbar.addAction(QIcon(':/minus'), self.tr('Decrease print size'), lambda: view.change_print_size(-0.1))
        toolbar.addWidget(QLabel('Change the print size with the red buttons.'))
        view.setModel(self.item_model)
        dialog.paintRequested.connect(view.print)
        dialog.showMaximized()
        dialog.exec_()


class PrintTreeView(QTreeView):
    def __init__(self, main_window, print_preview_widget):
        super(PrintTreeView, self).__init__()
        self.main_window = main_window
        self.print_preview_widget = print_preview_widget

    def change_print_size(self, change):
        self.main_window.print_size += change
        self.print_preview_widget.updatePreview()

    def print(self, printer):
        printer.setResolution(300)
        old_fontsize = self.main_window.fontsize
        self.main_window.fontsize = int(30 * self.main_window.print_size)
        painter = QPainter()
        painter.begin(printer)
        painter.setFont(QFont(model.FONT, 9))
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        tree_width = printer.pageRect().width() - printer.pageLayout().marginsPixels(printer.resolution()).right() * 2
        self.model().expand_saved(print_view=self)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setPalette(self.main_window.light_palette)
        self.header().setFont(QFont(model.FONT, self.main_window.fontsize))
        self.header().setPalette(self.main_window.light_palette)
        self.hideColumn(2)
        width_of_estimate_column = ESTIMATE_COLUMN_WIDTH * 2 * self.main_window.print_size
        self.setColumnWidth(0, tree_width - width_of_estimate_column)
        self.main_window.set_indentation_and_style_tree(
            self.main_window.focused_column().view.indentation() * 2 * self.main_window.print_size, self)
        delegate = model.Delegate(self.main_window, self.model(), self.header())
        self.setItemDelegate(delegate)

        # source: http://blog.qt.io/blog/2012/08/24/qt-commercial-support-weekly-25-printing-large-tables-2/
        tree_height = self.header().height()
        index = self.indexAt(self.rect().topLeft())
        while index.isValid():
            tree_height += delegate.sizeHint(None, index).height()
            index = self.indexBelow(index)
        self.resize(tree_width, tree_height)
        pixmap = self.grab()
        space_for_page_number = printer.pageLayout().marginsPixels(printer.resolution()).bottom()
        one_page_print_space = printer.pageRect().height() - space_for_page_number * 2
        pieces = tree_height // one_page_print_space + 1
        for i in range(pieces):
            rect = QRectF(0, i * one_page_print_space, printer.width(), one_page_print_space)
            painter.drawPixmap(printer.pageRect().topLeft(), pixmap, rect)
            painter.drawText(0, printer.pageRect().height() - space_for_page_number, printer.width(),
                             space_for_page_number, Qt.AlignCenter, '{} / {}'.format(i + 1, pieces))
            if i != pieces - 1:
                printer.newPage()
        painter.end()
        self.main_window.fontsize = old_fontsize


class ItemMimeData(QMimeData):
    def __init__(self, items):
        super(ItemMimeData, self).__init__()
        self.items = items


class FileLineEdit(QPlainTextEdit):
    def __init__(self, main_window, popup):
        super(FileLineEdit, self).__init__(popup)
        self.popup = popup
        self.main_window = main_window
        self.setMinimumWidth(400)
        self.setPlaceholderText(self.tr('File to:'))

        self._separator = ' '
        # moving an item to its own child is not possible, so don't propose it
        below_selection_set = set(self.main_window.focused_column().filter_proxy.mapToSource(index) for index in
                                  self.main_window.selected_indexes())
        other_indexes = set()
        for index in self.main_window.item_model.indexes():
            # works only, because indexes are in the right order
            if index in below_selection_set or index.parent() in below_selection_set:
                below_selection_set.add(index)
            else:
                other_indexes.add(index)
        self.completer = QCompleter([index.data() for index in other_indexes])
        self.completer.setFilterMode(Qt.MatchStartsWith)
        self.completer.setWidget(self)
        self.completer.activated[str].connect(self._insertCompletion)
        self._keysToIgnore = [Qt.Key_Enter, Qt.Key_Return, Qt.Key_Escape, Qt.Key_Tab]

    def _insertCompletion(self, completion):
        self.popup.hide()
        for index in self.main_window.item_model.indexes():
            if self.main_window.item_model.getItem(index).text == completion:
                lowest_index = self.main_window.focused_column().filter_proxy.mapToSource(
                    self.main_window.selected_indexes()[-1])
                old_row = lowest_index.row()
                old_parent = lowest_index.parent()
                self.main_window.focused_column().filter_proxy.file(self.main_window.selected_indexes(), index)
                # after moving / filing: select below item, or above item if no below item exists
                next_index = self.main_window.item_model.index(old_row, 0, old_parent)
                if not next_index.isValid():
                    next_index = self.main_window.item_model.index(old_row - 1, 0, old_parent)
                if not next_index.isValid():
                    next_index = old_parent
                self.main_window.set_selection(next_index, next_index)
                break

    def textUnderCursor(self):
        text = self.toPlainText()
        textUnderCursor = ''
        i = self.textCursor().position() - 1
        while i >= 0 and text[i] != self._separator:
            textUnderCursor = text[i] + textUnderCursor
            i -= 1
        return textUnderCursor

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.popup.hide()
        if event.key() in self._keysToIgnore and self.completer.popup().isVisible():
            event.ignore()
            return
        super(FileLineEdit, self).keyPressEvent(event)

        completionPrefix = self.textUnderCursor()
        if len(completionPrefix) > 0:
            if completionPrefix != self.completer.completionPrefix():
                self.completer.setCompletionPrefix(completionPrefix)
                self.completer.popup().setCurrentIndex(self.completer.completionModel().index(0, 0))
            # if something was just typed
            if len(event.text()) > 0:
                self.completer.complete()
                self.completer.popup().move(self.popup.x(), self.popup.y() + self.popup.height())


class SelectRowLineEdit(QPlainTextEdit):
    def __init__(self, main_window):
        super(SelectRowLineEdit, self).__init__()
        self.main_window = main_window
        self.setMinimumWidth(400)
        self.setMaximumHeight(36)

        index = self.main_window.get_index_by_creation_date(self.main_window.new_rows_plan_item_creation_date)
        if index:
            self.setPlainText(index.data())
        else:
            self.setPlaceholderText(self.tr('Type the name of a row'))

        self._separator = ' '
        self.completer = QCompleter([index.data() for index in self.main_window.item_model.indexes()])
        self.completer.setFilterMode(Qt.MatchStartsWith)
        self.completer.setWidget(self)
        self.completer.activated[str].connect(self._insertCompletion)
        self._keysToIgnore = [Qt.Key_Enter, Qt.Key_Return, Qt.Key_Escape, Qt.Key_Tab]

    def _insertCompletion(self, completion):
        for index in self.main_window.item_model.indexes():
            item = self.main_window.item_model.getItem(index)
            if item.text == completion:
                self.setPlainText(index.data())
                self.main_window.new_rows_plan_item_creation_date = item.creation_date_time
                break

    def textUnderCursor(self):
        text = self.toPlainText()
        textUnderCursor = ''
        i = self.textCursor().position() - 1
        while i >= 0 and text[i] != self._separator:
            textUnderCursor = text[i] + textUnderCursor
            i -= 1
        return textUnderCursor

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            pass
        if event.key() in self._keysToIgnore and self.completer.popup().isVisible():
            event.ignore()
            return
        super(SelectRowLineEdit, self).keyPressEvent(event)

        completionPrefix = self.textUnderCursor()
        if len(completionPrefix) > 0:
            if completionPrefix != self.completer.completionPrefix():
                self.completer.setCompletionPrefix(completionPrefix)
                self.completer.popup().setCurrentIndex(self.completer.completionModel().index(0, 0))
            # if something was just typed
            if len(event.text()) > 0:
                self.completer.complete()


class ImportDialog(QDialog):
    def __init__(self, main_window, open_filter, title, hint):
        super(ImportDialog, self).__init__(main_window)
        self.setWindowTitle(title)
        self.setMinimumWidth(900)
        self.main_window = main_window
        self.import_file_edit = QLineEdit()
        self.select_import_file_button = QPushButton('Select file...')
        self.select_import_file_button.clicked.connect(
            lambda: self.import_file_edit.setText(QFileDialog.getOpenFileName(self, "Open", filter=open_filter)[0]))
        self.treenote_file_edit = QLineEdit()
        self.select_treenote_file_button = QPushButton('Select file...')
        self.select_treenote_file_button.clicked.connect(
            lambda: self.treenote_file_edit.setText(
                QFileDialog.getSaveFileName(self, 'Save', 'imported_tree.treenote', '*.treenote')[0]))
        buttonBox = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Cancel)

        grid = QGridLayout()
        if hint:
            grid.addWidget(QLabel(hint), 0, 0, 1, 3)  # fromRow, fromColumn, rowSpan, columnSpan
        grid.addWidget(QLabel('The backup file to import:'), 1, 0)  # row, column
        grid.addWidget(self.import_file_edit, 1, 1)
        grid.addWidget(self.select_import_file_button, 1, 2)
        grid.addWidget(QLabel('Destination for the new TreeNote file:'), 2, 0)
        grid.addWidget(self.treenote_file_edit, 2, 1)
        grid.addWidget(self.select_treenote_file_button, 2, 2)
        grid.addWidget(buttonBox, 3, 0, 1, 3, Qt.AlignRight)
        self.setLayout(grid)
        buttonBox.button(QDialogButtonBox.Apply).clicked.connect(self.apply)
        buttonBox.button(QDialogButtonBox.Cancel).clicked.connect(self.reject)

    def apply(self):
        try:
            self.main_window.import_backup(self.import_file_edit.text(), self.treenote_file_edit.text())
        except Exception as e:
            QMessageBox.information(self, '', 'Import went wrong:\n{}'.format(e), QMessageBox.Ok)
        else:
            QMessageBox.information(self, '', 'Import successful!', QMessageBox.Ok)
            super(ImportDialog, self).accept()


class AboutBox(QDialog):
    def __init__(self, parent):
        super(AboutBox, self).__init__()
        headline = QLabel('TreeNote')
        headline.setFont(QFont(model.FONT, 25))
        label = QLabel(
            self.tr(
                'Version ' + version.version_nr.replace('v', '') +
                '<br><br>'
                'TreeNote is an easy outliner for personal knowledge and task management. '
                'More info at <a href="http://treenote.github.io">treenote.github.io</a>.<br>'
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
        rootIndex = self.main_window.focused_column().view.rootIndex()
        self.root_item = self.main_window.focused_column().filter_proxy.getItem(rootIndex)
        self.save_root_checkbox = QCheckBox()
        self.save_root_checkbox.setChecked(True)

        save_root_item_label_text = "Save current root item '{}':".format(self.root_item.text)
        if index is not None:
            item = main_window.bookmark_model.getItem(index)
            self.save_root_checkbox = None
            if item.saved_root_item_creation_date_time:
                save_root_item_label_text = "Saved root item: '{}''".format(self.root_item.text)
            else:
                save_root_item_label_text = 'No saved root item.'

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
        grid.addWidget(QLabel(save_root_item_label_text), 3, 0)
        grid.addWidget(self.name_edit, 0, 1)
        grid.addWidget(self.search_bar_text_edit, 1, 1)
        grid.addWidget(self.shortcut_edit, 2, 1)
        grid.addWidget(clearButton, 2, 2)
        if self.save_root_checkbox:
            grid.addWidget(self.save_root_checkbox, 3, 1)
        grid.addWidget(buttonBox, 4, 0, 1, 2, Qt.AlignRight)  # fromRow, fromColumn, rowSpan, columnSpan.
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
            if self.save_root_checkbox.isChecked():
                self.main_window.bookmark_model.set_data(self.root_item.creation_date_time, index=self.index,
                                                         field='saved_root_item_creation_date_time')
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
        buttonBox.button(QDialogButtonBox.Apply).setDefault(True)
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
        downloadButton.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('http://treenote.github.io/download')))

        grid = QGridLayout()  # fromRow, fromColumn, rowSpan, columnSpan
        new_version = parent.new_version_data['tag_name'][1:]
        your_version = version.version_nr[1:]
        grid.addWidget(QLabel(self.tr('Treenote ' + new_version +
                                      ' is the newest version. You have ' + your_version)), 0, 0, 1, -1)
        grid.addItem(QSpacerItem(-1, 10), 1, 0, 1, 1)
        if new_version == your_version:
            buttonBox = QDialogButtonBox(QDialogButtonBox.Close)
            buttonBox.button(QDialogButtonBox.Close).clicked.connect(self.close)
            grid.addWidget(buttonBox)
        else:
            grid.addWidget(QLabel(self.tr('Release notes:')), 2, 0, 1, -1)
            grid.addWidget(releaseNotesEdit, 3, 0, 1, -1)
            grid.addItem(QSpacerItem(-1, 10), 4, 0, 1, 1)
            grid.addWidget(QLabel(self.tr('Extract the downloaded archive, then doubleclick the executable inside.\n'
                                          'If you can’t open your old .treenote file with the new TreeNote version,\n'
                                          'just import the newest JSON export from the backups folder.')), 5, 0, 1, -1)
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
    def __init__(self, main_window):
        super(SettingsDialog, self).__init__(main_window)
        self.main_window = main_window
        theme_dropdown = QComboBox()
        theme_dropdown.addItems(['Light', 'Dark'])
        current_palette_index = 0 if QApplication.palette() == self.main_window.light_palette else 1
        theme_dropdown.setCurrentIndex(current_palette_index)
        theme_dropdown.currentIndexChanged[int].connect(self.change_theme)
        indentation_spinbox = QSpinBox()
        indentation_spinbox.setValue(main_window.focused_column().view.indentation())
        indentation_spinbox.setRange(30, 100)
        indentation_spinbox.valueChanged[int].connect(
            lambda: main_window.set_indentation_and_style_tree(indentation_spinbox.value()))
        buttonBox = QDialogButtonBox(QDialogButtonBox.Close)
        buttonBox.button(QDialogButtonBox.Close).clicked.connect(self.close)
        backup_interval_spinbox = QSpinBox()
        backup_interval_spinbox.setValue(main_window.backup_interval)
        backup_interval_spinbox.setRange(0, 10000)
        backup_interval_spinbox.valueChanged[int].connect(
            lambda: main_window.start_backup_service(backup_interval_spinbox.value()))

        new_rows_plan_view_label = QLabel('When inserting a row in the plan tab,\n'
                                          'add it below the following item of the tree:')
        new_rows_plan_view_label.setAlignment(Qt.AlignRight)
        new_rows_plan_view_edit = SelectRowLineEdit(self.main_window)

        layout = QFormLayout()
        layout.addRow('Theme:', theme_dropdown)
        layout.addRow('Indentation of children in the tree:', indentation_spinbox)
        backup_label = QLabel("Create a JSON export of the tree to the folder 'backups' "
                              "every ... minutes, if the tree has changed (0 minutes disables this feature):")
        backup_label.setWordWrap(True)
        backup_label.setAlignment(Qt.AlignRight)
        backup_label.setMinimumSize(550, 0)
        layout.addRow(backup_label, backup_interval_spinbox)
        layout.addRow(new_rows_plan_view_label, new_rows_plan_view_edit)
        layout.addRow(buttonBox)
        layout.setLabelAlignment(Qt.AlignRight)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setVerticalSpacing(30)
        self.setLayout(layout)
        self.setWindowTitle(self.tr('Preferences'))

    def change_theme(self, current_palette_index):
        if current_palette_index == 0:
            new_palette = self.main_window.light_palette
        else:
            new_palette = self.main_window.dark_palette
        self.main_window.set_palette(new_palette)


class DelayedExecutionTimer(QObject):  # source: https://wiki.qt.io/Delay_action_to_wait_for_user_interaction
    triggered = pyqtSignal(str)

    def __init__(self, parent):
        super(DelayedExecutionTimer, self).__init__(parent)
        # The minimum delay is the time the class will wait after being triggered before emitting the triggered() signal
        # (if there is no key press for this time: trigger)
        self.minimumDelay = 700
        self.minimumTimer = QTimer(self)
        self.minimumTimer.timeout.connect(self.timeout)

    def timeout(self):
        self.minimumTimer.stop()
        self.triggered.emit(self.string)

    def trigger(self, string):
        self.string = string
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
    def __init__(self, model):
        super(ResizeTreeView, self).__init__()
        self.setModel(model)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setAnimated(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.header().setStretchLastSection(False)
        self.setColumnWidth(1, ESTIMATE_COLUMN_WIDTH)
        self.setColumnWidth(2, 90)
        self.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.header().setSectionResizeMode(1, QHeaderView.Fixed)
        self.header().setSectionResizeMode(2, QHeaderView.Fixed)

    def resizeEvent(self, event):
        self.itemDelegate().sizeHintChanged.emit(QModelIndex())


class Spoiler(QWidget):
    # http://stackoverflow.com/questions/32476006/how-to-make-an-expandable-collapsable-section-widget-in-qt
    def __init__(self, parent, title):
        super(Spoiler, self).__init__(parent)

        self.animationDuration = 300
        self.toggleAnimation = QParallelAnimationGroup()
        self.contentArea = QScrollArea()
        self.toggleButton = QToolButton()
        mainLayout = QGridLayout()

        self.toggleButton.setStyleSheet("QToolButton { border: none; }")
        self.toggleButton.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggleButton.setArrowType(Qt.RightArrow)
        self.toggleButton.setText(title)
        self.toggleButton.setCheckable(True)
        self.toggleButton.setChecked(False)

        self.contentArea.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # start out collapsed
        self.contentArea.setMaximumHeight(0)
        self.contentArea.setMinimumHeight(0)
        # let the entire widget grow and shrink with its content
        toggleAnimation = self.toggleAnimation
        toggleAnimation.addAnimation(QPropertyAnimation(self, b"minimumHeight"))
        toggleAnimation.addAnimation(QPropertyAnimation(self, b"maximumHeight"))
        toggleAnimation.addAnimation(QPropertyAnimation(self.contentArea, b"maximumHeight"))
        mainLayout.setContentsMargins(0, 0, 0, 10)
        mainLayout.addWidget(self.toggleButton, 0, 0, 1, 1, Qt.AlignLeft)
        mainLayout.addWidget(self.contentArea, 1, 0, 1, 3)
        self.setLayout(mainLayout)

        def start_animation(checked):
            arrow_type = Qt.DownArrow if checked else Qt.RightArrow
            direction = QAbstractAnimation.Forward if checked else QAbstractAnimation.Backward
            self.toggleButton.setArrowType(arrow_type)
            self.toggleAnimation.setDirection(direction)
            self.toggleAnimation.start()

        self.toggleButton.clicked.connect(start_animation)

    def minimumSizeHint(self):
        return QSize(self.contentArea.layout().minimumSize().width(), 0)

    def setContentLayout(self, contentLayout):
        # Not sure if this is equivalent to self.contentArea.destroy()
        self.contentArea.destroy()
        self.contentArea.setLayout(contentLayout)
        collapsedHeight = self.sizeHint().height() - self.contentArea.maximumHeight()
        contentHeight = contentLayout.sizeHint().height()
        for i in range(self.toggleAnimation.animationCount()):
            spoilerAnimation = self.toggleAnimation.animationAt(i)
            spoilerAnimation.setDuration(self.animationDuration)
            spoilerAnimation.setStartValue(collapsedHeight)
            spoilerAnimation.setEndValue(collapsedHeight + contentHeight)
        contentAnimation = self.toggleAnimation.animationAt(self.toggleAnimation.animationCount() - 1)
        contentAnimation.setDuration(self.animationDuration)
        contentAnimation.setStartValue(0)
        contentAnimation.setEndValue(contentHeight)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setApplicationName('TreeNote')
    app.setOrganizationName('Jan Korte')
    app.setWindowIcon(QIcon(':/logo'))
    QFontDatabase.addApplicationFont(RESOURCE_FOLDER + 'SourceSansPro-Regular.otf')

    form = MainWindow()
    form.show()
    app.exec_()
