# Changelog

Package versions below describe the Python distribution, not a claim of a PyPI release
or a corresponding Git tag.

## Unreleased: CarryTrace brand migration (runtime 0.4.0)

- New CarryTrace identity, theme-aware vector artwork, bilingual Skill-first homepage and canonical repository links.
- Added `carrytrace` CLI; preserved `chat-distiller`, `chat_distiller`, existing environment names and data homes.
- New `carrytrace` Skill bundle and deterministic ZIP; legacy bundle remains available for compatibility.
- Explicit preview-first legacy migration keeps original instruction files outside host discovery, rejects edits/symlinks/duplicates and retains failed rollback evidence.
- Scope is branding and installation, not a new memory model or evidence of live host activation. No PyPI rename or v0.5 stable release.

## Unreleased: Skill-first pilot on package 0.4.0

- Added a portable Agent Skills-compatible bundle that guides source-linked context recovery,
  historical decision audits, cross-host handoff and authorized Generic JSONL extraction.
- Added local CLI skill install/status for Codex and Claude Code, user and project scopes.
- Added deterministic portable ZIP export for other clients that accept Agent Skills bundles; no
  claim of universal host activation or local CLI access from cloud environments.
  The managed installer is idempotent and refuses to overwrite foreign or modified skills.
- Added source and installed-wheel packaging checks; no new runtime dependencies.
- Existing Memory Engine, Knowledge Wiki, source adapters, benchmarks and publication
  authority are unchanged. No real host-agent activation, model-quality or auto-import
  improvement is claimed.

## Package 0.4.0: Context Gateway

- Added the simple `connect`, `sync`, `context`, and `status` surface for Doubao Work.
- Added automatic local session discovery, managed context home, content fingerprints, incremental extraction, and raw-session fallback context.
- Added plan-bound host-agent publication with stale-plan rejection and explicit retirement guards.
- Kept semantic distillation outside deterministic code; `sync` makes pending work visible rather than inventing memory.
- Added synthetic Gateway integration tests and an executed CLI experiment for source read-only behavior, no-op idempotence, byte budget, degraded input, and stale proposals.
- Kept legacy CLI, atomic memory schema 2, Knowledge Wiki, and frozen retrieval benchmarks compatible. No daemon, MCP, automatic LLM distillation, or PyPI publication is claimed.

## Package 0.3.0: Knowledge Wiki

- Added optional `KnowledgeStore` and `wiki` commands without changing atomic memory schema 2.
- Added cited proposals, scoped status validation, stable knowledge IDs, revision history and navigation links.
- Added conservative whole-source staleness checks, layered byte-bounded recovery and explicit Markdown exports.
- Added exclusive writer locks, revision guards and one-file compiled-state publication with failure tests.
- Added research/design notes, host synthesis workflow, a 16-command installed demo and CompileBench engineering experiments.
- Kept the old retrieval benchmark and legacy recovery packet unchanged. No automatic LLM accuracy claim or PyPI publication.

## Documentation and onboarding (2026-10-06)

- Rebuilt the homepage around the use case, a safe first run, evidence, and integration.
- Added an English README and a synchronized Chinese edition.
- Added a handwritten database-decision fixture and a generated, execution-checked demo.
- Added a documentation map, architecture/trust boundaries, ingestion guide, and contribution instructions.
- Added checks for local links, bilingual example parity, installed README commands, and generated demo drift.
- Kept the memory engine, schema, lexical algorithm, and frozen benchmark unchanged.

## Package 0.2.0: Memory Engine

Delivered in [PR #1](https://github.com/Anhao1314/chat-distiller/pull/1), merged 2026-10-06 (UTC+08:00).

- Packaged the existing implementation with a unified CLI and compatible script entry points.
- Added read-only `MemoryStore.search/get/inspect/recover`.
- Added complete-record recovery packets bounded by canonical UTF-8 JSON bytes.
- Rejected rendered-note status/kind projection drift in old and new query paths.
- Verified 137 source tests and 16 installed-wheel checks; retained the original benchmark scores.

See the [verification ledger](docs/verification.md) for evidence and limits.
