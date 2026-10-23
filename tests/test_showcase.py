"""The product page stays consistent with the artifacts and benchmark reports."""
import json
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"


class _Refs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []
        self.ids = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(values["id"])
        for key in ("src", "href"):
            value = values.get(key)
            if not value:
                continue
            parsed = urlparse(value)
            if parsed.scheme or parsed.netloc or value.startswith("#") or value.startswith("mailto:"):
                continue
            self.refs.append(value.split("?")[0].split("#")[0])


def _row_metrics(html, label):
    for section in re.split(r'<div class="bench-row[^"]*">', html)[1:]:
        block = section.split("</div>", 1)[0]
        if label not in block:
            continue
        return re.findall(r"\d+\.\d+%|\d+\.\d{4}", re.sub(r"<[^>]+>", " ", block))
    raise AssertionError("missing benchmark row: " + label)


class ShowcaseTests(unittest.TestCase):
    def test_site_local_references_exist_and_ids_are_unique(self):
        parser = _Refs()
        parser.feed((SITE / "index.html").read_text(encoding="utf-8"))
        missing = [ref for ref in parser.refs if not (SITE / ref).exists()]
        self.assertEqual(missing, [])
        duplicates = sorted({item for item in parser.ids if parser.ids.count(item) > 1})
        self.assertEqual(duplicates, [])

    def test_site_benchmark_rows_match_the_committed_report(self):
        html = (SITE / "index.html").read_text(encoding="utf-8")
        report = json.loads((ROOT / "benchmarks/benchmark-results.json").read_text(encoding="utf-8"))
        labels = {
            "Raw transcript lexical": "Baseline",
            "Structured memory": "Structured Memory",
            "Structured + status-aware": "Status-aware Memory",
        }
        for label, key in labels.items():
            metrics = report["results"][key]["metrics"]
            expected = [
                f"{metrics['Recall@1'] * 100:.1f}%",
                f"{metrics['Recall@5'] * 100:.1f}%",
                f"{metrics['MRR']:.4f}",
                f"{metrics['stale-hit@5'] * 100:.1f}%",
            ]
            self.assertEqual(_row_metrics(html, label), expected, label)

    def test_gif_and_social_preview_exist_and_are_small(self):
        gif = ROOT / "assets/demo/claimledger-demo.gif"
        social = ROOT / "assets/demo/social-preview.png"
        self.assertTrue(gif.is_file())
        self.assertTrue(social.is_file())
        self.assertLess(gif.stat().st_size, 5 * 1024 * 1024)
        self.assertGreater(social.stat().st_size, 20 * 1024)
        self.assertTrue((SITE / "assets" / "claimledger-demo.gif").is_file())
        self.assertTrue((SITE / "assets" / "og.png").is_file())


if __name__ == "__main__":
    unittest.main()
