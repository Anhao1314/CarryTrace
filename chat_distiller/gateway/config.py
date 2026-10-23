"""Managed Context Gateway state. JSON keeps Python 3.9 support dependency-free."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .._internal.memory_identity import atomic_write

CONFIG_SCHEMA = 1
STATE_SCHEMA = 1

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)

def digest(value):
    import hashlib
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()

class GatewayPaths:
    def __init__(self, home=None):
        raw = home or os.environ.get("CHAT_DISTILLER_HOME") or "~/.chat-distiller"
        self.home = Path(raw).expanduser().resolve()
        self.config = self.home / "config.json"
        self.state = self.home / "state/sync.json"
        self.source = self.home / "sources/doubao"
        self.transcripts = self.source / "transcripts"
        self.pending = self.home / "pending/sync-plan.json"
        self.vault = self.home / "vault"
    def ensure(self):
        for path in (self.home, self.state.parent, self.source, self.transcripts, self.pending.parent, self.vault):
            path.mkdir(parents=True, exist_ok=True)

def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    if not path.is_file() or path.is_symlink():
        raise ValueError("managed gateway state must be a regular file: " + str(path))
    return json.loads(path.read_text(encoding="utf-8"))

def write_json(path, value):
    atomic_write(Path(path), json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")

def empty_state():
    return {"schema_version": STATE_SCHEMA, "scan_revision": 0, "sessions": {}}

def validate_config(config):
    if not isinstance(config, dict) or config.get("schema_version") != CONFIG_SCHEMA:
        raise ValueError("unsupported gateway config")
    if config.get("connector") != "doubao":
        raise ValueError("unsupported connector")
    for key in ("sessions_root", "vault", "subdir"):
        if not isinstance(config.get(key), str) or not config[key]:
            raise ValueError("invalid gateway config field: " + key)
    return config

def validate_state(state):
    if not isinstance(state, dict) or state.get("schema_version") != STATE_SCHEMA:
        raise ValueError("unsupported gateway sync state")
    if type(state.get("scan_revision")) is not int or state["scan_revision"] < 0:
        raise ValueError("invalid scan revision")
    sessions = state.get("sessions")
    if not isinstance(sessions, dict):
        raise ValueError("invalid session registry")
    for sid, item in sessions.items():
        if not isinstance(sid, str) or not sid or not isinstance(item, dict):
            raise ValueError("invalid session state")
        if not isinstance(item.get("fingerprint"), str) or not isinstance(item.get("record"), dict):
            raise ValueError("invalid session snapshot")
        if item.get("status") not in {"pending", "published"} or type(item.get("present")) is not bool:
            raise ValueError("invalid session status")
    return state
