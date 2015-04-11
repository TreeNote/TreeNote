from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
import couchdb
import time
import sys
import subprocess
import threading
import socket

NEW_DB_ITEM = {'text': '', 'children': '', 'checked': 'None', 'date': ''}
DELIMITER = ':'
PALETTE = QPalette()
PALETTE.setColor(QPalette.Highlight, QColor('#C1E7FC'))


class Updater(QThread):
    """
    This Thread watches the db for own and foreign changes and updates the view.
    """

    def __init__(self, model):
        super(QThread, self).__init__()
        self.model = model

    def run(self):  # this updates the view
        all_changes = self.model.db.changes(descending=True)
        last_seq = all_changes['results'][0]['seq']
        changes_list = self.model.db.changes(feed='continuous', heartbeat=sys.maxsize, include_docs=True, since=last_seq)  # no need for heartbeet, because the db is local
        for line in changes_list:
            if 'doc' in line:
                print(line)
                db_item = line['doc']
                item_id = db_item['_id']
                # todo if item_id in self.model.id_index_dict:  # update the view only if the item is already loaded
                if 'change' in db_item:
                    change_dict = db_item['change']
                    my_edit = change_dict['user'] == socket.gethostname()
                    method = change_dict['method']
                    if method == 'updated':
                        self.model.updated_signal.emit(item_id, db_item, my_edit)
                    elif method == 'added':
                        self.model.added_signal.emit(item_id, change_dict['position'], change_dict['id_list'], my_edit, change_dict['set_edit_focus'])
                    elif method == 'removed':
                        self.model.removed_signal.emit(item_id, change_dict['position'], change_dict['count'], my_edit)
                    elif method == 'moved_vertical':
                        self.model.moved_vertical_signal.emit(item_id, change_dict['position'], change_dict['count'], change_dict['up_or_down'], my_edit)
                elif '_deleted' in db_item:
                    self.model.deleted_signal.emit(item_id)


class Tree_item(object):
    """
    To understand Qt's way of building a TreeView, read:
    http://trevorius.com/scrapbook/uncategorized/pyqt-custom-abstractitemmodel/
    http://doc.qt.io/qt-5/qtwidgets-itemviews-editabletreemodel-example.html
    """

    def __init__(self, text, model, parent=None):
        self.model = model
        self.parentItem = parent
        self.text = text
        self.childItems = None
        self.id = None
        self.date = ''

    def child_number(self):
        if self.parentItem is not None:
            return self.parentItem.childItems.index(self)
        return 0

    def init_childs(self, parent_index):
        if self.childItems is None:  # deserialise children from the db
            self.childItems = []
            children_id_list = self.model.db[self.id]['children'].split()
            for position in range(len(children_id_list)):
                id = children_id_list[position]
                self.add_child(position, id, parent_index)

    def add_child(self, position, id, parent_index):
        item = Tree_item('', self.model, self)
        self.childItems.insert(position, item)
        self.childItems[position].text = self.model.db[id]['text']
        self.childItems[position].date = self.model.db[id]['date']
        self.childItems[position].id = id

        new_index = self.model.index(position, 0, parent_index)
        self.model.id_index_dict[id] = QPersistentModelIndex(new_index)
        self.model.pointer_set.add(new_index.internalId())

    def remove_children(self, position, count):
        for row in range(count):
            self.childItems.pop(position)


