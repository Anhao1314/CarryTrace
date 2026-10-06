#!/usr/bin/env python3
"""Exercise the installed wheel from outside the checkout. Uses synthetic data only."""
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

import chat_distiller
from chat_distiller import MemoryStore, MemoryIntegrityError, serialize_packet

ROOT = Path(__file__).resolve().parents[1]
package = Path(chat_distiller.__file__).resolve()
if ROOT in package.parents:
    raise RuntimeError("smoke test imported source checkout rather than installed wheel")

checks = []


def require(condition, name):
    if not condition:
        raise AssertionError(name)
    checks.append(name)


with tempfile.TemporaryDirectory(prefix="chat-distiller-installed-") as tmp:
    base = Path(tmp)
    entry = Path(sys.executable).with_name("chat-distiller")
    if os.name == "nt":
        entry = entry.with_suffix(".exe")

    def command(*args, expected=0):
        proc = subprocess.run([str(entry), *map(str, args)], cwd=base, capture_output=True, text=True, timeout=60)
        if proc.returncode != expected:
            raise AssertionError(f"command {args!r}: exit {proc.returncode}\n{proc.stdout}\n{proc.stderr}")
        return proc.stdout

    require(chat_distiller.__version__ in command("--version"), "installed console entry point")
    raw = base / "messages.jsonl"
    messages = [
        {"session_id": "smoke", "timestamp": "2026-01-01T00:00:00Z", "role": "user", "content": "部署采用什么方案？"},
        {"session_id": "smoke", "timestamp": "2026-01-01T00:00:01Z", "role": "assistant", "content": "部署从云端改为本地 SQLite；保留旧 API；超时仍有争议。"},
    ]
    raw.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in messages), encoding="utf-8")
    command("extract", "--source", "generic_jsonl", "--input", raw, "--out", base / "staging")
    require((base / "staging/transcripts/smoke.transcript.md").is_file(), "generic JSONL extraction")
    # Curated synthetic semantic step. There is deliberately no automatic/model distillation claim.
    draft = {"conversations": [{"session_id": "smoke", "date": "2026-01-01", "title": "部署方案", "categories": ["技术开发/开发环境"], "cards": [
        {"kind": "decision", "title": "部署当前方案", "body": "部署使用本地 SQLite；保留旧 API。"},
        {"kind": "decision", "title": "部署旧方案", "body": "部署之前使用云端。", "status": "已过期"},
        {"kind": "decision", "title": "部署超时争议", "body": "部署超时尚未决定。", "status": "有争议"},
    ]}]}
    source = base / "draft.json"
    source.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
    registered = base / "registered.json"
    command("migrate", "--mode", "init", "--distill", source, "--out", registered)
    data = json.loads(registered.read_text(encoding="utf-8"))
    cards = data["conversations"][0]["cards"]
    cards[1]["superseded_by"] = cards[0]["memory_id"]
    registered.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    require(all(c["memory_id"].startswith("mem_") for c in cards), "stable identity initialization")
    vault = base / "vault"; vault.mkdir()
    command("render", "--distill", registered, "--vault", vault)
    require((vault / "对话沉淀/.chat-distiller/taxonomy.md").is_file(), "bundled taxonomy after wheel installation")
    store = MemoryStore(vault)
    require(store.inspect()["cards"] == 3, "installed MemoryStore inspection")
    current = store.search("部署")
    require({r["status"] for r in current} == {"现行", "有争议"}, "current status policy")
    historical = store.search("部署", intent="historical")
    require(len(historical) == 3 and any(r["superseded_by"] for r in historical), "historical lookup with supersession")
    require("SQLite" in store.get(cards[0]["memory_id"])["body"], "stable-ID inspection")
    wire = command("recover", "--vault", vault, "--query", "部署", "--max-bytes", "1800")
    packet = json.loads(wire)
    require(len(wire.encode("utf-8")) == packet["used_bytes"] <= 1800, "canonical UTF-8 packet byte budget")
    require(wire == serialize_packet(store.recover("部署", max_bytes=1800)), "CLI/API recovery equivalence")
    require(store.recover("zzzxxyy")["status"] == "no_match", "empty recovery is explicit")
    before = {str(p.relative_to(vault)): hashlib.sha256(p.read_bytes()).hexdigest() for p in vault.rglob("*") if p.is_file()}
    command("render", "--distill", registered, "--vault", vault)
    after = {str(p.relative_to(vault)): hashlib.sha256(p.read_bytes()).hexdigest() for p in vault.rglob("*") if p.is_file()}
    require(before == after, "idempotent rerender preserves all vault bytes")
    lint = json.loads(command("lint", "--vault", vault, "--transcripts", base / "staging/transcripts"))
    require(lint["ok"] and not lint["structure_issues"] and not lint["index_issues"], "installed lint on rendered memory")
    # Exercise the migration subprocess outside the checkout, not only v2 initialization.
    legacy_vault = base / "legacy"; legacy_vault.mkdir()
    legacy = {"conversations": [dict(draft["conversations"][0], cards=[draft["conversations"][0]["cards"][0]])]}
    source.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
    command("render", "--distill", source, "--vault", legacy_vault)
    upgraded = base / "upgraded.json"
    command("migrate", "--mode", "upgrade", "--distill", source, "--vault", legacy_vault, "--out", upgraded)
    command("render", "--distill", upgraded, "--vault", legacy_vault)
    require(len(MemoryStore(legacy_vault).search("部署")) == 1, "legacy-to-v2 migration outside checkout")
    note = vault / "对话沉淀/知识卡片" / (cards[0]["note_name"] + ".md")
    text = note.read_text(encoding="utf-8")
    note.write_text(text.replace("status: 现行", "status: 已过期"), encoding="utf-8")
    failure = json.loads(command("search", "--vault", vault, "--query", "部署", expected=1))
    require(not failure["ok"] and failure["results"] == [], "note status drift rejected")
    note.write_text(text, encoding="utf-8")
    (vault / "对话沉淀/知识索引.jsonl").write_text("corrupt", encoding="utf-8")
    failure = json.loads(command("recover", "--vault", vault, "--query", "部署", expected=1))
    require(not failure["ok"] and failure["results"] == [], "corrupt index rejected after successful read")

print(json.dumps({"ok": True, "version": chat_distiller.__version__, "python": platform.python_version(), "installed_package": str(package), "checks_passed": len(checks), "checks": checks, "data": "synthetic handwritten cards; no LLM or host compaction exercised"}, ensure_ascii=False, indent=2))
