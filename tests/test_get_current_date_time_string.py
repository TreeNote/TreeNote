# -*- coding: utf-8 -*-

import time
from unittest import TestCase
import treenote.main


class TestGetCurrentDateTimeString(TestCase):
    """Test of the Get_current_date_time_string function"""

    def test_get_current_date_time_string(self):
        """check if date_time_string in the format like 2017-02-13-22-04-31-908
        and check is the string unique"""
        date_time_string = treenote.main.get_current_date_time_string()
        self.assertRegex(date_time_string, r"2\d\d\d")  # \d = one digit 0-9
        self.assertRegex(date_time_string,
                         r"2\d\d\d-\d\d-\d\d-\d\d-\d\d-\d\d-\d\d\d")
        time.sleep(.1)
        date_time_string_new = treenote.main.get_current_date_time_string()
        self.assertNotEqual(date_time_string, date_time_string_new)
