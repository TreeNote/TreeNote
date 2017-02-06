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
import sip  # needed for pyinstaller, get's removed with 'optimize imports'!
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtPrintSupport import *
#
import treenote.model as model
import treenote.tag_model as tag_model
import treenote.planned_model as planned_model
import treenote.util as util
from treenote.version import __version__
from treenote.resources import qrc_resources  # get's removed with 'optimize imports'!


def resource_path(relative_path):
    """ Get absolute path to resource, works for developing and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(__file__)

    return os.path.join(base_path, relative_path)


BOOKMARKS_HEADER = ['Bookmarks']
COLUMNS_HIDDEN = 'columns_hidden'
EXPANDED_ITEMS = 'EXPANDED_ITEMS'
EXPANDED_QUICKLINKS_INDEXES = 'EXPANDED_QUICKLINKS'
SELECTED_INDEX = 'SELECTED_ID'
APP_FONT_SIZE = 17 if sys.platform == "darwin" else 14
INITIAL_SIDEBAR_WIDTH = 200
ESTIMATE_COLUMN_WIDTH = 85
TOOLBAR_MARGIN = 6
RESOURCE_FOLDER = resource_path('resources')
PLAN_TAB = 'Plan'
HOME_TREENOTE_FOLDER = os.path.join(os.path.expanduser("~"), 'TreeNote')
if not os.path.exists(HOME_TREENOTE_FOLDER):
    os.makedirs(HOME_TREENOTE_FOLDER)

logging.basicConfig(filename=os.path.join(HOME_TREENOTE_FOLDER, 'treenote.log'),
                    format='%(asctime)s - %(levelname)s - %(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)


def exception_handler(type_, text, traceback):
    print(''.join(format_exception(type_, text, traceback)))
    logger.exception('Uncaught exception:', exc_info=(type_, text, traceback))


sys.excepthook = exception_handler


def time_stamp():
    return QDate.currentDate().toString('yyyy-MM-dd') + '-' + QTime.currentTime().toString('hh-mm-ss-zzz')


class ExportThread(QThread):
    def run(self):
        splitted_path = os.path.split(self.main_window.save_path)
        path = os.path.join(self.main_window.backup_folder,
                            splitted_path[-1].replace('.treenote', '') + '_' + time_stamp())
        self.main_window.save_json(path + '.json')


class MainWindow(QMainWindow):
    popup_json_save_failed = pyqtSignal()

    def __init__(self, app):
        super(MainWindow, self).__init__()
        self.app = app
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

        self.tree_header = [self.tr('Text'), self.tr('Estimate'), self.tr('Start date')]
        self.item_model = model.TreeModel(self, header_list=self.tree_header)
        self.bookmark_model = model.TreeModel(self, header_list=BOOKMARKS_HEADER)

        settings = self.getQSettings()

        arguments = app.arguments()
        if len(arguments) > 1:
            self.open_file(arguments[1])
        else:
            last_opened_file_path = settings.value('last_opened_file_path')
            if last_opened_file_path:
                try:
                    self.open_file(last_opened_file_path)
                except Exception as e:
                    QMessageBox.information(self, '', self.tr('{} \n\n Did not find last Treenote '
                                                              'file. Creating a new treenote file...').format(e),
                                            QMessageBox.Ok)
                    self.new_file()
            else:
                example_tree_path = os.path.join(RESOURCE_FOLDER,
                                                 'example_tree_{}.json'.format(QLocale.system().name()))
                if not os.path.exists(example_tree_path):
                    example_tree_path = os.path.join(RESOURCE_FOLDER, 'example_tree.json')
                self.import_backup(example_tree_path,
                                   os.path.join(HOME_TREENOTE_FOLDER, 'example_tree_{}.treenote'.format(time_stamp())))

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

        self.quicklinks_view = SaveExpandTreeView(self.item_model)
        self.quicklinks_view.setItemDelegate(model.BookmarkDelegate(self, self.item_model))
        self.quicklinks_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.quicklinks_view.customContextMenuRequested.connect(self.open_edit_shortcut_contextmenu)
        self.quicklinks_view.clicked.connect(lambda i: self.focus_index(self.filter_proxy_index_from_model_index(i)))
        self.quicklinks_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.quicklinks_view.setHeader(CustomHeaderView(self.tr('Quick access')))
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
        self.date_dropdown = init_dropdown(model.DATE_BELOW, self.tr('all'), self.tr('0d'), self.tr('1w'),
                                           self.tr('2m'), self.tr('3y'))
        self.hideTagsCheckBox = QCheckBox(self.tr('Hide rows\nwith a tag'))
        self.hideTagsCheckBox.clicked.connect(self.filter_hide_tags)
        self.hideFutureStartdateCheckBox = QCheckBox(self.tr('Hide rows with a\nfuture start date'))
        self.hideFutureStartdateCheckBox.clicked.connect(self.filter_hide_future_startdate)

        layout = QGridLayout()
        layout.setContentsMargins(2 + 10, 0, 6, 0)  # left, top, right, bottom
        layout.addWidget(QLabel(self.tr('Color:')), 1, 0, 1, 1)
        layout.addWidget(self.color_dropdown, 1, 1, 1, 1)
        layout.addWidget(QLabel(self.tr('Type:')), 2, 0, 1, 1)
        layout.addWidget(self.task_dropdown, 2, 1, 1, 1)
        layout.addWidget(QLabel(self.tr('Date until:')), 3, 0, 1, 1)
        layout.addWidget(self.date_dropdown, 3, 1, 1, 1)
        layout.addWidget(QLabel(self.tr('Estimate:')), 4, 0, 1, 1)
        layout.addWidget(self.estimate_dropdown, 4, 1, 1, 1)
        layout.addWidget(self.hideTagsCheckBox, 5, 0, 1, 2)
        layout.addWidget(self.hideFutureStartdateCheckBox, 6, 0, 1, 2)
        layout.setColumnStretch(1, 10)
        self.filter_spoiler = Spoiler(self, self.tr('Filters'))
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

        QIcon.setThemeName('any_theme')

        def act(name, icon_name=None, trig=None, trigbool=None, shct=None):
            if not isinstance(shct, QKeySequence):
                shct = QKeySequence(shct)
            if icon_name:
                action = QAction(QIcon.fromTheme(icon_name), name)
            else:
                action = QAction(name)
            if trig:
                action.triggered.connect(trig)
            elif trigbool:
                action.setCheckable(True)
                action.triggered[bool].connect(trigbool)
            if shct:
                action.setShortcut(shct)
            return action

        def add_action(name, qaction, list=None):
            setattr(self, name, qaction)
            self.all_actions.append(qaction)
            if list is not None:
                list.append(qaction)
            return qaction

        add_action('settingsAct',
                   act(self.tr('P&references...'), 'preferences-system', lambda: SettingsDialog(self).exec_(),
                       shct='Ctrl+,'))
        add_action('aboutAct', act(self.tr('&About...'), 'help-about', lambda: AboutBox(self).exec()))
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
        add_action('expandAllChildrenAction', QAction(self.tr('Expand all children'), self, shortcut='Shift+Right',
                                                      triggered=lambda: self.expand_or_collapse_children_selected(
                                                          True)), list=self.item_view_not_editing_actions)
        add_action('collapseAllChildrenAction', QAction(self.tr('Collapse all children'), self, shortcut='Shift+Left',
                                                        triggered=lambda: self.expand_or_collapse_children_selected(
                                                            False)), list=self.item_view_not_editing_actions)
        add_action('focusSearchBarAction', act(self.tr('Focus search bar'), 'edit-find',
                                               lambda: self.focused_column().search_bar.setFocus(),
                                               shct=QKeySequence.Find))
        add_action('colorGreenAction',
                   QAction(self.tr('Green'), self, shortcut='G', triggered=lambda: self.color_row('g')),
                   list=self.item_view_actions)
        add_action('colorYellowAction',
                   QAction(self.tr('Yellow'), self, shortcut='Y', triggered=lambda: self.color_row('y')),
                   list=self.item_view_actions)
        add_action('colorBlueAction',
                   QAction(self.tr('Blue'), self, shortcut='B', triggered=lambda: self.color_row('b')),
                   list=self.item_view_actions)
        add_action('colorRedAction', QAction(self.tr('Red'), self, shortcut='R', triggered=lambda: self.color_row('r')),
                   list=self.item_view_actions)
        add_action('colorOrangeAction',
                   QAction(self.tr('Orange'), self, shortcut='O', triggered=lambda: self.color_row('o')),
                   list=self.item_view_actions)
        add_action('colorVioletAction',
                   QAction(self.tr('Violet'), self, shortcut='V', triggered=lambda: self.color_row('v')),
                   list=self.item_view_actions)
        add_action('colorGreyAction',
                   QAction(self.tr('Grey'), self, shortcut='E', triggered=lambda: self.color_row('e')),
                   list=self.item_view_actions)
        add_action('colorNoColorAction',
                   QAction(self.tr('No color'), self, shortcut='N', triggered=lambda: self.color_row('n')),
                   list=self.item_view_actions)
        add_action('noEstimateAction',
                   QAction(self.tr('No estimate'), self, shortcut='0', triggered=partial(self.estimate, '')),
                   list=self.item_view_actions)
        add_action('increaseEstimateAction',
                   QAction(self.tr('Increase estimate'), self, shortcut='+',
                           triggered=partial(self.adjust_estimate, 10)),
                   list=self.item_view_actions)
        add_action('decreaseEstimateAction',
                   QAction(self.tr('Decrease estimate'), self, shortcut='-',
                           triggered=partial(self.adjust_estimate, -10)),
                   list=self.item_view_actions)
        add_action('toggleTaskAction',
                   QAction(self.tr('Toggle: note, todo, done'), self, shortcut='Space', triggered=self.toggle_task),
                   list=self.item_view_actions)
        add_action('openLinkAction',
                   QAction(self.tr('Open URLs of selected rows in the web browser, or open file or open internal link'), self, shortcut='L',
                           triggered=self.open_links_or_files), list=self.item_view_actions)
        add_action('showInFolderAction',
                   QAction(self.tr('Show in folder'), self,
                           triggered=self.show_in_folder), list=self.item_view_actions)
        add_action('renameTagAction',
                   QAction(self.tr('Rename selected &tag'), self, triggered=lambda: RenameTagDialog(
                       self, self.tag_view.currentIndex().data()).exec_()), list=self.tag_view_actions)
        add_action('editBookmarkAction',
                   QAction(self.tr('Edit selected &bookmark'), self, triggered=lambda: BookmarkDialog(
                       self, index=self.bookmarks_view.selectionModel().currentIndex()).exec_()),
                   list=self.bookmark_view_actions)
        add_action('moveBookmarkUpAction',
                   QAction(self.tr('Move selected bookmark up'), self, triggered=self.move_bookmark_up),
                   list=self.bookmark_view_actions)
        add_action('moveBookmarkDownAction',
                   QAction(self.tr('Move selected bookmark down'), self, triggered=self.move_bookmark_down),
                   list=self.bookmark_view_actions)
        add_action('deleteBookmarkAction',
                   QAction(self.tr('&Delete selected bookmark'), self, triggered=self.remove_bookmark_selection),
                   list=self.bookmark_view_actions)
        add_action('editShortcutAction',
                   QAction(self.tr('Edit selected quick link &shortcut'), self, triggered=lambda: ShortcutDialog(
                       self, self.quicklinks_view.selectionModel().currentIndex()).exec_()),
                   list=self.quick_links_view_actions)
        add_action('resetViewAction',
                   QAction(self.tr('Reset search filter'), self, shortcut='esc', triggered=self.reset_view))
        add_action('toggleSideBarsAction',
                   QAction(self.tr('Hide / show the &sidebars'), self, shortcut='Shift+S',
                           triggered=self.toggle_sidebars))
        add_action('toggleFullScreenAction',
                   act(self.tr('Toggle &fullscreen mode'), 'view-fullscreen', self.toggle_fullscreen, shct=Qt.Key_F11))
        add_action('toggleColumnsAction',
                   QAction(self.tr("Hide / show the &columns 'Estimate' and 'Start date'"), self, shortcut='Shift+C',
                           triggered=self.toggle_columns))
        add_action('toggleProjectAction',
                   QAction(self.tr('Toggle: note, sequential project, parallel project, paused project'), self,
                           shortcut='P', triggered=self.toggle_project), list=self.item_view_actions)
        add_action('appendRepeatAction',
                   QAction(self.tr("Append '&repeat=1w'"), self, shortcut='Ctrl+R', triggered=self.append_repeat),
                   list=self.item_view_actions)
        add_action('goDownAction', QAction(self.tr('Set selected row as root'), self, shortcut='Ctrl+Down',
                                           triggered=lambda: self.focus_index(self.current_index())),
                   list=self.item_view_actions)
        add_action('goUpAction', QAction(self.tr('Set parent of current root as root'), self, shortcut='Ctrl+Up',
                                         triggered=self.focus_parent_of_focused), list=self.item_view_actions)
        add_action('increaseInterFaceFontAction', QAction(self.tr('Increase interface font-size'), self,
                                                          shortcut=QKeySequence(Qt.SHIFT + Qt.Key_Plus),
                                                          triggered=lambda: self.change_interface_font_size(+1)))
        add_action('decreaseInterFaceFontAction', QAction(self.tr('Decrease interface font-size'), self,
                                                          shortcut=QKeySequence(Qt.SHIFT + Qt.Key_Minus),
                                                          triggered=lambda: self.change_interface_font_size(-1)))
        add_action('increaseFontAction', QAction(self.tr('Increase font-size'), self, shortcut='Ctrl++',
                                                 triggered=lambda: self.change_font_size(+1)))
        add_action('decreaseFontAction', QAction(self.tr('Decrease font-size'), self, shortcut='Ctrl+-',
                                                 triggered=lambda: self.change_font_size(-1)))
        add_action('increasePaddingAction', QAction(self.tr('Increase padding'), self, shortcut='Ctrl+Shift++',
                                                    triggered=lambda: self.change_padding(+1)))
        add_action('decreasePaddingAction', QAction(self.tr('Decrease padding'), self, shortcut='Ctrl+Shift+-',
                                                    triggered=lambda: self.change_padding(-1)))
        add_action('cutAction', act(self.tr('Cut'), 'edit-cut', self.cut, shct=QKeySequence.Cut),
                   list=self.item_view_actions)
        add_action('copyAction', act(self.tr('Copy'), 'edit-copy', self.copy, shct=QKeySequence.Copy),
                   list=self.item_view_actions)
        add_action('pasteAction', act(self.tr('Paste'), 'edit-paste', self.paste, shct=QKeySequence.Paste),
                   list=self.item_view_actions)
        add_action('exportJSONAction',
                   QAction(self.tr('as a JSON file...'), self, triggered=self.export_json))
        add_action('exportPlainTextAction',
                   QAction(self.tr('as a plain text file...'), self, triggered=self.export_plain_text))
        add_action('printAction', act(self.tr('&Print'), 'document-print', self.print, shct=QKeySequence.Print))
        add_action('expandAction',
                   QAction(self.tr('Expand selected rows / add children to selection'), self, shortcut='Right',
                           triggered=self.expand), list=self.item_view_not_editing_actions)
        add_action('collapseAction', QAction(self.tr('Collapse selected rows / jump to parent'), self, shortcut='Left',
                                             triggered=self.collapse), list=self.item_view_not_editing_actions)
        add_action('quitAction', act(self.tr('&Quit'), 'application-exit', self.close, shct=QKeySequence.Quit))
        add_action('openFileAction',
                   act(self.tr('&Open file...'), 'document-open', self.start_open_file, shct=QKeySequence.Open))
        add_action('newFileAction', act(self.tr('&New file...'), 'document-new', self.new_file, shct=QKeySequence.New))
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

        self.fileMenu = self.menuBar().addMenu(self.tr('&File'))
        self.fileMenu.addAction(self.newFileAction)
        self.fileMenu.addAction(self.openFileAction)
        self.importMenu = self.fileMenu.addMenu(self.tr('&Import'))
        self.importMenu.addAction(self.importJSONAction)
        self.importMenu.addAction(self.importHitListAction)
        self.exportMenu = self.fileMenu.addMenu(self.tr('&Export'))
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

        self.structureMenu = self.menuBar().addMenu(self.tr('Edit &structure'))
        self.structureMenu.addAction(self.insertRowAction)
        self.structureMenu.addAction(self.insertChildAction)
        self.structureMenu.addAction(self.deleteSelectedRowsAction)
        self.moveMenu = self.structureMenu.addMenu(self.tr('&Move selected rows'))
        self.moveMenu.addAction(self.moveUpAction)
        self.moveMenu.addAction(self.moveDownAction)
        self.moveMenu.addAction(self.moveLeftAction)
        self.moveMenu.addAction(self.moveRightAction)
        self.structureMenu.addAction(self.fileSelectedRows)
        self.structureMenu.addSeparator()
        self.structureMenu.addAction(self.cutAction)
        self.structureMenu.addAction(self.copyAction)
        self.structureMenu.addAction(self.pasteAction)

        self.editRowMenu = self.menuBar().addMenu(self.tr('Edit &row'))
        self.editRowMenu.addAction(self.editRowAction)
        self.editRowMenu.addAction(self.toggleTaskAction)
        self.editRowMenu.addAction(self.toggleProjectAction)
        self.colorMenu = self.editRowMenu.addMenu(self.tr('&Color selected rows'))
        self.colorMenu.addAction(self.colorGreenAction)
        self.colorMenu.addAction(self.colorYellowAction)
        self.colorMenu.addAction(self.colorBlueAction)
        self.colorMenu.addAction(self.colorRedAction)
        self.colorMenu.addAction(self.colorOrangeAction)
        self.colorMenu.addAction(self.colorVioletAction)
        self.colorMenu.addAction(self.colorGreyAction)
        self.colorMenu.addAction(self.colorNoColorAction)
        self.estimateMenu = self.editRowMenu.addMenu(self.tr('Set &estimate of selected rows'))
        self.estimateMenu.addAction(self.noEstimateAction)
        for i in [15, 20, 30, 45, 60, 90, 120, 180]:
            action = add_action('',
                                QAction(self.tr('{} minutes').format(i), self,
                                        shortcut=','.join(number for number in str(i)),
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
        self.remindInMenu = self.editRowMenu.addMenu(self.tr('Set start &date of selected rows'))
        self.remindInMenu.addAction(
            add_action('', QAction(self.tr('No start date'), self, shortcut='.,D',
                                   triggered=partial(self.remindIn, 0)), list=self.item_view_actions))

        def add_shortcuts(time_unit, value, max):
            for i in range(1, max):
                keys = i if i < 10 else ','.join(list(str(i)))
                self.remindInMenu.addAction(
                    add_action('', QAction(self.tr('Remind in {} {}').format(i, time_unit), self,
                                           shortcut='{},{}'.format(keys, time_unit[0]),
                                           triggered=partial(self.remindIn, i * value)), list=self.item_view_actions))
                shortcut = QShortcut(QKeySequence('Num+{},{}'.format(keys, time_unit[0])), self)
                shortcut.setContext(Qt.ApplicationShortcut)
                shortcut.activated.connect(partial(self.remindIn, i * value))

        add_shortcuts('days', 1, 7)
        add_shortcuts('weeks', 7, 4)
        add_shortcuts('months', 30, 12)
        add_shortcuts('years', 365, 4)

        self.editRowMenu.addAction(self.appendRepeatAction)
        self.setPlanMenu = self.editRowMenu.addMenu(self.tr('Set &plan of selected rows'))
        for i in range(len(model.NUMBER_PLAN_DICT)):
            self.setPlanMenu.addAction(
                add_action('', QAction(model.NUMBER_PLAN_DICT[i], self, shortcut='Shift+{}'.format(i),
                                       triggered=partial(self.set_plan, i)), list=self.item_view_actions))
        line_break_action = QAction(self.tr('Insert a line break while editing a row:'), self, shortcut='Shift+Return')
        line_break_action.setDisabled(True)
        self.editRowMenu.addAction(line_break_action)
        internal_link_action = QAction(self.tr('Create an internal link while editing a row:'), self,
                                       shortcut='#')
        internal_link_action.setDisabled(True)
        self.editRowMenu.addAction(internal_link_action)

        self.viewMenu = self.menuBar().addMenu(self.tr('&View'))
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
        self.viewMenu.addAction(self.showInFolderAction)
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

        self.bookmarkShortcutsMenu = self.menuBar().addMenu(self.tr('&My shortcuts'))

        self.helpMenu = self.menuBar().addMenu(self.tr('&Help'))
        self.helpMenu.addAction(self.aboutAct)

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
        columns_hidden = settings.value(COLUMNS_HIDDEN, 'false')
        if columns_hidden == 'true':
            self.toggle_columns()

        self.backup_timer = QTimer()
        self.backup_timer.timeout.connect(self.backup_tree_if_changed)
        self.start_backup_service(settings.value('backup_interval', 0))

        self.print_size = float(settings.value('print_size', 1))
        self.new_rows_plan_item_creation_date = settings.value('new_rows_plan_item_creation_date')
        self.set_indentation_and_style_tree(settings.value('indentation', 40))
        self.backup_folder = settings.value('backup_folder', 'None set')

        self.popup_json_save_failed.connect(lambda: QMessageBox(QMessageBox.NoIcon, ' ',
                                                                "Backup failed: Could not find the folder '{}'.\n"
                                                                "Specifiy an existing folder in the settings!".format(
                                                                    self.backup_folder)).exec())

    def backup_tree_if_changed(self):
        if self.item_model.changed:
            self.item_model.changed = False
            self.worker = ExportThread()
            self.worker.main_window = self
            self.worker.start()

    def start_backup_service(self, minutes):
        self.backup_interval = int(minutes)
        self.backup_timer.stop()
        if self.backup_interval != 0:
            self.backup_timer.start(self.backup_interval * 1000 * 60)  # time specified in ms

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
        self.refresh_path_bar()

    def fill_bookmarkShortcutsMenu(self):
        self.bookmarkShortcutsMenu.clear()
        for index in self.item_model.indexes():
            item = self.bookmark_model.getItem(index)
            if item.shortcut:
                self.bookmarkShortcutsMenu.addAction(
                    QAction(item.text, self, shortcut=item.shortcut,
                            triggered=partial(self.focus_index, self.filter_proxy_index_from_model_index(index))))
        self.bookmarkShortcutsMenu.addSeparator()
        for index in self.bookmark_model.indexes():
            item = self.bookmark_model.getItem(index)
            if item.shortcut:
                self.bookmarkShortcutsMenu.addAction(
                    QAction(item.text, self, shortcut=item.shortcut, triggered=partial(self.filter_bookmark, index)))
        if self.bookmarkShortcutsMenu.isEmpty():
            no_shortcuts_yet_action = QAction(
                self.tr('No shortcuts from the quick access sidebar or the bookmarks set yet.'),
                self)
            no_shortcuts_yet_action.setDisabled(True)
            self.bookmarkShortcutsMenu.addAction(no_shortcuts_yet_action)

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
                self.select_from_to(index, index)
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
        self.undoAction.setShortcut(QKeySequence.Undo)
        self.undoAction.setIcon(QIcon.fromTheme('edit-undo'))
        self.redoAction = self.item_model.undoStack.createRedoAction(self)
        self.redoAction.setShortcut(QKeySequence.Redo)
        self.redoAction.setIcon(QIcon.fromTheme('edit-redo'))
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
        settings.setValue('backup_folder', self.backup_folder)

        # save theme
        theme = 'light' if self.app.palette() == self.light_palette else 'dark'
        settings.setValue('theme', theme)
        self.save_file()

    def getQSettings(self):
        return QSettings(os.path.join(HOME_TREENOTE_FOLDER, 'treenote_settings.ini'), QSettings.IniFormat)

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
        self.select_from_to(bookmark_index, bookmark_index)

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
            if re.search(key[:-1] + r'(<|>|=)', search_bar_text):
                search_bar_text = re.sub(key[:-1] + r'(<|>|=|\w|\d)* ', key + value + ' ', search_bar_text)
            else:
                # add filter
                search_bar_text += ' ' + key + value + ' '
        self.set_searchbar_text_and_search(search_bar_text)

    def set_searchbar_text_and_search(self, search_bar_text):
        self.focused_column().search_bar.setText(search_bar_text)
        self.search(search_bar_text)

    def filter_proxy_index_from_model_index(self, model_index):
        return self.focused_column().filter_proxy.mapFromSource(model_index)

    def select_from_to(self, index_from, index_to):
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

    def select(self, indexes):
        view = self.current_view()
        view.clearSelection()
        for index in indexes:
            index = self.map_to_view(index)
            view.selectionModel().select(index, QItemSelectionModel.Select | QItemSelectionModel.Rows)
        view.selectionModel().setCurrentIndex(index, QItemSelectionModel.Select)

    def set_top_row_selected(self):
        current_root_index = self.current_view().rootIndex()
        top_most_index = self.focused_column().filter_proxy.index(0, 0, current_root_index)
        self.select_from_to(top_most_index, top_most_index)
        self.current_view().setFocus()

    def reset_view(self):
        self.hideFutureStartdateCheckBox.setChecked(False)
        self.hideTagsCheckBox.setChecked(False)
        self.task_dropdown.setCurrentIndex(0)
        self.estimate_dropdown.setCurrentIndex(0)
        self.color_dropdown.setCurrentIndex(0)
        self.date_dropdown.setCurrentIndex(0)
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

    def is_no_text_search(self, text):
        def is_filter_keyword(token):
            return token.startswith(model.SORT) or token.startswith('c=') or token.startswith('t=') or \
                   re.match(r'e(<|>|=)', token) or token.startswith(model.DATE_BELOW) or \
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
        if self.current_view().header().isSortIndicatorShown():
            QMessageBox(QMessageBox.NoIcon, ' ',
                        "Moving is not possible when the tree is sorted.\n"
                        "Click the first column or Esc to disable sorting.").exec()
        else:
            indexes = self.selected_indexes()
            self.focused_column().filter_proxy.move_vertical(indexes, -1)

    def move_down(self):
        if self.current_view().header().isSortIndicatorShown():
            QMessageBox(QMessageBox.NoIcon, ' ',
                        "Moving is not possible when the tree is sorted.\n"
                        "Click the first column or Esc to disable sorting.").exec()
        else:
            indexes = self.selected_indexes()
            self.focused_column().filter_proxy.move_vertical(indexes, +1)

    def move_left(self):
        if self.focusWidget() is self.focused_column().view:
            if self.current_view().header().isSortIndicatorShown():
                QMessageBox(QMessageBox.NoIcon, ' ',
                            "Moving is not possible when the tree is sorted.\n"
                            "Click the first column or Esc to disable sorting.").exec()
            else:
                self.focused_column().filter_proxy.move_horizontal(self.focused_column().view.
                                                                   selectionModel().selectedRows(), -1)

    def move_right(self):
        if self.focusWidget() is self.focused_column().view:
            if self.current_view().header().isSortIndicatorShown():
                QMessageBox(QMessageBox.NoIcon, ' ',
                            "Moving is not possible when the tree is sorted.\n"
                            "Click the first column or Esc to disable sorting.").exec()
            else:
                selected_indexes = self.focused_column().view.selectionModel().selectedRows()
                self.focused_column().view.setAnimated(False)
                self.focused_column().view.setExpanded(selected_indexes[0].sibling(selected_indexes[0].row() - 1, 0),
                                                       True)
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
        elif self.current_view().hasFocus() and self.current_view() is self.planned_view:
            selected = self.selected_indexes()
            planned_level = self.current_view().model().getItem(selected[0]).planned if selected else 1
            parent_index = self.get_index_by_creation_date(self.new_rows_plan_item_creation_date)
            if parent_index:
                parent_filter_proxy_index = self.filter_proxy_index_from_model_index(parent_index)
            else:
                parent_filter_proxy_index = QModelIndex()
                parent_index = QModelIndex()
            self.focused_column().filter_proxy.insert_row(0, parent_filter_proxy_index)
            new_item_index = self.item_model.index(0, 0, parent_index)
            filter_proxy_index = self.filter_proxy_index_from_model_index(new_item_index)
            self.focused_column().filter_proxy.set_data(planned_level, indexes=[filter_proxy_index],
                                                        field=model.PLANNED)
            planned_index = self.planned_view.model().map_to_planned_index(new_item_index)
            self.focusWidget().edit(planned_index)
            self.select([planned_index])
        # if there are no entries, pressing enter shall create a child of the current root entry
        elif len(self.focused_column().filter_proxy.getItem(self.current_view().rootIndex()).childItems) == 0:
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

    def map_to_source(self, index):
        if index.model() is self.planned_view.model():
            return self.planned_view.model().map_to_original_index(index)
        else:
            return self.focused_column().filter_proxy.mapToSource(index)

    def map_to_view(self, index):
        if index.model() is self.item_model:
            if self.current_view() is self.planned_view:
                return self.planned_view.model().map_to_planned_index(index)
            else:
                return self.filter_proxy_index_from_model_index(index)
        return index

    def copy(self):
        if len(self.selected_indexes()) == 1:
            rows_string = self.selected_indexes()[0].data()
        else:
            selected_source_indexes = [self.map_to_source(index) for index in self.selected_indexes()]

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
            if idx.parent() != QModelIndex() and idx in indexes:
                if idx.parent() in indexes:
                    indexes.remove(idx)
                else:
                    remove_if_parent(idx.parent())

        for index in self.selected_indexes():
            remove_if_parent(index)
        items = [self.current_view().model().getItem(index) for index in indexes]
        mime_data = ItemMimeData(copy.deepcopy(items))
        mime_data.setText(rows_string)
        QApplication.clipboard().setMimeData(mime_data)

    def current_model(self):
        if self.current_view() is self.planned_view:
            return self.planned_view.model()
        else:
            return self.focused_column().filter_proxy

    def paste(self):
        position = 0
        # if there are no entries, pressing enter shall create a child of the current root entry
        root_index = self.focused_column().view.rootIndex() if len(
            self.focused_column().filter_proxy.getItem(self.current_view().rootIndex()).childItems) == 0 else None
        expanded_parent = self.current_view().isExpanded(self.current_index()) and \
                          self.current_model().rowCount(self.current_index()) > 0
        if isinstance(QApplication.clipboard().mimeData(), ItemMimeData):
            items = QApplication.clipboard().mimeData().items
            if self.current_view() is self.planned_view:
                planned_level = 1
                if self.selected_indexes():
                    last_selected_item = self.current_view().model().getItem(self.selected_indexes()[-1])
                    planned_level = last_selected_item.planned

                    next_index = self.current_view().model().index(self.selected_indexes()[-1].row() + 1, 0)
                    next_item = self.current_view().model().getItem(next_index)
                parent_index = self.get_index_by_creation_date(self.new_rows_plan_item_creation_date)
                if not parent_index:
                    parent_index = QModelIndex()
            else:
                if root_index:
                    parent_index = self.focused_column().filter_proxy.mapToSource(root_index)
                elif expanded_parent:
                    parent_index = self.focused_column().filter_proxy.mapToSource(self.current_index())
                else:
                    position = self.current_index().row() + 1
                    parent_index = self.focused_column().filter_proxy.mapToSource(self.current_index().parent())
            self.item_model.insert_remove_rows(position=position, parent_index=parent_index, set_edit_focus=False,
                                               items=items)
            if self.current_view() is self.planned_view:
                # add beneath the last selected item
                if last_selected_item:
                    for i, item in enumerate(items):
                        new_item_index = self.item_model.index(position + i, 0, parent_index)
                        filter_proxy_index = self.filter_proxy_index_from_model_index(new_item_index)
                        planned_order_diff = next_item.planned_order - last_selected_item.planned_order
                        self.focused_column().filter_proxy.set_data(
                            last_selected_item.planned_order + planned_order_diff / (len(items) + 1) * (i + 1),
                            indexes=[filter_proxy_index], field=model.PLANNED_ORDER)

                planned_indexes_to_select = []
                for i, item in enumerate(items):
                    new_item_index = self.item_model.index(position + i, 0, parent_index)
                    planned_indexes_to_select.append(self.planned_view.model().map_to_planned_index(new_item_index))
                self.select(planned_indexes_to_select)
        else:
            if QApplication.clipboard().mimeData().hasUrls():
                text = '\n'.join(url.url() for url in QApplication.clipboard().mimeData().urls())
            else:
                # paste from plain text
                # builds a tree structure out of indented rows
                # idea: insert new rows from top to bottom.
                # depending on the indention, the parent will be the last inserted row with one lower indention
                # we count the row position to know where to insert the next row
                # \r ist for windows compatibility. strip is to remove the last linebreak
                text = QApplication.clipboard().text().replace('\r\n', '\n').strip('\n')
            # which format style has the text?
            if re.search(r'(\n|^)([\t| ]*-)', text):  # each item starts with a dash
                text = re.sub(r'\n([\t| ]*-)', r'\r\1', text)  # replaces \n which produce a new item with \r
            else:  # each row is an item
                text = re.sub(r'\n([\t| ]*)', r'\r\1', text)  # replaces \n which produce a new item with \r
            lines = re.split(r'\r', text)
            source_index = self.focused_column().filter_proxy.mapToSource(self.current_index())
            indention_insert_position_dict = {}
            if root_index:
                indention_parent_index_dict = {-1: self.focused_column().filter_proxy.mapToSource(root_index)}
            elif expanded_parent:
                indention_parent_index_dict = {-1: source_index}
            else:
                indention_insert_position_dict[0] = source_index.row() + 1
                indention_parent_index_dict = {-1: source_index.parent()}
            # when indented with spaces, deep indentions are made with multiples of the smalles indention
            smallest_indention = None
            for line in lines:
                stripped_line = line.lstrip('\t')
                indention = len(line) - len(stripped_line)
                if line.startswith(' '):
                    stripped_line = line.lstrip(' ')
                    indention = len(line) - len(stripped_line)
                    if indention > 0:
                        # first indentions is also smallest indention
                        if not smallest_indention:
                            smallest_indention = indention
                        indention = indention / smallest_indention
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
            self.save_file()

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
        if self.current_view().state() == QAbstractItemView.EditingState:  # change column with tab key
            if not self.focused_column().view.isHeaderHidden():
                next_column_number = (current_index.column() + 2)
                if next_column_number == 0 or next_column_number == 2:
                    sibling_index = current_index.sibling(current_index.row(), next_column_number)
                    self.current_view().selectionModel().setCurrentIndex(sibling_index,
                                                                         QItemSelectionModel.ClearAndSelect)
                    self.current_view().edit(sibling_index)
                else:
                    self.current_view().setFocus()
        elif self.current_view().hasFocus():
            self.current_view().edit(current_index)
        else:
            self.current_view().setFocus()

    def current_index(self):
        return self.current_view().selectionModel().currentIndex()

    def current_view(self):
        return self.focused_column().stacked_widget.currentWidget()

    def toggle_task(self):
        selected = self.selected_indexes()
        self.focused_column().filter_proxy.toggle_task(selected)
        self.select(selected)

    def toggle_project(self):
        selected = self.selected_indexes()
        self.focused_column().filter_proxy.toggle_project(selected)
        self.select(selected)

    def remindIn(self, days):
        date = '' if days == 0 else QDate.currentDate().addDays(days).toString('dd.MM.yy')
        selected = self.selected_indexes()
        self.focused_column().filter_proxy.set_data(date, indexes=selected, field='date')
        self.select(selected)

    def append_repeat(self):
        if self.current_view() != self.planned_view:
            index = self.current_index()
            self.focused_column().filter_proxy.set_data(model.TASK, indexes=[index], field='type')
            self.focused_column().filter_proxy.set_data(QDate.currentDate().toString('dd.MM.yy'), indexes=[index],
                                                        field='date')
            self.focused_column().filter_proxy.set_data(index.data() + ' repeat=1w', indexes=[index])
            self.edit_row()

    def estimate(self, number):
        selected = self.selected_indexes()
        self.focused_column().filter_proxy.set_data(str(number), indexes=selected, field=model.ESTIMATE)
        self.select(selected)

    def adjust_estimate(self, adjustment):
        selected = self.selected_indexes()
        self.focused_column().filter_proxy.adjust_estimate(adjustment, selected)
        self.select(selected)

    def set_plan(self, i):
        selected = self.selected_indexes()
        creation_dates = [self.current_view().model().getItem(index).creation_date_time for index in selected]
        self.focused_column().filter_proxy.set_data(i, indexes=selected, field=model.PLANNED)
        if self.current_view() is self.planned_view:
            self.select(self.get_indexes_from_creation_dates(creation_dates))

    def get_indexes_from_creation_dates(self, creation_dates_list):
        indexes = []
        for index in self.current_view().model().indexes():
            if self.current_view().model().getItem(index).creation_date_time in creation_dates_list:
                indexes.append(index)
        return indexes

    @pyqtSlot(str)
    def color_row(self, color_character):
        selected = self.selected_indexes()
        self.focused_column().filter_proxy.set_data(model.CHAR_QCOLOR_DICT[color_character], indexes=selected,
                                                    field='color')
        self.select(selected)

    # view menu actions

    @pyqtSlot(QModelIndex)
    def focus_index(self, index):
        self.tab_bar.setCurrentIndex(0)
        if index.model() is self.planned_view.model():
            real_index = index.internalPointer()
            index = self.focused_column().filter_proxy.mapFromSource(real_index)
        else:
            real_index = self.focused_column().filter_proxy.mapToSource(index)
        self.current_view().setRootIndex(index)
        self.set_searchbar_text_and_search('')
        self.quicklinks_view.selectionModel().select(QItemSelection(real_index, real_index),
                                                     QItemSelectionModel.ClearAndSelect)
        if not self.focused_column().search_bar.isModified() and not self.is_selection_visible():
            self.set_top_row_selected()
        self.setup_tag_model()
        self.refresh_path_bar()

    def refresh_path_bar(self):
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
        if self.app.activeWindow():  # prevents qt warning on startup
            margin_count_between_toolbar_widgets = 4 if self.is_sidebar_shown() else 6
            self.path_bar.setMaximumWidth(self.item_views_splitter.width() - self.tab_bar.sizeHint().width()
                                          - self.focused_column().search_bar.width()
                                          - 2 * self.focused_column().bookmark_button.sizeHint().width()
                                          - margin_count_between_toolbar_widgets * TOOLBAR_MARGIN)

    def focus_parent_of_focused(self):
        self.focused_column().view.selectionModel().clear()
        root_index = self.focused_column().view.rootIndex()
        self.focus_index(root_index.parent())
        self.select_from_to(root_index, root_index)

    def show_in_folder(self):
        for row_index in self.focused_column().view.selectionModel().selectedRows():
            if row_index.data().startswith('file:///'):
                file_info = QFileInfo(row_index.data().replace('file://', ''))
                QDesktopServices.openUrl(QUrl.fromLocalFile(file_info.absoluteDir().absolutePath()))

    def open_links_or_files(self):
        for row_index in self.focused_column().view.selectionModel().selectedRows():
            match = re.search(model.FIND_INTERNAL_LINK, row_index.data())
            # open file
            if row_index.data().startswith('file:///'):
                QDesktopServices.openUrl(QUrl.fromLocalFile(row_index.data().replace('file://', '')))
            # open internal link
            elif match:
                text_to_find = match.group(1)[1:].strip(model.INTERNAL_LINK_DELIMITER)
                for index in self.item_model.indexes():
                    if self.item_model.getItem(index).text == text_to_find:
                        self.focus_index(self.filter_proxy_index_from_model_index(index))
                        break
            # open URL in web browser
            else:
                url_list = re.findall(util.url_regex, row_index.data())
                for url in url_list:
                    if not re.search(r'https?://', url):
                        url = 'http://' + url
                    QDesktopServices.openUrl(QUrl(url))
                    break
                else:  # no urls found: search the web for the selected entry
                    text_without_tags = re.sub(r':(\w|:)*', '', row_index.data())
                    QDesktopServices.openUrl(QUrl('https://www.google.de/search?q=' + text_without_tags))

    def split_window(self):  # creates another item_view
        new_column = QWidget()

        new_column.toggle_sidebars_button = QPushButton()
        new_column.toggle_sidebars_button.setToolTip(self.tr('Hide / show the sidebars'))
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
        self.tab_bar.addTab(self.tr('Tree'))
        self.tab_bar.addTab(PLAN_TAB)
        for i in range(2):
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

        new_column.view = ResizeTreeView(self, new_column.filter_proxy)
        new_column.view.setItemDelegate(model.Delegate(self, new_column.filter_proxy, new_column.view.header()))
        new_column.view.selectionModel().selectionChanged.connect(self.update_actions)
        new_column.view.header().sectionClicked[int].connect(self.toggle_sorting)
        new_column.view.header().setSectionsClickable(True)

        plan_model = planned_model.PlannedModel(self.item_model, new_column.filter_proxy)
        self.planned_view = ResizeTreeView(self, plan_model)
        self.planned_view.setItemDelegate(model.Delegate(self, plan_model, self.planned_view.header()))

        new_column.stacked_widget = QStackedWidget()
        new_column.stacked_widget.addWidget(new_column.view)
        new_column.stacked_widget.addWidget(self.planned_view)

        def change_tab(i):
            self.path_bar.setVisible(i == 0)
            new_column.stacked_widget.setCurrentIndex(i)
            if self.tab_bar.tabText(i) == PLAN_TAB and self.focused_column().search_bar.text():
                self.set_searchbar_text_and_search('')

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
        self.select_from_to(top_most_index, top_most_index)
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
            self.item_model = model.TreeModel(self, header_list=self.tree_header)
            self.bookmark_model = model.TreeModel(self, header_list=BOOKMARKS_HEADER)
            self.change_active_tree()

    def save_file(self):
        # self.item_model.selected_item = self.focused_column().filter_proxy.getItem(self.current_index())
        pickle.dump((self.item_model.selected_item, self.item_model.rootItem, self.bookmark_model.rootItem),
                    open(self.save_path, 'wb'),
                    protocol=pickle.HIGHEST_PROTOCOL)

        # this method is called everytime a change is done.
        # therefore it is the right place to set the model changed for backup purposes
        self.item_model.changed = True

        self.planned_view.model().refresh_model()

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
            self.app.processEvents()
            dic = obj.__dict__.copy()
            del dic['parentItem']
            return dic

        try:
            json.dump((self.item_model.rootItem, self.bookmark_model.rootItem), open(path, 'w'), default=json_encoder)
        except FileNotFoundError:
            self.popup_json_save_failed.emit()

    def start_open_file(self):
        path = QFileDialog.getOpenFileName(self, "Open", filter="*.treenote")[0]
        if path and len(path) > 0:
            self.open_file(path)

    def import_backup(self, open_path, save_path):
        self.item_model = model.TreeModel(self, header_list=self.tree_header)
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
                    item.header_list = self.tree_header
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
        if self.current_view() is self.planned_view:
            view.setModel(self.planned_view.model())
        else:
            view.setModel(self.item_model)
            view.model().expand_saved(print_view=view)
        toolbar = dialog.findChildren(QToolBar)[0]
        toolbar.addAction(QIcon(':/plus'), self.tr('Increase print size'), lambda: view.change_print_size(0.1))
        toolbar.addAction(QIcon(':/minus'), self.tr('Decrease print size'), lambda: view.change_print_size(-0.1))
        toolbar.addWidget(QLabel(self.tr('Change the print size with the red buttons.')))
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

        def item_length(item_text) -> int:
            try:
                return len(item_text)
            except TypeError:
                return 0

        self.completer = QCompleter(sorted((index.data() for index in other_indexes), key=item_length))
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
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
                self.main_window.select_from_to(next_index, next_index)
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

        completionPrefix = self.toPlainText()
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
            self.setPlaceholderText(self.tr('Type the name of an entry'))

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


class FocusTreeAfterCloseDialog(QDialog):
    def __init__(self, main_window):
        super(FocusTreeAfterCloseDialog, self).__init__(main_window)
        self.main_window = main_window

    def accept(self):
        super(FocusTreeAfterCloseDialog, self).accept()
        self.main_window.focused_column().view.setFocus()

    def reject(self):
        super(FocusTreeAfterCloseDialog, self).reject()
        self.main_window.focused_column().view.setFocus()


class ImportDialog(FocusTreeAfterCloseDialog):
    def __init__(self, main_window, open_filter, title, hint):
        super(ImportDialog, self).__init__(main_window)
        self.setWindowTitle(title)
        self.setMinimumWidth(900)
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
        buttonBox.button(QDialogButtonBox.Apply).clicked.connect(self.accept)
        buttonBox.button(QDialogButtonBox.Cancel).clicked.connect(self.reject)

    def accept(self):
        try:
            self.main_window.import_backup(self.import_file_edit.text(), self.treenote_file_edit.text())
        except Exception as e:
            QMessageBox.information(self, '', 'Import went wrong:\n{}'.format(e), QMessageBox.Ok)
        else:
            QMessageBox.information(self, '', 'Import successful!', QMessageBox.Ok)
            super(ImportDialog, self).accept()


class AboutBox(FocusTreeAfterCloseDialog):
    def __init__(self, main_window):
        super(AboutBox, self).__init__(main_window)
        headline = QLabel('TreeNote')
        headline.setFont(QFont(model.FONT, 25))
        label = QLabel(
            self.tr(
                'Version ' + __version__ +
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
        self.setClearButtonEnabled(True)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Down or event.key() == Qt.Key_Up:
            self.main.focused_column().view.setFocus()
            if self.main.selected_indexes():  # if the selection remains valid after the search
                QApplication.sendEvent(self.main.focused_column().view, event)
            else:
                self.main.set_top_row_selected()
        else:
            QLineEdit.keyPressEvent(self, event)


class BookmarkDialog(FocusTreeAfterCloseDialog):
    # init it with either search_bar_text or index set
    # search_bar_text is set: create new bookmark
    # index is set: edit existing bookmark

    def __init__(self, main_window, search_bar_text=None, index=None):
        super(BookmarkDialog, self).__init__(main_window)
        self.setMinimumWidth(600)
        self.search_bar_text = search_bar_text
        self.index = index
        rootIndex = self.main_window.focused_column().view.rootIndex()
        self.root_item = self.main_window.focused_column().filter_proxy.getItem(rootIndex)
        self.save_root_checkbox = QCheckBox()
        self.save_root_checkbox.setChecked(True)

        save_root_item_label_text = self.tr("Save current root item '{}':").format(self.root_item.text)
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
        buttonBox.button(QDialogButtonBox.Apply).clicked.connect(self.accept)
        buttonBox.button(QDialogButtonBox.Cancel).clicked.connect(self.reject)
        if self.index is None:
            self.setWindowTitle("Bookmark current filters")
        else:
            self.setWindowTitle("Edit bookmark")

    def accept(self):
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


class ShortcutDialog(FocusTreeAfterCloseDialog):
    def __init__(self, main_window, index):
        super(ShortcutDialog, self).__init__(main_window)
        self.setMinimumWidth(340)
        self.index = index
        item = main_window.item_model.getItem(index)
        self.shortcut_edit = QKeySequenceEdit()
        self.shortcut_edit.setKeySequence(QKeySequence(item.shortcut))
        clearButton = QPushButton('Clear')
        clearButton.clicked.connect(self.shortcut_edit.clear)
        buttonBox = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Cancel)
        buttonBox.button(QDialogButtonBox.Apply).clicked.connect(self.accept)
        buttonBox.button(QDialogButtonBox.Cancel).clicked.connect(self.reject)

        grid = QGridLayout()
        grid.addWidget(QLabel('Shortcut:'), 0, 0)  # row, column
        grid.addWidget(self.shortcut_edit, 0, 1)
        grid.addWidget(clearButton, 0, 2)
        grid.addWidget(buttonBox, 1, 0, 1, 2, Qt.AlignRight)  # fromRow, fromColumn, rowSpan, columnSpan.
        self.setLayout(grid)
        self.setWindowTitle('Edit selected quick link shortcut')

    def accept(self):
        self.main_window.item_model.set_data(self.shortcut_edit.keySequence().toString(), index=self.index,
                                             field=model.SHORTCUT)
        self.main_window.fill_bookmarkShortcutsMenu()
        super(ShortcutDialog, self).accept()


class RenameTagDialog(FocusTreeAfterCloseDialog):
    def __init__(self, main_window, tag):
        super(RenameTagDialog, self).__init__(main_window)
        self.tag = tag
        self.line_edit = QLineEdit(tag)
        buttonBox = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Cancel)

        grid = QGridLayout()
        grid.addWidget(QLabel('Enter new tag name:'), 0, 0)  # row, column
        grid.addWidget(self.line_edit, 0, 1)
        grid.addWidget(buttonBox, 1, 0, 1, 2, Qt.AlignRight)  # fromRow, fromColumn, rowSpan, columnSpan.
        self.setLayout(grid)
        buttonBox.button(QDialogButtonBox.Apply).clicked.connect(self.accept)
        buttonBox.button(QDialogButtonBox.Apply).setDefault(True)
        buttonBox.button(QDialogButtonBox.Cancel).clicked.connect(self.reject)
        self.setWindowTitle(self.tr('Rename tag'))

    def accept(self):
        self.main_window.rename_tag(self.tag, self.line_edit.text())
        super(RenameTagDialog, self).accept()


class SettingsDialog(FocusTreeAfterCloseDialog):
    def __init__(self, main_window):
        super(SettingsDialog, self).__init__(main_window)
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

        folder_chooser_layout = QHBoxLayout()
        folder_chooser_layout.setSpacing(5)
        self.backup_folder_textedit = QTextEdit()
        self.backup_folder_textedit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.backup_folder_textedit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.backup_folder_textedit.setReadOnly(True)
        self.backup_folder_textedit.setFixedWidth(300)
        self.update_backup_folder_textedit()
        choose_button = QPushButton('Browse...')
        choose_button.clicked.connect(self.choose_folder)
        folder_chooser_layout.addWidget(self.backup_folder_textedit)
        folder_chooser_layout.addWidget(choose_button)
        folder_chooser_layout.setStretchFactor(self.backup_folder_textedit, 1)

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
        layout.addRow(self.tr('Theme:'), theme_dropdown)
        layout.addRow(self.tr('Indentation of children in the tree:'), indentation_spinbox)
        layout.addRow(self.tr('Backup folder:'), folder_chooser_layout)
        backup_label = QLabel(self.tr("Create a JSON export of the tree to the specified backup folder "
                                      "every ... minutes, if the tree has changed (0 minutes disables this feature):"))
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

    def update_backup_folder_textedit(self):
        self.backup_folder_textedit.setText(self.main_window.backup_folder)
        self.backup_folder_textedit.document().setTextWidth(self.backup_folder_textedit.width())
        self.backup_folder_textedit.setFixedHeight(self.backup_folder_textedit.document().size().height() +
                                                   self.backup_folder_textedit.contentsMargins().top() * 2)

    def choose_folder(self):
        self.main_window.backup_folder = QFileDialog.getExistingDirectory(self, self.tr('Choose backup folder'),
                                                                          self.main_window.save_path,
                                                                          QFileDialog.ShowDirsOnly)
        self.update_backup_folder_textedit()

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


class SaveExpandTreeView(QTreeView):
    def __init__(self, model):
        super(SaveExpandTreeView, self).__init__()
        self.setModel(model)
        self.expanded.connect(self.expand)
        self.collapsed.connect(self.collapse)

    def expand(self, index):
        self.model().getItem(index).quicklink_expanded = True

    def collapse(self, index):
        self.model().getItem(index).quicklink_expanded = False


class ResizeTreeView(QTreeView):
    def __init__(self, main_window, model):
        super(ResizeTreeView, self).__init__()
        self.main_window = main_window
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
        self.expanded.connect(self.expand)
        self.collapsed.connect(self.collapse)

    def expand(self, index):
        # save expanded state only when in normal mode,
        # not when doing a text search and therefore having everything expanded
        if self.main_window.is_no_text_search(self.main_window.focused_column().search_bar.text()):
            self.model().getItem(index).expanded = True

    def collapse(self, index):
        if self.main_window.is_no_text_search(self.main_window.focused_column().search_bar.text()):
            self.model().getItem(index).expanded = False

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


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('TreeNote')
    app.setOrganizationName('Jan Korte')
    app.setWindowIcon(QIcon(':/logo'))
    QFontDatabase.addApplicationFont(os.path.join(RESOURCE_FOLDER, 'SourceSansPro-Regular.otf'))

    locale = QLocale.system().name()
    qt_translator = QTranslator()
    if qt_translator.load("qtbase_" + locale, QLibraryInfo.location(QLibraryInfo.TranslationsPath)):
        app.installTranslator(qt_translator)
    app_translator = QTranslator()
    if app_translator.load('treenote_' + locale, os.path.join(RESOURCE_FOLDER, 'locales')):
        app.installTranslator(app_translator)

    form = MainWindow(app)
    form.show()
    app.exec_()


if __name__ == '__main__':
    main()
