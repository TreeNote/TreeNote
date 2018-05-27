from unittest import TestCase
from PyQt5.QtWidgets import QApplication
from treenote.main import MainWindow
from treenote.model import TreeModel


class TestTreeModel(TestCase):
    """Test for class TreeModel"""

    def setUp(self):
        """Creates the QApplication instance"""

        # Simple way of making instance a singleton
        super(TestTreeModel, self).setUp()

        self.app = QApplication([])
        self.window = MainWindow(self.app)
        self.tree = TreeModel(self.window, ['a', 'b', 'c'])

    def tearDown(self):
        """Deletes the reference owned by self"""
        del self.app
        super(TestTreeModel, self).tearDown()

    def test_correct_init(self):
        self.assertEqual(self.tree.rootItem.header_list, ['a', 'b', 'c'])

    def test_move_vertical(self):
        """Test the move vertical,
        it the moment only to call the function

        :return: None
        """
        index = self.tree.indexes()
        self.assertEqual(index[1].row(), 0)
        self.assertEqual(index[1].column(), 0)

        # up_or_down is -1 for up and +1 for down
        self.tree.move_vertical(index, +1)
        self.assertEqual(index[1].row(), 0)
        self.assertEqual(index[1].column(), 0)
        # No Change after use move_vertical!
        # Todo: Add useful tests
