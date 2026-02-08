#!/usr/bin/env python3
"""
OpenCapture - Development entry point.

Adds src/ to sys.path so `opencapture` package is importable
without pip install. For production use: pip install -e .
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from opencapture.cli import main

main()
