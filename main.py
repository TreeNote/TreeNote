from PyQt5 import QtWidgets
import sys
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import qrc_resources
import model
import tag_model
import subprocess
import socket


class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()

        self.model = model.TreeModel()
        self.model.updated_signal[str, dict, bool].connect(self.updated)
        self.model.added_signal[str, int, list, bool, bool].connect(self.added)
        self.model.removed_signal[str, int, int, bool].connect(self.removed)
        self.model.moved_vertical_signal[str, int, int, int, bool].connect(self.moved_vertical)
        self.model.deleted_signal[str].connect(self.deleted)

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
        add_action('colorGreenAction', QAction(QIcon(':/filenew.png'), self.tr('&Green'), self, shortcut='G', triggered=lambda: self.color_row(QColor(Qt.green).name())))
        add_action('colorYellowAction', QAction(QIcon(':/filenew.png'), self.tr('&Yellow'), self, shortcut='Y', triggered=lambda: self.color_row(QColor(Qt.yellow).name())))
        add_action('colorBlueAction', QAction(QIcon(':/filenew.png'), self.tr('&Blue'), self, shortcut='B', triggered=lambda: self.color_row(QColor(Qt.blue).name())))
        add_action('colorRedAction', QAction(QIcon(':/filenew.png'), self.tr('&Red'), self, shortcut='R', triggered=lambda: self.color_row(QColor(Qt.red).name())))
        add_action('colorOrangeAction', QAction(QIcon(':/filenew.png'), self.tr('&Orange'), self, shortcut='O', triggered=lambda: self.color_row(QColor("darkorange").name())))
        add_action('colorNoColorAction', QAction(QIcon(':/filenew.png'), self.tr('&No color'), self, shortcut='N', triggered=lambda: self.color_row(QColor(Qt.white).name())))
        add_action('priority1Action', QAction(QIcon(':/filenew.png'), self.tr('&Priority 1'), self, shortcut='1', triggered=lambda: self.set_priority(1)))
        add_action('toggleTaskAction', QAction(QIcon(':/filenew.png'), self.tr('&Toggle: No task, Unchecked, Checked'), self, shortcut='Space', triggered=self.toggle_task))

        self.structureMenu = self.menuBar().addMenu(self.tr('&Edit structure'))
        self.structureMenu.addAction(self.insertRowAction)
        self.structureMenu.addAction(self.insertChildAction)
        self.structureMenu.addAction(self.deleteSelectedRowsAction)

        self.moveMenu = self.structureMenu.addMenu(self.tr('&Move task'))
        self.moveMenu.addAction(self.moveUpAction)
        self.moveMenu.addAction(self.moveDownAction)
        self.moveMenu.addAction(self.moveLeftAction)
        self.moveMenu.addAction(self.moveRightAction)

        self.taskMenu = self.menuBar().addMenu(self.tr('&Edit Task'))
        self.taskMenu.addAction(self.editRowAction)
        self.taskMenu.addAction(self.toggleTaskAction)
        self.colorMenu = self.taskMenu.addMenu(self.tr('&Color task'))
        self.colorMenu.addAction(self.colorGreenAction)
        self.colorMenu.addAction(self.colorYellowAction)
        self.colorMenu.addAction(self.colorBlueAction)
        self.colorMenu.addAction(self.colorRedAction)
        self.colorMenu.addAction(self.colorOrangeAction)
        self.colorMenu.addAction(self.colorNoColorAction)
        self.priorityMenu = self.taskMenu.addMenu(self.tr('&Set priority'))
        self.priorityMenu.addAction(self.priority1Action)

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
        self.grid_holder().view.setFocus()
        self.updateActions()

        self.grid_holder().tag_view.model().modelReset.connect(self.select_tag)
        self.point = None

        settings = QSettings()
        self.resize(settings.value('size', QSize(400, 400)))
        self.move(settings.value('pos', QPoint(200, 200)))

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

    def open_rename_tag_menu(self, point):
        menu = QMenu()
        renameTagAction = menu.addAction(self.tr("Rename tag"))
        action = menu.exec_(self.grid_holder().tag_view.viewport().mapToGlobal(point))
        if action == renameTagAction:
            tag = self.grid_holder().tag_view.indexAt(point).data()
            RenameDialog(self, tag, point).exec_()

    def rename_tag(self, tag, point, new_name):
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
        self.point = point  # model reset deletes selection, so restore selection

    def select_tag(self):
        if self.point is not None:
            index_new = self.grid_holder().tag_view.indexAt(self.point)
            self.grid_holder().tag_view.selectionModel().select(index_new, QItemSelectionModel.ClearAndSelect)
            self.point = None

    def tag_clicked(self):
        current_index = self.grid_holder().tag_view.selectionModel().currentIndex()
        current_tag = self.grid_holder().tag_view.model().data(current_index, tag_model.FULL_PATH)
        if current_tag is not None:
            self.grid_holder().search_bar.setText(current_tag)

    def updated(self, item_id, new_item_dict, my_edit):
        index = QModelIndex(self.model.id_index_dict[item_id])
        self.model.getItem(index).text = new_item_dict['text']
        self.model.getItem(index).date = new_item_dict['date']
        if my_edit:
            self.set_selection(index, index)
        self.setup_tag_model()
        self.model.dataChanged.emit(index, index)

    def added(self, item_id, position, id_list, my_edit, set_edit_focus):
        index = QModelIndex(self.model.id_index_dict[item_id])
        parentItem = self.model.getItem(index)
        self.model.beginInsertRows(index, position, position + len(id_list) - 1)
        for i, added_item_id in enumerate(id_list):
            parentItem.add_child(position + i, added_item_id, index)
        self.model.endInsertRows()
        if my_edit:
            index_first_added = self.model.index(position, 0, index)
            index_last_added = self.model.index(position + len(id_list) - 1, 0, index)
            if set_edit_focus:
                self.update_selection_and_edit(index_first_added)
            else:
                self.set_selection(index_first_added, index_last_added)

    def deleted(self, item_id):
        index = QModelIndex(self.model.id_index_dict[item_id])
        self.model.pointer_set.remove(index.internalId())
        self.setup_tag_model()

    def removed(self, item_id, position, count, my_edit):
        index = QModelIndex(self.model.id_index_dict[item_id])

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
                self.set_selection(index_next_child, index_next_child)
            else:  # all childs deleted, select parent
                self.set_selection(index, index)

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
            self.set_selection(index_first_moved_item, index_moved_item)

    def set_selection(self, index_from, index_to):
        if self.grid_holder().view.state() != QAbstractItemView.EditingState:
            if isinstance(index_from.model(), model.TreeModel):
                index_to = self.grid_holder().proxy.mapFromSource(index_to)
                index_from = self.grid_holder().proxy.mapFromSource(index_from)
            index_from = index_from.sibling(index_from.row(), 0)
            index_to = index_to.sibling(index_to.row(), 1)
            self.grid_holder().view.setFocus()
            self.grid_holder().view.selectionModel().setCurrentIndex(index_from, QItemSelectionModel.ClearAndSelect)  # todo not always correct index when moving
            self.grid_holder().view.selectionModel().select(QItemSelection(index_from, index_to), QItemSelectionModel.ClearAndSelect)

    def update_selection_and_edit(self, index):
        proxy_index = self.grid_holder().proxy.mapFromSource(index)
        self.grid_holder().view.selectionModel().setCurrentIndex(proxy_index, QItemSelectionModel.ClearAndSelect)
        self.grid_holder().view.edit(proxy_index)

    def escape(self):
        self.grid_holder().search_bar.setText('')
        self.grid_holder().view.setFocus()

    def search(self, str):
        # if search lags: increase keyboardInputInterval
        self.grid_holder().proxy.filter = str
        self.grid_holder().proxy.invalidateFilter()
        if str != self.grid_holder().tag_view.selectionModel().currentIndex().data():
            self.grid_holder().tag_view.selectionModel().setCurrentIndex(QModelIndex(), QItemSelectionModel.Clear)

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
        indexes = self.grid_holder().view.selectionModel().selectedRows()
        self.grid_holder().proxy.move_vertical(indexes, -1)

    def move_down(self):
        indexes = self.grid_holder().view.selectionModel().selectedRows()
        self.grid_holder().proxy.move_vertical(indexes, +1)

    def move_left(self):
        self.grid_holder().proxy.move_left(self.grid_holder().view.selectionModel().selectedRows())

    def move_right(self):
        self.grid_holder().proxy.move_right(self.grid_holder().view.selectionModel().selectedRows())

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
        self.grid_holder().proxy.removeRows(self.grid_holder().view.selectionModel().selectedRows())

    # task menu actions

    def editRow(self):
        current_index = self.grid_holder().view.selectionModel().currentIndex()
        if self.grid_holder().view.state() == QAbstractItemView.EditingState:  # change column with tab key
            swapped_column_number = 1 if current_index.column() == 0 else 0
            sibling_index = current_index.sibling(current_index.row(), swapped_column_number)
            self.grid_holder().view.selectionModel().setCurrentIndex(sibling_index, QItemSelectionModel.ClearAndSelect)
            self.grid_holder().view.edit(sibling_index)
        elif self.grid_holder().view.hasFocus():
            self.grid_holder().view.edit(current_index)
        else:
            self.grid_holder().view.setFocus()

    def toggle_task(self):
        if self.grid_holder().view.hasFocus():
            self.grid_holder().proxy.toggle_task(self.grid_holder().view.selectionModel().currentIndex())

    def color_row(self, color):
        if self.grid_holder().view.hasFocus():
            self.grid_holder().proxy.setData(self.grid_holder().view.selectionModel().currentIndex(), color, field='color')

    def set_priority(self, number):
        if self.grid_holder().view.hasFocus():
            self.grid_holder().proxy.setData(self.grid_holder().view.selectionModel().currentIndex(), number, field='priority')

    # view menu actions

    def focus_search_bar(self):
        self.grid_holder().search_bar.setFocus()

    def split_window(self):  # creates the view, too
        grid_holder = QWidget()

        grid_holder.search_bar = MyQLineEdit(self)
        grid_holder.search_bar.textChanged[str].connect(self.search)

        grid_holder.view = QTreeView()
        grid_holder.view.setPalette(model.PALETTE)
        size_policy_view = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        size_policy_view.setHorizontalStretch(2)  # 2/3
        grid_holder.view.setSizePolicy(size_policy_view)

        grid_holder.view.header().hide()
        grid_holder.view.setSelectionMode(QAbstractItemView.ExtendedSelection)

        grid_holder.proxy = model.FilterProxyModel()
        grid_holder.proxy.setSourceModel(self.model)
        grid_holder.proxy.setDynamicSortFilter(True)  # re-sort and re-filter data whenever the original model changes
        grid_holder.proxy.filter = ''
        grid_holder.view.setModel(grid_holder.proxy)
        grid_holder.view.setItemDelegate(model.Delegate(self, grid_holder.proxy))
        grid_holder.view.selectionModel().selectionChanged.connect(self.updateActions)
        grid_holder.view.setColumnWidth(0, 300)  # todo update ratio when window size changes
        grid_holder.view.setColumnWidth(1, 100)

        grid_holder.tag_view = QTreeView()
        grid_holder.tag_view.setContextMenuPolicy(Qt.CustomContextMenu)
        grid_holder.tag_view.customContextMenuRequested.connect(self.open_rename_tag_menu)
        size_policy_tag_view = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        size_policy_tag_view.setHorizontalStretch(1)  # 1/3
        grid_holder.tag_view.setSizePolicy(size_policy_tag_view)
        grid_holder.tag_view.header().hide()
        grid_holder.tag_view.setModel(tag_model.TagModel())
        grid_holder.tag_view.selectionModel().selectionChanged.connect(self.tag_clicked)

        grid = QGridLayout()
        grid.addWidget(grid_holder.search_bar, 0, 0, 1, 0)  # fill entire first cell
        grid.addWidget(grid_holder.view, 1, 0)
        grid.addWidget(grid_holder.tag_view, 1, 1)
        grid_holder.setLayout(grid)
        self.mainSplitter.addWidget(grid_holder)
        self.setup_tag_model()
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

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Down:
            index = self.main.grid_holder().proxy.index(0, 0, QModelIndex())
            self.main.set_selection(index, index)
            self.main.focusNextChild()
        else:
            QLineEdit.keyPressEvent(self, event)


class RenameDialog(QDialog):
    def __init__(self, parent, tag, point):
        super(RenameDialog, self).__init__(parent)
        self.parent = parent
        self.tag = tag
        self.point = point
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
        self.parent.rename_tag(self.tag, self.point, self.line_edit.text())
        super(RenameDialog, self).accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setApplicationName(QApplication.translate('main', 'TreeNote'))
    app.setWindowIcon(QIcon(':/icon.png'))
    app.setStyleSheet(
        "QTreeView::branch:closed:has-children {\
            image: url(:/branch-closed);\
        }\
        QTreeView::branch:open:has-children {\
            image: url(:/branch-open);\
        }")
    form = MainWindow()
    form.show()
    app.exec_()