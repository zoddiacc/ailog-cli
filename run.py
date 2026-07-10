#!/usr/bin/env python3
"""
Dev/source launcher for ailog — runs the CLI without installing the package.

    python3 run.py <command> [...]

(Installed users get the `ailog` console command instead. This file is named
run.py rather than ailog.py so it doesn't shadow the `ailog` package when
importing from the repo root.)
"""

import sys
import os

# Add src to path so 'ailog' package is importable
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

from ailog.cli import main

if __name__ == '__main__':
    main()
