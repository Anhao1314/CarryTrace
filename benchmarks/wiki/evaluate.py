#!/usr/bin/env python3
"""Synthetic compiler engineering experiments, NOT semantic model evaluation."""
import argparse
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
from chat_distiller import KnowledgeStore, serialize_packet
from chat_distiller.cli import main as cli_main
from chat_distiller._internal.memory_identity import prepare
from chat_distiller._internal.render_notes import safe_filename


def render(data, source, vault):
    source.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()) as output:
        result = cli_main(["render", "--distill", str(source), "--vault", str(vault)])
    if result != 0:
        raise AssertionError(output.getvalue())


def evaluate(fixtures=None):
    fixtures = Path(fixtures or Path(__file__).with_name("fixtures.json"))
    raw = fixtures.read_bytes()
    cases = json.loads(raw)["cases"]
    results = []
    failures = []
    for case in cases:
        with tempfile.TemporaryDirectory(prefix="chat-distiller-compilebench-") as tmp:
            root = Path(tmp); vault = root / "vault"; vault.mkdir(); source = root / "source.json"
            cards = [{"kind": "decision", "title": case["topic"] + " " + key, "body": case[key], "status": status}
                     for key, status in (("old", "已过期"), ("current", "现行"), ("dispute", "有争议"))]
            data = {"conversations": [{"session_id": case["topic"], "date": "2026-01-01", "title": case["topic"],
                                      "categories": ["技术开发/开发环境"], "cards": cards}]}
            data, _ = prepare(data, safe_filename)
            registered = data["conversations"][0]["cards"]
            registered[0]["superseded_by"] = registered[1]["memory_id"]
            render(data, source, vault)
            store = KnowledgeStore(vault)
            proposal = store.prepare(case["topic"], case["query"], title=case["query"] + " architecture")
            invalid = {}
            variations = {}
            bad = copy.deepcopy(proposal); bad["claims"][0]["evidence"][0]["memory_id"] = "mem_" + "0" * 32; variations["unknown_id"] = bad
            bad = copy.deepcopy(proposal); bad["claims"][0]["evidence"][0]["quote"] = "nonexistent quote"; variations["invented_quote"] = bad
            bad = copy.deepcopy(proposal); bad["claims"] = [c for c in bad["claims"] if c["status"] != "disputed"]; variations["omitted_dispute"] = bad
            bad = copy.deepcopy(proposal); next(c for c in bad["claims"] if c["status"] == "disputed")["status"] = "current"; variations["status_laundering"] = bad
            for name, candidate in variations.items():
                try:
                    store.compile(candidate, apply=True)
                    invalid[name] = False
                except ValueError:
                    invalid[name] = not store.storage.root.exists()
            created = store.compile(proposal, apply=True)
            before = store.storage.path.read_bytes()
            repeat = store.compile(proposal, apply=True)
            same = repeat["operation"] == "no_change" and before == store.storage.path.read_bytes()
            packet = store.recover(case["query"], top_k=1, max_bytes=20000)
            current_states = {c["status"] for c in packet["knowledge"][0]["claims"]}
            initial_page = store.get(case["topic"])
            registered[1]["body"] = case["updated"]
            render(data, source, vault)
            # Ablation holds the old page and query fixed. The comparison is a
            # static-page consumer with its freshness check disabled, NOT another
            # project's implementation or a model-generated answer benchmark.
            ungated_served = bool(initial_page["proposal"]["claims"])
            gated_served = bool(store.search(case["query"]))
            fallback = store.recover(case["query"], max_bytes=20000)
            stale_rejected = False
            try:
                store.compile(proposal, apply=True)
            except ValueError:
                stale_rejected = True
            updated = store.compile(store.prepare(case["topic"], case["query"], title=case["query"] + " architecture"), apply=True)
            historic = store.get(case["topic"], revision=1, allow_stale=True)
            store.export(root / "wiki")
            budget_checks = []
            for budget in (900, 1800, 4096, 8192):
                bounded = store.recover(case["query"], max_bytes=budget)
                budget_checks.append(len(serialize_packet(bounded).encode("utf-8")) == bounded["used_bytes"] <= budget)
            result = {"topic": case["topic"], "input_cards": 3, "page_count": len(store.status()["pages"]),
                      "repeat_byte_identical": same, "invalid_proposals_rejected_without_state": invalid,
                      "initial_current_and_dispute_preserved": current_states == {"current", "disputed"},
                      "freshness_ablation": {"disabled_stale_page_served": ungated_served, "enabled_stale_page_served": gated_served},
                      "stale_proposal_rejected": stale_rejected,
                      "atomic_fallback_has_updated_value": any(r["body"] == case["updated"] for r in fallback["memories"]),
                      "identity_preserved_after_refresh": updated["knowledge_id"] == created["knowledge_id"],
                      "page_revision_after_refresh": updated["page_revision"],
                      "old_revision_inspectable": historic["archived"] and any(r["body"] == case["current"] for r in historic["dependencies"]),
                      "exact_budget_checks": budget_checks,
                      "export_manifest_exists": (root / "wiki/manifest.json").is_file(),
                      "initial_layered_packet_bytes": packet["used_bytes"]}
            for key in ("repeat_byte_identical", "initial_current_and_dispute_preserved", "stale_proposal_rejected",
                        "atomic_fallback_has_updated_value", "identity_preserved_after_refresh", "old_revision_inspectable", "export_manifest_exists"):
                if not result[key]:
                    failures.append(case["topic"] + ": " + key)
            if not all(invalid.values()) or not all(budget_checks) or gated_served or updated["page_revision"] != 2 or result["page_count"] != 1:
                failures.append(case["topic"] + ": lifecycle/guard failure")
            results.append(result)
    return {"suite": "CompileBench engineering v1", "fixture_sha256": hashlib.sha256(raw).hexdigest(),
            "data": "curated synthetic atomic cards; extractive proposals; no model calls",
            "scope": "lifecycle and structural safety, not entailment or agent task success",
            "cases": results, "summary": {"topics": len(results), "cards": 3 * len(results),
                "invalid_proposals_blocked": sum(sum(r["invalid_proposals_rejected_without_state"].values()) for r in results),
                "invalid_proposals_total": 4 * len(results),
                "stale_served_gate_disabled": sum(r["freshness_ablation"]["disabled_stale_page_served"] for r in results),
                "stale_served_gate_enabled": sum(r["freshness_ablation"]["enabled_stale_page_served"] for r in results),
                "exact_budget_passes": sum(sum(r["exact_budget_checks"]) for r in results),
                "exact_budget_total": 4 * len(results), "failures": failures},
            "limits": ["Not an independent holdout or automatic LLM synthesis evaluation.",
                       "Status and scope are explicit; unknown semantic contradictions can be missed.",
                       "A false synthesis with a real quote can pass structurally and remains review-required.",
                       "Ablation is a controlled static-page consumer, not a comparison to other wiki products.",
                       "Conservative whole-source invalidation also stales pages after unrelated changes."]}


