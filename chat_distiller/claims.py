"""Project-scoped claim store: in-situ capture and budgeted briefs.

Claims are the pipeline's single authority. Sessions and Markdown exports are
evidence and views, never the source. The store is a strict JSONL file that is
fully validated on every read; corruption refuses service instead of guessing.
Deterministic code owns identity, status transitions, conflict surfacing and
byte budgets; semantic judgment stays with the calling agent or human.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ._internal.query_memory import features
from .context import (
    DEFAULT_CONTEXT_BYTES, JsonlEvidenceIndex, build_context, serialize_context, suggest_claim,
)
from .recovery import _measure, serialize_packet

SCHEMA_VERSION = 1
STATUSES = ("现行", "已过期", "有争议")
STATUS_ALIASES = {"current": "现行", "superseded": "已过期", "disputed": "有争议"}
CLAIM_ID_RE = re.compile(r"clm_[0-9a-f]{16}\Z")
TOPIC_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,39}\Z")
ISO_Z_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
MAX_TEXT = 1000
MAX_CONTEXT = 300
DEFAULT_MAX_BYTES = 8192
CONFLICT_MIN_SHARED = 2
CONFLICT_RATIO = 0.6
KEYS = frozenset((
    "claim_id", "text", "status", "topic", "tags",
    "created_at", "updated_at", "superseded_by",
    "source", "quote", "session_hint",
))


class ClaimStoreError(ValueError):
    """The store is missing, corrupt or the requested transition is invalid."""


def _utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_store():
    env = os.environ.get("CLAIM_LEDGER_STORE")
    if env:
        return Path(env).expanduser()
    return Path.cwd() / ".claim-ledger" / "claims.jsonl"


def _validate_claim(claim):
    if not isinstance(claim, dict):
        raise ClaimStoreError("claim must be a JSON object")
    if set(claim) != KEYS:
        missing = sorted(KEYS - set(claim))
        extra = sorted(set(claim) - KEYS)
        raise ClaimStoreError(f"schema mismatch; missing={missing} unknown={extra}")
    if not isinstance(claim["claim_id"], str) or not CLAIM_ID_RE.fullmatch(claim["claim_id"]):
        raise ClaimStoreError(f"invalid claim_id: {claim['claim_id']!r}")
    if not isinstance(claim["text"], str) or not claim["text"].strip() or len(claim["text"]) > MAX_TEXT:
        raise ClaimStoreError(f"invalid text on {claim['claim_id']}")
    if claim["status"] not in STATUSES:
        raise ClaimStoreError(f"unknown status on {claim['claim_id']}: {claim['status']!r}")
    if not isinstance(claim["topic"], str) or not TOPIC_RE.fullmatch(claim["topic"]):
        raise ClaimStoreError(f"invalid topic on {claim['claim_id']}: {claim['topic']!r}")
    if (not isinstance(claim["tags"], list)
            or any(not isinstance(t, str) or not t or len(t) > 40 for t in claim["tags"])
            or len(set(claim["tags"])) != len(claim["tags"])):
        raise ClaimStoreError(f"invalid tags on {claim['claim_id']}")
    for key in ("created_at", "updated_at"):
        if not isinstance(claim[key], str) or not ISO_Z_RE.fullmatch(claim[key]):
            raise ClaimStoreError(f"invalid {key} on {claim['claim_id']}")
    if claim["superseded_by"] is not None and not CLAIM_ID_RE.fullmatch(str(claim["superseded_by"])):
        raise ClaimStoreError(f"invalid superseded_by on {claim['claim_id']}")
    for key in ("source", "quote", "session_hint"):
        value = claim[key]
        if value is not None and (not isinstance(value, str) or len(value) > MAX_CONTEXT):
            raise ClaimStoreError(f"invalid {key} on {claim['claim_id']}")


def normalize_status(value):
    """Accept the stored status or its English alias used by the docs and MCP clients."""
    if not isinstance(value, str):
        raise ClaimStoreError("status must be a string")
    normalized = STATUS_ALIASES.get(value.strip().lower(), value)
    if normalized not in STATUSES:
        raise ClaimStoreError(f"unknown status filter: {value!r}")
    return normalized


def _supersede_targets(supersedes):
    """Normalize a single id or an explicit list of ids without losing intent."""
    if supersedes is None:
        return []
    if isinstance(supersedes, str):
        targets = [supersedes]
    elif isinstance(supersedes, (list, tuple, set)):
        targets = sorted(supersedes) if isinstance(supersedes, set) else list(supersedes)
    else:
        raise ClaimStoreError("supersedes must be a claim_id or a list of claim_ids")
    if not targets:
        return []
    if any(not isinstance(target, str) or not CLAIM_ID_RE.fullmatch(target) for target in targets):
        raise ClaimStoreError("supersedes must contain valid claim_ids")
    if len(set(targets)) != len(targets):
        raise ClaimStoreError("supersedes must not contain duplicate claim_ids")
    return targets


def find_conflicts(text, current):
    """Lexical overlap against current claims; a candidate is surfaced, never auto-resolved.

    Deterministic matching cannot see semantic contradictions; a high overlap is
    reported as a possible conflict and the caller must resolve it explicitly.
    """
    query = features(text)
    if len(query) < CONFLICT_MIN_SHARED:
        return []
    out = []
    for claim in current:
        other = features(claim["text"])
        shared = query & other
        if len(shared) >= CONFLICT_MIN_SHARED and len(shared) / min(len(query), len(other)) >= CONFLICT_RATIO:
            out.append(claim)
    return out


class ClaimStore:
    """Single-writer local claim store over one strict JSONL file."""

    def __init__(self, path=None):
        self.path = Path(path or default_store())

    def _read(self):
        if not self.path.exists():
            return []
        rows = []
        for lineno, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            try:
                claim = json.loads(line)
                _validate_claim(claim)
            except (json.JSONDecodeError, ClaimStoreError) as exc:
                raise ClaimStoreError(f"{self.path} line {lineno}: {exc}") from exc
            rows.append(claim)
        by_id = {}
        for claim in rows:
            if claim["claim_id"] in by_id:
                raise ClaimStoreError(f"duplicate claim_id: {claim['claim_id']}")
            by_id[claim["claim_id"]] = claim
        for claim in rows:
            target = claim["superseded_by"]
            if claim["status"] == "已过期":
                if target is None:
                    raise ClaimStoreError(f"expired claim without successor: {claim['claim_id']}")
                if target not in by_id:
                    raise ClaimStoreError(f"dangling superseded_by on {claim['claim_id']}: {target}")
            elif target is not None:
                raise ClaimStoreError(f"superseded_by set on non-expired claim: {claim['claim_id']}")
        for claim in rows:
            seen, cursor = set(), claim["claim_id"]
            while cursor is not None:
                if cursor in seen:
                    raise ClaimStoreError(f"supersession cycle reached from {claim['claim_id']}")
                seen.add(cursor)
                cursor = by_id[cursor]["superseded_by"] if cursor in by_id else None
        return rows

    def _write(self, rows):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = "".join(
            json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            for r in rows)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=".claims-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(body)
            for attempt in range(5):
                try:
                    os.replace(tmp, self.path)
                    break
                except OSError as exc:
                    if attempt == 4 or getattr(exc, "winerror", None) not in (5, 32):
                        raise
                    time.sleep(0.05 * (attempt + 1))
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def digest(self, rows=None):
        """SHA-256 over the canonical serialization; independent of file formatting."""
        if rows is None:
            rows = self._read()
        body = "".join(
            json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            for r in rows)
        return hashlib.sha256(body.encode("utf-8")).hexdigest()

    def record(self, text, *, topic="general", tags=None, supersedes=None,
               dispute=False, source=None, quote=None, session_hint=None):
        """Capture one claim at decision time; conflicts must be resolved explicitly."""
        if not isinstance(text, str) or not text.strip():
            raise ClaimStoreError("claim text must be non-empty")
        text = " ".join(text.split())
        if len(text) > MAX_TEXT:
            raise ClaimStoreError(f"claim text exceeds {MAX_TEXT} characters")
        if not TOPIC_RE.fullmatch(str(topic)):
            raise ClaimStoreError(f"topic must match {TOPIC_RE.pattern!r}: {topic!r}")
        tags = list(tags or [])
        if any(not isinstance(t, str) or not t.strip() for t in tags):
            raise ClaimStoreError("tags must be non-empty strings")
        tags = [t.strip() for t in tags]
        if len(set(tags)) != len(tags):
            raise ClaimStoreError("tags must be unique")
        rows = self._read()
        by_id = {c["claim_id"]: c for c in rows}
        for claim in rows:
            if claim["text"] == text:
                raise ClaimStoreError(
                    f"identical claim already exists: {claim['claim_id']}; supersede it instead of duplicating")
        targets = _supersede_targets(supersedes)
        for target in targets:
            if target not in by_id:
                raise ClaimStoreError(f"--supersedes target not found: {target}")
            if by_id[target]["status"] == "已过期":
                raise ClaimStoreError(f"--supersedes target already superseded: {target}")
        current = [c for c in rows if c["status"] == "现行"]
        conflicts = find_conflicts(text, current)
        conflict_ids = {c["claim_id"] for c in conflicts}
        if conflicts and not targets and not dispute:
            ids = ", ".join(c["claim_id"] for c in conflicts)
            raise ClaimStoreError(
                f"possible conflict with current claim(s): {ids}; "
                "pass --supersedes <id> to replace, or --dispute to record as disputed")
        if conflicts and targets and not dispute:
            missing = conflict_ids - set(targets)
            if missing:
                ids = ", ".join(sorted(missing))
                raise ClaimStoreError(
                    f"unresolved conflict with current claim(s): {ids}; "
                    "supersede every detected conflict, or use --dispute")
        status = "有争议" if dispute else "现行"
        claim_id = "clm_" + uuid.uuid4().hex[:16]
        while claim_id in by_id:
            claim_id = "clm_" + uuid.uuid4().hex[:16]
        now = _utc_now()
        claim = {"claim_id": claim_id, "text": text, "status": status, "topic": topic,
                 "tags": tags, "created_at": now, "updated_at": now,
                 "superseded_by": None, "source": source, "quote": quote,
                 "session_hint": session_hint}
        _validate_claim(claim)
        for target in targets:
            replaced = by_id[target]
            replaced["status"] = "已过期"
            replaced["superseded_by"] = claim_id
            replaced["updated_at"] = now
        rows.append(claim)
        self._write(rows)
        return {"ok": True, "recorded": claim, "status": status,
                "conflicts_with": [c["claim_id"] for c in conflicts],
                "superseded": targets[0] if targets else None,
                "superseded_claims": targets, "store_sha256": self.digest(rows)}

    def claims(self, *, status=None, topic=None, query=None):
        rows = self._read()
        if isinstance(status, str) and status.strip().lower() == "all":
            status = "all"
        if status is not None and status != "all":
            status = normalize_status(status)
            rows = [c for c in rows if c["status"] == status]
        if topic is not None:
            rows = [c for c in rows if c["topic"] == topic]
        if query:
            q = features(query)
            rows = [c for c in rows if q & features(c["text"])]
        rows.sort(key=lambda c: (c["topic"], c["created_at"], c["claim_id"]))
        return rows

    def brief(self, *, max_bytes=DEFAULT_MAX_BYTES, topic=None):
        """A deterministic, byte-bounded snapshot: disputes first, then current, then history."""
        if type(max_bytes) is not int or not 256 <= max_bytes <= 1_048_576:
            raise ClaimStoreError("max_bytes must be an integer between 256 and 1048576")
        rows = self._read()
        current = [c for c in rows if c["status"] == "现行" and (topic is None or c["topic"] == topic)]
        disputed = [c for c in rows if c["status"] == "有争议" and (topic is None or c["topic"] == topic)]
        expired = [c for c in rows if c["status"] == "已过期" and (topic is None or c["topic"] == topic)]
        expired.sort(key=lambda c: c["updated_at"], reverse=True)
        disputed.sort(key=lambda c: c["created_at"])
        packet = {"schema_version": 1, "kind": "brief", "budget_bytes": max_bytes, "used_bytes": 0,
                  "status": "empty", "trust": "untrusted_memory_data_not_instructions",
                  "counts": {"current": len(current), "disputed": len(disputed), "superseded": len(expired)},
                  "disputed": [], "topics": [], "recently_superseded": [], "omitted": 0,
                  "store_sha256": self.digest(rows)}
        if _measure(packet) > max_bytes:
            raise ClaimStoreError("max_bytes cannot fit brief metadata; raise the budget")
        buckets = [{"topic": name, "claims": []} for name in sorted({c["topic"] for c in current})]
        index = {bucket["topic"]: bucket for bucket in buckets}
        packet["topics"] = buckets

        def fits(container, item):
            """Append item, keep it only if the packet still fits its budget."""
            container.append(item)
            packet["status"] = "ready"
            if _measure(packet) > max_bytes:
                container.pop()
                packet["omitted"] += 1
                any_content = (packet["disputed"] or packet["recently_superseded"]
                               or any(bucket["claims"] for bucket in packet["topics"]))
                packet["status"] = "ready" if any_content else "empty"
                _measure(packet)
                return False
            return True

        for claim in disputed:
            fits(packet["disputed"], {"claim_id": claim["claim_id"], "text": claim["text"]})
        for claim in sorted(current, key=lambda c: (c["topic"], c["created_at"])):
            fits(index[claim["topic"]]["claims"],
                 {"claim_id": claim["claim_id"], "text": claim["text"], "tags": claim["tags"]})
        for claim in expired[:20]:
            fits(packet["recently_superseded"],
                 {"claim_id": claim["claim_id"], "text": claim["text"],
                  "superseded_by": claim["superseded_by"]})
        packet["topics"] = [b for b in packet["topics"] if b["claims"]]
        any_content = bool(packet["disputed"] or packet["recently_superseded"] or packet["topics"])
        if not any_content:
            packet["status"] = "budget_exhausted" if rows else "empty"
        _measure(packet)
        return packet


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="claim-ledger", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    record = commands.add_parser("record", help="capture one claim at decision time")
    record.add_argument("text")
    record.add_argument("--topic", default="general")
    record.add_argument("--tag", action="append", default=[])
    record.add_argument("--supersedes", action="append", default=[],
                        help="claim_id replaced by this claim; repeat for multiple conflicts")
    record.add_argument("--dispute", action="store_true",
                        help="record as disputed; also resolves a detected conflict without superseding")
    record.add_argument("--source")
    record.add_argument("--quote")
    record.add_argument("--session", dest="session_hint")
    record.add_argument("--store")
    record.add_argument("--json", action="store_true")

    brief = commands.add_parser("brief", help="render the current-state brief within a byte budget")
    brief.add_argument("--store")
    brief.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    brief.add_argument("--topic")
    brief.add_argument("--compact", action="store_true", help="omit indentation")

    listing = commands.add_parser("claims", help="list or search claims")
    listing.add_argument("--store")
    listing.add_argument("--status", default="现行")
    listing.add_argument("--topic")
    listing.add_argument("--query")
    listing.add_argument("--limit", type=int, default=100)

    recall = commands.add_parser(
        "recall", help="brief + optional status-filtered RAG evidence in one packet")
    recall.add_argument("--query", required=True)
    recall.add_argument("--store")
    recall.add_argument("--evidence", help="optional JSONL evidence index (or use the Python API)")
    recall.add_argument("--max-bytes", type=int, default=DEFAULT_CONTEXT_BYTES)
    recall.add_argument("--intent", choices=["current", "historical"], default="current")
    recall.add_argument("--top-k", type=int, default=8)
    recall.add_argument("--max-per-claim", type=int, default=2,
                        help="maximum evidence chunks retained per claim (default 2)")
    recall.add_argument("--timeout", type=float, default=5.0,
                        help="seconds before the evidence adapter falls back to brief-only")
    recall.add_argument("--compact", action="store_true", help="emit the canonical wire packet")

    suggest = commands.add_parser(
        "suggest", help="propose a claim for review; never writes to the store")
    suggest.add_argument("--text", required=True)
    suggest.add_argument("--topic", default="general")
    suggest.add_argument("--tag", action="append", default=[])
    suggest.add_argument("--query", help="evidence query; defaults to the proposed text")
    suggest.add_argument("--store")
    suggest.add_argument("--evidence", help="optional JSONL evidence index")
    suggest.add_argument("--top-k", type=int, default=8)
    suggest.add_argument("--max-per-claim", type=int, default=2)
    suggest.add_argument("--timeout", type=float, default=5.0)

    index = commands.add_parser("index", help="seal or inspect a JSONL evidence index")
    index_commands = index.add_subparsers(dest="index_command", required=True)
    index_build = index_commands.add_parser("build", help="seal a source index to one claim store")
    index_build.add_argument("--source", required=True)
    index_build.add_argument("--out", required=True)
    index_build.add_argument("--store", required=True)
    index_status = index_commands.add_parser("status", help="check index freshness and integrity")
    index_status.add_argument("--evidence", required=True)
    index_status.add_argument("--store")

    args = parser.parse_args(argv)
    try:
        if args.command == "record":
            result = ClaimStore(args.store).record(
                args.text, topic=args.topic, tags=args.tag, supersedes=args.supersedes or None,
                dispute=args.dispute, source=args.source,
                quote=args.quote, session_hint=args.session_hint)
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                line = f"recorded {result['recorded']['claim_id']} [{result['recorded']['status']}] topic={result['recorded']['topic']}"
                if result["superseded_claims"]:
                    line += " superseded=" + ",".join(result["superseded_claims"])
                if result["conflicts_with"]:
                    line += f" conflicts_with={','.join(result['conflicts_with'])}"
                print(line)
        elif args.command == "brief":
            packet = ClaimStore(args.store).brief(max_bytes=args.max_bytes, topic=args.topic)
            if args.compact:
                print(serialize_packet(packet), end="")
            else:
                print(json.dumps(packet, ensure_ascii=False, indent=2))
        elif args.command == "recall":
            evidence = JsonlEvidenceIndex(args.evidence) if args.evidence else None
            packet = build_context(
                ClaimStore(args.store), args.query, max_bytes=args.max_bytes,
                intent=args.intent, retriever=evidence, top_k=args.top_k,
                max_per_claim=args.max_per_claim, retriever_timeout=args.timeout)
            if args.compact:
                print(serialize_context(packet), end="")
            else:
                print(json.dumps(packet, ensure_ascii=False, indent=2))
        elif args.command == "suggest":
            evidence = JsonlEvidenceIndex(args.evidence) if args.evidence else None
            proposal = suggest_claim(
                ClaimStore(args.store), args.text, topic=args.topic, tags=args.tag,
                query=args.query, retriever=evidence, top_k=args.top_k,
                max_per_claim=args.max_per_claim, retriever_timeout=args.timeout)
            print(json.dumps(proposal, ensure_ascii=False, indent=2))
        elif args.command == "index":
            if args.index_command == "build":
                index = JsonlEvidenceIndex(args.source)
                result = index.seal(args.out, ClaimStore(args.store).digest())
            else:
                index = JsonlEvidenceIndex(args.evidence)
                digest = ClaimStore(args.store).digest() if args.store else None
                result = index.status(digest)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["ok"] else 1
        else:
            if args.limit < 1 or args.limit > 1000:
                raise ClaimStoreError("limit must be between 1 and 1000")
            rows = ClaimStore(args.store).claims(status=args.status, topic=args.topic, query=args.query)
            print(json.dumps({"ok": True, "count": len(rows),
                              "claims": rows[:args.limit]}, ensure_ascii=False, indent=2))
        return 0
    except (ClaimStoreError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc), "error_type": type(exc).__name__},
                         ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
