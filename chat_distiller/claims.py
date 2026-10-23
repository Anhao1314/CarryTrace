"""Project-scoped claim store: in-situ capture and budgeted briefs.

Claims are the pipeline's single authority. Sessions and Markdown exports are
evidence and views, never the source. The store is a strict JSONL file that is
fully validated on every read; corruption refuses service instead of guessing.
Deterministic code owns identity, status transitions, conflict surfacing and
byte budgets; semantic judgment stays with the calling agent or human.
"""
from __future__ import annotations

import argparse
import contextlib
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
from .locking import DEFAULT_LOCK_TIMEOUT, FileLock, LockTimeout
from .recovery import _measure, serialize_packet

SCHEMA_VERSION = 1
BACKUP_KIND = "claim-ledger-backup"
AUDIT_KIND = "claim-ledger-audit"
REDACTED_TEXT = "[redacted]"
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
OPTIONAL_KEYS = frozenset(("redacted_at",))


class ClaimStoreError(ValueError):
    """The store is missing, corrupt or the requested transition is invalid."""


class ClaimStoreBusy(ClaimStoreError):
    """Another process holds the store write lock past the timeout."""


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
    allowed = KEYS | OPTIONAL_KEYS
    if not KEYS <= set(claim) or set(claim) - allowed:
        missing = sorted(KEYS - set(claim))
        extra = sorted(set(claim) - allowed)
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
    if "redacted_at" in claim:
        redacted_at = claim["redacted_at"]
        if not isinstance(redacted_at, str) or not ISO_Z_RE.fullmatch(redacted_at):
            raise ClaimStoreError(f"invalid redacted_at on {claim['claim_id']}")
        if (claim["text"] != REDACTED_TEXT or claim["tags"]
                or claim["source"] is not None or claim["quote"] is not None
                or claim["session_hint"] is not None):
            raise ClaimStoreError(f"redacted claim still contains content: {claim['claim_id']}")


def _validate_rows(rows, source):
    """Validate identity and supersession relations for a complete row set."""
    by_id = {}
    for claim in rows:
        if claim["claim_id"] in by_id:
            raise ClaimStoreError(f"{source}: duplicate claim_id: {claim['claim_id']}")
        by_id[claim["claim_id"]] = claim
    for claim in rows:
        target = claim["superseded_by"]
        if claim["status"] == "已过期":
            if target is None:
                raise ClaimStoreError(f"{source}: expired claim without successor: {claim['claim_id']}")
            if target not in by_id:
                raise ClaimStoreError(
                    f"{source}: dangling superseded_by on {claim['claim_id']}: {target}")
        elif target is not None:
            raise ClaimStoreError(
                f"{source}: superseded_by set on non-expired claim: {claim['claim_id']}")
    for claim in rows:
        seen, cursor = set(), claim["claim_id"]
        while cursor is not None:
            if cursor in seen:
                raise ClaimStoreError(
                    f"{source}: supersession cycle reached from {claim['claim_id']}")
            seen.add(cursor)
            cursor = by_id[cursor]["superseded_by"] if cursor in by_id else None


def _serialize_rows(rows):
    return "".join(
        json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for r in rows)