class TreeModel(QAbstractItemModel):
    """
    The methods of this model changes the database only. The view gets updated by the Updater-Thread.
    """
    updated_signal = pyqtSignal(str, dict, bool)
    added_signal = pyqtSignal(str, int, list, bool, bool)
    removed_signal = pyqtSignal(str, int, int, bool)
    moved_vertical_signal = pyqtSignal(str, int, int, int, bool)
    deleted_signal = pyqtSignal(str)

    def __init__(self, parent=None):
        super(TreeModel, self).__init__(parent)

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
                #del server[new_db_name]
                return server, server[new_db_name]
            except couchdb.http.ResourceNotFound:
                new_db = server.create(new_db_name)
                new_db['0'] = (NEW_DB_ITEM.copy())
                print("Database does not exist. Created the database.")
                return server, new_db
            except couchdb.http.Unauthorized as err:
                print(err.message)

            except couchdb.http.ServerError as err:
                print(err.message)

        # If a database change is arriving, we just have the id. To get the corresponding Tree_item, we store it's QModelIndex in this dict:
        self.id_index_dict = dict()  # New indexes are created by TreeModel.index(). That function stores the index in this dict.
        self.pointer_set = set()

        db_name = 'tree'
        server_url = 'http://192.168.178.42:5984/'
        local_server = None
        while local_server is None:  # wait until couchdb is started
            try:
                time.sleep(0.1)
                local_server, self.db = get_create_db(db_name)
                break
            except:
                pass

        # get_create_db(db_name, server_url)
        # local_server.replicate(db_name, server_url + db_name, continuous=True)
        # local_server.replicate(server_url + db_name, db_name, continuous=True)

        self.rootItem = Tree_item('root item', self)
        self.rootItem.id = '0'
        index = QModelIndex()
        self.id_index_dict['0'] = index
        self.pointer_set.add(QModelIndex().internalId())

        self.updater = Updater(self)
        self.updater.start()

    def columnCount(self, parent):
        return 2

    def flags(self, index):
        if not index.isValid():
            return 0

        return Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def getItem(self, index):
        if index.isValid():
            item = index.internalPointer()
            if item:
                return item

        return self.rootItem

    def index(self, row, column, parent=QModelIndex()):
        if parent.isValid() and parent.column() != 0:
            return QModelIndex()

        if parent.internalId() not in self.pointer_set:
            return QModelIndex()

        parentItem = self.getItem(parent)
        childItem = parentItem.childItems[row]
        return self.createIndex(row, column, childItem)

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()

        if index.internalId() not in self.pointer_set:
            return QModelIndex()

        childItem = self.getItem(index)
        parentItem = childItem.parentItem

        if parentItem == self.rootItem:
            return QModelIndex()
        return self.createIndex(parentItem.child_number(), 0, parentItem)

    def rowCount(self, parent=QModelIndex()):
        parentItem = self.getItem(parent)
        parentItem.init_childs(parent)
        return len(parentItem.childItems)

    def data(self, index, role):
        if not index.isValid():
            return None

        if role != Qt.DisplayRole and role != Qt.EditRole:
            return None

        item = self.getItem(index)
        return item.text if index.column() == 0 else item.date

    def setData(self, index, value, role=Qt.EditRole, field='text'):
        if role != Qt.EditRole:
            return False

        item = self.getItem(index)
        db_item = self.db[item.id]
        if index.column() == 0:
            db_item[field] = value
        else:
            db_item['date'] = value.toString('dd.MM.yy')
        db_item['change'] = dict(method='updated', user=socket.gethostname())
        self.db[item.id] = db_item
        return True

    def insertRows(self, position, parent, indexes=None):
        id_list = list()
        if indexes is None:  # used from view, create a single new row / self.db item
            set_edit_focus = True
            child_id, _ = self.db.save(NEW_DB_ITEM.copy())
            id_list.append(child_id)
        else:  # used from move methods, add existing db items to the parent
            set_edit_focus = False
            for index in indexes:  # todo ginge auch über position
                id_list.append(self.getItem(index).id)
        parent_item_id = self.getItem(parent).id
        db_item = self.db[parent_item_id]
        children_list = db_item['children'].split()
        children_list_new = children_list[:position] + id_list + children_list[position:]
        db_item['children'] = ' '.join(children_list_new)
        db_item['change'] = dict(method='added', id_list=id_list, position=position, set_edit_focus=set_edit_focus, user=socket.gethostname())
        self.db[parent_item_id] = db_item
        return True

    def removeRows(self, indexes, delete=True, restore_selection=False):
        for index in indexes:
            child_item = self.getItem(index)
            child_db_item = self.db.get(child_item.id)
            if child_db_item is not None:
                self.db.delete(child_db_item)

                def delete_childs(item):
                    for ch_item in item.childItems:
                        delete_childs(ch_item)
                        ch_db_item = self.db.get(ch_item.id)
                        if ch_db_item is not None:
                            self.db.delete(ch_db_item)

                delete_childs(child_item)

                parent_item_id = child_item.parentItem.id
                parent_db_item = self.db[parent_item_id]
                children_list = parent_db_item['children'].split()
                parent_db_item['change'] = dict(method='removed', position=children_list.index(child_item.id), count=1, user=socket.gethostname())
                children_list.remove(child_item.id)
                parent_db_item['children'] = ' '.join(children_list)
                self.db[parent_item_id] = parent_db_item

    def move_vertical(self, indexes, up_or_down):
        # up_or_down is -1 for up and +1 for down
        item = self.getItem(indexes[0])
        parent_item_id = item.parentItem.id
        db_item = self.db[parent_item_id]
        children_list = db_item['children'].split()
        old_position = children_list.index(item.id)
        if up_or_down == -1 and old_position == 0 or up_or_down == +1 and old_position + len(indexes) - 1 == len(children_list) - 1:  # don't move if already at top or bottom
            return
        self.layoutAboutToBeChanged.emit()
        if up_or_down == -1:  # if we want to move several items up, we can move the item-above below the selection instead
            swapped_item = children_list.pop(old_position - 1)
            swapped_item_new_position = old_position + len(indexes) - 1
        elif up_or_down == +1:
            swapped_item = children_list.pop(old_position + len(indexes))
            swapped_item_new_position = old_position
        children_list.insert(swapped_item_new_position, swapped_item)
        db_item['children'] = ' '.join(children_list)
        db_item['change'] = dict(method='moved_vertical', position=old_position, count=len(indexes), up_or_down=up_or_down, user=socket.gethostname())
        self.db[parent_item_id] = db_item

    def move_left(self, indexes):
        item = self.getItem(indexes[0])
        parent_parent_item = item.parentItem.parentItem
        if parent_parent_item is not None:  # stop moving left if parent is root_item
            self.remove_consecutive_rows_from_parent(indexes)

            # insert as a child of the parent's parent
            parent_parent_item_index = QModelIndex(self.id_index_dict[parent_parent_item.id])
            position = item.parentItem.child_number() + 1
            self.insertRows(position, parent_parent_item_index, indexes)

    def move_right(self, indexes):
        # insert as a child of the sibling above
        item = self.getItem(indexes[0])
        childNumber = item.child_number()
        if childNumber != 0:  # stop moving right if the moving item is the top item
            self.remove_consecutive_rows_from_parent(indexes)  # we have to restore the selection of the moved item, because removeRow() discards it

            sibling_index = self.index(childNumber - 1, 0, self.parent(indexes[0]))
            last_childnr_of_sibling = len(item.parentItem.childItems[childNumber - 1].childItems)
            self.insertRows(last_childnr_of_sibling, sibling_index, indexes)

    def remove_consecutive_rows_from_parent(self, indexes):  # just for moving
        child_item = self.getItem(indexes[0])
        parent_item_id = child_item.parentItem.id
        parent_db_item = self.db[parent_item_id]
        children_list = parent_db_item['children'].split()
        position = children_list.index(child_item.id)
        parent_db_item['change'] = dict(method='removed', position=position, count=len(indexes), user=socket.gethostname())
        children_list[position:position + len(indexes)] = []
        parent_db_item['children'] = ' '.join(children_list)
        self.db[parent_item_id] = parent_db_item

    def get_tags_set(self, cut_delimiter=True):
        tags_set = set()
        map = "function(doc) { \
                    if (doc.text && doc.text.indexOf('" + DELIMITER + "') != -1) \
                        emit(doc, null); \
                }"
        res = self.db.query(map)
        for row in res:
            word_list = row.key['text'].split()
            for word in word_list:
                if word[0] == DELIMITER:
                    delimiter = '' if cut_delimiter else DELIMITER
                    tags_set.add(delimiter + word.strip(DELIMITER))
        return tags_set


