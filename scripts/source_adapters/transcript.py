"""Backward-compatible adapter import."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from chat_distiller._internal.source_adapters import transcript as _implementation
sys.modules[__name__] = _implementation
