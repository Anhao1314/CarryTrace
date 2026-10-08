"""Context Gateway integration tests. Synthetic Doubao layout; no model calls."""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from chat_distiller import ContextGateway, MemoryStore
from chat_distiller.gateway.config import read_json
from chat_distiller.gateway.core import GatewayError
from chat_distiller.connectors import SourceChangedError


def make_session(root, sid, user, assistant, *, assignment=True, corrupt=False):
    system = root / sid / "agents" / "agent-1" / "system"
    system.mkdir(parents=True)
    if assignment:
        (system / "assignment.md").write_text(
            "# Assignment\n\n## [2026-10-01T01:00:00Z] 需求\n\n" + user + "\n", encoding="utf-8")
    rows = []
    if not assignment:
        rows.append({"role": "user", "content": user})
    rows += [{"role": "assistant", "content": assistant},
             {"role": "tool", "content": "SECRET TOOL OUTPUT SHOULD NOT BE EXTRACTED"}]
    text = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n"
    if corrupt:
        text += "{bad json\n"
    (system / "trajectory.jsonl").write_text(text, encoding="utf-8")
    return system


def distill_for(sid, body="当前数据库使用 PostgreSQL，保留 API v1 兼容层。"):
    return {"conversations": [{
        "session_id": sid, "date": "2026-10-01", "title": "数据库迁移",
        "categories": ["技术开发/开发环境"], "summary": "数据库迁移决策。",
        "cards": [{"kind": "decision", "title": "当前数据库方案", "body": body,
                   "status": "现行", "categories": ["技术开发/开发环境"]}],
    }]}


class GatewayTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name); self.sessions = self.root / ".sessions"; self.sessions.mkdir()
        make_session(self.sessions, "session-db", "继续数据库迁移，SQLite 并发写有问题。", "改用 PostgreSQL，API v1 兼容层保留。")
        make_session(self.sessions, "session-ui", "继续首页视觉精修。", "README 首页保持 Wiki 生命周期主线。", assignment=False, corrupt=True)
        self.home = self.root / "gateway"; self.gateway = ContextGateway(self.home)

    def source_hash(self):
        h = hashlib.sha256()
        for p in sorted(self.sessions.rglob("*")):
            if p.is_file():
                h.update(str(p.relative_to(self.sessions)).encode()); h.update(p.read_bytes())
        return h.hexdigest()

    def connect_sync(self):
        self.gateway.connect("doubao", sessions_root=self.sessions)
        return self.gateway.sync()

    def test_connect_is_one_command_and_source_is_read_only(self):
        before = self.source_hash(); result = self.gateway.connect("doubao", sessions_root=self.sessions)
        self.assertEqual(result["discovered_sessions"], 2); self.assertTrue((self.home / "config.json").is_file())
        self.assertEqual(before, self.source_hash())
        again = self.gateway.connect("doubao", sessions_root=self.sessions)
        self.assertEqual(again["sessions_root"], result["sessions_root"])

    def test_connect_refuses_silent_rebind(self):
        self.gateway.connect("doubao", sessions_root=self.sessions)
        other = self.root / "other"; other.mkdir()
        with self.assertRaises(GatewayError): self.gateway.connect("doubao", sessions_root=other)
        self.gateway.connect("doubao", sessions_root=other, force=True)

    def test_force_rebind_refuses_published_memory(self):
        sync = self.connect_sync()
        wrapper = {"gateway_schema_version": 1, "plan_sha256": sync["plan_sha256"],
                   "covered_sessions": ["session-db"], "retire_memory_ids": [], "distill": distill_for("session-db")}
        proposal = self.root / "proposal.json"; proposal.write_text(json.dumps(wrapper, ensure_ascii=False), encoding="utf-8")
        self.gateway.sync(apply=proposal)
        other = self.root / "other-published-rebind"; other.mkdir()
        with self.assertRaisesRegex(GatewayError, "published memory"):
            self.gateway.connect("doubao", sessions_root=other, force=True)
        self.assertEqual(self.gateway.status()["discovered_sessions"], 2)

    def test_removed_session_is_not_returned_as_live_context(self):
        self.connect_sync()
        import shutil
        shutil.rmtree(self.sessions / "session-db")
        result = self.gateway.sync(); self.assertEqual(result["removed_sessions"], 1)
        packet = self.gateway.context("PostgreSQL 数据库迁移", max_bytes=4096)
        self.assertFalse(any(x["session_id"] == "session-db" for x in packet["raw_sessions"]))

    def test_sync_is_incremental_idempotent_and_source_read_only(self):
        self.gateway.connect("doubao", sessions_root=self.sessions)
        before_source = self.source_hash(); first = self.gateway.sync()
        state_before = (self.home / "state/sync.json").read_bytes()
        transcripts_before = {p.name: p.read_bytes() for p in (self.home / "sources/doubao/transcripts").glob("*.md")}
        second = self.gateway.sync()
        self.assertEqual(first["changed_sessions"], 2); self.assertEqual(first["pending_sessions"], 2)
        self.assertEqual(second["changed_sessions"], 0)
        self.assertEqual((self.home / "state/sync.json").read_bytes(), state_before)
        self.assertEqual({p.name: p.read_bytes() for p in (self.home / "sources/doubao/transcripts").glob("*.md")}, transcripts_before)
        self.assertEqual(before_source, self.source_hash())

    def test_sync_keeps_degraded_and_bad_json_visible(self):
        self.connect_sync()
        text = (self.home / "sources/doubao/transcripts/session-ui.transcript.md").read_text(encoding="utf-8")
        self.assertIn("提取降级", text); self.assertIn("解析时跳过 1 行坏 JSON", text)
        self.assertNotIn("SECRET TOOL OUTPUT", text)

    def test_sync_updates_only_changed_session(self):
        self.connect_sync()
        path = self.sessions / "session-db/agents/agent-1/system/assignment.md"
        path.write_text(path.read_text(encoding="utf-8") + "\n## [2026-10-02T01:00:00Z] 需求\n\n连接池改成 8。\n", encoding="utf-8")
        result = self.gateway.sync(); self.assertEqual(result["changed_sessions"], 1); self.assertEqual(result["pending_sessions"], 2)

    def test_moving_session_is_skipped_not_committed(self):
        self.gateway.connect("doubao", sessions_root=self.sessions)
        real = __import__("chat_distiller.gateway.core", fromlist=["DoubaoConnector"]).DoubaoConnector.fingerprint
        calls = {"n": 0}
        def moving(root, session_dir):
            if Path(session_dir).name == "session-db":
                calls["n"] += 1
                if calls["n"] == 3: raise SourceChangedError("moving")
            return real(root, session_dir)
        with patch("chat_distiller.gateway.core.DoubaoConnector.fingerprint", side_effect=moving):
            result = self.gateway.sync()
        self.assertIn("session-db", result["unstable_sessions"])
        self.assertNotIn("session-db", read_json(self.home / "state/sync.json")["sessions"])

    def test_context_works_before_semantic_distillation(self):
        self.connect_sync(); packet = self.gateway.context("PostgreSQL 数据库迁移", max_bytes=4096)
        self.assertEqual(packet["status"], "ready"); self.assertIsNone(packet["structured"])
        self.assertEqual(packet["raw_sessions"][0]["session_id"], "session-db")
        self.assertTrue(packet["requires_review"]); self.assertLessEqual(packet["used_bytes"], 4096)

    def test_context_generic_query_falls_back_to_recent_sessions(self):
        self.connect_sync(); packet = self.gateway.context("继续昨天的工作", max_bytes=4096, top_k=1)
        self.assertEqual(packet["status"], "ready"); self.assertEqual(len(packet["raw_sessions"]), 1)

    def test_apply_plan_initializes_managed_memory_and_clears_only_covered(self):
        sync = self.connect_sync()
        wrapper = {"gateway_schema_version": 1, "plan_sha256": sync["plan_sha256"],
                   "covered_sessions": ["session-db"], "retire_memory_ids": [], "distill": distill_for("session-db")}
        proposal = self.root / "proposal.json"; proposal.write_text(json.dumps(wrapper, ensure_ascii=False), encoding="utf-8")
        result = self.gateway.sync(apply=proposal)
        self.assertTrue(result["applied"]); self.assertEqual(result["pending_sessions"], 1)
        self.assertEqual(MemoryStore(self.home / "vault").inspect()["cards"], 1)
        packet = self.gateway.context("PostgreSQL", max_bytes=4096)
        self.assertIsNotNone(packet["structured"]); self.assertEqual(packet["structured"]["status"], "ready")

    def test_stale_plan_is_rejected(self):
        sync = self.connect_sync()
        wrapper = {"gateway_schema_version": 1, "plan_sha256": sync["plan_sha256"],
                   "covered_sessions": ["session-db"], "retire_memory_ids": [], "distill": distill_for("session-db")}
        proposal = self.root / "proposal.json"; proposal.write_text(json.dumps(wrapper), encoding="utf-8")
        path = self.sessions / "session-db/agents/agent-1/system/assignment.md"
        path.write_text(path.read_text() + "\nchanged", encoding="utf-8"); self.gateway.sync()
        with self.assertRaises(GatewayError): self.gateway.sync(apply=proposal)
        self.assertFalse((self.home / "vault/对话沉淀/.chat-distiller/distill.json").exists())

    def test_update_cannot_retire_identity_without_explicit_list(self):
        sync = self.connect_sync()
        first = {"gateway_schema_version": 1, "plan_sha256": sync["plan_sha256"],
                 "covered_sessions": ["session-db"], "retire_memory_ids": [], "distill": distill_for("session-db")}
        p1 = self.root / "p1.json"; p1.write_text(json.dumps(first), encoding="utf-8"); self.gateway.sync(apply=p1)
        assignment = self.sessions / "session-db/agents/agent-1/system/assignment.md"
        assignment.write_text(assignment.read_text() + "\n## [2026-10-03T01:00:00Z] 需求\n\n更新。\n", encoding="utf-8")
        s2 = self.gateway.sync()
        published = json.loads((self.home / "vault/对话沉淀/.chat-distiller/distill.json").read_text())
        candidate = copy.deepcopy(published); candidate["conversations"][0]["cards"] = []
        second = {"gateway_schema_version": 1, "plan_sha256": s2["plan_sha256"],
                  "covered_sessions": ["session-db"], "retire_memory_ids": [], "distill": candidate}
        p2 = self.root / "p2.json"; p2.write_text(json.dumps(second), encoding="utf-8")
        with self.assertRaises(GatewayError): self.gateway.sync(apply=p2)
        self.assertEqual(MemoryStore(self.home / "vault").inspect()["cards"], 1)

    def test_status_is_observable_before_and_after_publish(self):
        sync = self.connect_sync(); before = self.gateway.status()
        self.assertEqual(before["pending_sessions"], 2); self.assertFalse(before["memory"]["available"])
        wrapper = {"gateway_schema_version": 1, "plan_sha256": sync["plan_sha256"],
                   "covered_sessions": ["session-db"], "retire_memory_ids": [], "distill": distill_for("session-db")}
        p = self.root / "proposal.json"; p.write_text(json.dumps(wrapper, encoding="utf-8") if False else json.dumps(wrapper), encoding="utf-8")
        self.gateway.sync(apply=p); after = self.gateway.status()
        self.assertTrue(after["memory"]["available"]); self.assertTrue(after["memory"]["ok"]); self.assertEqual(after["pending_sessions"], 1)

    def test_handoff_no_match_is_not_budget_exhausted(self):
        # A published memory source can legitimately have no evidence for a query.
        sync = self.connect_sync()
        wrapper = {"gateway_schema_version": 1, "plan_sha256": sync["plan_sha256"],
                   "covered_sessions": ["session-db"], "retire_memory_ids": [], "distill": distill_for("session-db")}
        proposal = self.root / "handoff-source.json"
        proposal.write_text(json.dumps(wrapper, ensure_ascii=False), encoding="utf-8")
        self.gateway.sync(apply=proposal)
        import shutil
        shutil.rmtree(self.sessions / "session-db")
        shutil.rmtree(self.sessions / "session-ui")
        self.gateway.sync()
        packet = self.gateway.context("galaxywalrusbutterknife", max_bytes=4096)
        self.assertEqual(packet["structured"]["status"], "no_match")
        self.assertEqual(packet["raw_sessions"], [])
        self.assertEqual(packet["status"], "no_match")

    def test_handoff_matching_raw_excludes_unrelated_sessions(self):
        # A lexical hit should not be padded with zero-score sessions.
        self.connect_sync()
        packet = self.gateway.context("PostgreSQL", max_bytes=8192, top_k=5)
        self.assertEqual(packet["status"], "ready")
        self.assertEqual([s["session_id"] for s in packet["raw_sessions"]], ["session-db"])
        self.assertEqual(packet["raw_sessions"][0]["selection_basis"], "lexical_match")

    def test_handoff_unmatched_recent_fallback_is_disclosed(self):
        # Backwards-compatible recent fallback must not masquerade as query relevance.
        self.connect_sync()
        packet = self.gateway.context("galaxywalrusbutterknife", max_bytes=4096, top_k=1)
        self.assertEqual(packet["status"], "ready")
        self.assertTrue(packet["requires_review"])
        self.assertEqual(packet["raw_sessions"][0]["score"], 0)
        self.assertEqual(packet["raw_sessions"][0]["selection_basis"], "recent_fallback")
        self.assertTrue(any("no lexical match" in note for note in packet["notes"]))

    def test_handoff_oversized_relevant_raw_must_not_fall_back_to_irrelevant(self):
        self.connect_sync()
        make_session(self.sessions, "session-large",
                     "uniquehandoffneedle " + "X" * 5000, "Some long source details " + "Y" * 5000)
        self.gateway.sync()
        packet = self.gateway.context("uniquehandoffneedle", max_bytes=1024, top_k=1)
        self.assertEqual(packet["raw_sessions"], [])
        self.assertEqual(packet["status"], "budget_exhausted")

    def test_context_budget_validation(self):
        self.connect_sync()
        for bad in (0, 1023, True, 1.2):
            with self.subTest(bad=bad), self.assertRaises(GatewayError):
                self.gateway.context("db", max_bytes=bad)


if __name__ == "__main__":
    unittest.main()
