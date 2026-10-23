"""Generic and Claude Code connectors through the full gateway pipeline."""
import hashlib
import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from chat_distiller import ContextGateway
from chat_distiller.gateway.core import GatewayError
from chat_distiller.connectors.file_sessions import FileSessionSource


def generic_rows():
    return [
        {"session_id": "sess-db", "role": "user",
         "content": "继续数据库迁移，SQLite 并发写有问题。",
         "timestamp": "2026-10-01T01:00:00Z"},
        {"session_id": "sess-db", "role": "assistant",
         "content": "改用 PostgreSQL，API v1 兼容层保留。",
         "timestamp": "2026-10-01T01:05:00Z"},
        {"session_id": "sess-db", "role": "tool", "content": "SECRET TOOL OUTPUT",
         "timestamp": "2026-10-01T01:06:00Z"},
        {"session_id": "sess-ui", "role": "user",
         "content": "继续首页视觉精修。",
         "timestamp": "2026-10-02T09:00:00+00:00"},
        {"session_id": "sess-ui", "role": "assistant",
         "content": "README 首页保持 Wiki 生命周期主线。",
         "timestamp": "2026-10-02T09:10:00+00:00"},
    ]


def claude_code_lines(session_id="3d61026c-eb70-47b2-81c2-610e3c958e65"):
    return [
        {"type": "queue-operation", "operation": "enqueue", "sessionId": session_id,
         "timestamp": "2026-10-06T17:16:50.619Z", "content": "queued prompt"},
        {"type": "user", "sessionId": session_id, "isSidechain": False,
         "timestamp": "2026-10-06T17:16:50.719Z",
         "message": {"role": "user", "content": "继续数据库迁移，SQLite 并发写有问题。"}},
        {"type": "attachment", "sessionId": session_id,
         "timestamp": "2026-10-06T17:16:51.000Z", "rendered": "<system-reminder>x</system-reminder>"},
        {"type": "assistant", "sessionId": session_id, "isSidechain": False,
         "timestamp": "2026-10-06T17:17:10.000Z",
         "message": {"role": "assistant", "content": [
             {"type": "thinking", "thinking": "SECRET REASONING SHOULD NOT APPEAR"},
             {"type": "tool_use", "id": "t1", "name": "Read", "input": {}},
             {"type": "text", "text": "改用 PostgreSQL，API v1 兼容层保留。"},
         ]}},
        {"type": "user", "sessionId": session_id, "isSidechain": False,
         "timestamp": "2026-10-06T17:17:20.000Z",
         "message": {"role": "user", "content": [
             {"type": "tool_result", "tool_use_id": "t1", "content": "SECRET TOOL OUTPUT"},
         ]}},
        {"type": "user", "sessionId": session_id, "isSidechain": True,
         "timestamp": "2026-10-06T17:17:30.000Z",
         "message": {"role": "user", "content": "sidechain subagent prompt should be excluded"}},
        {"type": "system", "sessionId": session_id, "level": "error",
         "timestamp": "2026-10-06T17:17:40.000Z", "error": "retry"},
        {"type": "assistant", "sessionId": session_id, "isSidechain": False,
         "timestamp": "2026-10-06T17:18:00.000Z",
         "message": {"role": "assistant", "content": [
             {"type": "tool_use", "id": "t2", "name": "Edit", "input": {}},
         ]}},
    ]


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    return path


class GenericConnectorTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.input = write_jsonl(self.root / "export.jsonl", generic_rows())
        self.home = self.root / "gateway"
        self.gateway = ContextGateway(self.home)

    def source_hash(self):
        return hashlib.sha256(self.input.read_bytes()).hexdigest()

    def connect_sync(self):
        self.gateway.connect("generic", input=self.input)
        return self.gateway.sync()

    def test_connect_sync_plan_and_source_stay_read_only(self):
        before = self.source_hash()
        connect = self.gateway.connect("generic", input=self.input)
        self.assertEqual(connect["connector"], "generic")
        self.assertEqual(connect["discovered_sessions"], 2)
        result = self.connect_sync()
        self.assertTrue(result["needs_agent_judgment"])
        self.assertEqual(result["changed_sessions"], 2)
        self.assertEqual(before, self.source_hash())
        plan = json.loads((self.home / "pending" / "sync-plan.json").read_text(encoding="utf-8"))
        self.assertEqual(plan["connector"], "generic")
        self.assertEqual({s["session_id"] for s in plan["pending_sessions"]},
                         {"sess-db", "sess-ui"})
        transcript = (self.home / "sources" / "generic" / "transcripts" / "sess-db.transcript.md").read_text(encoding="utf-8")
        self.assertIn("继续数据库迁移", transcript)
        self.assertIn("改用 PostgreSQL", transcript)
        self.assertNotIn("SECRET TOOL OUTPUT", transcript)
        # Idempotent: a second sync changes nothing.
        again = self.gateway.sync()
        self.assertEqual(again["changed_sessions"], 0)
        self.assertEqual(again["pending_sessions"], 2)

    def test_sync_updates_only_the_changed_session(self):
        self.connect_sync()
        rows = generic_rows()
        rows[1]["content"] = "改用 PostgreSQL 16，API v1 兼容层保留。"
        write_jsonl(self.input, rows)
        result = self.gateway.sync()
        self.assertEqual(result["changed_sessions"], 1)
        state = json.loads((self.home / "state" / "sync.json").read_text(encoding="utf-8"))
        self.assertEqual(state["sessions"]["sess-db"]["record"]["assistant_replies"], 1)
        self.assertIn("PostgreSQL 16",
                      (self.home / "sources" / "generic" / "transcripts" / "sess-db.transcript.md").read_text(encoding="utf-8"))

    def test_removed_session_is_withdrawn_not_served(self):
        self.connect_sync()
        write_jsonl(self.input, [row for row in generic_rows() if row["session_id"] == "sess-db"])
        result = self.gateway.sync()
        self.assertEqual(result["removed_sessions"], 1)
        state = json.loads((self.home / "state" / "sync.json").read_text(encoding="utf-8"))
        self.assertFalse(state["sessions"]["sess-ui"]["present"])
        packet = self.gateway.context("数据库迁移")
        self.assertFalse(any(s["session_id"] == "sess-ui" for s in packet["raw_sessions"]))

    def test_context_matches_before_any_distillation(self):
        self.connect_sync()
        packet = self.gateway.context("SQLite 并发写问题")
        self.assertEqual(packet["status"], "ready")
        self.assertTrue(packet["raw_sessions"])
        self.assertTrue(packet["requires_review"])
        self.assertIn("SQLite", packet["raw_sessions"][0]["first_request"])

    def test_strict_contract_refuses_bad_rows(self):
        bad = self.root / "bad.jsonl"
        bad.write_text('{"session_id":"x","role":"wizard","content":"hi","timestamp":"2026-10-01T00:00:00Z"}\n', encoding="utf-8")
        with self.assertRaisesRegex(GatewayError, "role"):
            self.gateway.connect("generic", input=bad)

    def test_rebind_requires_force_and_config_validates_connector(self):
        self.gateway.connect("generic", input=self.input)
        other = write_jsonl(self.root / "other.jsonl", generic_rows())
        with self.assertRaisesRegex(GatewayError, "already connected"):
            self.gateway.connect("generic", input=other)
        self.gateway.connect("generic", input=self.input, force=True)
        config = json.loads((self.home / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["connector"], "generic")
        with self.assertRaisesRegex(GatewayError, "unsupported connector"):
            self.gateway.connect("sqlite", input=other)

    def test_status_reports_the_connector(self):
        self.connect_sync()
        status = self.gateway.status()
        self.assertEqual(status["connector"], "generic")
        self.assertEqual(status["discovered_sessions"], 2)
        self.assertEqual(status["pending_sessions"], 2)


class ClaudeCodeConnectorTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.projects = self.root / ".claude" / "projects"
        self.session_file = write_jsonl(
            self.projects / "D--work-demo" / "3d61026c-eb70-47b2-81c2-610e3c958e65.jsonl",
            claude_code_lines())
        self.home = self.root / "gateway"
        self.gateway = ContextGateway(self.home)

    def connect_sync(self):
        self.gateway.connect("claude-code", input=self.projects)
        return self.gateway.sync()

    def test_transcript_excludes_thinking_tool_output_and_sidechains(self):
        connect = self.gateway.connect("claude-code", input=self.projects)
        self.assertEqual(connect["discovered_sessions"], 1)
        # The source records the resolved path; on macOS /var is a symlink to
        # /private/var, so compare resolved paths on both sides.
        self.assertEqual(connect["input"], str(self.projects.resolve()))
        self.connect_sync()
        plan = json.loads((self.home / "pending" / "sync-plan.json").read_text(encoding="utf-8"))
        self.assertEqual(len(plan["pending_sessions"]), 1)
        record = plan["pending_sessions"][0]["record"]
        self.assertEqual(record["agents"], ["claude-code"])
        self.assertTrue(record["degraded"])
        transcript = (self.home / "sources" / "claude-code" / "transcripts" /
                      "3d61026c-eb70-47b2-81c2-610e3c958e65.transcript.md").read_text(encoding="utf-8")
        self.assertIn("继续数据库迁移", transcript)
        self.assertIn("改用 PostgreSQL", transcript)
        self.assertNotIn("SECRET REASONING", transcript)
        self.assertNotIn("SECRET TOOL OUTPUT", transcript)
        self.assertNotIn("sidechain subagent prompt", transcript)
        self.assertIn("Read", transcript)
        self.assertIn("Edit", transcript)
        status = self.gateway.status()
        self.assertEqual(status["connector"], "claude-code")
        self.assertEqual(status["pending_sessions"], 1)

    def test_file_additions_are_discovered_incrementally(self):
        self.connect_sync()
        write_jsonl(self.projects / "D--work-demo" / "ffffffff-0000-0000-0000-000000000001.jsonl",
                    claude_code_lines("ffffffff-0000-0000-0000-000000000001"))
        result = self.gateway.sync()
        self.assertEqual(result["changed_sessions"], 1)
        status = self.gateway.status()
        self.assertEqual(status["discovered_sessions"], 2)
        self.assertEqual(status["tracked_sessions"], 2)

    def test_millis_timestamps_sort_and_convert(self):
        self.connect_sync()
        record = json.loads(
            (self.home / "pending" / "sync-plan.json").read_text(encoding="utf-8")
        )["pending_sessions"][0]["record"]
        self.assertEqual(record["created"], "2026-10-07 01:16")
        self.assertEqual(record["updated"], "2026-10-07 01:18")

    def test_default_discovery_uses_claude_projects(self):
        with unittest.mock.patch("pathlib.Path.home", return_value=self.root):
            connect = self.gateway.connect("claude-code")
            self.assertEqual(connect["discovered_sessions"], 1)


if __name__ == "__main__":
    unittest.main()