def markdown(result):
    s = result["summary"]
    lines = ["# CompileBench: executed engineering evidence", "", result["data"], "", result["scope"], "",
             "Fixture SHA-256: `" + result["fixture_sha256"] + "`", "",
             "| Check | Observed |", "| --- | ---: |",
             f"| Invalid proposals blocked | {s['invalid_proposals_blocked']}/{s['invalid_proposals_total']} |",
             f"| Stale pages served, freshness gate disabled | {s['stale_served_gate_disabled']}/{s['topics']} |",
             f"| Stale pages served, freshness gate enabled | {s['stale_served_gate_enabled']}/{s['topics']} |",
             f"| Complete UTF-8 budget checks | {s['exact_budget_passes']}/{s['exact_budget_total']} |", "",
             "| Topic | Cards → pages | Revision after update | Identity preserved | Old revision retained |", "| --- | --- | ---: | --- | --- |"]
    for r in result["cases"]:
        lines.append(f"| {r['topic']} | 3 → {r['page_count']} | {r['page_revision_after_refresh']} | {r['identity_preserved_after_refresh']} | {r['old_revision_inspectable']} |")
    lines += ["", "The 3 → 1 grouping is a chosen topic organization, not a measured compression or quality improvement.",
              "The ablation changes only freshness enforcement. It is not a leaderboard result.", "", "## Limitations", ""]
    lines += ["- " + line for line in result["limits"]]
    lines += ["", "Failures: " + json.dumps(s["failures"]), ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path(__file__).parent)
    parser.add_argument("--check", action="store_true", help="compare against committed results without changing them")
    args = parser.parse_args()
    result = evaluate()
    outputs = {"results.json": json.dumps(result, ensure_ascii=False, indent=2) + "\n", "results.md": markdown(result)}
    if args.check:
        for name, content in outputs.items():
            if (args.out / name).read_text(encoding="utf-8") != content:
                raise SystemExit("recorded result differs: " + name)
    else:
        args.out.mkdir(parents=True, exist_ok=True)
        for name, content in outputs.items():
            (args.out / name).write_text(content, encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 1 if result["summary"]["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
