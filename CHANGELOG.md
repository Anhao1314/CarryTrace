# Changelog

Package versions below describe the Python distribution, not a claim of a PyPI release
or a corresponding Git tag.

## Unreleased: documentation and onboarding

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
