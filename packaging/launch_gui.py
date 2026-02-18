"""
PyInstaller entry point for OpenCapture.app.

This thin wrapper avoids the relative-import issue that occurs when
PyInstaller runs a package module (app.py) as the top-level script.
"""
from opencapture.app import main

main()
