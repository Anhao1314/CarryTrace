# Memory Engine 0.2.0

This release packages the existing deterministic implementation, adds a read-only integration API and a bounded recovery packet, and closes two note-projection validation gaps. It does not change the v2 memory schema or the lexical ranking algorithm.

## Install from a checkout

```bash
python3 -m pip install .
chat-distiller --version
chat-distiller --help
```

The distribution has no third-party runtime dependencies. Building a wheel requires setuptools and wheel. This repository release is not a claim of publication on PyPI.

Existing `python3 scripts/*.py` commands remain available from a source checkout, including invocation from another working directory. The standalone compaction hook remains unchanged. The implementation is now under `chat_distiller/_internal`; legacy wrappers do not maintain a second implementation.

## Public Python API

```python
from chat_distiller import MemoryStore, serialize_packet

memory = MemoryStore("/absolute/path/to/vault")
results = memory.search("之前为什么放弃云端方案？", top_k=5)
if results:
    card = memory.get(results[0]["memory_id"])
health = memory.inspect()
packet = memory.recover("当前部署方案与限制", max_bytes=4096, top_k=5)
wire = serialize_packet(packet)
assert len(wire.encode("utf-8")) <= 4096
```

The vault must already exist and contain published v2 memory. Construction never creates a vault; read operations never migrate, rewrite, repair, or cache authoritative state. Each operation revalidates the source, registry, note projections, and regenerated index. `get` is explicit inspection and can return an expired card or a conversation; search/recovery return cards only. Explicit inspection does not change a memory's status.

`MemoryIntegrityError` means a read failed consistency checks; stop and repair from a consistent source/backup. `MemoryNotFoundError` means a stable ID is not in the active index. Invalid arguments raise `ValueError`. A search with no lexical matches returns an empty list, not an invented answer.

## Unified commands

| Command | Function |
| --- | --- |
| `extract` | Existing Doubao Work / generic JSONL extraction |
| `migrate` | Existing explicit init / upgrade / register modes |
| `render` | Existing deterministic rendering and migration safeguards |
| `lint` | Existing T1/T2 diagnostics |
| `search` | Validated lexical search |
| `get` | Inspect an explicit stable memory ID |
| `inspect` | Consistency-validated counts, statuses, and source hash |
| `recover` | Serialize a size-bounded packet of relevant memory records |

```bash
chat-distiller search --vault /path/to/vault --query '当前部署方案'
chat-distiller search --vault /path/to/vault --query '过去的部署方案' --intent historical
chat-distiller get --vault /path/to/vault --id mem_0123456789abcdef0123456789abcdef
chat-distiller inspect --vault /path/to/vault
chat-distiller recover --vault /path/to/vault --query '当前部署限制' --max-bytes 4096
```

The sample ID above is illustrative, not a real memory. Use an ID returned by search.

Current intent uses the existing policy: expired cards are excluded, current cards rank ahead of disputed cards, and disputed results remain labelled. Historical intent allows all states and preserves `superseded_by`. Intent is supplied explicitly by the caller, not guessed from wording. This release does not discover conflicts automatically or implement event-time temporal reasoning.

## Recovery packet contract

`schema_version=1` identifies the packet format; memory source schema remains 2. The packet includes query, explicit intent, source SHA-256, complete selected card bodies, stable IDs, source session and source memory IDs, relative note paths, statuses, supersession links, and lexical scores. Scores are not confidence or factuality probabilities. The hash identifies the published source bytes, not an authenticity signature.

`serialize_packet` produces canonical compact UTF-8 JSON with a final newline. `used_bytes` counts the complete serialized packet, including metadata, escaping, Unicode, and the newline. The byte budget is not a token budget and does not predict a model's tokenizer. The CLI emits this exact representation; pretty-printing or embedding the packet in another envelope changes its size.

Recovery examines at most the top 100 matching candidates. It selects at most `top_k` complete records within the budget, skipping oversized records rather than cutting a claim or its source identifiers. `omitted_count` is relative to that candidate window, not all possible matches in the vault. Skipping an oversized high-ranked record may include a lower-ranked disputed record; all states stay visible and `requires_review` is then true.

| Status | Meaning |
| --- | --- |
| `ready` | At least one full record fits; not a guarantee the agent can complete its task |
| `no_match` | No lexical candidates in this query |
| `budget_exhausted` | Candidates exist but none fit with complete metadata |

A budget too small for metadata and query is rejected. Historical/disputed records set `requires_review`. A structural error produces a nonzero CLI exit and an error object with no results, not a recovery packet.

## Integrity fixes

The frozen baseline could return a query result after only the corresponding rendered note's `status` or `kind` was edited. The source and index still agreed, but the note projection contradicted them. The shared identity-projection checker now verifies both fields against the published source; old query commands and the new API reject these mismatches. The intended repair remains editing the authoritative source and rendering, not editing generated Markdown in place.

## Boundaries

This is a local single-writer implementation. Source-before/source-after checks can detect an observed source change during a read; they are not a multi-file transaction, concurrency lock, or protection against a hostile filesystem. Managed paths resolving outside the vault are rejected by the new API, but there is no OS sandbox or adversarial race protection.

Integrity checks validate structure and identity/status/type projections, not every Markdown body byte or the truth of a claim. Returned bodies come from the validated source-derived index. The packet marks memory as untrusted data, not instructions; this label alone is not a prompt-injection defense. No content is executed, sent over the network, or automatically injected into a model by the API.

The semantic distillation step still belongs to the host agent or a human. No automatic knowledge writing, proposal transactions, vector retrieval, MCP server, web inspector, LongMemEval result, LLM answer evaluation, or real host-compaction integration is claimed in this release.
