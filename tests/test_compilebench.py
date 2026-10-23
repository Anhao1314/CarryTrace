"""Regression checks for executed engineering evidence, not model accuracy."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("compilebench", ROOT / "benchmarks/wiki/evaluate.py")
bench = importlib.util.module_from_spec(spec); spec.loader.exec_module(bench)


class CompileBenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = bench.evaluate()

    def test_recorded_result_is_reproducible(self):
        self.assertEqual(self.result, json.loads((ROOT / "benchmarks/wiki/results.json").read_text(encoding="utf-8")))
        self.assertEqual(bench.markdown(self.result), (ROOT / "benchmarks/wiki/results.md").read_text(encoding="utf-8"))

    def test_freshness_ablation_exposes_failure(self):
        self.assertEqual(self.result["summary"]["stale_served_gate_disabled"], 4)
        self.assertEqual(self.result["summary"]["stale_served_gate_enabled"], 0)

    def test_invalid_proposals_and_budget_cases_pass(self):
        summary = self.result["summary"]
        self.assertEqual(summary["invalid_proposals_blocked"], summary["invalid_proposals_total"])
        self.assertEqual(summary["exact_budget_passes"], summary["exact_budget_total"])
        self.assertEqual(summary["failures"], [])

    def test_lifecycle_checks_cover_all_topics(self):
        self.assertEqual(len(self.result["cases"]), 4)
        for case in self.result["cases"]:
            self.assertTrue(case["repeat_byte_identical"])
            self.assertTrue(case["identity_preserved_after_refresh"])
            self.assertTrue(case["old_revision_inspectable"])

    def test_limits_do_not_claim_model_accuracy(self):
        self.assertIn("no model calls", self.result["data"])
        self.assertTrue(any("false synthesis" in limitation for limitation in self.result["limits"]))
