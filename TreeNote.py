#!/usr/bin/env python3

"""Simple launcher for TreeNote.
It must have a different name than the python package, otherwise PyInstaller runs into problems."""

import treenote.main

if __name__ == '__main__':
    treenote.main.start()
