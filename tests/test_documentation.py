"""Documentation contracts; CLI execution also runs against installed wheels in CI."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("verify_docs", ROOT / "tools/verify_docs.py")
docs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docs)


class DocumentationTests(unittest.TestCase):
    def test_marked_example_extraction(self):
        self.assertEqual(docs.example("<!-- verify:a -->\n```bash\necho ok\n```", "a", "bash"), "echo ok")

    def test_missing_or_duplicate_marker_rejected(self):
        block = "<!-- verify:a -->\n```bash\necho ok\n```\n"
        for text in ("no example", block + block):
            with self.assertRaises(ValueError):
                docs.example(text, "a", "bash")

    def test_bilingual_examples_match(self):
        en, zh = [(ROOT / f).read_text(encoding="utf-8") for f in docs.README_FILES]
        for name, language in (("quickstart", "bash"), ("sdk", "python"), ("expected", "json"), ("wiki", "bash"), ("lifecycle", "bash"), ("lifecycle-expected", "json")):
            self.assertEqual(docs.example(en, name, language), docs.example(zh, name, language))

    def test_headings_and_explicit_anchors(self):
        text = '# Start\n## Start\n<a id="quick-start"></a>\n## 中文标题\n```text\n# Ignore\n```'
        self.assertEqual(docs.anchors(text), {"start", "start-1", "quick-start", "中文标题"})

    def test_local_links_and_external_accounting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.md").write_text('[ok](b.md#target) [web](https://example.com)\n```text\n[x](missing.md)\n```', encoding="utf-8")
            (root / "b.md").write_text("# Target\n", encoding="utf-8")
            self.assertEqual(docs.check_links(root, ["a.md"]), {"local_links_checked": 1, "external_links_not_fetched": 1})

    def test_missing_file_and_fragment_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "b.md").write_text("# Target", encoding="utf-8")
            for target in ("absent.md", "b.md#absent"):
                (root / "a.md").write_text(f'[broken]({target})', encoding="utf-8")
                with self.assertRaises(ValueError):
                    docs.check_links(root, ["a.md"])

    def test_traversal_and_executable_link_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for target in ("../outside.md", "javascript:alert"):
                (root / "a.md").write_text(f'[bad]({target})', encoding="utf-8")
                with self.assertRaises(ValueError):
                    docs.check_links(root, ["a.md"])

    def test_svg_is_static_and_generated_from_receipt(self):
        receipt = json.loads((ROOT / "examples/recovery/expected.json").read_text(encoding="utf-8"))
        svg = (ROOT / "assets/recovery-demo.svg").read_text(encoding="utf-8")
        self.assertEqual(svg, docs.demo_svg(receipt["cases"]))
        document = ET.fromstring(svg)
        self.assertEqual(document.attrib["role"], "img")
        self.assertFalse(any(el.tag.endswith(("script", "image", "foreignObject")) for el in document.iter()))

    def test_demo_fixture_uses_existing_identity_contract(self):
        from chat_distiller._internal.memory_identity import prepare, validate
        from chat_distiller._internal.render_notes import safe_filename
        data = json.loads((ROOT / "examples/recovery/distill.json").read_text(encoding="utf-8"))
        before = copy.deepcopy(data)
        registered, _ = prepare(data, safe_filename)
        validate(registered)
        self.assertEqual(data, before)
        old = registered["conversations"][0]["cards"][0]
        new = registered["conversations"][1]["cards"][0]
        self.assertEqual(old["superseded_by"], new["memory_id"])
        cards = [c for cv in registered["conversations"] for c in cv["cards"]]
        self.assertEqual({c["status"] for c in cards}, {"现行", "已过期", "有争议"})

    def test_display_projection_does_not_mutate_packet(self):
        packet = dict(status="ready", intent="current", memories=[{"status": "现行"}], used_bytes=700, budget_bytes=800, requires_review=False)
        before = copy.deepcopy(packet)
        projection = docs.summarize(packet)
        self.assertEqual(projection["memory_count"], 1)
        self.assertEqual(projection["expired_count"], 0)
        self.assertEqual(packet, before)


class WikiHomepageTests(unittest.TestCase):
    def test_bilingual_lifecycle_assets_match_checked_receipt(self):
        receipt = json.loads((ROOT / "examples/wiki/lifecycle.expected.json").read_text(encoding="utf-8"))
        for language, filename in (("en", "wiki-lifecycle.svg"), ("zh-CN", "wiki-lifecycle.zh-CN.svg")):
            svg = (ROOT / "assets" / filename).read_text(encoding="utf-8")
            self.assertEqual(svg, docs.lifecycle_svg(receipt, language))
            document = ET.fromstring(svg)
            self.assertEqual(document.attrib["role"], "img")
            self.assertEqual(document.attrib["lang"], language)
            self.assertFalse(any(el.tag.endswith(("script", "image", "foreignObject")) for el in document.iter()))
            self.assertNotIn("http:", svg.replace("http://www.w3.org/2000/svg", ""))

    def test_lifecycle_illustration_escapes_data_and_does_not_mutate_receipt(self):
        receipt = json.loads((ROOT / "examples/wiki/lifecycle.expected.json").read_text(encoding="utf-8"))
        receipt["published"]["current_value"] = '<SQLite & "prototype">'
        before = copy.deepcopy(receipt)
        svg = docs.lifecycle_svg(receipt)
        ET.fromstring(svg)
        self.assertIn("&lt;SQLite &amp; &quot;prototype&quot;&gt;", svg)
        self.assertEqual(receipt, before)

    def test_unsupported_language_or_identity_claim_rejected(self):
        receipt = json.loads((ROOT / "examples/wiki/lifecycle.expected.json").read_text(encoding="utf-8"))
        with self.assertRaises(ValueError):
            docs.lifecycle_svg(receipt, "invalid")
        receipt["refreshed"]["identity_preserved"] = False
        with self.assertRaises(ValueError):
            docs.lifecycle_svg(receipt)

    def test_homepage_metrics_match_reports(self):
        self.assertEqual(docs.check_evidence_tables(ROOT), {"metric_tables_checked": 4})

    def test_homepage_metric_drift_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = [*docs.README_FILES, "benchmarks/wiki/results.json", "benchmarks/benchmark-results.json"]
            for name in files:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / name).read_bytes())
            target = root / "README.md"
            original = target.read_text(encoding="utf-8")
            for old, new in (("16 / 16", "15 / 16"), ("0.7083", "0.9999")):
                target.write_text(original.replace(old, new, 1), encoding="utf-8")
                with self.assertRaises(AssertionError):
                    docs.check_evidence_tables(root)

    def test_wiki_preview_receipt_has_no_machine_specific_identifiers(self):
        receipt = json.loads((ROOT / "examples/wiki/lifecycle.expected.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["commands_executed"], 16)
        self.assertEqual(receipt["checks_passed"], 12)
        self.assertEqual(receipt["model_calls"], 0)
        self.assertNotIn("output_directory", receipt)
        self.assertNotIn("knowledge_id", receipt)
        self.assertNotIn("source_sha256", receipt)
        for name, digest in receipt["inputs_sha256"].items():
            import hashlib
            self.assertEqual(digest, hashlib.sha256((ROOT / name).read_bytes()).hexdigest())
