"""Committed RAG benchmark: status filtering removes stale evidence, not coverage."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("rag_bench", ROOT / "benchmarks/rag/evaluate.py")
rag_bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rag_bench)


class RagBenchmarkTests(unittest.TestCase):
    def test_status_aware_context_has_no_stale_evidence(self):
        report = rag_bench.evaluate()
        blind = report["methods"]["status_blind_evidence"]
        aware = report["methods"]["status_aware_context"]
        self.assertGreater(blind["stale_evidence_hits"], 0)
        self.assertEqual(aware["stale_evidence_hits"], 0)
        self.assertEqual(aware["stale_query_rate"], 0.0)
        self.assertEqual(aware["current_evidence_ratio"], 1.0)
        self.assertEqual(aware["expected_claim_coverage"], 1.0)
        self.assertEqual(blind["expected_claim_coverage"], 1.0)
        for case in report["cases"]:
            self.assertEqual(case["status_aware_context"]["stale_claim_ids"], [])

    def test_committed_report_matches_the_benchmark(self):
        committed = json.loads((ROOT / "benchmarks/rag/results.json").read_text(encoding="utf-8"))
        self.assertEqual(committed, rag_bench.evaluate())


if __name__ == "__main__":
    unittest.main()
