from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
import couchdb
import time
import sys
import subprocess
import threading
import socket
import re

NEW_DB_ITEM = {'text': '', 'children': '', 'checked': 'None', 'date': '', 'color': QColor(Qt.white).name(), 'deleted_date': '', 'estimate': ''}
DELIMITER = ':'
PALETTE = QPalette()
PALETTE.setColor(QPalette.Highlight, QColor('#C1E7FC'))
CHAR_QCOLOR_DICT = {
    'g': QColor(Qt.green).name(),
    'y': QColor(Qt.yellow).name(),
    'b': QColor(Qt.blue).name(),
    'r': QColor(Qt.red).name(),
    'o': QColor("darkorange").name(),
    'n': QColor(Qt.white).name()
}
CHAR_CHECKED_DICT = {
    'd': 'True',  # done task
    't': 'False',  # task
    'n': 'None'  # note
}
EMPTY_DATE = '14.09.52'


class QUndoCommandStructure(QUndoCommand):
    # this class is just for making the initialization of QUndoCommand easier. Source: http://chimera.labs.oreilly.com/books/1230000000393/ch08.html#_solution_129
    _fields = []  # Class variable that specifies expected fields

    def __init__(self, *args):
        if len(args) != len(self._fields):
            raise TypeError('Expected {} arguments'.format(len(self._fields)))

        # Set the arguments
        for name, value in zip(self._fields, args):
            setattr(self, name, value)

        super(QUndoCommandStructure, self).__init__(QApplication.translate('command', self.title))


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
                # todo if item_id in self.model.id_index_dict:  # update the view only if the item is already loaded
                if 'change' in db_item:
                    self.model.db_change_signal.emit(db_item)
                elif '_deleted' in db_item:
                    self.model.deleted_signal.emit(db_item['_id'])


