from PyQt5 import QtWidgets
import sys
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import qrc_resources
import model
import subprocess


class MainWindow(QMainWindow):
    def _getView(self):
        # return focused view
        for i in range(0, self.mainSplitter.count()):
            if self.mainSplitter.widget(i).hasFocus():
                return self.mainSplitter.widget(i)
        return self.mainSplitter.widget(0)

    view = property(fget=_getView)

    def __init__(self):
        super(MainWindow, self).__init__()

        self.model = model.TreeModel()
        self.model.update_selection_signal[QModelIndex, QModelIndex, int].connect(self.update_selection)
        self.model.update_selection_and_edit_signal[QModelIndex].connect(self.update_selection_and_edit)
        self.model.layout_changed_signal.connect(self.layout_changed)
        self.mainSplitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(self.mainSplitter)

        self.actions = list()

        def add_action(name, qaction):
            setattr(self, name, qaction)
            self.actions.append(qaction)
        add_action('aboutAct', QAction(self.tr('&About'), self, triggered=self.about))
        add_action('unsplitWindowAct', QAction(QIcon(':/editedit.png'), self.tr('&Unsplit window'), self, shortcut='Ctrl+Shift+S', triggered=self.unsplit_window))
        self.unsplitWindowAct.setEnabled(False)  # todo put in update actions
        add_action('splitWindowAct', QAction(QIcon(':/filenew.png'), self.tr('&Split window'), self, shortcut='Ctrl+S', triggered=self.split_window))
        add_action('editRowAction', QAction(QIcon(':/filenew.png'), self.tr('&Edit row'), self, shortcut='Tab', triggered=self.editRow))
        add_action('deleteSelectedRowsAction', QAction(QIcon(':/filenew.png'), self.tr('&Delete selected rows'), self, shortcut='delete', triggered=self.removeSelection))
        add_action('insertRowAction', QAction(QIcon(':/filenew.png'), self.tr('&Insert row'), self, shortcut='Return', triggered=self.insertRow))
        add_action('insertChildAction', QAction(QIcon(':/filenew.png'), self.tr('&Insert child'), self, shortcut='Shift+Return', triggered=self.insertChild))
        add_action('moveUpAction', QAction(QIcon(':/filenew.png'), self.tr('&Up'), self, shortcut='W', triggered=self.move_up))
        add_action('moveDownAction', QAction(QIcon(':/filenew.png'), self.tr('&Down'), self, shortcut='S', triggered=self.move_down))
        add_action('moveLeftAction', QAction(QIcon(':/filenew.png'), self.tr('&Left'), self, shortcut='A', triggered=self.move_left))
        add_action('moveRightAction', QAction(QIcon(':/filenew.png'), self.tr('&Right'), self, shortcut='D', triggered=self.move_right))
        add_action('expandAllChildrenAction', QAction(QIcon(':/filenew.png'), self.tr('&Expand all children'), self, shortcut='Shift+Right', triggered=self.expand_all_children))
        add_action('collapseAllChildrenAction', QAction(QIcon(':/filenew.png'), self.tr('&Collapse all children'), self, shortcut='Shift+Left', triggered=self.collapse_all_children))

        self.structureMenu = self.menuBar().addMenu(self.tr('&Edit structure'))
        self.structureMenu.addAction(self.insertChildAction)
        self.structureMenu.addAction(self.insertRowAction)
        self.structureMenu.addAction(self.deleteSelectedRowsAction)

        self.moveMenu = self.structureMenu.addMenu(self.tr('&Move task'))
        self.moveMenu.addAction(self.moveUpAction)
        self.moveMenu.addAction(self.moveDownAction)
        self.moveMenu.addAction(self.moveLeftAction)
        self.moveMenu.addAction(self.moveRightAction)

        self.taskMenu = self.menuBar().addMenu(self.tr('&Edit Task'))

        self.viewMenu = self.menuBar().addMenu(self.tr('&View'))
        self.viewMenu.addAction(self.expandAllChildrenAction)
        self.viewMenu.addAction(self.collapseAllChildrenAction)
        self.viewMenu.addAction(self.splitWindowAct)
        self.viewMenu.addAction(self.unsplitWindowAct)

        self.helpMenu = self.menuBar().addMenu(self.tr('&Help'))
        self.helpMenu.addAction(self.aboutAct)

        # make single key menu shortcuts work on all operating systems http://thebreakfastpost.com/2014/06/03/single-key-menu-shortcuts-with-qt5-on-osx/
        self.signalMapper = QSignalMapper(self)  # This class collects a set of parameterless signals, and re-emits them with a string corresponding to the object that sent the signal.
        self.signalMapper.mapped[str].connect(self.evoke_singlekey_action)
        for action in self.actions:
            keySequence = action.shortcut()
            if keySequence.count() == 1:
                shortcut = QShortcut(keySequence, self)
                shortcut.activated.connect(self.signalMapper.map)
                self.signalMapper.setMapping(shortcut, action.text())  # pass the action's name
                action.shortcut = QKeySequence()  # disable the old shortcut

        self.split_window()
        self.updateActions()

        settings = QSettings()
        self.resize(settings.value('size', QSize(400, 400)))
        self.move(settings.value('pos', QPoint(200, 200)))

    def closeEvent(self, event):
        settings = QSettings()
        settings.setValue('pos', self.pos())
        settings.setValue('size', self.size())
        self.model.updater.terminate()
        if sys.platform == "darwin":
            subprocess.call(['osascript', '-e', 'tell application "Apache CouchDB" to quit'])

    def evoke_singlekey_action(self, action_name):  # fix shortcuts for mac
        for action in self.actions:
            if action.text() == action_name and action.isEnabled():
                action.trigger()
                break

    def updateActions(self):
        pass  # todo embed split action

    def expand_node(self, parent_index, bool_expand):
        self.view.setExpanded(parent_index, bool_expand)
        for row_num in range(self.model.rowCount(parent_index)):
            child_index = self.model.index(row_num, 0, parent_index)
            self.view.setExpanded(parent_index, bool_expand)
            self.expand_node(child_index, bool_expand)

    # structure menu actions

    def expand_all_children(self):
        self.expand_node(self.view.selectionModel().currentIndex(), True)

    def collapse_all_children(self):
        self.expand_node(self.view.selectionModel().currentIndex(), False)

    def move_up(self):
        indexes = self.view.selectionModel().selectedIndexes()
        self.model.move_vertical(indexes, -1)

    def move_down(self):
        indexes = self.view.selectionModel().selectedIndexes()
        self.model.move_vertical(indexes, +1)

    def move_left(self):
        self.model.move_left(self.view.selectionModel().selectedIndexes())

    def move_right(self):
        self.model.move_right(self.view.selectionModel().selectedIndexes())

    def editRow(self):
        self.view.edit(self.view.selectionModel().currentIndex())

    def insertChild(self):
        index = self.view.selectionModel().currentIndex()
        if self.view.state() == QAbstractItemView.EditingState:
            # commit data by changing the current selection
            self.view.selectionModel().currentChanged.emit(index, index)
        self.model.insertRows(0, index)

    def insertRow(self):
        index = self.view.selectionModel().currentIndex()
        if self.view.state() == QAbstractItemView.EditingState:
            # commit data by changing the current selection
            self.view.selectionModel().currentChanged.emit(index, index)
        else:
            self.model.insertRows(index.row() + 1, index.parent())

    def removeSelection(self):
        self.view.model().removeRows(self.view.selectionModel().selectedIndexes())

    # view menu actions

    def split_window(self): # creates the view, too
        view = QTreeView()
        view.header().hide()
        view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        view.setModel(self.model)
        view.selectionModel().selectionChanged.connect(self.updateActions)
        self.mainSplitter.addWidget(view)
        self.unsplitWindowAct.setEnabled(True)
        self.__view = view

    def unsplit_window(self):
        index_last_widget = self.mainSplitter.count() - 1
        self.mainSplitter.widget(index_last_widget).setParent(None)
        if self.mainSplitter.count() == 1:
            self.unsplitWindowAct.setEnabled(False)

    # help menu actions

    def about(self):
        QMessageBox.about(self, self.tr('About'), self.tr('teeeext'))

    # signals from model thread

    def layout_changed(self):
        self.model.layoutChanged.emit()

    def update_selection(self, index_from, index_to, seq):
        # Events are queued, so it may happen that the model was changed meanwhile. Then ignore the event and process the next event with the right sequence number.
        if seq == self.model.seq:
            selection = QItemSelection(index_from, index_to)
            self.view.selectionModel().select(selection, QItemSelectionModel.ClearAndSelect)
            self.view.selectionModel().setCurrentIndex(index_from, QItemSelectionModel.ClearAndSelect)

    def update_selection_and_edit(self, index):
        self.view.selectionModel().setCurrentIndex(index, QItemSelectionModel.ClearAndSelect)
        self.view.edit(index)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setApplicationName(QApplication.translate('main', 'NoteTree'))
    app.setWindowIcon(QIcon(':/icon.png'))
    form = MainWindow()
    form.show()
    app.exec_()
