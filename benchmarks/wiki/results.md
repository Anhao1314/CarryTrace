# CompileBench: executed engineering evidence

curated synthetic atomic cards; extractive proposals; no model calls

lifecycle and structural safety, not entailment or agent task success

Fixture SHA-256: `6c4f7f4b96c80ed189af012ec341f3bdd55b3b645aeedf71cf734edf4f954037`

| Check | Observed |
| --- | ---: |
| Invalid proposals blocked | 16/16 |
| Stale pages served, freshness gate disabled | 4/4 |
| Stale pages served, freshness gate enabled | 0/4 |
| Complete UTF-8 budget checks | 16/16 |

| Topic | Cards → pages | Revision after update | Identity preserved | Old revision retained |
| --- | --- | ---: | --- | --- |
| database | 3 → 1 | 2 | True | True |
| deployment | 3 → 1 | 2 | True | True |
| scheduler | 3 → 1 | 2 | True | True |
| retrieval | 3 → 1 | 2 | True | True |

The 3 → 1 grouping is a chosen topic organization, not a measured compression or quality improvement.
The ablation changes only freshness enforcement. It is not a leaderboard result.

## Limitations

- Not an independent holdout or automatic LLM synthesis evaluation.
- Status and scope are explicit; unknown semantic contradictions can be missed.
- A false synthesis with a real quote can pass structurally and remains review-required.
- Ablation is a controlled static-page consumer, not a comparison to other wiki products.
- Conservative whole-source invalidation also stales pages after unrelated changes.

Failures: []