class Tree_item(object):
    """
    This item holds all id, parent, childs, text, estimate and date attributes. Other attributes like color are in the db only.
    Attributes saved here are accessed faster than through the db.

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
        self.estimate = ''

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
        self.childItems[position].estimate = self.model.db[id]['estimate']
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
    db_change_signal = pyqtSignal(dict)

    def __init__(self, parent=None):
        super(TreeModel, self).__init__(parent)

        self.undoStack = QUndoStack(self)

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
        self.rootItem.header_list = ['Text', 'Start date', 'Estimate']
        self.rootItem.id = '0'
        index = QModelIndex()
        self.id_index_dict['0'] = index
        self.pointer_set.add(QModelIndex().internalId())

        self.updater = Updater(self)
        self.updater.start()

    def headerData(self, column, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.rootItem.header_list[column]

        return None

    def columnCount(self, parent=None):
        return 3

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
        if index.column() == 0:
            return item.text
        elif index.column() == 1:
            return item.date
        else:  # index.column() == 2:
            return item.estimate

    def setData(self, index, value, role=None, field='text'):

        class SetDataCommand(QUndoCommandStructure):
            _fields = ['model', 'item_id', 'value', 'column', 'field']
            title = 'Edit row'

            def set_data(self, value):
                db_item = self.model.db[self.item_id]
                if self.column == 0:  # used for setting color etc, too
                    self.old_value = db_item[self.field]
                    db_item[self.field] = value
                elif self.column == 1:
                    self.old_value = db_item['date']
                    value = value.toString('dd.MM.yy') if type(value) == QDate else value
                    if value == EMPTY_DATE:  # workaround to set empty date
                        value = ''
                    db_item['date'] = value
                elif self.column == 2:
                    self.old_value = db_item['estimate']
                    db_item['estimate'] = value
                db_item['change'] = dict(method='updated', user=socket.gethostname())
                self.model.db[self.item_id] = db_item

            def redo(self):
                self.set_data(self.value)

            def undo(self):
                self.set_data(self.old_value)

        item_id = self.getItem(index).id
        self.undoStack.push(SetDataCommand(self, item_id, value, index.column(), field))
        return True

    def insert_remove_rows(self, position=None, parent_item_id=None, id_list=None, indexes=None):

        class InsertRemoveRowCommand(QUndoCommandStructure):
            _fields = ['model', 'position', 'parent_item_id', 'id_list', 'set_edit_focus', 'delete_child_from_parent_id_list']
            title = 'Add or remove row'

            @staticmethod  # because it is called from the outside for moving
            def add_rows(model, position, parent_item_id, id_list, set_edit_focus):
                db_item = model.db[parent_item_id]
                children_list = db_item['children'].split()
                children_list_new = children_list[:position] + id_list + children_list[position:]
                db_item['children'] = ' '.join(children_list_new)
                db_item['change'] = dict(method='added', id_list=id_list, position=position, set_edit_focus=set_edit_focus, user=socket.gethostname())
                model.db[parent_item_id] = db_item

            def remove_rows(self):
                for child_item_id, parent_item_id, _ in self.delete_child_from_parent_id_list:
                    parent_db_item = self.model.db[parent_item_id]
                    children_list = parent_db_item['children'].split()
                    parent_db_item['change'] = dict(method='removed', position=children_list.index(child_item_id), count=1, user=socket.gethostname())
                    children_list.remove(child_item_id)
                    parent_db_item['children'] = ' '.join(children_list)
                    self.model.db[parent_item_id] = parent_db_item

                    child_db_item = self.model.db[child_item.id]
                    # todo: set deleted flag for child_db_item
                    child_db_item['deleted_date'] = 'todo'
                    self.model.db[child_db_item] = child_db_item

                    def delete_childs(item):
                        for ch_item in item.childItems:
                            delete_childs(ch_item)
                            ch_db_item = self.db.get(ch_item.id)
                            if ch_db_item is not None:
                                pass
                                # todo: set deleted flag for ch_db_item

                    delete_childs(child_item)

            def redo(self):  # is called when pushed to the stack
                if position is not None:  # insert command
                    if self.id_list is None:
                        child_id, _ = self.model.db.save(NEW_DB_ITEM.copy())
                        self.id_list = [child_id]
                    self.add_rows(self.model, self.position, self.parent_item_id, self.id_list, self.set_edit_focus)
                    self.set_edit_focus = False  # when redo is called the second time (when the user is redoing), he doesn't want edit focus
                    self.delete_child_from_parent_id_list = [(self.id_list[0], parent_item_id, None)]
                else:
                    self.remove_rows()

            def undo(self):
                if self.position is not None:  # undo insert command
                    # todo: delete really instead of set delete marker
                    self.remove_rows()
                else:  # undo remove command
                    for child_item_id, parent_item_id, position in delete_child_from_parent_id_list:
                        self.add_rows(self.model, position, parent_item_id, [child_item_id], False)

        if position is not None:  # insert command
            if id_list is None:
                # used from view, create a single new row / self.db item
                set_edit_focus = True
                self.undoStack.push(InsertRemoveRowCommand(self, position, parent_item_id, None, set_edit_focus, None))
            else:  # used from move methods, add existing db items to the parent. Don't add to stack, because already part of an UndoCommand
                set_edit_focus = False
                InsertRemoveRowCommand.add_rows(self, position, parent_item_id, id_list, set_edit_focus)
        else:  # remove command
            delete_child_from_parent_id_list = list()
            for index in indexes:
                child_item = self.getItem(index)
                delete_child_from_parent_id_list.append((child_item.id, child_item.parentItem.id, child_item.child_number()))  # save the position information for adding (undo)
            self.undoStack.push(InsertRemoveRowCommand(self, position, parent_item_id, id_list, False, delete_child_from_parent_id_list))

    def move_vertical(self, indexes, up_or_down):
        # up_or_down is -1 for up and +1 for down

        class MoveVerticalCommand(QUndoCommandStructure):
            _fields = ['model', 'item_id', 'parent_item_id', 'count', 'up_or_down']
            title = 'Move vertically'

            def move(self, up_or_down):
                db_item = self.model.db[self.parent_item_id]
                children_list = db_item['children'].split()
                old_position = children_list.index(self.item_id)
                if up_or_down == -1 and old_position == 0 or up_or_down == +1 and old_position + self.count - 1 == len(children_list) - 1:  # don't move if already at top or bottom
                    return
                self.model.layoutAboutToBeChanged.emit()
                if up_or_down == -1:  # if we want to move several items up, we can move the item-above below the selection instead
                    swapped_item = children_list.pop(old_position - 1)
                    swapped_item_new_position = old_position + self.count - 1
                elif up_or_down == +1:
                    swapped_item = children_list.pop(old_position + self.count)
                    swapped_item_new_position = old_position
                children_list.insert(swapped_item_new_position, swapped_item)
                db_item['children'] = ' '.join(children_list)
                db_item['change'] = dict(method='moved_vertical', position=old_position, count=self.count, up_or_down=up_or_down, user=socket.gethostname())
                self.model.db[self.parent_item_id] = db_item

            def redo(self):
                self.move(self.up_or_down)

            def undo(self):
                self.move(self.up_or_down * -1)

        item = self.getItem(indexes[0])
        self.undoStack.push(MoveVerticalCommand(self, item.id, item.parentItem.id, len(indexes), up_or_down))

    def move_horizontal(self, indexes, direction):
        item = self.getItem(indexes[0])
        id_list = list()
        for index in indexes:
            id_list.append(self.getItem(index).id)

        parent_parent_item = item.parentItem.parentItem
        if parent_parent_item is None and direction == -1:  # stop moving left if parent is root_item
            return
        elif parent_parent_item is not None:  # just for moving left
            parent_parent_item_id = parent_parent_item.id
        else:  # for moving right we don't need 'parent_parent_item_id'
            parent_parent_item_id = None

        original_position = item.child_number()
        if original_position == 0 and direction == 1:  # stop moving right if the moving item is the top item
            return
        sibling_index = self.index(original_position - 1, 0, self.parent(indexes[0]))
        sibling_id = self.getItem(sibling_index).id
        last_childnr_of_sibling = len(item.parentItem.childItems[original_position - 1].childItems)

        class MoveHorizontalCommand(QUndoCommandStructure):
            _fields = ['model', 'direction', 'parent_parent_item_id', 'parent_item_id',
                       'child_item_id', 'id_list', 'position', 'original_position', 'sibling_id', 'last_childnr_of_sibling']
            title = 'move horizontal'

            def move(self, from_parent, insert_in, position):
                self.model.remove_consecutive_rows_from_parent(from_parent, self.child_item_id, len(self.id_list))
                self.model.insert_remove_rows(position, insert_in, self.id_list)

            def redo(self):
                if self.direction == -1:  # left
                    self.move(self.parent_item_id, self.parent_parent_item_id, self.position)  # insert as a child of the parent's parent
                else:  # right
                    self.move(self.parent_item_id, self.sibling_id, self.last_childnr_of_sibling)  # insert as a child of the sibling above

            def undo(self):
                if self.direction == 1:  # undo moving right
                    self.move(self.sibling_id, self.parent_item_id, self.original_position)
                else:  # undo moving left
                    self.move(self.parent_parent_item_id, self.parent_item_id, self.original_position)

        position = item.parentItem.child_number() + 1
        self.undoStack.push(MoveHorizontalCommand(self, direction, parent_parent_item_id, item.parentItem.id,
                                                  item.id, id_list, position, original_position, sibling_id, last_childnr_of_sibling))

    def remove_consecutive_rows_from_parent(self, parent_item_id, child_item_id, count):  # just for moving
        parent_db_item = self.db[parent_item_id]
        children_list = parent_db_item['children'].split()
        position = children_list.index(child_item_id)
        parent_db_item['change'] = dict(method='removed', position=position, count=count, user=socket.gethostname())
        children_list[position:position + count] = []
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

        # return True if this row's data is accepted
        # todo tokenize, but not in "", and ignore tags in ""
        tokens = self.filter.split()  # all tokens must be in the row's data
        for token in tokens:
            item = self.sourceModel().getItem(index)
            db_item = self.sourceModel().db[item.id]
            if token.startswith('c='):
                color_character = token[2:3]
                if db_item['color'] == CHAR_QCOLOR_DICT.get(color_character):
                    continue
            if token.startswith('t='):
                task_character = token[2:3]
                if db_item['checked'] == CHAR_CHECKED_DICT.get(task_character):
                    continue
            if re.match(r'e(<|>|=)', token):
                if db_item['estimate'] == '':
                    break
                less_greater_equal_sign = token[1]
                estimate_search = token[2:]
                if eval(db_item['estimate'] + less_greater_equal_sign + estimate_search):
                    continue
            elif token in index.data():
                continue
            break
        else:  # just executed when not breaked
            return True  # all tokens are in the row

        # return True if a child row is accepted
        for row in range(self.sourceModel().rowCount(index)):
            if self.filterAcceptsRow(row, index):
                return True;

        return False

    def lessThan(self, left_index, right_index):
        column = left_index.column()
        left_data = left_index.data()
        right_data = right_index.data()
        if column == 0:
            return True
        elif column == 2:
            left_data = int(left_data) if left_data != '' else 0
            right_data = int(right_data) if right_data != '' else 0
        return left_data < right_data

    def insertRow(self, position, parent):
        self.sourceModel().insert_remove_rows(position, self.getItem(parent).id)

    def removeRows(self, indexes):
        self.sourceModel().insert_remove_rows(indexes=[self.mapToSource(index) for index in indexes])

    def move_horizontal(self, indexes, direction):
        if len(indexes) > 0:
            self.sourceModel().move_horizontal([self.mapToSource(index) for index in indexes], direction)

    def move_vertical(self, indexes, up_or_down):
        if len(indexes) > 0:
            self.sourceModel().move_vertical([self.mapToSource(index) for index in indexes], up_or_down)

    def getItem(self, index):
        return self.sourceModel().getItem(self.mapToSource(index))

    def setData(self, index, value, role=None, field='text'):
        return self.sourceModel().setData(self.mapToSource(index), value, field=field)

    def toggle_task(self, index):
        db_item = self.sourceModel().db[self.sourceModel().getItem(self.mapToSource(index)).id]
        checked = db_item['checked']
        if checked == 'None':
            self.setData(index, 'False', field='checked')
        elif checked == 'False':
            self.setData(index, 'True', field='checked')
        elif checked == 'True':
            self.setData(index, 'None', field='checked')

    def toggle_project(self, index):
        db_item = self.sourceModel().db[self.sourceModel().getItem(self.mapToSource(index)).id]
        project_state = db_item['checked']
        if project_state == 'None':
            self.setData(index, 'sequential', field='checked')
        elif project_state == 'sequential':
            self.setData(index, 'parallel', field='checked')
        elif project_state == 'parallel':
            self.setData(index, 'paused', field='checked')
        elif project_state == 'paused':
            self.setData(index, 'None', field='checked')


class Delegate(QStyledItemDelegate):
    def __init__(self, parent, model):
        super(Delegate, self).__init__(parent)
        self.model = model
        self.main_window = parent

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
            color = QColor(db_item['color'])
        painter.save()
        painter.fillRect(option.rect, color)
        gap_for_checkbox = 17 if checked != 'None' else 0
        painter.translate(option.rect.x() + gap_for_checkbox - 2, option.rect.y() - 3)  # -3: put the text in the middle of the line
        document.drawContents(painter)
        painter.restore()

        if checked != 'None' and index.column() == 0:
            if checked == 'True' or checked == 'False':  # task
                check_box_style_option = QStyleOptionButton()
                if checked == 'True':
                    check_box_style_option.state |= QStyle.State_On
                elif checked == 'False':
                    check_box_style_option.state |= QStyle.State_Off
                check_box_style_option.rect = self.getCheckBoxRect(option)
                check_box_style_option.state |= QStyle.State_Enabled
                QApplication.style().drawControl(QStyle.CE_CheckBox, check_box_style_option, painter)
            else:  # project
                painter.save()
                icon = QIcon(':/' + checked)
                iconsize = option.decorationSize
                painter.drawPixmap(option.rect.x(), option.rect.y(), icon.pixmap(iconsize.width(), iconsize.height()))
                painter.restore()

    def getCheckBoxRect(self, option):  # source: http://stackoverflow.com/questions/17748546/pyqt-column-of-checkboxes-in-a-qtableview
        check_box_style_option = QStyleOptionButton()
        check_box_rect = QApplication.style().subElementRect(QStyle.SE_CheckBoxIndicator, check_box_style_option, None)
        check_box_point = QPoint(option.rect.x(), option.rect.y())
        return QRect(check_box_point, check_box_rect.size())

    def createEditor(self, parent, option, index):
        if index.column() == 0:
            suggestions_model = self.model.sourceModel().get_tags_set(cut_delimiter=False)
            return AutoCompleteEdit(parent, list(suggestions_model))
        if index.column() == 1:
            date_edit = OpenPopupDateEdit(parent, self)
            date = QDate.currentDate() if index.data() == '' else QDate.fromString(index.data(), 'dd.MM.yy')
            date_edit.setDate(date)
            date_edit.setCalendarPopup(True)
            date_edit.setCalendarWidget(EscCalendarWidget(parent))
            return date_edit
        else:  # index.column() == 2:
            line_edit = QLineEdit(parent)
            line_edit.setValidator(QIntValidator(0, 999, self));
            return line_edit


    def setEditorData(self, editor, index):
        QStyledItemDelegate.setEditorData(self, editor, index)

    def setModelData(self, editor, model, index):
        QStyledItemDelegate.setModelData(self, editor, model, index)


class EscCalendarWidget(QCalendarWidget):
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            open_popup_date_edit = self.parent().parent()
            open_popup_date_edit.delegate.closeEditor.emit(open_popup_date_edit, QAbstractItemDelegate.NoHint)


class OpenPopupDateEdit(QDateEdit):
    def __init__(self, parent, delegate):
        super(OpenPopupDateEdit, self).__init__(parent)
        self.delegate = delegate
        self.installEventFilter(self)

    def focusInEvent(self, event):  # open popup on focus. source: http://forum.qt.io/topic/26821/solved-activating-calender-popup-on-focus-in-event
        self.calendarWidget().activated.connect(self.commit)  # commit edit as soon as the user goes back from the calendar popup to the dateEdit
        opt = QStyleOptionSpinBox()
        self.initStyleOption(opt)
        rect = self.style().subControlRect(QStyle.CC_SpinBox, opt, QStyle.SC_SpinBoxDown)
        e = QMouseEvent(QEvent.MouseButtonPress, rect.center(), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        QApplication.sendEvent(self, e)

    def commit(self):
        self.delegate.commitData.emit(self)
        self.delegate.closeEditor.emit(self, QAbstractItemDelegate.NoHint)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.ShortcutOverride and event.key() == Qt.Key_Tab:
            self.delegate.main_window.edit_row()
        if event.type() == QEvent.ShortcutOverride and event.key() == Qt.Key_Delete:
            self.setSpecialValueText(' ')
            self.setDate(QDate.fromString(EMPTY_DATE, 'dd.MM.yy'))  # workaround to set empty date
            self.commit()
        return False  # don't stop the event being handled further


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