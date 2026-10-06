# Documentation map / 文档导航

Start with the [English overview](../README.md) or [中文首页](../README.zh-CN.md).
The overview explains the use case and provides a temporary-vault demo. Detailed
contracts live here and in `references/`, rather than being repeated on the homepage.

| I need to… / 我想… | Read / 阅读 |
| --- | --- |
| Connect Doubao Work and recover context | [Context Gateway](context-gateway.md) · [Gateway proposal](../references/gateway-proposal.md) |\n| Try the low-level engine without touching real memory | [Quick start](../README.md#quick-start) / [快速体验](../README.zh-CN.md#quick-start) |
| Import conversations or upgrade existing data | [Ingestion and migration](ingestion.md) |
| Integrate a Python agent or understand packet limits | [Memory Engine API](memory-engine.md) |
| Understand authority and trust boundaries | [Architecture](architecture.md) |
| Compile versioned topic pages and recover layered context | [Knowledge Wiki](knowledge-wiki.md) · [Proposal contract](../references/knowledge-schema.md) |
| Understand the research and controlled wiki experiments | [Design](wiki-design.md) · [Verification](wiki-verification.md) · [CompileBench](../benchmarks/wiki/results.md) |
| Inspect test evidence and reproduce results | [Verification ledger](verification.md) |
| Inspect every benchmark case, including failures | [Benchmark report](../benchmarks/benchmark-results.md) |
| Instruct a host agent to perform semantic distillation | [Skill workflow](../SKILL.md) |
| Write valid cards and preserve stable identities | [Distillation schema](../references/distillation-schema.md) · [Identity and migration](../references/stable-memory.md) |
| Understand lexical ranking and T1/T2/T3 validation | [Retrieval](../references/retrieval.md) · [Validation rules](../references/lint-rules.md) |
| Report a bug or propose a contribution | [Contributing](../CONTRIBUTING.md) · [Changelog](../CHANGELOG.md) |

## Scope of the documentation

English and Chinese READMEs share executable examples and the same measured demo.
Some detailed authoring references remain Chinese; the Python API contract is English.
Only implemented behavior belongs in quick-start examples. Planned work must be labelled
as planned, not presented as an available command.
