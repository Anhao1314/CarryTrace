"""Guard the frozen Gateway benchmark from silent rebaselining."""
import unittest

from tools.verify_gateway_delta import compare


class GatewayDeltaAuditTests(unittest.TestCase):
    def setUp(self):
        self.original = {"context_used_bytes": 1241, "context_budget_bytes": 4096,
                         "context_status": "ready", "context_top_session": "db",
                         "source_cache_unchanged": True}

    def test_only_smaller_packet_with_unmodified_other_fields_passes(self):
        candidate = dict(self.original, context_used_bytes=892)
        observed = compare(self.original, candidate)
        self.assertTrue(observed["ok"])
        self.assertEqual(observed["byte_delta"], -349)
        self.assertEqual(observed["unchanged_fields"], 4)

    def test_unrelated_metric_drift_is_rejected(self):
        candidate = dict(self.original, context_used_bytes=892, context_top_session="fallback")
        with self.assertRaisesRegex(ValueError, "outside audited bytes"):
            compare(self.original, candidate)

    def test_packet_increase_or_equal_size_is_rejected(self):
        for size in (1241, 1242):
            with self.subTest(size=size), self.assertRaises(ValueError):
                compare(self.original, dict(self.original, context_used_bytes=size))


if __name__ == "__main__":
    unittest.main()
