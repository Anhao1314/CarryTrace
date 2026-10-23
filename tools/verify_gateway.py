#!/usr/bin/env python3
"""Exercise Context Gateway from an installed wheel outside the source checkout."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import chat_distiller
from chat_distiller import ContextGateway

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path(chat_distiller.__file__).resolve()
if ROOT in PACKAGE.parents:
    raise RuntimeError("gateway smoke imported source checkout rather than installed wheel")

checks = []
def require(value, name):
    if not value: raise AssertionError(name)
    checks.append(name)

def session(root, sid, user, assistant):
    system = root / sid / "agents/agent-1/system"; system.mkdir(parents=True)
    (system / "assignment.md").write_text("## [2026-10-01T01:00:00Z] 需求\n\n" + user + "\n", encoding="utf-8")
    (system / "trajectory.jsonl").write_text(
        json.dumps({"role": "assistant", "content": assistant}, ensure_ascii=False) + "\n" +
        json.dumps({"role": "tool", "content": "hidden"}, ensure_ascii=False) + "\n", encoding="utf-8")

def tree_hash(root):
    h = hashlib.sha256()
    for p in sorted(Path(root).rglob("*")):
        if p.is_file(): h.update(p.relative_to(root).as_posix().encode("utf-8") + b"\0" + p.read_bytes())
    return h.hexdigest()

with tempfile.TemporaryDirectory(prefix="chat-distiller-gateway-installed-") as tmp:
    base = Path(tmp); sessions = base / ".sessions"; sessions.mkdir(); home = base / "home"
    session(sessions, "db", "继续数据库迁移。", "PostgreSQL 是当前方向，保留 API v1。")
    entry = Path(sys.executable).with_name("chat-distiller")
    if os.name == "nt": entry = entry.with_suffix(".exe")
    def command(*args, expected=0):
        proc = subprocess.run([str(entry), *map(str,args)], cwd=base, capture_output=True, text=True, timeout=60)
        if proc.returncode != expected: raise AssertionError(f"{args}: {proc.returncode}\n{proc.stdout}\n{proc.stderr}")
        return json.loads(proc.stdout) if "--json" in args else proc.stdout
    before = tree_hash(sessions)
    connected = command("connect", "doubao", "--sessions-root", sessions, "--home", home, "--json")
    require(connected["discovered_sessions"] == 1, "installed connect discovers Doubao fixture")
    first = command("sync", "--home", home, "--json")
    require(first["changed_sessions"] == 1 and first["pending_sessions"] == 1, "installed first incremental sync")
    state_before = (home / "state/sync.json").read_bytes()
    second = command("sync", "--home", home, "--json")
    require(second["changed_sessions"] == 0, "installed repeated sync is no-op")
    require((home / "state/sync.json").read_bytes() == state_before, "installed no-op keeps sync state byte-identical")
    packet = command("context", "PostgreSQL 数据库", "--home", home, "--max-bytes", "4096", "--json")
    require(packet["status"] == "ready" and packet["raw_sessions"][0]["session_id"] == "db", "installed raw context fallback")
    require(packet["used_bytes"] <= 4096 and packet["requires_review"], "installed context byte budget and review flag")
    status = command("status", "--home", home, "--json")
    require(status["tracked_sessions"] == 1 and status["pending_sessions"] == 1, "installed observable status")
    require(tree_hash(sessions) == before, "installed Gateway never mutates Doubao source")
    require(ContextGateway(home).context("数据库", max_bytes=4096)["status"] == "ready", "installed ContextGateway Python API")

print(json.dumps({"ok": True, "version": chat_distiller.__version__, "installed_package": str(PACKAGE),
                  "checks_passed": len(checks), "checks": checks,
                  "data": "synthetic Doubao fixture; zero model calls"}, ensure_ascii=False, indent=2))
