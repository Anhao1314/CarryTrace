<picture>
  <source media="(prefers-color-scheme: dark) and (prefers-reduced-motion: no-preference)" srcset="assets/brand/hero-dark.svg">
  <source media="(prefers-reduced-motion: no-preference)" srcset="assets/brand/hero-light.svg">
  <source media="(prefers-color-scheme: dark)" srcset="assets/brand/hero-dark-static.svg">
  <img src="assets/brand/hero-light-static.svg" alt="CarryTrace. Your work continues. The continuity skill for AI agents." width="100%">
</picture>

# CarryTrace

**The continuity skill for AI agents.** Recover earlier decisions, constraints and source-linked context before continuing the next task.

Previously **chat-distiller**. Same local memory engine; a new Skill-first identity. No new account, hosted database or model key is required by the runtime.

[![Tests](https://github.com/Anhao1314/CarryTrace/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/Anhao1314/CarryTrace/actions/workflows/tests.yml)
[![Evidence](https://github.com/Anhao1314/CarryTrace/actions/workflows/evidence.yml/badge.svg?branch=main)](https://github.com/Anhao1314/CarryTrace/actions/workflows/evidence.yml)

[Install](#install) · [Upgrade safely](docs/brand-migration.md) · [How it works](#how-it-works) · [Evidence](#evidence) · [简体中文](README.zh-CN.md)

<a id="install"></a>
## Install once. Continue with context.

**New installation:** use a local shell-capable Agent and Python 3.9+. Install from this repository, not an assumed PyPI package named `carrytrace`.

```bash
git clone https://github.com/Anhao1314/CarryTrace.git
cd CarryTrace
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
carrytrace skill install --host codex --scope user
```

Use `--host claude` for Claude Code or `--host both` for both local hosts. The host must be able to execute the installed CLI from this environment.

**Already installed chat-distiller?** Update the same Python environment, then follow the [preview-first migration guide](docs/brand-migration.md). Do not install two active Skill names in the same host/scope.

Ask your Agent:

> Continue the previous project. Recover the decisions, constraints and open questions before changing anything.

On first use, explicitly authorize a local source or provide an existing vault. Automatic Gateway discovery currently supports Doubao Work local cache only. Installing a Skill does not grant access to Codex, Claude or ChatGPT history.

## Useful beyond a single conversation

| Your task | What CarryTrace helps the host do |
| --- | --- |
| Resume a build | Recover prior choices and constraints with source identifiers. |
| Review a changed decision | Distinguish current, superseded and disputed records. |
| Hand off to another Agent | Assemble a bounded context packet, with consent for the destination. |

[Skill guide](docs/skill-first.md) · [Portable Skill](chat_distiller/skills/carrytrace/SKILL.md)

```bash
carrytrace skill status --host codex --scope user --json
carrytrace skill export --out carrytrace-skill.zip
```

The ZIP contains instructions, not runtime code or private memory. Import and automatic activation depend on the destination host and remain unverified by our offline tests.

<a id="how-it-works"></a>
## One Skill. An existing local engine.

**You ask → the host reads the Skill → the local engine selects evidence → the host reviews and continues.**

The Skill routes requests. Context Gateway finds relevant context; Memory Engine keeps stable identities; Knowledge Wiki maintains derived, versioned pages. The human or authorized host still judges meaning. A valid citation is not proof of a true conclusion.

`carrytrace` is the new CLI entry. `chat-distiller`, `chat_distiller`, `CHAT_DISTILLER_HOME` and `~/.chat-distiller` remain compatible. The runtime stays at **0.4.0** during this brand pilot; no data migration or new independent database is required.

<details>
<summary><strong>Advanced engine workflows and legacy CLI examples</strong></summary>

## Start here: three commands

[Context Gateway guide](docs/context-gateway.md): the compatible `connect / sync / context` path remains available. Do not treat recent-session fallback as a lexical match.

<a id="demo"></a>
## Run the full lifecycle

From the installed environment, run this synthetic demo in the repository root. It creates a new disposable directory, not a personal vault. It changes an example from SQLite to PostgreSQL; it does not connect to or migrate an actual database.

<!-- verify:lifecycle -->
```bash
export WIKI_DEMO_PARENT="$(mktemp -d)"
python tools/wiki_demo.py --out "$WIKI_DEMO_PARENT/run"
```

<!-- verify:lifecycle-expected -->
```json
{
  "ok": true,
  "model_calls": 0,
  "commands_executed": 16
}
```

The 16 commands and 12 checks use handwritten inputs, a prewritten synthesis and extractive refresh. No model is called. [Demo source](tools/wiki_demo.py) · [Checked receipt](examples/wiki/lifecycle.expected.json).

![ Synthetic lifecycle, not a model evaluation](assets/wiki-lifecycle.svg)

<a id="quick-start"></a>
<a id="knowledge-wiki"></a>
## Manual memory and Wiki walkthrough

Use the installed CLI from this checkout. These commands define `DEMO_DIR` for the SDK and ingestion examples. The cards are synthetic. Never initialize fresh identities over an existing vault.

<!-- verify:quickstart -->
```bash
export DEMO_DIR="$(mktemp -d)"
mkdir "$DEMO_DIR/vault"
chat-distiller migrate --mode init --distill examples/recovery/distill.json --out "$DEMO_DIR/memory.json"
chat-distiller render --distill "$DEMO_DIR/memory.json" --vault "$DEMO_DIR/vault"
chat-distiller recover --vault "$DEMO_DIR/vault" --query database --max-bytes 4096 > "$DEMO_DIR/recovery.json"
python -m json.tool "$DEMO_DIR/recovery.json"
```

<!-- verify:expected -->
```json
{
  "status": "ready",
  "requires_review": true,
  "used_bytes": 1398,
  "budget_bytes": 4096
}
```

`ready` means records fit, not truth or task completion. The unresolved timeout remains review-required. The whole serialized UTF-8 JSON packet is byte-bounded; bytes are not tokens.

<!-- verify:wiki -->
```bash
chat-distiller wiki prepare --vault "$DEMO_DIR/vault" --topic database --query database > "$DEMO_DIR/proposal.json"
chat-distiller wiki compile --vault "$DEMO_DIR/vault" --proposal "$DEMO_DIR/proposal.json"
chat-distiller wiki compile --vault "$DEMO_DIR/vault" --proposal "$DEMO_DIR/proposal.json" --apply
chat-distiller wiki recover --vault "$DEMO_DIR/vault" --query database --max-bytes 8192 > "$DEMO_DIR/knowledge.json"
chat-distiller wiki export --vault "$DEMO_DIR/vault" --out "$DEMO_DIR/wiki-view"
```

`prepare` is extractive; the host supplies semantic synthesis. `compile` previews; only `--apply` publishes. Source changes invalidate old pages, including unrelated changes; recompile the same topic to retain identity and prior revisions. Markdown export is a point-in-time snapshot, not a second authority. [Wiki guide](docs/knowledge-wiki.md) · [Ingestion](docs/ingestion.md).

<a id="python-api"></a>
## Python API

<!-- verify:sdk -->
```python
import os
from pathlib import Path
from chat_distiller import KnowledgeStore, MemoryStore, serialize_packet

vault = Path(os.environ["DEMO_DIR"]) / "vault"
memory = MemoryStore(vault)
wiki = KnowledgeStore(vault)

hits = memory.search("database")
page = wiki.get("database")
packet = wiki.recover("database", max_bytes=8192)
wire = serialize_packet(packet)
assert len(wire.encode("utf-8")) == packet["used_bytes"] <= 8192
print(packet["status"], len(packet["knowledge"]), packet["requires_review"])
```

`MemoryStore` is read-only. `KnowledgeStore.compile(..., apply=True)` publishes explicitly. Neither calls a model.

</details>

<a id="evidence"></a>
## Evidence you can replay

**CompileBench:** four topics, twelve curated atomic cards, zero model calls. Engineering checks only, not semantic accuracy or real-user task success.

| Check | Observed |
| --- | ---: |
| Invalid proposals blocked without creating compiled state | 16 / 16 |
| Complete UTF-8 packet budget checks | 16 / 16 |
| Stale pages served with the freshness gate disabled | 4 / 4 |
| Stale pages served with the freshness gate enabled | 0 / 4 |
| Updated topics retaining identity and the old revision | 4 / 4 |

An incorrect synthesis with a real quote can still pass structural checks. Source references do not prove entailment. [Results and limits](benchmarks/wiki/results.md).

<details>
<summary>Original retrieval benchmark, including the trade-off</summary>

40 synthetic sessions, 40 handwritten cards, 24 queries. Retrieval only, no independent holdout and no final Agent answer evaluation.

| Method | Recall@1 | Recall@5 | MRR@5 | stale-hit@5 |
| --- | ---: | ---: | ---: | ---: |
| Raw transcript lexical | 0.4167 | 0.9583 | 0.6528 | 0.5417 |
| Structured memory | 0.5417 | **1.0000** | 0.7604 | 0.5000 |
| Structured + status-aware | **0.7083** | 0.9167 | **0.7931** | 0.0000 |

Status-aware ranking improves Recall@1 in this fixture but reduces Recall@5 from 1.0000 to 0.9167 and can suppress disputed cards. Zero stale hits comes from filtering declared expired records, not detecting outdated truth. [Per-case results and intent slices](benchmarks/benchmark-results.md).

</details>

```bash
python -m unittest discover -s tests -v
python tools/build_brand_assets.py --check
python tools/verify_docs.py
```

<a id="limits"></a>
## Boundaries, not hidden promises

This is a local memory/knowledge component exposed as a Skill, not an autonomous Agent or truth detector. Retrieval is lexical, not embedding search. Host or human semantic review is still required. No built-in model service, MCP server, web UI, native Codex/Claude history parser or universal compaction hook is claimed. Hook templates are reminders only. The Wiki layer follows the LLM Wiki maintenance pattern; it is not a fork or bundled third-party Wiki. [Architecture](docs/architecture.md) · [Design and attribution](docs/wiki-design.md).

Memory text is untrusted data. Corruption must not be bypassed, private transcripts must not be committed, and a failed post-replacement write may already have published state. The old multi-file renderer is not a cross-layer transaction. Brand migration handles instruction directories only, with scoped locks and retained backups; it does not establish real-host activation or improve Agent task quality by itself. [Migration and recovery](docs/brand-migration.md).

## Documentation and contribution

[Documentation](docs/README.md) · [Skill guide](docs/skill-first.md) · [Python API](docs/memory-engine.md) · [Changelog](CHANGELOG.md) · [Contributing](CONTRIBUTING.md)

Use synthetic fixtures in public issues. Keep private conversations and credentials out of commits.

## License

[MIT](LICENSE).
