#!/usr/bin/env python3
"""Audit an intentional Gateway contract change without rewriting the frozen baseline.

The original recorded synthetic fixture remains immutable. Changes to any other
measured field remain failures; byte savings alone do not establish Agent utility.
"""
import argparse
import json
from pathlib import Path


def compare(baseline, candidate):
    if not isinstance(baseline, dict) or not isinstance(candidate, dict):
        raise ValueError("Gateway results must be objects")
    if set(baseline) != set(candidate):
        raise ValueError("Gateway schema/metric names changed; require separate review")
    changed = sorted(key for key in baseline if baseline[key] != candidate[key])
    if changed != ["context_used_bytes"]:
        raise ValueError("Gateway result drift outside audited bytes: " + repr(changed))
    old, new = baseline["context_used_bytes"], candidate["context_used_bytes"]
    if type(old) is not int or type(new) is not int or new >= old:
        raise ValueError("expected smaller context packet after excluding unrelated sessions")
    if new <= 0 or new > candidate["context_budget_bytes"]:
        raise ValueError("candidate packet exceeds budget or has an invalid size")
    return {"ok": True, "comparison": "historical_baseline_preserved",
            "changed_fields": changed, "baseline_bytes": old, "candidate_bytes": new,
            "byte_delta": new - old, "unchanged_fields": len(baseline) - 1,
            "claim_boundary": "synthetic_packet_size_not_tokens_or_agent_task_success"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--out")
    args = parser.parse_args()
    try:
        baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
        candidate = json.loads(Path(args.candidate).read_text(encoding="utf-8"))
        result = compare(baseline, candidate)
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
