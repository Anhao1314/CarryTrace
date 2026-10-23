# Synthetic development benchmark results

synthetic development benchmark; retrieval only

Fixture SHA-256: `94aaade788c6ff76ffe19d8ade10b25473700fc680cc58e7fab7895a9d7d2579`

| Method | Recall@1 | Recall@3 | Recall@5 | MRR | stale-hit@1 | stale-hit@3 | stale-hit@5 | controversial-hit@1 | controversial-hit@3 | controversial-hit@5 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline | 0.4167 | 0.8750 | 0.9583 | 0.6528 | 0.3750 | 0.5000 | 0.5417 | 0.1250 | 0.2500 | 0.2917 |
| Structured Memory | 0.5417 | 0.9583 | 1.0000 | 0.7604 | 0.3333 | 0.5000 | 0.5000 | 0.1250 | 0.2917 | 0.2917 |
| Status-aware Memory | 0.7083 | 0.8750 | 0.9167 | 0.7931 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.1667 | 0.2500 |

Dataset: `{"sessions": 40, "cards": 40, "queries": 24, "raw_transcript_characters": 92780, "memory_index_characters": 35278}`

MRR is truncated at 5. Hit rates measure queries with any such result. Disputed exposure can be correct.

| Method | Mean retrieved characters | Reduction vs full raw corpus |
| --- | --- | --- |
| Baseline | 9378.5 | 89.8917% |
| Structured Memory | 1578.83 | 98.2983% |
| Status-aware Memory | 1345.0 | 98.5503% |

These character counts are not tokens. Whole-corpus reduction is not a fair advantage over an already retrieving baseline; compare retrieved sizes too.
See JSON for every case and scenario, including misses. No model answered questions; no production or real-user accuracy claim.

## Query intent split (additive; aggregate above is unchanged)

Intent annotations partition the same 24 queries; fixture text and expected IDs are unchanged.
Current-state: q05–08 and q23. Historical: q01–04, q21, q22, q24. Other groups retain their four cases.
The fixture scenario named superseded asks about the current state, not the old answer.

| Intent | N | Method | Recall@1 | Recall@3 | Recall@5 | MRR | stale-hit@1 | stale-hit@3 | stale-hit@5 | controversial-hit@1 | controversial-hit@3 | controversial-hit@5 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| current-state | 5 | Baseline | 0.2000 | 1.0000 | 1.0000 | 0.5667 | 0.8000 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 0.0000 |
| current-state | 5 | Structured Memory | 0.2000 | 1.0000 | 1.0000 | 0.6000 | 0.8000 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 0.0000 |
| current-state | 5 | Status-aware Memory | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.2000 | 0.2000 |
| historical/superseded | 7 | Baseline | 0.4286 | 0.7143 | 0.8571 | 0.6071 | 0.2857 | 0.2857 | 0.4286 | 0.0000 | 0.1429 | 0.1429 |
| historical/superseded | 7 | Structured Memory | 0.4286 | 0.8571 | 1.0000 | 0.6786 | 0.2857 | 0.2857 | 0.2857 | 0.0000 | 0.0000 | 0.0000 |
| historical/superseded | 7 | Status-aware Memory | 0.5714 | 1.0000 | 1.0000 | 0.7619 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| conflict/controversial | 4 | Baseline | 0.7500 | 0.7500 | 1.0000 | 0.8125 | 0.0000 | 0.2500 | 0.2500 | 0.7500 | 0.7500 | 1.0000 |
| conflict/controversial | 4 | Structured Memory | 0.7500 | 1.0000 | 1.0000 | 0.8750 | 0.0000 | 0.2500 | 0.2500 | 0.7500 | 1.0000 | 1.0000 |
| conflict/controversial | 4 | Status-aware Memory | 0.0000 | 0.2500 | 0.5000 | 0.1750 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.2500 | 0.5000 |
| cross-session | 4 | Baseline | 0.2500 | 1.0000 | 1.0000 | 0.6250 | 0.2500 | 0.2500 | 0.2500 | 0.0000 | 0.2500 | 0.2500 |
| cross-session | 4 | Structured Memory | 0.7500 | 1.0000 | 1.0000 | 0.8750 | 0.2500 | 0.2500 | 0.2500 | 0.0000 | 0.5000 | 0.5000 |
| cross-session | 4 | Status-aware Memory | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.2500 | 0.5000 |
| compaction-recovery | 4 | Baseline | 0.5000 | 1.0000 | 1.0000 | 0.7083 | 0.5000 | 0.7500 | 0.7500 | 0.0000 | 0.2500 | 0.2500 |
| compaction-recovery | 4 | Structured Memory | 0.7500 | 1.0000 | 1.0000 | 0.8750 | 0.2500 | 0.7500 | 0.7500 | 0.0000 | 0.2500 | 0.2500 |
| compaction-recovery | 4 | Status-aware Memory | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.2500 | 0.2500 |

### Interpret the slices

- Current-memory Recall@1/3/5 uses only the five current-state queries. Stale-hit is contamination here.
- Historical lookup with `--include-noncurrent`: Recall@1/3/5 = 0.4286 / 0.8571 / 1.0000.
- **Expired-target recall: not measured (0 expected-expired queries).** Historical queries still expect current decision records. Returning an old card is exposure, not automatically success or contamination.
- Conflict visibility must distinguish the relevant disputed target (Recall) from any disputed result (controversial-hit). Both are reported; default-policy misses remain visible.
- Cross-session and compaction-recovery are contextual intent groups, not claims of live Agent evaluation.
