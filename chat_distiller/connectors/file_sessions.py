"""File-backed session sources for the Context Gateway.

Two connector kinds share this module:

- ``generic``: the documented public JSONL contract (``session_id`` / ``role`` /
  ``content`` / ``timestamp``), one session per ``session_id``. Parsing is strict:
  a bad row refuses the whole file, matching the ``extract_sessions`` adapter.
- ``claude-code``: Claude Code session transcripts (``~/.claude/projects``),
  one session per ``<uuid>.jsonl`` file. Unparsable lines and non-conversation
  rows are skipped and disclosed in the record's ``degraded`` notes.

Both are read-only. The source of truth stays with the user's files; the gateway
stages derived transcript Markdown next to the Doubao sources and fingerprints
each session so ``sync`` only re-extracts what changed.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from .._internal.source_adapters.transcript import (
    CN_TZ, build_transcript, clean_text, slug_preview,
)

SAFE_SID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\Z")
GENERIC_ROLES = {"user", "assistant", "tool", "system"}


class SourceChangedError(OSError):
    """A source file changed while it was being read or extracted."""


def parse_timestamp(value):
    """Accept RFC-3339 with optional millis; return an aware datetime or None."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        pass
    match = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", text)
    if not match:
        return None
    try:
        return datetime.fromisoformat(match.group(1)).replace(tzinfo=None)
    except ValueError:
        return None


def _cn(moment):
    return moment.astimezone(CN_TZ).strftime("%Y-%m-%d %H:%M") if moment else ""


