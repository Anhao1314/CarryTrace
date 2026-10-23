# Context Gateway

Context Gateway is the simple user surface over the existing Memory Engine and Knowledge Wiki.
It supports three conversation sources: **Doubao Work**, **generic JSONL** and **Claude Code**.

## Connect any conversation source

```bash
claim connect doubao                       # Doubao Work agent sessions (auto-discovered)
claim connect generic --input talks.jsonl  # any tool that can emit the public JSONL contract
claim connect claude-code                  # ~/.claude/projects, or pass --input <dir|file>
claim sync
claim context "continue the previous project"
claim status
```

Every connector feeds the same pipeline: read-only staging of clean transcripts → a review plan
(`pending/sync-plan.json`) → host-agent distillation → published memory. Connectors differ only
in how sessions are discovered and fingerprinted.

**generic JSONL contract** — one JSON object per line; the whole file is validated before
anything is staged:

```json
{"session_id": "api-freeze", "role": "user", "content": "…", "timestamp": "2026-10-20T02:00:00Z"}
{"session_id": "api-freeze", "role": "assistant", "content": "…", "timestamp": "2026-10-20T02:01:00Z"}
```

`role` is `user` / `assistant` / `tool` / `system`; `timestamp` is ISO 8601 with timezone;
`session_id` is 1–120 safe ASCII characters. Wrap any chat tool with a ten-line exporter and
its history becomes claim-minable.

**Claude Code** — reads `<dir|file>.jsonl` session transcripts (default `~/.claude/projects`).
User text turns and assistant text/tool-call blocks are kept; `thinking` blocks, tool results,
sidechain (subagent) rows and system metadata are excluded from the transcript and disclosed
in the record's `degraded` notes.

On macOS, `connect doubao` checks the current Doubao Work default `.sessions` location. If
discovery fails, pass `--sessions-root /path/to/.sessions` once. The managed home defaults to
`~/.chat-distiller`; staged sources live under `sources/<connector>/transcripts/`.

## What sync does

`sync` fingerprints each session — for Doubao only the `assignment.md` / `trajectory.jsonl`
files the adapter consumes; for file sources a per-session hash over canonical row JSON.
New or changed sessions are re-extracted into the managed, read-only source cache. A source
that changes during extraction is skipped rather than committing a mixed snapshot.

The command writes `pending/sync-plan.json`. This is a review bundle, not semantic memory.
Running sync twice without source changes leaves the sync state unchanged and does not publish duplicate memory.

## Context before semantic distillation

Before structured memory exists, `context` can return lexical/recent raw session **excerpts**.
They are untrusted evidence and force `requires_review=true`. This gives a useful first lookup without
pretending raw transcripts are verified memory.

After structured memory exists, `context` first uses the validated KnowledgeStore layered recovery and
adds relevant pending raw evidence for newer work that has not yet been reviewed.

## Handoff recovery result semantics

The Gateway distinguishes **lexical matches** from a **recent-session fallback**:

- When any raw session matches the query lexically, only matching raw sessions are candidates.
  A relevant oversized result cannot be replaced with unrelated smaller sessions.
- When no raw session matches but sessions are available, the existing orientation-only
  fallback remains. Each session has `selection_basis: "recent_fallback"`, the packet
  contains a `no lexical match` note and `requires_review` remains true.
- Actual lexical matches carry `selection_basis: "lexical_match"`.
- A structured `no_match` with no raw candidate stays `no_match`; `budget_exhausted`
  is for available candidates that do not fit the requested budget.

These are *retrieval-selection and result-status* guarantees, **not** semantic relevance,
truth verification or a completed Agent task.
[Executed synthetic regression protocol](experiments/handoff-recovery-2026-10-08.md).

## Host-agent publication

A host Agent can read the pending plan and transcripts, perform semantic judgment under
[SKILL.md](../SKILL.md), then submit a [plan-bound proposal](../references/gateway-proposal.md).

Publication checks the current plan hash, covered sessions, stable v2 identity history, explicit identity
retirements, and renderer dry-run validation. If the source changes after review, the old proposal is rejected.
This is a staleness guard, not a semantic truth detector.

## Current limits

- Doubao Work is the Doubao Work, generic JSONL and Claude Code connectors are available.
- `sync` does not call an LLM or infer importance, truth, expiry, or conflicts.
- Raw fallback is lexical/recent evidence selection, not semantic retrieval.
- No daemon, filesystem watcher, MCP server, or native Doubao lifecycle hook is claimed.
- Experiments use synthetic local sessions and do not measure real-user task success.

[Executed Gateway experiment](../benchmarks/gateway/results.md)
