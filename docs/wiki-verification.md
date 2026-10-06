# Knowledge Wiki 0.3.0: verification ledger

Baseline: `6fa679dbe94d13570f64714086c973043e98e8ab`. Research and implementation date: 2026-10-06.
All local runs below used an isolated Linux / Python 3.13.5 environment and disposable synthetic data.
The GitHub PR and Actions runs provide independent execution receipts for the final committed tree.

## Executed checks

| Check | Local observation |
| --- | --- |
| Pre-upgrade main | 147 tests passed |
| Candidate suite | 215 tests passed; original 147 retained, 63 knowledge tests and 5 CompileBench regressions added |
| Existing installed-wheel checks | 16 checks; use the recorded smoke output / CI to inspect the run |
| New installed knowledge demo | 16 real CLI commands, 12 assertions passed |
| README examples | Both language versions execute the same CLI and SDK snippets, now including wiki preparation/compilation/recovery/export |
| Frozen retrieval benchmark | Output JSON and Markdown unchanged |
| CompileBench | Two repeat runs match the committed per-case report |
| Failure injection | File sync, replacement, post-replacement directory sync, post-publication lock cleanup, and process exit before/after replacement |
| Cooperative concurrency | Two processes with proposals targeting one wiki revision cannot both overwrite it |

The post-replacement failures deliberately do **not** claim rollback. They produce an uncertain-commit error while the new revision can already be visible. A terminated process can leave a lock; the code never automatically steals it.

## Controlled compiler experiment

See [results.md](../benchmarks/wiki/results.md) and [results.json](../benchmarks/wiki/results.json).
Four topics use twelve curated atomic cards. Each topic has an old decision, a current decision and a dispute.
The experiment compiles a page, repeats the input, changes current memory, attempts stale consumption, refreshes the page,
and inspects the prior revision. It also attempts invalid proposals and different byte budgets.

Observed: 16/16 invalid proposals rejected without creating compiled state; 16/16 complete UTF-8 budget checks passed.
With the old page and query fixed, a static consumer without freshness enforcement would serve the stale page in 4/4 cases;
the production freshness gate serves it in 0/4. The refreshed identity is preserved in all four cases and the old revision remains inspectable.
This ablation is not another product's implementation and is not evidence of general model superiority.

## Negative result retained

A false synthesis can cite an existing literal quote and still pass the structural validator. The unit test deliberately
supplies an unsupported assertion about a database on Mars. It passes only as review-required synthesis; no semantic
verification is claimed. This is a boundary of the implemented validator, not a solved hallucination problem.

Conservative invalidation marks all compiled pages stale after any atomic-source change, including unrelated additions.
This sacrifices availability to avoid claiming that dependency-only checks find newly introduced contradictions.
The project does not measure how much this policy improves real agent outcomes.

## Reproduce

Run from a source checkout with the installed CLI environment activated:

```bash
python -m unittest discover -s tests -v
python benchmarks/evaluate.py --out /tmp/chat-distiller-legacy-benchmark
python benchmarks/wiki/evaluate.py --check
python tools/verify_docs.py
DEMO_PARENT="$(mktemp -d)"
python tools/wiki_demo.py --out "$DEMO_PARENT/run"
```

For installed-wheel verification, build and install the wheel into a separate virtual environment, change to a directory
outside the checkout, then run `tools/verify_install.py` and `tools/verify_wiki.py` by their absolute paths using that
environment's Python. Both tools reject a source-checkout import. CI executes this procedure on Python 3.9 and 3.12.
CI also archives raw demo receipts, exported Wiki snapshots, per-case benchmark results and the exact checked-out source.

No external LLM calls were made. The authored synthesis fixture demonstrates the host proposal interface, not an automated
model study. No real user data, native host compaction, browser UI, hardware power loss, macOS or Windows execution is claimed.