def _write_bytes(path, payload):
    """Write bytes atomically with an fsync before replacement."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".claims-")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        for attempt in range(5):
            try:
                os.replace(tmp, path)
                break
            except OSError as exc:
                if attempt == 4 or getattr(exc, "winerror", None) not in (5, 32):
                    raise
                time.sleep(0.05 * (attempt + 1))
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _actor():
    value = os.environ.get("CLAIM_LEDGER_ACTOR", "").strip()
    return value[:80] or None


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
    """Single-file claim store with one cross-process writer at a time."""

    def __init__(self, path=None, *, lock_timeout=DEFAULT_LOCK_TIMEOUT):
        if not isinstance(lock_timeout, (int, float)) or lock_timeout < 0:
            raise ClaimStoreError("lock_timeout must be a non-negative number")
        self.path = Path(path or default_store())
        self.lock_timeout = float(lock_timeout)

    @contextlib.contextmanager
    def _locked(self):
        try:
            with FileLock(self.path.with_name(self.path.name + ".lock"),
                          timeout=self.lock_timeout):
                yield
        except LockTimeout as exc:
            raise ClaimStoreBusy(str(exc)) from exc

    def _read(self):
        if not self.path.exists():
            return []
        try:
            text = self.path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ClaimStoreError(f"cannot read {self.path}: {exc}") from exc
        return self._parse_rows(text, self.path)

    def _parse_rows(self, text, source):
        rows = []
        for lineno, line in enumerate(text.splitlines(), 1):
            try:
                claim = json.loads(line)
                _validate_claim(claim)
            except (json.JSONDecodeError, ClaimStoreError) as exc:
                raise ClaimStoreError(f"{source} line {lineno}: {exc}") from exc
            rows.append(claim)
        _validate_rows(rows, source)
        return rows

    def _write(self, rows):
        _validate_rows(rows, self.path)
        _write_bytes(self.path, _serialize_rows(rows).encode("utf-8"))

    def digest(self, rows=None):
        """SHA-256 over the canonical serialization; independent of file formatting."""
        if rows is None:
            rows = self._read()
        body = "".join(
            json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            for r in rows)
        return hashlib.sha256(body.encode("utf-8")).hexdigest()

    def backup(self, directory=None, *, keep=None):
        """Write a verified snapshot plus manifest; optionally prune older ones."""
        if keep is not None and (type(keep) is not int or keep < 1):
            raise ClaimStoreError("keep must be a positive integer when provided")
        with self._locked():
            if not self.path.exists():
                raise ClaimStoreError(f"claim store not found: {self.path}")
            result = self._backup_locked(self._read(), directory)
        if keep is not None:
            result["pruned"] = self._prune_backups(result, keep)
        return result

    def _prune_backups(self, result, keep):
        """Delete older snapshots beyond ``keep``; the fresh one is never removed."""
        backup_dir = Path(result["path"]).parent
        prefix = f"{self.path.stem}-"
        snapshots = sorted(
            (p for p in backup_dir.glob(prefix + "*.jsonl")
             if not p.name.endswith(".manifest.json")),
            key=lambda p: p.name, reverse=True)
        fresh = Path(result["path"]).resolve()
        pruned = []
        for old in snapshots[keep:]:
            if old.resolve() == fresh:
                continue
            manifest = old.with_name(old.stem + ".manifest.json")
            try:
                old.unlink()
                if manifest.is_file():
                    manifest.unlink()
            except OSError as exc:
                raise ClaimStoreError(f"could not prune backup {old.name}: {exc}") from exc
            pruned.append(old.name)
        return pruned

    def audit_entries(self, *, limit=50, action=None):
        """Return audit entries, newest first; corruption refuses service."""
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ClaimStoreError("limit must be an integer between 1 and 1000")
        if action is not None and action not in ("redact", "delete", "restore"):
            raise ClaimStoreError("action must be redact, delete or restore")
        path = self._audit_path()
        if not path.is_file():
            return {"ok": True, "path": str(path), "total": 0, "entries": []}
        entries = []
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ClaimStoreError(f"{path} line {lineno}: invalid audit entry") from exc
            if not isinstance(entry, dict) or entry.get("kind") != AUDIT_KIND:
                raise ClaimStoreError(f"{path} line {lineno}: not an audit entry")
            entries.append(entry)
        if action is not None:
            entries = [entry for entry in entries if entry.get("action") == action]
        return {"ok": True, "path": str(path), "total": len(entries),
                "entries": list(reversed(entries))[:limit]}

    def backups(self):
        """List snapshots with their manifests, newest first."""
        backup_dir = self._backup_dir()
        out = []
        if backup_dir.is_dir():
            for manifest_path in sorted(backup_dir.glob("*.manifest.json"), reverse=True):
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    raise ClaimStoreError(
                        f"invalid backup manifest {manifest_path.name}: {exc}") from exc
                if not isinstance(manifest, dict) or manifest.get("kind") != BACKUP_KIND:
                    raise ClaimStoreError(
                        f"unknown manifest kind in {manifest_path.name}")
                snapshot = manifest_path.with_name(
                    manifest_path.name[: -len(".manifest.json")] + ".jsonl")
                out.append({
                    "snapshot": snapshot.name,
                    "manifest": manifest_path.name,
                    "present": snapshot.is_file(),
                    "created_at": manifest.get("created_at"),
                    "claims": manifest.get("claims"),
                    "redacted": manifest.get("redacted"),
                    "bytes": manifest.get("bytes"),
                    "file_sha256": manifest.get("file_sha256"),
                    "store_sha256": manifest.get("store_sha256"),
                })
        return {"ok": True, "directory": str(backup_dir), "backups": out}

    def init(self):
        """Create an empty store file; refuse to touch one that already has data."""
        if self.path.is_file() and self.path.stat().st_size > 0:
            raise ClaimStoreError(f"store already exists and is not empty: {self.path}")
        created = not self.path.exists()
        if created:
            _write_bytes(self.path, b"")
        elif not self.path.is_file():
            _write_bytes(self.path, b"")
        absolute = str(self.path.resolve())
        store_flag = f'--store "{absolute}"' if absolute != str(Path(default_store()).resolve()) else ""
        return {
            "ok": True,
            "store": absolute,
            "created": created,
            "next_steps": [
                f'claim record "One-line decision" {store_flag}'.replace("  ", " "),
                f"claim brief {store_flag}".replace("  ", " "),
                f"claim mcp {store_flag}".replace("  ", " "),
                "claim skill install --host claude --scope user",
            ],
        }

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
        with self._locked():
            return self._record_locked(
                text, topic=topic, tags=tags, supersedes=supersedes, dispute=dispute,
                source=source, quote=quote, session_hint=session_hint)

    def _record_locked(self, text, *, topic, tags, supersedes, dispute,
                       source, quote, session_hint):
        rows = self._read()
        by_id = {c["claim_id"]: c for c in rows}
        for claim in rows:
            if claim["text"] == text and not claim.get("redacted_at"):
                raise ClaimStoreError(
                    f"identical claim already exists: {claim['claim_id']}; supersede it instead of duplicating")
        targets = _supersede_targets(supersedes)
        for target in targets:
            if target not in by_id:
                raise ClaimStoreError(f"--supersedes target not found: {target}")
            if by_id[target].get("redacted_at"):
                raise ClaimStoreError(f"--supersedes target is redacted: {target}")
            if by_id[target]["status"] == "已过期":
                raise ClaimStoreError(f"--supersedes target already superseded: {target}")
        current = [c for c in rows
                   if c["status"] == "现行" and not c.get("redacted_at")]
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

    def claims(self, *, status=None, topic=None, query=None, include_redacted=False):
        rows = self._read()
        if not include_redacted:
            rows = [c for c in rows if not c.get("redacted_at")]
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
        visible = [c for c in rows if not c.get("redacted_at")]
        current = [c for c in visible if c["status"] == "现行" and (topic is None or c["topic"] == topic)]
        disputed = [c for c in visible if c["status"] == "有争议" and (topic is None or c["topic"] == topic)]
        expired = [c for c in visible if c["status"] == "已过期" and (topic is None or c["topic"] == topic)]
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
            packet["status"] = "budget_exhausted" if visible else "empty"
        _measure(packet)
        return packet

    def _backup_dir(self, directory=None):
        return Path(directory) if directory is not None else self.path.parent / "backups"

    def _backup_locked(self, rows, directory=None):
        backup_dir = self._backup_dir(directory)
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        base = f"{self.path.stem}-{stamp}"
        target = backup_dir / f"{base}.jsonl"
        counter = 1
        while target.exists():
            target = backup_dir / f"{base}-{counter}.jsonl"
            counter += 1
        body = _serialize_rows(rows).encode("utf-8")
        _write_bytes(target, body)
        manifest = {
            "schema_version": 1,
            "kind": BACKUP_KIND,
            "created_at": _utc_now(),
            "source_name": self.path.name,
            "claims": len(rows),
            "redacted": sum(1 for row in rows if row.get("redacted_at")),
            "bytes": len(body),
            "file_sha256": hashlib.sha256(body).hexdigest(),
            "store_sha256": self.digest(rows),
        }
        manifest_path = backup_dir / f"{base}.manifest.json"
        _write_bytes(
            manifest_path,
            (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"))
        return {"ok": True, "path": str(target), "manifest": str(manifest_path),
                "claims": len(rows), "bytes": len(body),
                "file_sha256": manifest["file_sha256"], "store_sha256": manifest["store_sha256"]}

    def _chain_ids(self, rows, claim_id):
        adjacency = {}
        for row in rows:
            adjacency.setdefault(row["claim_id"], set())
            target = row["superseded_by"]
            if target is not None:
                adjacency.setdefault(target, set())
                adjacency[row["claim_id"]].add(target)
                adjacency[target].add(row["claim_id"])
        seen = set()
        stack = [claim_id]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(adjacency.get(current, ()))
        return sorted(seen)

    def _audit_path(self):
        return self.path.with_name(self.path.stem + ".audit.jsonl")

    def _append_audit(self, action, claim_ids, before_digest, after_digest, backup):
        entry = {
            "schema_version": 1,
            "kind": AUDIT_KIND,
            "action": action,
            "claim_ids": list(claim_ids),
            "at": _utc_now(),
            "actor": _actor(),
            "store_sha256_before": before_digest,
            "store_sha256_after": after_digest,
            "backup_file": Path(backup["path"]).name if backup else None,
            "backup_file_sha256": backup["file_sha256"] if backup else None,
        }
        path = self._audit_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return str(path)

    def _finish_mutation(self, action, rows_before, rows_after, claim_ids,
                         before_digest, backup, *, previous_exists=True):
        self._write(rows_after)
        after_digest = self.digest(rows_after)
        try:
            audit = self._append_audit(action, claim_ids, before_digest, after_digest, backup)
        except OSError as exc:
            if previous_exists:
                self._write(rows_before)
            elif self.path.exists():
                self.path.unlink()
            raise ClaimStoreError(
                f"{action} rolled back: could not write audit log: {exc}") from exc
        return audit, after_digest

    def redact(self, claim_id, *, cascade=False, keep_backup=True, backup_dir=None):
        """Remove claim content in place while preserving identity and chain shape.

        A backup is written first unless ``keep_backup`` is False, then the store
        and an audit entry. Redacted rows are excluded from briefs, listings and
        evidence resolution by default; the topic is replaced too, since it may be
        sensitive. Derived evidence indexes must be rebuilt or purged separately.
        """
        if not isinstance(claim_id, str) or not CLAIM_ID_RE.fullmatch(claim_id):
            raise ClaimStoreError("claim_id must be a valid claim id")
        with self._locked():
            rows = self._read()
            by_id = {row["claim_id"]: row for row in rows}
            if claim_id not in by_id:
                raise ClaimStoreError(f"claim not found: {claim_id}")
            if by_id[claim_id].get("redacted_at"):
                return {"ok": True, "action": "redact", "claim_ids": [claim_id],
                        "already_redacted": True, "store_sha256": self.digest(rows)}
            targets = self._chain_ids(rows, claim_id) if cascade else [claim_id]
            targets = [target for target in targets
                       if not by_id[target].get("redacted_at")]
            if not targets:
                return {"ok": True, "action": "redact", "claim_ids": [claim_id],
                        "already_redacted": True, "store_sha256": self.digest(rows)}
            rows_before = [dict(row) for row in rows]
            before_digest = self.digest(rows)
            backup = self._backup_locked(rows, backup_dir) if keep_backup else None
            now = _utc_now()
            for target in targets:
                row = by_id[target]
                row["text"] = REDACTED_TEXT
                row["tags"] = []
                row["topic"] = "redacted"
                row["source"] = None
                row["quote"] = None
                row["session_hint"] = None
                row["redacted_at"] = now
                row["updated_at"] = now
            audit, after_digest = self._finish_mutation(
                "redact", rows_before, rows, targets, before_digest, backup)
            return {"ok": True, "action": "redact", "claim_ids": targets,
                    "already_redacted": False, "backup": backup, "audit": audit,
                    "store_sha256": after_digest}

    def delete(self, claim_id, *, cascade=False, keep_backup=True, backup_dir=None):
        """Permanently remove one claim, or its whole supersession chain with cascade."""
        if not isinstance(claim_id, str) or not CLAIM_ID_RE.fullmatch(claim_id):
            raise ClaimStoreError("claim_id must be a valid claim id")
        with self._locked():
            rows = self._read()
            by_id = {row["claim_id"]: row for row in rows}
            if claim_id not in by_id:
                raise ClaimStoreError(f"claim not found: {claim_id}")
            referenced_by = sorted(
                row["claim_id"] for row in rows if row["superseded_by"] == claim_id)
            if referenced_by and not cascade:
                raise ClaimStoreError(
                    f"claim {claim_id} is referenced by {', '.join(referenced_by)}; "
                    "use --cascade to delete the whole supersession chain")
            remove_ids = set(self._chain_ids(rows, claim_id)) if cascade else {claim_id}
            remaining = [row for row in rows if row["claim_id"] not in remove_ids]
            _validate_rows(remaining, self.path)
            rows_before = [dict(row) for row in rows]
            before_digest = self.digest(rows)
            backup = self._backup_locked(rows, backup_dir) if keep_backup else None
            audit, after_digest = self._finish_mutation(
                "delete", rows_before, remaining, sorted(remove_ids),
                before_digest, backup)
            return {"ok": True, "action": "delete", "claim_ids": sorted(remove_ids),
                    "backup": backup, "audit": audit, "store_sha256": after_digest}

    def restore(self, backup_path, *, overwrite=False, allow_unverified=False,
                backup_dir=None):
        """Verify and atomically restore a backup snapshot, preserving the current store."""
        backup_path = Path(backup_path)
        if not backup_path.is_file():
            raise ClaimStoreError(f"backup not found: {backup_path}")
        raw = backup_path.read_bytes()
        manifest_path = backup_path.with_name(backup_path.stem + ".manifest.json")
        manifest = None
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise ClaimStoreError(f"invalid backup manifest: {exc}") from exc
            if not isinstance(manifest, dict) or manifest.get("kind") != BACKUP_KIND:
                raise ClaimStoreError("backup manifest has an unknown kind")
            if manifest.get("bytes") != len(raw):
                raise ClaimStoreError("backup byte count does not match its manifest")
            if manifest.get("file_sha256") != hashlib.sha256(raw).hexdigest():
                raise ClaimStoreError("backup file digest does not match its manifest")
        elif not allow_unverified:
            raise ClaimStoreError(
                "backup manifest is missing; pass --allow-unverified to restore raw JSONL")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ClaimStoreError(f"backup is not UTF-8: {exc}") from exc
        rows = self._parse_rows(text, backup_path)
        store_digest = self.digest(rows)
        if manifest is not None:
            if manifest.get("store_sha256") != store_digest:
                raise ClaimStoreError("backup store digest does not match its manifest")
            if manifest.get("claims") != len(rows):
                raise ClaimStoreError("backup claim count does not match its manifest")
        with self._locked():
            previous_exists = self.path.exists()
            current_rows = self._read()
            if previous_exists and current_rows and not overwrite:
                raise ClaimStoreError(
                    "destination store is not empty; pass overwrite to replace it")
            before_digest = self.digest(current_rows)
            previous_backup = (
                self._backup_locked(current_rows, backup_dir)
                if previous_exists and current_rows else None)
            audit, after_digest = self._finish_mutation(
                "restore", current_rows, rows, [], before_digest,
                previous_backup, previous_exists=previous_exists)
            return {"ok": True, "action": "restore", "restored": str(backup_path),
                    "claims": len(rows), "backup_of_previous": previous_backup,
                    "audit": audit, "store_sha256": after_digest}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="claim-ledger", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    init_cmd = commands.add_parser("init", help="create an empty claim store and print next steps")
    init_cmd.add_argument("--store")
    init_cmd.add_argument("--json", action="store_true")

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
    listing.add_argument("--include-redacted", action="store_true",
                         help="include content-free redaction tombstones")

    backup = commands.add_parser("backup", help="write a verified snapshot and manifest")
    backup.add_argument("--store")
    backup.add_argument("--out", help="backup directory (default: <store>/backups)")
    backup.add_argument("--keep", type=int,
                        help="after writing, delete older snapshots beyond this many")
    backup.add_argument("--json", action="store_true")

    listing_backups = commands.add_parser("backups", help="list snapshots and manifests")
    listing_backups.add_argument("--store")

    audit = commands.add_parser("audit", help="inspect the redact/delete/restore audit log")
    audit.add_argument("--store")
    audit.add_argument("--limit", type=int, default=50)
    audit.add_argument("--action", choices=["redact", "delete", "restore"])
    audit.add_argument("--json", action="store_true")

    restore = commands.add_parser("restore", help="verify and restore a backup snapshot")
    restore.add_argument("--from", dest="backup_path", required=True)
    restore.add_argument("--store")
    restore.add_argument("--yes", action="store_true",
                         help="replace a non-empty destination store")
    restore.add_argument("--allow-unverified", action="store_true",
                         help="allow a raw JSONL backup without a manifest")
    restore.add_argument("--backup-dir")
    restore.add_argument("--json", action="store_true")

    redact = commands.add_parser(
        "redact", help="remove claim content in place while keeping identity and history")
    redact.add_argument("claim_id")
    redact.add_argument("--store")
    redact.add_argument("--cascade", action="store_true",
                        help="redact the whole supersession chain")
    redact.add_argument("--backup-dir")
    redact.add_argument("--no-backup", action="store_true",
                        help="do not retain a plaintext pre-redaction copy")
    redact.add_argument("--yes", action="store_true", help="confirm content destruction")
    redact.add_argument("--json", action="store_true")

    delete = commands.add_parser(
        "delete", help="permanently delete a claim, or its supersession chain")
    delete.add_argument("claim_id")
    delete.add_argument("--store")
    delete.add_argument("--cascade", action="store_true",
                        help="delete every claim in the supersession chain")
    delete.add_argument("--backup-dir")
    delete.add_argument("--no-backup", action="store_true",
                        help="do not retain a plaintext pre-deletion copy")
    delete.add_argument("--yes", action="store_true", help="confirm permanent deletion")
    delete.add_argument("--json", action="store_true")

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
        elif args.command == "init":
            result = ClaimStore(args.store).init()
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(f"store ready: {result['store']}" + ("" if result["created"] else " (already existed, empty)"))
                for step in result["next_steps"]:
                    print("  " + step)
        elif args.command == "backups":
            result = ClaimStore(args.store).backups()
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "audit":
            result = ClaimStore(args.store).audit_entries(limit=args.limit, action=args.action)
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(f"audit log: {result['path']} ({result['total']} entries)")
                for entry in result["entries"]:
                    actor = entry.get("actor") or "-"
                    backup_name = entry.get("backup_file") or "-"
                    print(f"{entry['at']} {entry['action']:<8} {','.join(entry['claim_ids'])} "
                          f"actor={actor} backup={backup_name}")
        elif args.command == "backup":
            result = ClaimStore(args.store).backup(args.out, keep=args.keep)
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(f"backup {result['path']} ({result['claims']} claims, sha256 {result['file_sha256'][:12]}…)")
                if result.get("pruned"):
                    print("pruned: " + ", ".join(result["pruned"]))
        elif args.command == "restore":
            result = ClaimStore(args.store).restore(
                args.backup_path, overwrite=args.yes,
                allow_unverified=args.allow_unverified, backup_dir=args.backup_dir)
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(f"restored {result['claims']} claims from {result['restored']}")
        elif args.command in ("redact", "delete"):
            if not args.yes:
                raise ClaimStoreError(
                    f"{args.command} is destructive; pass --yes to confirm")
            store = ClaimStore(args.store)
            operation = getattr(store, args.command)
            result = operation(
                args.claim_id, cascade=args.cascade,
                keep_backup=not args.no_backup, backup_dir=args.backup_dir)
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            elif result.get("already_redacted"):
                print(f"claim {args.claim_id} is already redacted")
            else:
                verb = "redacted" if args.command == "redact" else "deleted"
                suffix = (f"backup {result['backup']['path']}"
                          if result.get("backup") else "no backup retained")
                print(f"{verb} {','.join(result['claim_ids'])}; {suffix}")
        else:
            if args.limit < 1 or args.limit > 1000:
                raise ClaimStoreError("limit must be between 1 and 1000")
            rows = ClaimStore(args.store).claims(
                status=args.status, topic=args.topic, query=args.query,
                include_redacted=args.include_redacted)
            print(json.dumps({"ok": True, "count": len(rows),
                              "claims": rows[:args.limit]}, ensure_ascii=False, indent=2))
        return 0
    except (ClaimStoreError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc), "error_type": type(exc).__name__},
                         ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
