# Synthetic development benchmark v1

Hand-authored synthetic project decisions, not private or real-user conversations.
24 fixed queries, four per scenario. Each case has one expected stable memory ID.
Raw documents are session-sized chunks, each mapped to its distilled card by explicit
annotation; this optimistic provenance mapping helps the raw baseline rather than
penalizing it for a different output format. Distractor/expired documents remain in
all corpora. Noise consists of repeated commands, tool failures, greetings and paths.

Fixtures were authored before evaluating the first scores. Do not edit queries or
expected IDs in response to a score; future revisions require a new version and a
separate rationale. The evaluator contains no expected-answer-dependent ranking.
This is a development ablation of retrieval, not an assessment of agent answers,
automatic distillation quality, real compaction, or production accuracy.

The compaction cases supply only a query and external memory to the retriever.
They simulate an empty working context; they do not call or compact a live model.
