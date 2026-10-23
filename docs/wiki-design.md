# Knowledge Compiler design and research

Research date: 2026-10-06. Implementation baseline: `6fa679dbe94d13570f64714086c973043e98e8ab` (147 tests replayed in a clean Python 3.13.5 environment).

## Sources and interpretation

- [Karpathy's original LLM Wiki idea](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f): a pattern, not a package. Immutable inputs, maintained knowledge pages, operating rules, ingest/query/lint workflows, an index and a chronological log. We adopt these ideas, not third-party implementation code. Claims made in the gist's comment thread are not attributed to its author.
- [Python file operations](https://docs.python.org/3/library/os.html#os.replace): same-filesystem replacement is the publication primitive. Flush the candidate file before replacement. This does not make the existing multi-file memory renderer transactional.
- [SQLite atomic commit](https://www.sqlite.org/atomiccommit.html): considered for page/log transactions, but not selected for this small local-first release. One authoritative JSON snapshot keeps the existing inspectable-file workflow; it includes all page revisions and the compilation log in a single replacement.

## Decisions made before implementation

1. Do not move existing notes, change memory schema 2, or replace the stable memory registry. Add a derived knowledge layer only.
2. A host agent supplies semantic synthesis as a proposal. Deterministic preparation offers an extractive draft so the complete workflow also runs offline. No hidden model service, key, or automatic-LLM-quality claim.
3. Every claim cites a memory ID and a literal excerpt from that memory's body. These checks establish referential integrity, not entailment, completeness of raw evidence, or real-world truth. A fluent false paraphrase can still pass; semantic review is mandatory for synthesis/inference.
4. Preparation deterministically selects a declared lexical scope, including old topic dependencies and supersession successors. Compilation requires every selected card to remain represented, with conservative current/historical/disputed labels. This protects known scoped disputes, not conflicts the query never found.
5. All changes to the published memory snapshot mark old knowledge stale, including additions not in an old dependency list. This is deliberately conservative; dependency-only invalidation can miss newly added contradictions. Unrelated edits also require refresh.
6. A stable topic key owns one `kn_` identity and an append-only revision history. Optimistic source/wiki revisions plus an exclusive local writer lock prevent cooperative stale writers. Identical replay is a no-op. Markdown is an explicit snapshot export, never a second authority.
7. Layered recovery returns complete topic units with their cited memory records, subject to the entire UTF-8 JSON budget. It can fall back to atomic memory when no fresh page fits. Such fallback does not promise topic-level conflict coverage. Existing `MemoryStore.recover` remains unchanged.
8. The first release is text-only, local, and single-writer relative to the old memory renderer. No distributed transaction, hostile-filesystem protection, cloud service, MCP, automatic expiry inference, or broad RAG superiority claim.

## Experiment protocol

Preserve the frozen retrieval benchmark byte-for-byte. Add an independently named synthetic *engineering* suite that executes the production compiler, local store, export and layered retrieval. Replay a fixed multi-topic lifecycle: compile, repeat, modify evidence, verify staleness, recompile with stable identity, inspect history, recover. Compare stale serving with and without the freshness gate while holding the page and query fixed. Exercise invalid IDs, invented quotations, omitted scoped disputes, status laundering, obsolete proposals, lock contention, corruption and injected publication failures. Measure exact budget compliance and report all outcomes.

The suite uses curated cards and extractive proposals; it cannot measure automatic summarization quality, independent holdout accuracy, user success, or real compaction recovery. An additional host-agent-authored synthesis example demonstrates the proposal interface, not an accuracy benchmark. Keep this distinction in documentation and reports.