def _text_blocks(content):
    """Pull human-readable text out of a message content value."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "\n".join(parts)
    return ""


def rows_fingerprint(sid, rows):
    """Stable per-session hash over canonical row JSON (formatting-independent)."""
    digest = hashlib.sha256()
    digest.update(f"session:{sid}\n".encode("utf-8"))
    for row in rows:
        digest.update(
            json.dumps(row, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


class FileSessionSource:
    """Read-only session source over user-supplied JSONL files."""

    def __init__(self, kind, input_path):
        if kind not in ("generic", "claude-code"):
            raise ValueError("unsupported file source kind: " + str(kind))
        self.kind = kind
        self.input = Path(input_path).expanduser().resolve()
        if not self.input.exists():
            raise ValueError(f"{kind} session source does not exist: {self.input}")

    # -- discovery ----------------------------------------------------------

    def files(self):
        """JSONL files covered by this source, sorted and validated."""
        if self.input.is_file():
            return [self.input]
        if self.input.is_dir():
            found = sorted(p for p in self.input.rglob("*.jsonl")
                           if p.is_file() and not p.is_symlink())
            if not found:
                raise ValueError(f"no .jsonl sessions under {self.input}")
            return found
        raise ValueError(
            f"{self.kind} source must be a JSONL file or a directory of them: {self.input}")

    def snapshot(self):
        """Map session_id -> {"fingerprint", "path", "rows"} for current sessions."""
        out = {}
        for path in self.files():
            for sid, rows in self._group(self._read_file(path), path).items():
                out[sid] = {"fingerprint": rows_fingerprint(sid, rows),
                            "path": path, "rows": rows}
        if not out:
            raise ValueError(f"no sessions found in {self.kind} source: {self.input}")
        return out

    # -- extraction ---------------------------------------------------------

    def extract(self, sid, entry, out_dir):
        """Stage one session's transcript; refuse when the file changed mid-read."""
        out_dir = Path(out_dir)
        rows = self._read_file(entry["path"])
        grouped = self._group(rows, entry["path"])
        if sid not in grouped:
            raise ValueError(f"session disappeared from source: {sid}")
        if rows_fingerprint(sid, grouped[sid]) != entry["fingerprint"]:
            raise SourceChangedError(f"{self.kind} session changed during read: {sid}")
        record, turns, replies, tool_trail, degraded = self._convert(sid, grouped[sid], entry["path"])
        transcript = build_transcript(
            sid, record["created"], record["updated"], turns, replies, tool_trail,
            record["agents"], 0, record["rel_source"], degraded)
        target = out_dir / record["transcript"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(transcript, encoding="utf-8")
        rows_after = self._read_file(entry["path"])
        after = self._group(rows_after, entry["path"]).get(sid, [])
        if rows_fingerprint(sid, after) != entry["fingerprint"]:
            raise SourceChangedError(f"{self.kind} session changed during read: {sid}")
        return record

    # -- row handling -------------------------------------------------------

    def _read_file(self, path):
        try:
            return path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as exc:
            raise ValueError(f"cannot read {self.kind} session file {path}: {exc}") from exc

    def _group(self, raw_lines, path):
        """Parse every line; return {session_id: [row, ...]}.

        The generic contract is validated here so ``connect`` fails fast on a
        malformed file — the whole input is refused before anything is staged.
        """
        sessions = {}
        for lineno, line in enumerate(raw_lines, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("record must be an object")
                if self.kind == "generic":
                    if row.get("role") not in GENERIC_ROLES:
                        raise ValueError(
                            f"role must be one of {sorted(GENERIC_ROLES)}")
                    if not isinstance(row.get("content"), str):
                        raise ValueError("content must be a string")
                    if parse_timestamp(row.get("timestamp")) is None:
                        raise ValueError(
                            "timestamp must be an ISO 8601 string with timezone")
            except (ValueError, TypeError) as exc:
                if self.kind == "generic":
                    raise ValueError(f"{path}: line {lineno}: {exc}") from exc
                continue  # claude-code files tolerate foreign/metadata lines
            sid = self._session_id(row, path, lineno)
            sessions.setdefault(sid, []).append(row)
        if not sessions:
            raise ValueError(f"{path}: no parsable records")
        return sessions

    def _session_id(self, row, path, lineno):
        if self.kind == "generic":
            sid = row.get("session_id")
            if not isinstance(sid, str) or not SAFE_SID_RE.fullmatch(sid):
                raise ValueError(
                    f"{path}: line {lineno}: session_id must be 1-120 safe ASCII characters")
            return sid
        sid = row.get("sessionId")
        if isinstance(sid, str) and SAFE_SID_RE.fullmatch(sid):
            return sid
        return SAFE_SID_RE.sub("", path.stem)[:120] or "session"

    # -- conversion ---------------------------------------------------------

    def _convert(self, sid, rows, path):
        if self.kind == "generic":
            return self._convert_generic(sid, rows, path)
        return self._convert_claude_code(sid, rows, path)

    def _convert_generic(self, sid, rows, path):
        timed = []
        for index, row in enumerate(rows):
            role = row.get("role")
            if role not in GENERIC_ROLES:
                raise ValueError(f"{path}: role must be one of {sorted(GENERIC_ROLES)}")
            if not isinstance(row.get("content"), str):
                raise ValueError(f"{path}: content must be a string")
            moment = parse_timestamp(row.get("timestamp"))
            if moment is None:
                raise ValueError(
                    f"{path}: timestamp must be an ISO 8601 string with timezone")
            timed.append((moment, index, row))
        timed.sort(key=lambda item: (item[0], item[1]))
        turns, replies = [], []
        for moment, _, row in timed:
            if row["role"] in {"system", "tool"}:
                continue
            text = clean_text(row["content"])
            if not text:
                continue
            if row["role"] == "user":
                turns.append((moment.isoformat(), _cn(moment), text))
            else:
                replies.append(text)
        record = self._record(
            sid, created=_cn(timed[0][0]), updated=_cn(timed[-1][0]),
            turns=turns, replies=replies, agents=["generic"],
            degraded=[], rel_source=f"generic/{path.name}")
        return record, turns, replies, [], []

    def _convert_claude_code(self, sid, rows, path):
        def sort_key(item):
            index, row = item
            moment = parse_timestamp(row.get("timestamp"))
            return (moment is None, moment or index, index)

        turns, replies, tool_trail = [], [], []
        sidechains = skipped_meta = 0
        for index, row in sorted(enumerate(rows), key=sort_key):
            moment = parse_timestamp(row.get("timestamp"))
            kind = row.get("type")
            if kind not in ("user", "assistant"):
                skipped_meta += 1
                continue
            if row.get("isSidechain"):
                sidechains += 1
                continue
            message = row.get("message")
            if not isinstance(message, dict):
                skipped_meta += 1
                continue
            content = message.get("content")
            if kind == "user":
                # Tool results ride on user-role rows as non-text blocks; real
                # user intent is plain text (string or text blocks).
                if isinstance(content, list) and not _text_blocks(content):
                    skipped_meta += 1
                    continue
                text = clean_text(_text_blocks(content))
                if not text:
                    skipped_meta += 1
                    continue
                turns.append((moment.isoformat() if moment else "", _cn(moment), text))
            else:
                if isinstance(content, str):
                    text = clean_text(content)
                    if text:
                        replies.append(text)
                    continue
                if not isinstance(content, list):
                    skipped_meta += 1
                    continue
                reply_parts, trail = [], []
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "text":
                        cleaned = clean_text(block.get("text", ""))
                        if cleaned:
                            reply_parts.append(cleaned)
                    elif block.get("type") == "tool_use":
                        name = block.get("name")
                        if isinstance(name, str) and name:
                            trail.append(name)
                if reply_parts:
                    replies.append("\n\n".join(reply_parts))
                tool_trail.extend(trail)
        degraded = []
        if sidechains:
            degraded.append(f"excluded {sidechains} sidechain (subagent) rows")
        if skipped_meta:
            degraded.append(f"excluded {skipped_meta} meta/system rows")
        moments = [m for m in (parse_timestamp(row.get("timestamp")) for row in rows) if m]
        record = self._record(
            sid, created=_cn(min(moments)) if moments else "",
            updated=_cn(max(moments)) if moments else "",
            turns=turns, replies=replies, agents=["claude-code"],
            degraded=degraded, rel_source=f"claude-code/{path.name}")
        return record, turns, replies, tool_trail, degraded

    @staticmethod
    def _record(sid, *, created, updated, turns, replies, agents, degraded, rel_source):
        return {
            "session_id": sid,
            "created": created,
            "updated": updated,
            "first_request": slug_preview(turns[0][2]) if turns else "",
            "user_turns": len(turns),
            "assistant_replies": len(replies),
            "chars": sum(len(t[2]) for t in turns) + sum(len(r) for r in replies),
            "agents": agents,
            "degraded": degraded,
            "transcript": f"transcripts/{sid}.transcript.md",
            "empty": not turns and not replies,
            "rel_source": rel_source,
        }
