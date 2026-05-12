"""Pytest config for feature-builder."""

from __future__ import annotations

import os
import sys

# Make the function module importable as `function_app`, `pipeline`, etc.
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
