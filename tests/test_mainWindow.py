from unittest import TestCase
from PyQt5 import QtWidgets
from treenote.main import MainWindow

class TestMainWindow(TestCase):
    """test of the treenote.main.MainWindow class"""

    def setUp(self):
        """Creates the QApplication instance"""

        # Simple way of making instance a singleton
        super(TestMainWindow, self).setUp()

        self.app = QtWidgets.QApplication([])
        self.window = MainWindow(self.app)

    def tearDown(self):
        """Deletes the reference owned by self"""
        del self.app
        super(TestMainWindow, self).tearDown()

    def test_is_sidebar_shown(self):
        """Test is_sidebar_shown"""
        self.assertEqual(self.window.is_sidebar_shown(), False)