class FilterProxyModel(QSortFilterProxyModel):
    # many of the default implementations of functions in QSortFilterProxyModel are written so that they call the equivalent functions in the relevant source model.
    # This simple proxying mechanism may need to be overridden for source models with more complex behavior; for example, if the source model provides a custom hasChildren() implementation, you should also provide one in the proxy model.
    # The QSortFilterProxyModel acts as a wrapper for the original model. If you need to convert source QModelIndexes to sorted/filtered model indexes or vice versa, use mapToSource(), mapFromSource(), mapSelectionToSource(), and mapSelectionFromSource().
    def filterAcceptsRow(self, row, parent):
        index = self.sourceModel().index(row, 0, parent)
        if not index.isValid():
            return False

        if self.filter in index.data():
            return True

        for row in range(self.sourceModel().rowCount(index)):
            if self.filterAcceptsRow(row, index):
                return True;

        return False

    def map_indexes_to_source(self, indexes):
        indexes_source = []
        for index in indexes:
            indexes_source.append(self.mapToSource(index))
        return indexes_source

    def move_right(self, indexes):
        if len(indexes) > 0:
            self.sourceModel().move_right(self.map_indexes_to_source(indexes))

    def move_left(self, indexes):
        if len(indexes) > 0:
            self.sourceModel().move_left(self.map_indexes_to_source(indexes))

    def move_vertical(self, indexes, up_or_down):
        if len(indexes) > 0:
            self.sourceModel().move_vertical(self.map_indexes_to_source(indexes), up_or_down)

    def insertRow(self, position, parent):
        self.sourceModel().insertRows(position, self.mapToSource(parent))

    def removeRows(self, indexes):
        self.sourceModel().removeRows(self.map_indexes_to_source(indexes))

    def getItem(self, index):
        return self.sourceModel().getItem(self.mapToSource(index))

    def setData(self, index, value, role=Qt.EditRole, field='text'):
        return self.sourceModel().setData(self.mapToSource(index), value, role=role, field=field)

    def toggle_task(self, index_proxy):
        index = self.mapToSource(index_proxy)
        db_item = self.sourceModel().db[self.sourceModel().getItem(index).id]
        checked = db_item['checked']
        if checked == 'None':
            self.sourceModel().setData(index, 'False', field='checked')
        elif checked == 'False':
            self.sourceModel().setData(index, 'True', field='checked')
        elif checked == 'True':
            self.sourceModel().setData(index, 'None', field='checked')


