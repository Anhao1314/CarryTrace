#!/usr/bin/env python3
"""Run the installed CLI through a synthetic host-authored wiki lifecycle."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="new directory for disposable demo data and receipts")
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=False, exist_ok=False)
    vault = out / "vault"; vault.mkdir()
    entry = Path(sys.executable).with_name("chat-distiller")
    if os.name == "nt":
        entry = entry.with_suffix(".exe")
    if not entry.is_file():
        raise SystemExit("Run with the Python environment where chat-distiller is installed.")
    receipts = []

    def command(name, *arguments):
        proc = subprocess.run([str(entry), *map(str, arguments)], cwd=out, capture_output=True, text=True, timeout=60)
        (out / (name + ".json")).write_text(proc.stdout, encoding="utf-8")
        if proc.returncode:
            raise RuntimeError(f"{name}: exit {proc.returncode}: {proc.stdout} {proc.stderr}")
        result = json.loads(proc.stdout)
        receipts.append(name)
        return result

    source = out / "memory.json"
    command("01-register", "migrate", "--mode", "init", "--distill", ROOT / "examples/recovery/distill.json", "--out", source)
    command("02-render", "render", "--distill", source, "--vault", vault)
    draft = command("03-prepare", "wiki", "prepare", "--vault", vault, "--topic", "database", "--query", "database")
    authored = json.loads((ROOT / "examples/wiki/synthesis.json").read_text(encoding="utf-8"))
    roles = {c["status"]: c["evidence"][0] for c in draft["claims"]}
    draft["title"] = authored["title"]
    draft["claims"] = [dict(text=c["text"], status=c["status"], origin=c["origin"], evidence=[roles[role] for role in c["support_roles"]]) for c in authored["claims"]]
    proposal = out / "proposal.json"; proposal.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    preview = command("04-validate", "wiki", "compile", "--vault", vault, "--proposal", proposal)
    if preview["applied"]:
        raise AssertionError("dry-run wrote state")
    created = command("05-publish", "wiki", "compile", "--vault", vault, "--proposal", proposal, "--apply")
    current = command("06-current", "wiki", "search", "--vault", vault, "--query", "database")
    history = command("07-history", "wiki", "search", "--vault", vault, "--query", "database", "--intent", "historical")
    packet = command("08-recovery", "wiki", "recover", "--vault", vault, "--query", "database", "--max-bytes", "16384")
    command("09-export", "wiki", "export", "--vault", vault, "--out", out / "wiki-v1")
    data = json.loads(source.read_text(encoding="utf-8"))
    data["conversations"][1]["cards"][0]["body"] = "Use PostgreSQL for the database and preserve the existing API."
    source.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    command("10-update-memory", "render", "--vault", vault, "--distill", source)
    status = command("11-stale", "wiki", "status", "--vault", vault)
    fallback = command("12-fallback", "wiki", "recover", "--vault", vault, "--query", "database")
    fresh = command("13-prepare-refresh", "wiki", "prepare", "--vault", vault, "--topic", "database", "--query", "database")
    refresh_file = out / "refresh.json"; refresh_file.write_text(json.dumps(fresh, ensure_ascii=False), encoding="utf-8")
    updated = command("14-refresh", "wiki", "compile", "--vault", vault, "--proposal", refresh_file, "--apply")
    archive = command("15-archive", "wiki", "get", "--vault", vault, "--topic", "database", "--revision", "1", "--allow-stale")
    command("16-export", "wiki", "export", "--vault", vault, "--out", out / "wiki-v2")
    checks = {
        "dry_run_is_read_only": not preview["applied"],
        "host_synthesis_is_review_required": created["requires_review"],
        "current_preserves_dispute_not_history": {c["status"] for c in current["results"][0]["claims"]} == {"current", "disputed"},
        "historical_keeps_old_and_new_sources": len(history["results"][0]["evidence_memories"]) == 3,
        "layered_packet_contains_synthesis": bool(packet["knowledge"]),
        "literal_packet_budget_matches": packet["used_bytes"] == len((out / "08-recovery.json").read_bytes()) <= 16384,
        "source_update_stales_wiki": status["stale"] == 1,
        "fallback_has_no_stale_wiki": fallback["knowledge"] == [] and fallback["stale_pages_excluded"] == 1,
        "fallback_reads_updated_memory": any("PostgreSQL" in m["body"] for m in fallback["memories"]),
        "identity_preserved": created["knowledge_id"] == updated["knowledge_id"],
        "revision_advanced": updated["page_revision"] == 2,
        "archive_keeps_original_synthesis": archive["archived"] and archive["proposal"]["title"] == authored["title"],
    }
    report = {"ok": all(checks.values()), "data": "synthetic; host-authored synthesis template; extractive refresh",
              "model_calls": 0, "commands_executed": len(receipts), "checks": checks,
              "output_directory": str(out), "receipts": receipts}
    (out / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
