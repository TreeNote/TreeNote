from PyQt5 import QtWidgets
import sys
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import qrc_resources
import model
import subprocess


class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()

        self.model = model.TreeModel()
        self.model.updated_signal[str, str, bool].connect(self.updated)
        self.model.added_signal[str, int, list, bool, bool].connect(self.added)
        self.model.removed_signal[str, int, int, bool].connect(self.removed)
        self.model.moved_vertical_signal[str, int, int, int, bool].connect(self.moved_vertical)

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
        add_action('insertRowAction', QAction(QIcon(':/filenew.png'), self.tr('&Insert row'), self, shortcut='Return', triggered=self.insert_row))
        add_action('insertChildAction', QAction(QIcon(':/filenew.png'), self.tr('&Insert child'), self, shortcut='Shift+Return', triggered=self.insert_child))
        add_action('moveUpAction', QAction(QIcon(':/filenew.png'), self.tr('&Up'), self, shortcut='W', triggered=self.move_up))
        add_action('moveDownAction', QAction(QIcon(':/filenew.png'), self.tr('&Down'), self, shortcut='S', triggered=self.move_down))
        add_action('moveLeftAction', QAction(QIcon(':/filenew.png'), self.tr('&Left'), self, shortcut='A', triggered=self.move_left))
        add_action('moveRightAction', QAction(QIcon(':/filenew.png'), self.tr('&Right'), self, shortcut='D', triggered=self.move_right))
        add_action('expandAllChildrenAction', QAction(QIcon(':/filenew.png'), self.tr('&Expand all children'), self, shortcut='Shift+Right', triggered=self.expand_all_children))
        add_action('collapseAllChildrenAction', QAction(QIcon(':/filenew.png'), self.tr('&Collapse all children'), self, shortcut='Shift+Left', triggered=self.collapse_all_children))
        add_action('focusSearchBarAction', QAction(QIcon(':/filenew.png'), self.tr('&Focus search bar'), self, shortcut='Ctrl+F', triggered=self.focus_search_bar))
        add_action('escapeAction', QAction(QIcon(':/filenew.png'), self.tr('&Escape'), self, shortcut='Esc', triggered=self.escape))

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
        self.viewMenu.addAction(self.focusSearchBarAction)

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
        self.grid_holder().view.setFocus();
        self.updateActions()

        settings = QSettings()
        self.resize(settings.value('size', QSize(400, 400)))
        self.move(settings.value('pos', QPoint(200, 200)))

    def grid_holder(self):  # returns focused grid_holder
        for i in range(0, self.mainSplitter.count()):
            if self.mainSplitter.widget(i).hasFocus():
                return self.mainSplitter.widget(i)
        return self.mainSplitter.widget(0)

    def closeEvent(self, event):
        settings = QSettings()
        settings.setValue('pos', self.pos())
        settings.setValue('size', self.size())
        self.model.updater.terminate()
        if sys.platform == "darwin":
            subprocess.call(['osascript', '-e', 'tell application "Apache CouchDB" to quit'])

        print(len(self.model.internal_id_set)) # for debugging: is the len == #rows + root?

    def evoke_singlekey_action(self, action_name):  # fix shortcuts for mac
        for action in self.actions:
            if action.text() == action_name and action.isEnabled():
                action.trigger()
                break

    def updateActions(self):
        pass  # todo embed split action

    def updated(self, item_id, new_text, my_edit):
        index = QModelIndex(self.model.id_index_dict[item_id])
        self.model.getItem(index).text = new_text
        if my_edit:
            self.update_selection(index, index)

    def added(self, item_id, position, id_list, my_edit, set_edit_focus):
        index = QModelIndex(self.model.id_index_dict[item_id])
        parentItem = self.model.getItem(index)
        self.model.beginInsertRows(index, position, position + len(id_list) - 1)
        for i, added_item_id in enumerate(id_list):
            parentItem.add_child(position + i, self.model.db[added_item_id]['text'], added_item_id)
            new_index = self.model.index(position + i, 0, index)
            self.model.id_index_dict[added_item_id] = QPersistentModelIndex(new_index)
            self.model.internal_id_set.add(new_index.internalId())
        self.model.endInsertRows()
        if my_edit:
            index_first_added = self.model.index(position, 0, index)
            index_last_added = self.model.index(position + len(id_list) - 1, 0, index)
            if set_edit_focus:
                self.update_selection_and_edit(index_first_added)
            else:
                self.update_selection(index_first_added, index_last_added)

    def removed(self, item_id, position, count, my_edit):
        index = QModelIndex(self.model.id_index_dict[item_id])
        self.model.internal_id_set.remove(self.model.index(position, 0, index).internalId())

        item = self.model.getItem(index)
        self.model.beginRemoveRows(index, position, position + count - 1)
        item.childItems[position:position + count] = []
        self.model.endRemoveRows()
        if my_edit:
            # select the item below
            if position == len(item.childItems):  # there is no item below, so select the one above
                position -= 1
            if len(item.childItems) > 0:
                index_next_child = self.model.index(position, 0, index)
                self.update_selection(index_next_child, index_next_child)
            else:  # all childs deleted, select parent
                self.update_selection(index, index)

    def moved_vertical(self, item_id, position, count, up_or_down, my_edit):
        index = QModelIndex(self.model.id_index_dict[item_id])

        item = self.model.getItem(index)
        if up_or_down == -1:
            # if we want to move several items up, we can move the item-above below the selection instead:
            item.childItems.insert(position + count - 1, item.childItems.pop(position - 1))
        elif up_or_down == +1:
            item.childItems.insert(position, item.childItems.pop(position + count))
        for i in range(count):
            index_moved_item = self.model.index(position + up_or_down + i, 0, index)  # calling index() refreshes the self.tree_model.id_index_dict of that item
            if i == 0:
                index_first_moved_item = index_moved_item
        self.grid_holder().proxy.layoutChanged.emit()
        if my_edit:
            self.update_selection(index_first_moved_item, index_moved_item)

    def update_selection(self, index_from, index_to):
        self.grid_holder().view.selectionModel().setCurrentIndex(self.grid_holder().proxy.mapFromSource(index_from), QItemSelectionModel.ClearAndSelect)  # todo not always correct index when moving
        selection = self.grid_holder().proxy.mapSelectionFromSource(QItemSelection(index_from, index_to))
        self.grid_holder().view.selectionModel().select(selection, QItemSelectionModel.ClearAndSelect)

    def update_selection_and_edit(self, index):
        proxy_index = self.grid_holder().proxy.mapFromSource(index)
        self.grid_holder().view.selectionModel().setCurrentIndex(proxy_index, QItemSelectionModel.ClearAndSelect)
        self.grid_holder().view.edit(proxy_index)

    def escape(self):
        self.grid_holder().search_bar.setText('')

    def search(self, str):
        # if search lags: increase keyboardInputInterval
        self.grid_holder().proxy.filter = str
        self.grid_holder().proxy.invalidateFilter()

    def expand_node(self, parent_index, bool_expand):
        self.grid_holder().view.setExpanded(parent_index, bool_expand)
        for row_num in range(self.grid_holder().proxy.rowCount(parent_index)):
            child_index = self.grid_holder().proxy.index(row_num, 0, parent_index)
            self.grid_holder().view.setExpanded(parent_index, bool_expand)
            self.expand_node(child_index, bool_expand)

    # structure menu actions

    def expand_all_children(self):
        self.expand_node(self.grid_holder().view.selectionModel().currentIndex(), True)

    def collapse_all_children(self):
        self.expand_node(self.grid_holder().view.selectionModel().currentIndex(), False)

    def move_up(self):
        indexes = self.grid_holder().view.selectionModel().selectedIndexes()
        self.grid_holder().proxy.move_vertical(indexes, -1)

    def move_down(self):
        indexes = self.grid_holder().view.selectionModel().selectedIndexes()
        self.grid_holder().proxy.move_vertical(indexes, +1)

    def move_left(self):
        self.grid_holder().proxy.move_left(self.grid_holder().view.selectionModel().selectedIndexes())

    def move_right(self):
        self.grid_holder().proxy.move_right(self.grid_holder().view.selectionModel().selectedIndexes())

    def editRow(self):
        if self.grid_holder().view.hasFocus():
            self.grid_holder().view.edit(self.grid_holder().view.selectionModel().currentIndex())
        elif self.grid_holder().view.state() == QAbstractItemView.EditingState:
            pass
        else:
            self.focusNextChild()

    def insert_child(self):
        index = self.grid_holder().view.selectionModel().currentIndex()
        if self.grid_holder().view.state() == QAbstractItemView.EditingState:
            # commit data by changing the current selection
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
        self.grid_holder().proxy.removeRows(self.grid_holder().view.selectionModel().selectedIndexes())

    # view menu actions

    def focus_search_bar(self):
        self.grid_holder().search_bar.setFocus()

    def split_window(self):  # creates the view, too
        grid_holder = QWidget()

        grid_holder.search_bar = QLineEdit()
        grid_holder.search_bar.textChanged[str].connect(self.search)

        grid_holder.view = QTreeView()
        grid_holder.view.header().hide()
        grid_holder.view.setSelectionMode(QAbstractItemView.ExtendedSelection)

        grid_holder.proxy = model.FilterProxyModel()
        grid_holder.proxy.setSourceModel(self.model)
        grid_holder.proxy.setDynamicSortFilter(True)  # re-sort and re-filter data whenever the original model changes
        grid_holder.proxy.filter = ''
        grid_holder.view.setModel(grid_holder.proxy)
        grid_holder.view.selectionModel().selectionChanged.connect(self.updateActions)

        grid = QGridLayout()
        grid.addWidget(grid_holder.search_bar, 0, 0)
        grid.addWidget(grid_holder.view, 1, 0)
        grid_holder.setLayout(grid)
        self.mainSplitter.addWidget(grid_holder)
        self.unsplitWindowAct.setEnabled(True)


    def unsplit_window(self):
        index_last_widget = self.mainSplitter.count() - 1
        self.mainSplitter.widget(index_last_widget).setParent(None)
        if self.mainSplitter.count() == 1:
            self.unsplitWindowAct.setEnabled(False)

    # help menu actions

    def about(self):
        QMessageBox.about(self, self.tr('About'), self.tr('teeeext'))

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setApplicationName(QApplication.translate('main', 'TreeNote'))
    app.setWindowIcon(QIcon(':/icon.png'))
    form = MainWindow()
    form.show()
    app.exec_()