class Delegate(QStyledItemDelegate):
    def __init__(self, parent, model):
        super(Delegate, self).__init__(parent)
        self.model = model

    def paint(self, painter, option, index):
        db_item = self.model.sourceModel().db[self.model.getItem(index).id]
        checked = db_item['checked']

        word_list = index.data().split()
        for idx, word in enumerate(word_list):
            if word[0] == DELIMITER:
                word_list[idx] = "<b><font color={}>{}</font></b>".format(QColor(Qt.darkMagenta).name(), word)
        document = QTextDocument()
        document.setHtml(' '.join(word_list))
        if option.state & QStyle.State_Selected:
            color = PALETTE.highlight().color()
        else:
            db_item = self.model.sourceModel().db[self.model.getItem(index).id]
            if 'color' in db_item:
                color = QColor(db_item['color'])
            else:
                color = QColor(Qt.white)
        painter.save()
        painter.fillRect(option.rect, color)
        gap_for_checkbox = 17 if checked != 'None' else 0
        painter.translate(option.rect.x() + gap_for_checkbox - 2, option.rect.y() - 3)  # -3: put the text in the middle of the line
        document.drawContents(painter)
        painter.restore()

        if checked != 'None':
            check_box_style_option = QStyleOptionButton()
            if checked == 'True':
                check_box_style_option.state |= QStyle.State_On
            else:
                check_box_style_option.state |= QStyle.State_Off
            check_box_style_option.rect = self.getCheckBoxRect(option)
            check_box_style_option.state |= QStyle.State_Enabled
            QApplication.style().drawControl(QStyle.CE_CheckBox, check_box_style_option, painter)

    def getCheckBoxRect(self, option):  # source: http://stackoverflow.com/questions/17748546/pyqt-column-of-checkboxes-in-a-qtableview
        check_box_style_option = QStyleOptionButton()
        check_box_rect = QApplication.style().subElementRect(QStyle.SE_CheckBoxIndicator, check_box_style_option, None)
        check_box_point = QPoint(option.rect.x(), option.rect.y())
        return QRect(check_box_point, check_box_rect.size())

    def editorEvent(self, event, model, option, index):
        '''
        Change the data in the model and the state of the checkbox
        if the user presses the left mousebutton or Key_Space
        '''
        if event.type() == QEvent.MouseButtonPress:
            return False
        if event.type() == QEvent.MouseButtonRelease or event.type() == QEvent.MouseButtonDblClick:
            if event.button() != Qt.LeftButton or not self.getCheckBoxRect(option).contains(event.pos()):
                return False
            if event.type() == QEvent.MouseButtonDblClick:
                return True
        elif event.type() == QEvent.KeyPress:
            if event.key() != Qt.Key_Space and event.key() != Qt.Key_Select:
                return False

        model.toggle_task(index)
        return True

    def createEditor(self, parent, option, index):
        if index.column() == 0:
            suggestions_model = self.model.sourceModel().get_tags_set(cut_delimiter=False)
            return AutoCompleteEdit(parent, list(suggestions_model))
        else:
            date_edit = OpenPopupDateEdit(parent, self)
            date = QDate.currentDate() if index.data() == '' else QDate.fromString(index.data(), 'dd.MM.yy')
            date_edit.setDate(date)
            date_edit.setCalendarPopup(True)
            return date_edit

    def setEditorData(self, editor, index):
        QStyledItemDelegate.setEditorData(self, editor, index)

    def setModelData(self, editor, model, index):
        QStyledItemDelegate.setModelData(self, editor, model, index)


