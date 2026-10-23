"""Public API regression and fault-injection tests; synthetic data, no model calls."""
import contextlib
import copy
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from chat_distiller import MemoryStore, MemoryIntegrityError, MemoryNotFoundError, serialize_packet
from chat_distiller.cli import main as cli
from chat_distiller._internal import render_notes
from chat_distiller._internal.memory_identity import prepare, json_text
from chat_distiller._internal.query_memory import load_index, search


def fixture():
    """Handwritten cards, not an evaluation of automatic distillation."""
    return {"conversations": [{
        "session_id": "demo-session", "date": "2026-01-01", "title": "部署决策",
        "categories": ["技术开发/开发环境"], "summary": "部署从旧方案变更，超时仍有争议。",
        "cards": [
            {"kind": "decision", "title": "部署当前方案", "body": "部署使用本地 SQLite，保留旧 API。", "status": "现行"},
            {"kind": "decision", "title": "部署旧方案", "body": "部署旧方案使用云端服务。", "status": "已过期"},
            {"kind": "decision", "title": "部署超时争议", "body": "部署超时采用三十秒还是六十秒尚未决定。", "status": "有争议"},
        ]}]}


def publish(data, source, vault):
    source.write_text(json_text(data), encoding="utf-8")
    with patch.object(sys, "argv", ["render", "--distill", str(source), "--vault", str(vault)]), contextlib.redirect_stdout(io.StringIO()):
        render_notes.main()


class EngineTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.vault = self.root / "vault"
        self.vault.mkdir()
        self.source = self.root / "source.json"
        self.data, _ = prepare(fixture(), render_notes.safe_filename)
        self.cards = self.data["conversations"][0]["cards"]
        self.cards[1]["superseded_by"] = self.cards[0]["memory_id"]
        publish(self.data, self.source, self.vault)
        self.store = MemoryStore(self.vault)
        self.base = self.vault / "对话沉淀"

    def snapshot(self):
        return {str(p.relative_to(self.vault)): p.read_bytes() for p in self.vault.rglob("*") if p.is_file()}

    def note(self, index=0):
        return self.base / "知识卡片" / (self.cards[index]["note_name"] + ".md")

    def test_search_preserves_legacy_ranking(self):
        self.assertEqual(self.store.search("部署"), search(load_index(self.base), "部署"))

    def test_current_excludes_expired_and_marks_dispute(self):
        hits = self.store.search("部署")
        self.assertEqual({r["status"] for r in hits}, {"现行", "有争议"})
        self.assertEqual(hits[0]["status"], "现行")
        self.assertTrue(hits[1]["disputed"])

    def test_history_retains_supersession(self):
        hits = self.store.search("部署", intent="historical")
        old = next(r for r in hits if r["status"] == "已过期")
        self.assertEqual(old["superseded_by"], self.cards[0]["memory_id"])

    def test_get_returns_full_source_projection(self):
        row = self.store.get(self.cards[0]["memory_id"])
        self.assertIn("SQLite", row["body"])
        self.assertEqual(row["source_session"], "demo-session")

    def test_get_expired_is_explicit_inspection(self):
        self.assertEqual(self.store.get(self.cards[1]["memory_id"])["status"], "已过期")

    def test_get_unknown_does_not_guess(self):
        with self.assertRaises(MemoryNotFoundError):
            self.store.get("mem_" + "0" * 32)
        with self.assertRaises(ValueError):
            self.store.get("C01")

    def test_no_match_and_empty_query(self):
        self.assertEqual(self.store.search("zzzxxyy"), [])
        self.assertEqual(self.store.search(""), [])
        self.assertEqual(self.store.recover("zzzxxyy")["status"], "no_match")

    def test_inspect_counts_and_source_hash(self):
        out = self.store.inspect()
        self.assertEqual((out["cards"], out["conversations"]), (3, 1))
        self.assertEqual(out["statuses"], {"现行": 1, "已过期": 1, "有争议": 1})
        self.assertEqual(out["source_sha256"], hashlib.sha256((self.base / ".chat-distiller/distill.json").read_bytes()).hexdigest())

    def test_read_operations_do_not_mutate_vault(self):
        before = self.snapshot()
        self.store.search("部署"); self.store.inspect(); self.store.get(self.cards[0]["memory_id"]); self.store.recover("部署")
        self.assertEqual(before, self.snapshot())

    def test_caller_mutation_cannot_pollute_later_reads(self):
        row = self.store.get(self.cards[0]["memory_id"])
        row["body"] = "modified"
        row["categories"].append("corrupt")
        self.assertNotEqual(self.store.get(row["memory_id"])["body"], "modified")
        self.assertNotIn("corrupt", self.store.get(row["memory_id"])["categories"])

    def test_source_update_is_visible_without_reopening(self):
        self.cards[0]["body"] += " 已验证 WAL。"
        publish(self.data, self.source, self.vault)
        self.assertIn("WAL", self.store.get(self.cards[0]["memory_id"])["body"])

    def test_corrupt_index_fails_after_prior_success(self):
        self.store.search("部署")
        (self.base / "知识索引.jsonl").write_text("{}\n", encoding="utf-8")
        for op in (lambda: self.store.search("部署"), self.store.inspect, lambda: self.store.recover("部署"), lambda: self.store.get(self.cards[0]["memory_id"])):
            with self.assertRaises(MemoryIntegrityError):
                op()

    def test_corrupt_registry_fails_closed(self):
        (self.base / ".chat-distiller/identity-registry.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(MemoryIntegrityError):
            self.store.inspect()

    def test_missing_source_fails_without_initializing(self):
        (self.base / ".chat-distiller/distill.json").unlink()
        before = self.snapshot()
        with self.assertRaises(MemoryIntegrityError):
            self.store.recover("部署")
        self.assertEqual(before, self.snapshot())

    def test_note_status_drift_is_rejected_by_old_and_new_query(self):
        p = self.note()
        p.write_text(p.read_text(encoding="utf-8").replace("status: 现行", "status: 已过期"), encoding="utf-8")
        with self.assertRaises(ValueError):
            load_index(self.base)
        with self.assertRaises(MemoryIntegrityError):
            self.store.search("部署")

    def test_note_kind_drift_is_rejected(self):
        p = self.note()
        p.write_text(p.read_text(encoding="utf-8").replace("kind: decision", "kind: fact"), encoding="utf-8")
        with self.assertRaises(MemoryIntegrityError):
            self.store.inspect()

    def test_missing_note_fails_closed(self):
        self.note().unlink()
        with self.assertRaises(MemoryIntegrityError):
            self.store.inspect()

    def test_source_change_during_read_is_rejected(self):
        real_load = load_index
        def changing(base):
            rows = real_load(base)
            path = self.base / ".chat-distiller/distill.json"
            path.write_bytes(path.read_bytes() + b"\n")
            return rows
        with patch("chat_distiller.store.load_index", side_effect=changing), self.assertRaises(MemoryIntegrityError):
            self.store.search("部署")

    def test_path_traversal_is_rejected(self):
        for sub in ("../other", "/tmp", "", ".", "a/../../outside", "..\\other"):
            with self.subTest(sub=sub), self.assertRaises(ValueError):
                MemoryStore(self.vault, subdir=sub)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_external_note_symlink_is_rejected(self):
        p = self.note()
        external = self.root / "external.md"
        external.write_bytes(p.read_bytes())
        p.unlink(); p.symlink_to(external)
        with self.assertRaises(MemoryIntegrityError):
            self.store.get(self.cards[0]["memory_id"])

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_external_state_symlink_is_rejected(self):
        p = self.base / ".chat-distiller/distill.json"
        external = self.root / "external.json"
        external.write_bytes(p.read_bytes())
        p.unlink(); p.symlink_to(external)
        with self.assertRaises(MemoryIntegrityError):
            self.store.inspect()

    def test_missing_vault_never_created(self):
        missing = self.root / "missing"
        with self.assertRaises(MemoryIntegrityError):
            MemoryStore(missing)
        self.assertFalse(missing.exists())

    def test_argument_validation(self):
        for k in (0, 101, True, 1.2, "5"):
            with self.subTest(k=k), self.assertRaises(ValueError):
                self.store.search("部署", top_k=k)
        with self.assertRaises(ValueError):
            self.store.search(None)
        with self.assertRaises(ValueError):
            self.store.search("部署", intent="automatic")

    def test_recovery_is_deterministic_and_keeps_evidence(self):
        a = self.store.recover("部署"); b = self.store.recover("部署")
        self.assertEqual(serialize_packet(a), serialize_packet(b))
        self.assertEqual(a["status"], "ready")
        self.assertTrue(a["requires_review"])
        self.assertEqual(a["memories"][0]["source_memory_id"], self.data["conversations"][0]["memory_id"])
        self.assertIn("not_instructions", a["trust"])

    def test_recovery_byte_budget_includes_unicode_and_metadata(self):
        for budget in (800, 1200, 1800, 4096, 8192):
            with self.subTest(budget=budget):
                packet = self.store.recover('部署 "规则"\n中文🙂', max_bytes=budget)
                wire = serialize_packet(packet).encode("utf-8")
                self.assertEqual(packet["used_bytes"], len(wire))
                self.assertLessEqual(len(wire), budget)
                json.loads(wire)

    def test_recovery_never_truncates_a_claim(self):
        packet = self.store.recover("部署", max_bytes=1600)
        for memory in packet["memories"]:
            self.assertEqual(memory["body"], self.store.get(memory["memory_id"])["body"])
        self.assertEqual(packet["omitted_count"], packet["candidates_in_window"] - len(packet["memories"]))

    def test_oversized_claim_can_be_skipped_for_smaller_candidate(self):
        self.cards[0]["body"] = "部署" * 2000
        publish(self.data, self.source, self.vault)
        packet = self.store.recover("部署", max_bytes=1800)
        self.assertEqual(len(packet["memories"]), 1)
        self.assertEqual(packet["memories"][0]["status"], "有争议")
        self.assertTrue(packet["requires_review"])

    def test_packet_limit_does_not_claim_all_candidates_returned(self):
        packet = self.store.recover("部署", top_k=1)
        self.assertEqual(len(packet["memories"]), 1)
        self.assertEqual(packet["omitted_count"], 1)

    def test_history_packet_marks_noncurrent_and_keeps_successor(self):
        packet = self.store.recover("部署", intent="historical")
        old = next(r for r in packet["memories"] if r["status"] == "已过期")
        self.assertFalse(old["is_current"])
        self.assertEqual(old["superseded_by"], self.cards[0]["memory_id"])

    def test_budget_exhausted_differs_from_no_match(self):
        packet = self.store.recover("部署", max_bytes=800)
        self.assertEqual(packet["status"], "budget_exhausted")
        self.assertEqual(packet["memories"], [])
        self.assertGreater(packet["candidates_in_window"], 0)

    def test_too_small_or_invalid_budget_rejected(self):
        for value in (0, True, 1.5, 256, 1048577):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.store.recover("部署", max_bytes=value)

    def test_cli_recovery_wire_matches_reported_budget(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = cli(["recover", "--vault", str(self.vault), "--query", "部署", "--max-bytes", "1800"])
        raw = output.getvalue()
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(raw)["used_bytes"], len(raw.encode("utf-8")))

    def test_cli_corruption_is_json_error_and_no_results(self):
        (self.base / "知识索引.jsonl").write_text("not JSON", encoding="utf-8")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = cli(["search", "--vault", str(self.vault), "--query", "部署"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.getvalue())["results"], [])
        self.assertNotIn("Traceback", output.getvalue())

    def test_cli_legacy_delegation_restores_argv(self):
        previous = sys.argv
        with contextlib.redirect_stdout(io.StringIO()):
            cli(["render", "--vault", str(self.vault), "--distill", str(self.source), "--dry-run"])
        self.assertIs(sys.argv, previous)

    def test_template_copy_stays_identical(self):
        self.assertEqual((ROOT / "references/taxonomy.template.md").read_bytes(), Path(render_notes.TEMPLATE_TAXONOMY).read_bytes())

    def test_import_does_not_change_path_or_load_legacy_global_names(self):
        code = "import sys; before=list(sys.path); import chat_distiller; assert before==sys.path; assert not ({'memory_identity','query_memory','render_notes','lint_notes'} & set(sys.modules))"
        proc = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
