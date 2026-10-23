"""Adversarial knowledge lifecycle tests. All data is synthetic and disposable."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from chat_distiller import (KnowledgeStore, MemoryStore, WikiIntegrityError, StaleProposalError,
                            WikiBusyError, CommitUncertainError, serialize_packet)
from chat_distiller._internal.memory_identity import prepare
from chat_distiller._internal.render_notes import safe_filename
from chat_distiller.wiki.contracts import canonical, digest, strict_json

ROOT = Path(__file__).resolve().parents[1]


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.vault = self.root / "vault"
        self.vault.mkdir()
        self.source = self.root / "source.json"
        self.data, _ = prepare(json.loads((ROOT / "examples/recovery/distill.json").read_text(encoding="utf-8")), safe_filename)
        self.render()
        self.store = KnowledgeStore(self.vault)

    def command(self, *args):
        return subprocess.run([sys.executable, "-m", "chat_distiller", *map(str, args)],
                              cwd=ROOT, capture_output=True, text=True, timeout=30)

    def render(self):
        self.source.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
        output = self.command("render", "--vault", self.vault, "--distill", self.source)
        self.assertEqual(output.returncode, 0, output.stdout + output.stderr)

    def proposal(self, topic="database", query="database"):
        return self.store.prepare(topic, query, title="Database architecture")

    def publish(self):
        proposal = self.proposal()
        return self.store.compile(proposal, apply=True)

    def snapshot(self):
        return {str(p.relative_to(self.vault)): p.read_bytes() for p in self.vault.rglob("*") if p.is_file()}

    def change_memory(self):
        self.data["conversations"][1]["cards"][0]["body"] = "Use PostgreSQL for the database and preserve the existing API."
        self.render()

    def write_state(self, state):
        self.store.storage.path.write_text(canonical({"payload": state, "sha256": digest(state)}), encoding="utf-8")

    def test_prepare_and_validate_do_not_write(self):
        before = self.snapshot()
        p = self.proposal()
        receipt = self.store.compile(p)
        self.assertFalse(receipt["applied"])
        self.assertNotIn("knowledge_id", receipt)
        self.assertEqual(before, self.snapshot())
        self.assertFalse(self.store.storage.root.exists())

    def test_creation_public_api_and_stable_identity(self):
        result = self.publish()
        self.assertEqual(result["operation"], "create")
        self.assertTrue(result["knowledge_id"].startswith("kn_"))
        self.assertEqual(self.store.status()["fresh"], 1)
        self.assertEqual(self.store.get("database")["revision"], 1)

    def test_repeat_is_byte_identical_no_log_growth(self):
        p = self.proposal()
        self.store.compile(p, apply=True)
        before = self.snapshot()
        self.assertEqual(self.store.compile(p, apply=True)["operation"], "no_change")
        refreshed = self.proposal()
        self.assertEqual(self.store.compile(refreshed, apply=True)["operation"], "no_change")
        self.assertEqual(before, self.snapshot())

    def test_update_keeps_id_and_history(self):
        old = self.publish()
        self.change_memory()
        result = self.store.compile(self.proposal(), apply=True)
        self.assertEqual(result["operation"], "update")
        self.assertEqual(result["knowledge_id"], old["knowledge_id"])
        self.assertEqual(result["page_revision"], 2)
        archive = self.store.get("database", revision=1, allow_stale=True)
        self.assertTrue(archive["archived"])
        self.assertEqual(archive["freshness"], "stale")
        self.assertIn("SQLite", canonical(archive))
        self.assertEqual(self.store.status()["fresh"], 1)

    def test_old_revision_same_source_requires_explicit_inspection(self):
        self.publish()
        p = self.proposal(); p["title"] = "Renamed database"
        self.store.compile(p, apply=True)
        with self.assertRaises(StaleProposalError):
            self.store.get("database", revision=1)
        self.assertTrue(self.store.get("database", revision=1, allow_stale=True)["archived"])

    def test_stale_pages_do_not_serve_current_or_history(self):
        self.publish(); self.change_memory()
        self.assertEqual(self.store.search("database"), [])
        self.assertEqual(self.store.search("database", intent="historical"), [])
        with self.assertRaises(StaleProposalError):
            self.store.get("database")
        self.assertEqual(self.store.status()["pages"][0]["reason"], "dependency_changed")

    def test_unrelated_addition_also_requires_scope_review(self):
        self.publish()
        self.data["conversations"][1]["cards"].append({"kind": "fact", "title": "Gardening", "body": "Water the plants."})
        self.data, _ = prepare(self.data, safe_filename)
        self.render()
        row = self.store.status()["pages"][0]
        self.assertEqual(row["freshness"], "stale")
        self.assertEqual(row["changed_dependencies"], [])
        self.assertEqual(row["reason"], "source_changed_review_scope")

    def test_source_addition_new_dispute_is_not_missed(self):
        self.publish()
        self.data["conversations"][1]["cards"].append({"kind": "decision", "title": "Database doubt", "body": "Database selection is contested.", "status": "有争议"})
        self.data, _ = prepare(self.data, safe_filename)
        self.render()
        self.assertEqual(self.store.status()["stale"], 1)
        p = self.proposal()
        self.assertEqual(len(p["scope"]), 4)
        self.store.compile(p, apply=True)
        self.assertEqual(sum(c["status"] == "disputed" for c in self.store.search("database")[0]["claims"]), 2)

    def test_changed_status_invalidates_page(self):
        self.publish()
        self.data["conversations"][1]["cards"][0]["status"] = "有争议"
        self.render()
        self.assertEqual(self.store.status()["stale"], 1)

    def test_obsolete_source_proposal_rejected_without_mutation(self):
        p = self.proposal(); self.change_memory(); before = self.snapshot()
        with self.assertRaises(StaleProposalError):
            self.store.compile(p, apply=True)
        self.assertEqual(before, self.snapshot())

    def test_obsolete_wiki_proposal_cannot_overwrite(self):
        self.publish()
        a = self.proposal(); b = copy.deepcopy(a)
        a["title"] = "A"; b["title"] = "B"
        self.store.compile(a, apply=True); before = self.snapshot()
        with self.assertRaises(StaleProposalError):
            self.store.compile(b, apply=True)
        self.assertEqual(before, self.snapshot())

    def test_invalid_memory_id_rejected(self):
        p = self.proposal(); p["claims"][0]["evidence"][0]["memory_id"] = "mem_" + "0" * 32
        with self.assertRaises(ValueError):
            self.store.compile(p, apply=True)
        self.assertFalse(self.store.storage.root.exists())

    def test_wiki_pages_cannot_ground_other_pages(self):
        p = self.proposal(); p["claims"][0]["evidence"][0]["memory_id"] = "kn_" + "a" * 32
        with self.assertRaises(ValueError):
            self.store.compile(p)

    def test_fake_quote_rejected(self):
        p = self.proposal(); p["claims"][0]["evidence"][0]["quote"] = "Invented quotation from nowhere"
        with self.assertRaisesRegex(ValueError, "quote is absent"):
            self.store.compile(p)

    def test_quote_from_wrong_card_rejected(self):
        p = self.proposal()
        p["claims"][0]["evidence"][0]["quote"] = p["claims"][1]["text"]
        with self.assertRaises(ValueError):
            self.store.compile(p)

    def test_known_dispute_cannot_be_omitted(self):
        p = self.proposal(); p["claims"] = [c for c in p["claims"] if c["status"] != "disputed"]
        with self.assertRaisesRegex(ValueError, "all scoped"):
            self.store.compile(p)

    def test_scope_shrinking_cannot_hide_lexically_selected_dispute(self):
        p = self.proposal()
        dispute = next(c for c in p["claims"] if c["status"] == "disputed")
        p["claims"].remove(dispute); p["scope"].remove(dispute["evidence"][0]["memory_id"])
        with self.assertRaisesRegex(ValueError, "scope differs"):
            self.store.compile(p)

    def test_existing_scope_preserved_when_query_changes(self):
        self.publish()
        p = self.store.prepare("database", "SQLite")
        self.assertEqual(len(p["scope"]), 3)

    def test_status_laundering_rejected(self):
        for old in ("historical", "disputed"):
            p = self.proposal()
            next(c for c in p["claims"] if c["status"] == old)["status"] = "current"
            with self.assertRaisesRegex(ValueError, "status"):
                self.store.compile(p)

    def test_extract_cannot_paraphrase(self):
        p = self.proposal(); p["claims"][0]["text"] = "A new assertion."
        with self.assertRaisesRegex(ValueError, "extract"):
            self.store.compile(p)

    def test_synthesis_is_supported_but_not_semantically_verified(self):
        p = self.proposal()
        claim = next(c for c in p["claims"] if c["status"] == "current")
        claim["origin"] = "synthesis"; claim["text"] = "The prototype retains its API while using SQLite locally."
        self.assertTrue(self.store.compile(p, apply=True)["requires_review"])
        self.assertTrue(self.store.search("prototype")[0]["requires_review"])

    def test_false_paraphrase_can_pass_and_is_explicitly_review_required(self):
        # Negative capability test: IDs/quotes do NOT establish entailment.
        p = self.store.prepare("narrow", "SQLite")
        self.assertEqual(len(p["claims"]), 1)
        claim = next(c for c in p["claims"] if c["status"] == "current")
        claim["origin"] = "synthesis"; claim["text"] = "The database uses a quantum computer on Mars."
        receipt = self.store.compile(p)
        self.assertTrue(receipt["requires_review"])
        self.assertIn("not_entailment", receipt["validation"])

    def test_inference_marked_for_review(self):
        p = self.proposal(); p["claims"][0]["origin"] = "inference"
        self.assertTrue(self.store.compile(p)["requires_review"])

    def test_unknown_fields_rejected(self):
        p = self.proposal(); p["automatic_truth"] = True
        with self.assertRaises(ValueError):
            self.store.compile(p)

    def test_duplicate_claims_rejected(self):
        p = self.proposal(); p["claims"].append(copy.deepcopy(p["claims"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate claim"):
            self.store.compile(p)

    def test_empty_scope_no_match_and_bad_topic(self):
        for topic, query in (("database", "zzzxxyy"), ("../escape", "database"), ("UPPER", "database")):
            with self.assertRaises(ValueError):
                self.store.prepare(topic, query)

    def test_current_search_omits_history_but_preserves_dispute(self):
        self.publish()
        self.assertEqual({c["status"] for c in self.store.search("database")[0]["claims"]}, {"current", "disputed"})
        self.assertEqual({c["status"] for c in self.store.search("database", intent="historical")[0]["claims"]}, {"current", "historical", "disputed"})

    def test_no_match_is_explicit(self):
        self.publish()
        self.assertEqual(self.store.search("zzzxxyy"), [])
        self.assertEqual(self.store.recover("zzzxxyy")["status"], "no_match")

    def test_current_page_with_only_historical_claims_not_returned(self):
        for cv in self.data["conversations"]:
            for card in cv["cards"]:
                card["status"] = "已过期"
        self.render(); self.publish()
        self.assertEqual(self.store.search("database"), [])
        self.assertEqual(len(self.store.search("database", intent="historical")), 1)

    def test_layered_recovery_has_complete_scoped_current_claims(self):
        self.publish()
        packet = self.store.recover("database", max_bytes=20000)
        self.assertEqual(packet["status"], "ready")
        page = packet["knowledge"][0]
        self.assertEqual({c["status"] for c in page["claims"]}, {"current", "disputed"})
        ids = {r["memory_id"] for r in page["evidence_memories"]}
        self.assertEqual(ids, {e["memory_id"] for c in page["claims"] for e in c["evidence"]})
        self.assertEqual(packet["memories"], [])

    def test_utf8_budget_is_exact(self):
        self.publish()
        for budget in (900, 1200, 1800, 4096, 8192):
            packet = self.store.recover("database 数据库", max_bytes=budget)
            self.assertEqual(packet["used_bytes"], len(serialize_packet(packet).encode("utf-8")))
            self.assertLessEqual(packet["used_bytes"], budget)
            for page in packet["knowledge"]:
                self.assertEqual(len(page["claims"]), 2)

    def test_budget_exhausted_differs_from_no_match(self):
        self.publish()
        packet = self.store.recover("database", max_bytes=800)
        self.assertEqual(packet["status"], "budget_exhausted")
        self.assertEqual(packet["knowledge"], [])
        self.assertEqual(packet["memories"], [])

    def test_stale_wiki_falls_back_to_updated_atomic_memory(self):
        self.publish(); self.change_memory()
        packet = self.store.recover("database")
        self.assertEqual(packet["stale_pages_excluded"], 1)
        self.assertEqual(packet["knowledge"], [])
        self.assertIn("PostgreSQL", canonical(packet["memories"]))
        self.assertTrue(packet["requires_review"])

    def test_no_wiki_can_use_atomic_fallback_without_initializing(self):
        packet = self.store.recover("database")
        self.assertTrue(packet["memories"])
        self.assertFalse(self.store.storage.root.exists())

    def test_legacy_recovery_contract_unchanged(self):
        old = MemoryStore(self.vault).recover("database")
        self.publish()
        self.assertEqual(old, MemoryStore(self.vault).recover("database"))
        self.assertEqual(old["schema_version"], 1)

    def test_read_operations_do_not_mutate(self):
        self.publish(); before = self.snapshot()
        self.store.search("database"); self.store.get("database"); self.store.status(); self.store.recover("database")
        self.assertEqual(before, self.snapshot())

    def test_return_mutation_does_not_change_store(self):
        self.publish()
        page = self.store.get("database"); page["proposal"]["title"] = "tamper"
        self.assertNotEqual(self.store.get("database")["proposal"]["title"], "tamper")

    def test_corrupt_state_fails_closed(self):
        self.publish(); self.store.storage.path.write_text("broken", encoding="utf-8")
        for operation in (self.store.status, lambda: self.store.search("database"), lambda: self.store.recover("database")):
            with self.assertRaises(WikiIntegrityError):
                operation()

    def test_checksum_drift_rejected(self):
        self.publish()
        envelope = strict_json(self.store.storage.path.read_text(encoding="utf-8"))
        envelope["payload"]["pages"]["database"][0]["proposal"]["title"] = "bad"
        self.store.storage.path.write_text(canonical(envelope), encoding="utf-8")
        with self.assertRaises(WikiIntegrityError):
            self.store.status()

    def test_log_drift_rejected_even_with_new_checksum(self):
        self.publish(); state = self.store.storage.read(); state["log"][0]["page_revision"] = 100
        self.write_state(state)
        with self.assertRaises(WikiIntegrityError):
            self.store.status()

    def test_missing_authority_never_silently_resets(self):
        self.publish(); self.store.storage.path.unlink()
        with self.assertRaises(WikiIntegrityError):
            self.store.prepare("database", "database")

    def test_state_symlink_rejected(self):
        self.publish(); content = self.store.storage.path.read_bytes()
        self.store.storage.path.unlink(); outside = self.root / "outside.json"; outside.write_bytes(content)
        self.store.storage.path.symlink_to(outside)
        with self.assertRaises(WikiIntegrityError):
            self.store.status()

    def test_atomic_memory_corruption_cannot_be_bypassed_by_wiki(self):
        self.publish()
        (self.vault / "对话沉淀/知识索引.jsonl").write_text("bad", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.store.recover("database")

    def test_duplicate_json_keys_rejected(self):
        for data in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}'):
            with self.assertRaises(ValueError):
                strict_json(data)

    def test_pre_replace_failure_preserves_authority(self):
        self.publish(); before = self.snapshot(); p = self.proposal(); p["title"] = "Update"
        with patch("chat_distiller.wiki.storage.os.replace", side_effect=OSError("injected replace failure")):
            with self.assertRaises(OSError):
                self.store.compile(p, apply=True)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.store.status()["wiki_revision"], 1)

    def test_pre_fsync_failure_preserves_authority(self):
        self.publish(); before = self.snapshot(); p = self.proposal(); p["title"] = "Update"
        with patch("chat_distiller.wiki.storage.os.fsync", side_effect=OSError("injected flush failure")):
            with self.assertRaises(OSError):
                self.store.compile(p, apply=True)
        self.assertEqual(before, self.snapshot())

    @unittest.skipUnless(os.name == "posix", "directory fsync is POSIX-specific")
    def test_post_replace_durability_failure_is_explicit(self):
        self.publish(); p = self.proposal(); p["title"] = "Update"
        with patch("chat_distiller.wiki.storage.os.fsync", side_effect=[None, OSError("directory sync failed")]):
            with self.assertRaises(CommitUncertainError):
                self.store.compile(p, apply=True)
        self.assertEqual(self.store.status()["wiki_revision"], 2)
        self.assertEqual(self.store.compile(p, apply=True)["operation"], "no_change")

    def test_first_publication_failure_can_retry_without_resetting_existing_state(self):
        p = self.proposal()
        with patch("chat_distiller.wiki.storage.os.replace", side_effect=OSError("failure")):
            with self.assertRaises(OSError):
                self.store.compile(p, apply=True)
        self.assertFalse(self.store.storage.root.exists())
        self.assertTrue(self.store.compile(p, apply=True)["applied"])

    def test_existing_lock_never_stolen(self):
        self.publish(); p = self.proposal(); p["title"] = "Update"
        self.store.storage.lock.write_text("unknown writer", encoding="utf-8")
        with self.assertRaises(WikiBusyError):
            self.store.compile(p, apply=True)
        self.assertEqual(self.store.storage.lock.read_text(encoding="utf-8"), "unknown writer")

    def test_source_changes_at_last_check_do_not_publish(self):
        self.publish(); before = self.snapshot(); p = self.proposal(); p["title"] = "Update"
        original = self.store.memory._snapshot
        calls = [0]
        def changing():
            rows, source = original(); calls[0] += 1
            return rows, "0" * 64 if calls[0] == 4 else source
        with patch.object(self.store.memory, "_snapshot", side_effect=changing):
            with self.assertRaises(StaleProposalError):
                self.store.compile(p, apply=True)
        self.assertEqual(before, self.snapshot())

    def test_related_pages_and_export_backlinks(self):
        self.publish()
        p = self.proposal("operations"); p["related_topics"] = ["database"]
        self.store.compile(p, apply=True)
        target = self.root / "export"
        self.store.export(target)
        self.assertTrue((target / "index.md").exists())
        self.assertTrue((target / "log.md").exists())
        original = self.store.get("database")["knowledge_id"]
        self.assertIn("operations", (target / (original + ".md")).read_text(encoding="utf-8"))
        manifest = strict_json((target / "manifest.json").read_text(encoding="utf-8"))
        for filename, expected in manifest["files"].items():
            self.assertEqual(hashlib.sha256((target / filename).read_bytes()).hexdigest(), expected)

    def test_missing_related_page_rejected(self):
        p = self.proposal(); p["related_topics"] = ["unknown"]
        with self.assertRaisesRegex(ValueError, "related topic"):
            self.store.compile(p)

    def test_export_is_snapshot_not_authority(self):
        self.publish(); before = self.snapshot(); target = self.root / "export"
        self.store.export(target)
        for file in target.glob("*.md"):
            file.write_text("edited exported view", encoding="utf-8")
        self.assertEqual(before, self.snapshot())
        self.assertTrue(self.store.search("database"))

    def test_export_never_overwrites_existing_directory(self):
        self.publish(); target = self.root / "export"; target.mkdir()
        marker = target / "user.md"; marker.write_text("user", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.store.export(target)
        self.assertEqual(marker.read_text(encoding="utf-8"), "user")

    def test_export_inside_managed_memory_rejected(self):
        self.publish()
        with self.assertRaises(ValueError):
            self.store.export(self.store.memory.base / "new-wiki")

    def test_export_stale_page_is_clearly_marked(self):
        self.publish(); self.change_memory(); target = self.root / "export"
        self.store.export(target)
        self.assertIn("stale", (target / "index.md").read_text(encoding="utf-8"))

    def test_cli_prepare_compile_recover_get_and_status(self):
        p = self.command("wiki", "prepare", "--vault", self.vault, "--topic", "database", "--query", "database")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        path = self.root / "proposal.json"; path.write_text(p.stdout, encoding="utf-8")
        for extra in ([], ["--apply"]):
            r = self.command("wiki", "compile", "--vault", self.vault, "--proposal", path, *extra)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for name in ("status", "lint", "get", "recover", "search", "export"):
            extra = {"get": ["--topic", "database"], "recover": ["--query", "database"],
                     "search": ["--query", "database"], "export": ["--out", self.root / "export"]}.get(name, [])
            output = self.command("wiki", name, "--vault", self.vault, *extra)
            self.assertEqual(output.returncode, 0, output.stdout + output.stderr)
            json.loads(output.stdout)
            if name == "recover":
                self.assertEqual(output.stdout, serialize_packet(self.store.recover("database")))

    def test_cli_rejects_invalid_json_with_no_mutation(self):
        path = self.root / "bad.json"; path.write_text('{"topic":"a","topic":"b"}', encoding="utf-8")
        before = self.snapshot()
        r = self.command("wiki", "compile", "--vault", self.vault, "--proposal", path, "--apply")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(json.loads(r.stdout)["results"], [])
        self.assertEqual(before, self.snapshot())

    def test_two_process_writers_cannot_lose_updates(self):
        self.publish()
        paths = []
        for title in ("Concurrent A", "Concurrent B"):
            p = self.proposal(); p["title"] = title
            file = self.root / (title[-1] + ".json"); file.write_text(canonical(p), encoding="utf-8"); paths.append(file)
        processes = [subprocess.Popen([sys.executable, "-m", "chat_distiller", "wiki", "compile", "--vault", str(self.vault),
                                       "--proposal", str(p), "--apply"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for p in paths]
        outputs = [p.communicate(timeout=30) for p in processes]
        self.assertEqual(sorted(p.returncode for p in processes), [0, 1], outputs)
        self.assertEqual(self.store.status()["wiki_revision"], 2)

    def test_bad_recovery_arguments(self):
        for kwargs in ({"max_bytes": 10}, {"max_bytes": True}, {"top_k": 0}, {"intent": "automatic"}):
            with self.assertRaises(ValueError):
                self.store.recover("database", **kwargs)

    def test_lock_cleanup_failure_after_publish_is_explicit(self):
        self.publish(); p = self.proposal(); p["title"] = "Update"
        original = Path.unlink
        def fail_lock(path, *args, **kwargs):
            if path == self.store.storage.lock:
                raise OSError("injected lock cleanup failure")
            return original(path, *args, **kwargs)
        with patch.object(Path, "unlink", fail_lock):
            with self.assertRaises(CommitUncertainError):
                self.store.compile(p, apply=True)
        self.assertEqual(self.store.status()["wiki_revision"], 2)
        self.assertTrue(self.store.storage.lock.exists())

    def _process_exit_at_replace(self, after):
        self.publish(); p = self.proposal(); p["title"] = "After interruption"
        file = self.root / "interrupted.json"; file.write_text(canonical(p), encoding="utf-8")
        code = """import json, os, sys
from chat_distiller import KnowledgeStore
import chat_distiller.wiki.storage as storage
real = storage.os.replace
def stop(a, b):
    if sys.argv[3] == 'after':
        real(a, b)
    os._exit(91)
storage.os.replace = stop
KnowledgeStore(sys.argv[1]).compile(json.load(open(sys.argv[2])), apply=True)
"""
        result = subprocess.run([sys.executable, "-c", code, str(self.vault), str(file), "after" if after else "before"], cwd=ROOT, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 91)
        self.assertEqual(self.store.status()["wiki_revision"], 2 if after else 1)
        self.assertTrue(self.store.storage.lock.exists())
        self.assertTrue(self.store.search("database"))

    def test_process_exit_before_publication_keeps_old_snapshot(self):
        self._process_exit_at_replace(False)

    def test_process_exit_after_publication_keeps_new_snapshot(self):
        self._process_exit_at_replace(True)
