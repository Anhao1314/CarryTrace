# Task-handoff recovery status / 任务接续恢复实验

**Date:** 2026-10-08

**Frozen main baseline:** `b263167b4f269af7252824a1efbf94828b4c0515` (package 0.4.0).

## Why this experiment

Task continuation depends on telling apart: relevant retrieved history,
unverified recent-session orientation, no available evidence, and evidence
that exists but cannot fit the requested output budget.

## Protocol and non-negotiable controls

1. Add behavioral tests before changing production code.
2. Retain the red baseline CI run and unchanged historical results.
3. Change only Gateway relevance selection, fallback labeling and status mapping.
4. Replay all existing tests, existing synthetic benchmarks and wheel-installed checks.
5. Never change prior gold labels, thresholds or experimental artifacts to improve a result.

All four scenarios use temporary **synthetic Doubao-style sessions** and the
production `ContextGateway` implementation. No personal chat history or model API is involved.

| Scenario | Expected behavior | Frozen baseline observation |
| --- | --- | --- |
| Structured source with zero query matches and no raw sessions | `no_match` | `budget_exhausted` |
| One lexical match plus an unrelated session | Only relevant session, labeled `lexical_match` | Both sessions returned |
| Zero lexical matches, but sessions exist | Explicit, review-required `recent_fallback` | Returned recent session without basis label |
| Relevant source exceeds byte budget; unrelated source is smaller | `budget_exhausted`, no unrelated source | Unrelated source returned as `ready` |

## Reproducible baseline failure

- [Original green baseline](https://github.com/Anhao1314/chat-distiller/actions/runs/37420019756): 236 tests passed.
- Red-only test commit: `a8c1105874083a3f3df4da5ef20ef5954c06a98e`.
- [Baseline-red CI](https://github.com/Anhao1314/chat-distiller/actions/runs/37741992861):
  240 tests run, **3 failures and 1 error**, precisely the four new assertions.
- The baseline-red artifact is intentionally preserved, not rewritten.

## Candidate verification

To reproduce after applying the change:

```bash
python -m unittest discover -s tests -v
python benchmarks/evaluate.py
python benchmarks/wiki/evaluate.py --check
python benchmarks/gateway/evaluate.py
python tools/verify_docs.py
```

Compare the CI checks on the PR and on the final commit; keep existing benchmark
fixtures fixed. Candidate observations are recorded in GitHub Actions rather than
silently substituting a new expected benchmark.

## Claim boundary

The regression tests establish **result selection, status and byte-budget semantics**
on synthetic local sessions. They do not test an actual model resuming a user project,
measure long-horizon recall, evaluate semantic distillation quality or authorize
automatic memory publication. Real-data experiments require consent and private execution.
