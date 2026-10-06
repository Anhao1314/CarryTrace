# Changelog

Package versions below describe the Python distribution, not a claim of a PyPI release
or a corresponding Git tag.

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
