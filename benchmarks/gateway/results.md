# Context Gateway 0.4 engineering experiment

Synthetic local Doubao Work fixture. No external model calls and no real user data.

| Check | Observed |
| --- | --- |
| commands_to_first_context | 3 |
| first_sync_changed_sessions | 2 |
| second_sync_changed_sessions | 0 |
| noop_sync_state_identical | true |
| source_cache_unchanged | true |
| context_used_bytes / context_budget_bytes | 1241 / 4096 |
| degraded_fallback_visible | true |
| stale_plan_rejected | true |
| stale_plan_created_memory | false |
| model_calls | 0 |

This verifies interaction-surface reduction, source read-only behavior, incremental idempotence,
byte-bounded raw context fallback, degraded extraction visibility, and stale-plan rejection.

It does **not** measure semantic distillation quality or downstream agent task success.
