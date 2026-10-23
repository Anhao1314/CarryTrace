#!/usr/bin/env python3
"""Executed Context Gateway engineering experiment. Synthetic local Doubao data; zero model calls."""
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def session(root, sid, user, assistant, assignment=True, corrupt=False):
    system = root / sid / "agents/agent-1/system"; system.mkdir(parents=True)
    if assignment:
        (system / "assignment.md").write_text("## [2026-10-01T01:00:00Z] 需求\n\n" + user + "\n", encoding="utf-8")
    rows = ([] if assignment else [{"role": "user", "content": user}]) + [
        {"role": "assistant", "content": assistant}, {"role": "tool", "content": "hidden tool output"}]
    text = "\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n"
    if corrupt: text += "{broken\n"
    (system / "trajectory.jsonl").write_text(text, encoding="utf-8")

def tree_hash(root):
    h = hashlib.sha256()
    for p in sorted(Path(root).rglob("*")):
        if p.is_file(): h.update(p.relative_to(root).as_posix().encode() + b"\0" + p.read_bytes())
    return h.hexdigest()

def run(args):
    proc = subprocess.run([sys.executable, "-m", "chat_distiller"] + args, cwd=ROOT, capture_output=True, text=True)
    try: payload = json.loads(proc.stdout)
    except json.JSONDecodeError: payload = {"raw_stdout": proc.stdout}
    return proc.returncode, payload, proc.stderr

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default=str(ROOT / "benchmarks/gateway")); args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="chat-distiller-gateway-") as tmp:
        tmp = Path(tmp); sessions = tmp / ".sessions"; sessions.mkdir(); home = tmp / "home"
        session(sessions, "db", "继续数据库迁移，SQLite 并发写有问题。", "决定切到 PostgreSQL，并保留 API v1。")
        session(sessions, "fallback", "继续视觉精修。", "README 继续保持 Wiki 主线。", assignment=False, corrupt=True)
        source_before = tree_hash(sessions)
        rc1, connected, _ = run(["connect", "doubao", "--sessions-root", str(sessions), "--home", str(home), "--json"])
        rc2, first, _ = run(["sync", "--home", str(home), "--json"])
        state_before = hashlib.sha256((home / "state/sync.json").read_bytes()).hexdigest()
        rc3, context, _ = run(["context", "PostgreSQL 数据库迁移", "--home", str(home), "--max-bytes", "4096", "--json"])
        rc4, second, _ = run(["sync", "--home", str(home), "--json"])
        state_after = hashlib.sha256((home / "state/sync.json").read_bytes()).hexdigest()
        source_after = tree_hash(sessions)
        degraded = (home / "sources/doubao/transcripts/fallback.transcript.md").read_text(encoding="utf-8")
        stale = {"gateway_schema_version": 1, "plan_sha256": first["plan_sha256"], "covered_sessions": ["db"],
                 "retire_memory_ids": [], "distill": {"conversations": [{
                     "session_id": "db", "date": "2026-10-01", "title": "数据库迁移",
                     "categories": ["技术开发/开发环境"], "summary": "数据库迁移。",
                     "cards": [{"kind": "decision", "title": "当前数据库", "body": "当前使用 PostgreSQL。",
                                "categories": ["技术开发/开发环境"]}]}]}}
        stale_path = tmp / "stale.json"; stale_path.write_text(json.dumps(stale, ensure_ascii=False), encoding="utf-8")
        assignment = sessions / "db/agents/agent-1/system/assignment.md"
        assignment.write_text(assignment.read_text(encoding="utf-8") + "\n## [2026-10-02T01:00:00Z] 需求\n\n连接池改成 8。\n", encoding="utf-8")
        run(["sync", "--home", str(home), "--json"])
        stale_rc, stale_result, _ = run(["sync", "--home", str(home), "--apply", str(stale_path), "--json"])
        results = {
            "schema_version": 1, "fixture": "synthetic Doubao Work layout; zero model calls",
            "commands_to_first_context": 3, "connect_exit_zero": rc1 == 0,
            "first_sync_exit_zero": rc2 == 0, "context_exit_zero": rc3 == 0,
            "first_sync_changed_sessions": first.get("changed_sessions"),
            "first_sync_pending_sessions": first.get("pending_sessions"),
            "second_sync_changed_sessions": second.get("changed_sessions"),
            "noop_sync_state_identical": state_before == state_after,
            "source_cache_unchanged": source_before == source_after,
            "context_status": context.get("status"),
            "context_top_session": (context.get("raw_sessions") or [{}])[0].get("session_id"),
            "context_used_bytes": context.get("used_bytes"), "context_budget_bytes": context.get("budget_bytes"),
            "context_within_budget": (context.get("used_bytes") or 10**9) <= (context.get("budget_bytes") or 0),
            "degraded_fallback_visible": "提取降级" in degraded and "解析时跳过 1 行坏 JSON" in degraded,
            "stale_plan_rejected": stale_rc != 0 and "stale gateway proposal" in stale_result.get("error", ""),
            "stale_plan_created_memory": (home / "vault/对话沉淀/.chat-distiller/distill.json").exists(), "model_calls": 0}
        (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        lines = ["# Context Gateway 0.4 engineering experiment", "", "Synthetic local Doubao Work fixture. No external model calls and no real user data.", "",
                 "| Check | Observed |", "| --- | --- |"]
        for key, value in results.items():
            if key not in {"schema_version", "fixture"}: lines.append(f"| `{key}` | `{value}` |")
        lines += ["", "## Interpretation", "", "This verifies interaction-surface reduction, source read-only behavior, incremental idempotence,",
                  "byte-bounded raw context fallback, degraded extraction visibility, and stale-plan rejection.",
                  "It does **not** measure semantic distillation quality or downstream agent task success."]
        (out / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        ok = all([results["connect_exit_zero"], results["first_sync_exit_zero"], results["context_exit_zero"],
                  results["second_sync_changed_sessions"] == 0, results["noop_sync_state_identical"],
                  results["source_cache_unchanged"], results["context_within_budget"], results["degraded_fallback_visible"],
                  results["stale_plan_rejected"], not results["stale_plan_created_memory"]])
        print(json.dumps(results, ensure_ascii=False, indent=2)); return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
