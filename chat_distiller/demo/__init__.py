"""Local demo app for ClaimLedger (stdlib HTTP server + static UI)."""
from .server import DemoApp, DemoServer, build_server, main

__all__ = ["DemoApp", "DemoServer", "build_server", "main"]