class OpenPopupDateEdit(QDateEdit):
    def __init__(self, parent, delegate):
        super(OpenPopupDateEdit, self).__init__(parent)
        self.delegate = delegate

    def focusInEvent(self, event):  # open popup on focus. source: http://forum.qt.io/topic/26821/solved-activating-calender-popup-on-focus-in-event
        self.calendarWidget().activated.connect(self.commit)
        opt = QStyleOptionSpinBox()
        self.initStyleOption(opt)
        rect = self.style().subControlRect(QStyle.CC_SpinBox, opt, QStyle.SC_SpinBoxDown)
        e = QMouseEvent(QEvent.MouseButtonPress, rect.center(), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        QApplication.sendEvent(self, e)

    def commit(self):
        self.delegate.commitData.emit(self)
        self.delegate.closeEditor.emit(self, QAbstractItemDelegate.NoHint)


class AutoCompleteEdit(QLineEdit):  # source: http://blog.elentok.com/2011/08/autocomplete-textbox-for-multiple.html
    def __init__(self, parent, model, separator=' '):
        super(AutoCompleteEdit, self).__init__(parent)
        self._separator = separator
        self._completer = QCompleter(model)
        self._completer.setFilterMode(Qt.MatchContains)
        self._completer.setWidget(self)
        self._completer.activated[str].connect(self._insertCompletion)
        self._keysToIgnore = [Qt.Key_Enter,
                              Qt.Key_Return,
                              Qt.Key_Escape,
                              Qt.Key_Tab]

    def _insertCompletion(self, completion):
        """
        This is the event handler for the QCompleter.activated(QString) signal,
        it is called when the user selects an item in the completer popup.
        """
        old_text_minus_new_word = self.text()[:-len(self._completer.completionPrefix())]
        self.setText(old_text_minus_new_word + completion + ' ')

    def textUnderCursor(self):
        text = self.text()
        textUnderCursor = ''
        i = self.cursorPosition() - 1
        while i >= 0 and text[i] != self._separator:
            textUnderCursor = text[i] + textUnderCursor
            i -= 1
        return textUnderCursor

    def keyPressEvent(self, event):
        if self._completer.popup().isVisible():
            if event.key() in self._keysToIgnore:
                event.ignore()
                return
        super(AutoCompleteEdit, self).keyPressEvent(event)
        completionPrefix = self.textUnderCursor()
        if len(completionPrefix) == 0:
            self._completer.popup().hide()
            return
        if completionPrefix[0] == DELIMITER:
            if completionPrefix != self._completer.completionPrefix():
                self._updateCompleterPopupItems(completionPrefix)
            if len(event.text()) > 0 and len(completionPrefix) > 0:
                self._completer.complete()


    def _updateCompleterPopupItems(self, completionPrefix):
        """
        Filters the completer's popup items to only show items
        with the given prefix.
        """
        self._completer.setCompletionPrefix(completionPrefix)
        self._completer.popup().setCurrentIndex(
            self._completer.completionModel().index(0, 0))