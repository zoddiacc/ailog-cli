#!/usr/bin/env python3
"""
ailog - AI-powered Android/AOSP log interpreter
Usage:
  ailog build [-- <make args>]     Wrap AOSP build with AI interpretation
  ailog cat [<adb logcat args>]    Wrap adb logcat with AI filtering
  ailog analyze <file>             Batch analyze a saved log file
  ailog config                     Configure provider, API key, model
"""

import sys
import os

# Add src to path so 'ailog' package is importable
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

from ailog.cli import main

if __name__ == '__main__':
    main()
