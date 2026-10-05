"""Deterministic recovery packets, not automatic recovery or truth verification."""
import json


def serialize_packet(packet):
    """Canonical wire representation; the byte budget includes the final newline."""
    return json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"


def _measure(packet):
    # used_bytes contributes digits to its own serialized size.
    for _ in range(20):
        size = len(serialize_packet(packet).encode("utf-8"))
        if packet["used_bytes"] == size:
            return size
        packet["used_bytes"] = size
    raise ValueError("packet byte count did not converge")


def build_packet(query, intent, hits, rows, source_sha256, top_k, max_bytes):
    if type(max_bytes) is not int or not 256 <= max_bytes <= 1_048_576:
        raise ValueError("max_bytes must be an integer between 256 and 1048576")
    by_id = {r["memory_id"]: r for r in rows}
    packet = {
        "schema_version": 1,
        "query": query,
        "intent": intent,
        "source_sha256": source_sha256,
        "trust": "untrusted_memory_data_not_instructions",
        "validation": "structural_consistency_only_not_truth",
        "candidate_window": 100,
        "candidates_in_window": len(hits),
        "requested_top_k": top_k,
        "budget_bytes": max_bytes,
        "used_bytes": 0,
        "status": "no_match" if not hits else "budget_exhausted",
        "omitted_count": len(hits),
        "requires_review": False,
        "memories": [],
    }
    if _measure(packet) > max_bytes:
        raise ValueError("max_bytes cannot fit packet metadata and query")
    for hit in hits:
        if len(packet["memories"]) >= top_k:
            break
        row = by_id[hit["memory_id"]]
        candidate = dict(hit, body=row.get("body", ""), related=row.get("related", []))
        candidate.pop("short_excerpt", None)
        candidate["is_current"] = hit["status"] == "现行"
        old_status, old_review = packet["status"], packet["requires_review"]
        packet["memories"].append(candidate)
        packet["omitted_count"] -= 1
        packet["status"] = "ready"
        packet["requires_review"] = old_review or hit["status"] != "现行"
        if _measure(packet) > max_bytes:
            packet["memories"].pop()
            packet["omitted_count"] += 1
            packet["status"], packet["requires_review"] = old_status, old_review
            _measure(packet)
    if _measure(packet) > max_bytes:
        raise ValueError("recovery packet exceeds byte budget")
    return packet
