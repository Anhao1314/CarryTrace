#!/usr/bin/env python3
"""Status-filter benchmark for the RAG evidence adapter.

This is a structural benchmark, not a semantic retrieval evaluation: it uses the
checked-in lexical reference index and synthetic claims. It answers one narrow
question: does resolving evidence to claims and applying the lifecycle policy
remove superseded evidence without losing expected current/disputed evidence?

    python benchmarks/rag/evaluate.py
    python benchmarks/rag/evaluate.py --out benchmarks/rag/results.json \
        --markdown benchmarks/rag/results.md
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chat_distiller import ClaimStore, JsonlEvidenceIndex, StatusAwareRetriever
from chat_distiller.demo import scenario

FIXTURES = ROOT / "benchmarks" / "rag" / "fixtures.json"
EVIDENCE = ROOT / "examples" / "rag" / "evidence.jsonl"
TOP_K = 5


def _ratio(numerator, denominator):
    return round(numerator / denominator, 4) if denominator else None


def _coverage(expected, found):
    if not expected:
        return 1.0
    return round(len(set(expected) & set(found)) / len(expected), 4)


def evaluate():
    fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="claim-rag-bench-") as tmp:
        store_path = Path(tmp) / "claims.jsonl"
        scenario.seed(store_path)
        store = ClaimStore(store_path)
        rows = store.claims(status="all")
        by_id = {row["claim_id"]: row for row in rows}
        superseded = {row["claim_id"] for row in rows if row["status"] == "已过期"}
        index = JsonlEvidenceIndex(EVIDENCE)
        retriever = StatusAwareRetriever(store, index, max_per_claim=2, timeout=5)

        raw_stale_hits = 0
        raw_hits_total = 0
        raw_coverage = []
        raw_stale_queries = 0
        aware_stale_hits = 0
        aware_hits_total = 0
        aware_coverage = []
        aware_stale_queries = 0
        stale_excluded = 0
        per_claim_omitted = 0
        cases = []

        for case in fixtures["queries"]:
            expected = case["expected_claim_ids"]
            raw = index.search(case["query"], top_k=TOP_K)
            raw_ids = [hit.claim_id for hit in raw]
            raw_stale = [claim_id for claim_id in raw_ids if claim_id in superseded]
            raw_cov = _coverage(expected, raw_ids)
            raw_stale_hits += len(raw_stale)
            raw_hits_total += len(raw_ids)
            raw_coverage.append(raw_cov)
            raw_stale_queries += 1 if raw_stale else 0

            selection = retriever.retrieve(case["query"], top_k=TOP_K, intent="current")
            aware_ids = [hit["claim_id"] for hit in selection.hits]
            aware_stale = [claim_id for claim_id in aware_ids if claim_id in superseded]
            aware_cov = _coverage(expected, aware_ids)
            aware_stale_hits += len(aware_stale)
            aware_hits_total += len(aware_ids)
            aware_coverage.append(aware_cov)
            aware_stale_queries += 1 if aware_stale else 0
            stale_excluded += selection.stale_excluded
            per_claim_omitted += selection.per_claim_omitted

            cases.append({
                "query": case["query"],
                "expected_claim_ids": expected,
                "status_blind_evidence": {
                    "claim_ids": raw_ids,
                    "stale_claim_ids": raw_stale,
                    "expected_coverage": raw_cov,
                },
                "status_aware_context": {
                    "claim_ids": aware_ids,
                    "stale_claim_ids": aware_stale,
                    "expected_coverage": aware_cov,
                    "stale_excluded": selection.stale_excluded,
                    "per_claim_omitted": selection.per_claim_omitted,
                    "candidate_window": selection.candidate_window,
                    "attempts": selection.attempts,
                },
            })

        digest_input = FIXTURES.read_bytes() + EVIDENCE.read_bytes()
        return {
            "schema_version": 1,
            "suite": fixtures["suite"],
            "data": "synthetic claims; lexical reference evidence index; no model calls",
            "scope": "status filtering and evidence identity only, not semantic entailment or answer quality",
            "fixture_sha256": hashlib.sha256(digest_input).hexdigest(),
            "store_sha256": store.digest(rows),
            "queries": len(fixtures["queries"]),
            "top_k": TOP_K,
            "methods": {
                "status_blind_evidence": {
                    "evidence_hits": raw_hits_total,
                    "stale_evidence_hits": raw_stale_hits,
                    "stale_query_rate": _ratio(raw_stale_queries, len(fixtures["queries"])),
                    "expected_claim_coverage": _ratio(sum(raw_coverage), len(raw_coverage)),
                    "current_evidence_ratio": _ratio(raw_hits_total - raw_stale_hits, raw_hits_total),
                },
                "status_aware_context": {
                    "evidence_hits": aware_hits_total,
                    "stale_evidence_hits": aware_stale_hits,
                    "stale_query_rate": _ratio(aware_stale_queries, len(fixtures["queries"])),
                    "expected_claim_coverage": _ratio(sum(aware_coverage), len(aware_coverage)),
                    "current_evidence_ratio": _ratio(aware_hits_total - aware_stale_hits, aware_hits_total),
                    "stale_excluded": stale_excluded,
                    "per_claim_omitted": per_claim_omitted,
                },
            },
            "cases": cases,
            "limits": [
                "Synthetic claims and a lexical reference index; no embedding model.",
                "Expected-claim coverage is not semantic answer quality or entailment.",
                "A vector retriever may have different recall; re-run this benchmark with your adapter.",
            ],
        }


def markdown(report):
    blind = report["methods"]["status_blind_evidence"]
    aware = report["methods"]["status_aware_context"]
    lines = [
        "# RAG status-filter benchmark",
        "",
        report["data"] + ". " + report["scope"] + ".",
        "",
        "| Method | Evidence hits | Stale evidence hits | Stale query rate | Expected claim coverage | Current evidence ratio |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        f"| Status-blind evidence | {blind['evidence_hits']} | {blind['stale_evidence_hits']} | "
        f"{blind['stale_query_rate']:.2%} | {blind['expected_claim_coverage']:.2%} | "
        f"{blind['current_evidence_ratio']:.2%} |",
        f"| Status-aware context | {aware['evidence_hits']} | {aware['stale_evidence_hits']} | "
        f"{aware['stale_query_rate']:.2%} | {aware['expected_claim_coverage']:.2%} | "
        f"{aware['current_evidence_ratio']:.2%} |",
        "",
        f"Queries: {report['queries']} · top-k: {report['top_k']} · fixture: "
        f"`{report['fixture_sha256'][:16]}…`",
        "",
        "## Cases",
        "",
        "| Query | Status-blind claim ids | Status-aware claim ids |",
        "| --- | --- | --- |",
    ]
    for case in report["cases"]:
        raw = ", ".join(case["status_blind_evidence"]["claim_ids"]) or "—"
        aware = ", ".join(case["status_aware_context"]["claim_ids"]) or "—"
        lines.append(f"| `{case['query']}` | {raw} | {aware} |")
    lines += ["", "## Limits", ""]
    lines += [f"- {limit}" for limit in report["limits"]]
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", help="write the JSON report")
    parser.add_argument("--markdown", help="write a Markdown report")
    args = parser.parse_args(argv)
    report = evaluate()
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                  encoding="utf-8")
    if args.markdown:
        Path(args.markdown).write_text(markdown(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
