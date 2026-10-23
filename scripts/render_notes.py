#!/usr/bin/env python3
"""Backward-compatible entry point; implementation lives in the package."""
import sys
from pathlib import Path

# Only legacy script entry points adjust the source-checkout import path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chat_distiller._internal import render_notes as _implementation

if __name__ == "__main__":
    sys.exit(_implementation.main())
else:
    sys.modules[__name__] = _implementation
