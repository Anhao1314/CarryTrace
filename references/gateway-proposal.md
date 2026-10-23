# Gateway proposal contract v1

This protocol is for host Agents after `chat-distiller sync`. Ordinary users should not hand-author it.

```json
{
  "gateway_schema_version": 1,
  "plan_sha256": "<current sync-plan hash>",
  "covered_sessions": ["session-id"],
  "retire_memory_ids": [],
  "distill": {"conversations": []}
}
```

Rules:

- `plan_sha256` must match the current pending plan. A source rescan makes an older proposal stale.
- `covered_sessions` must be a non-empty subset of current pending sessions and each covered session must
  appear in `distill.conversations`.
- First publication may start from legacy/v1 distill content. Updates to an existing managed vault must start
  from the complete current v2 source and preserve its identity registry.
- A previously active identity can disappear only when its ID is explicitly listed in `retire_memory_ids`.
  Silent retirement is rejected.
- The Gateway allocates new identities through the existing registration path and dry-runs the existing renderer
  before publication.
- These checks validate snapshot binding and structural integrity. They do not prove Agent synthesis is correct.
