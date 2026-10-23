# Data safety: locking, backups, redaction and deletion

The claim store is one local JSONL file. That makes it inspectable, but it also
means every write is a read-modify-write of the whole file. This page describes
the guarantees around concurrent writers, snapshots, and removing content.

All commands are local and zero-dependency. They do not upload, encrypt or sync
anything.

The same operations are available in the demo UI: the **Safety** view lists
snapshots and the audit trail and can take a backup with one click, and every
claim card in **Ledger** carries **Redact** / **Delete** actions behind a
confirmation dialog. Read-only ledgers keep backup and audit readable and refuse
removals. To start a real ledger, run `claim init`; it creates the store, refuses
to touch one that already has data, and prints the exact commands for recording,
briefing and registering the store with your agent.

## One writer at a time

`ClaimStore.record`, `redact`, `delete` and `restore` take an exclusive writer
lock before reading. The lock is:

- an in-process re-entrant lock for threads in one server, plus
- an OS advisory byte lock for separate processes: `flock` on POSIX and
  `msvcrt.locking` on Windows.

The lock file is `<store>.lock` (for example `claims.jsonl.lock`). The file is
left in place; only the byte range is locked. The operating system releases the
lock when the process exits, so a crash does not leave a stale lock that needs
manual deletion.

If the lock cannot be acquired within the timeout (default 10 seconds), the
operation fails with `ClaimStoreBusy` / `BUSY` instead of overwriting another
writer. The Python constructor accepts `ClaimStore(path, lock_timeout=...)`.
The demo maps the failure to HTTP `423`.

The lock is advisory and local-filesystem based. Do not put the store on a
network filesystem whose locking semantics are not reliable across hosts.

## Backups

```bash
claim backup --store /path/to/claims.jsonl
claim backup --store /path/to/claims.jsonl --out /secure/backups
```

The default destination is `<store directory>/backups/`. Each backup consists
of:

```text
claims-20261023T171500123456Z.jsonl
claims-20261023T171500123456Z.manifest.json
```

The JSONL is a canonical, validated snapshot. The manifest records:

- `kind: claim-ledger-backup`
- `claims` and `redacted` counts
- `bytes` and `file_sha256` of the snapshot
- `store_sha256`, the canonical store digest
- `created_at`

The snapshot is written atomically with an fsync, and the manifest is verified
before any restore. Backups are **plaintext**; protect the backup directory with
the same care as the store. `claim redact` and `claim delete` create a
pre-change backup by default. Use `--no-backup` only when the user wants true
erasure rather than recoverability.

`claim backups` lists snapshots with their manifest facts, newest first.
Retention is explicit, never automatic: pass `--keep N` to `claim backup` to
prune older snapshots after a successful write (the fresh one is never removed).
A backup contains whatever the store contained at that moment, including content
that was later redacted.

## Restore

```bash
claim restore --from /secure/backups/claims-20261023T171500123456Z.jsonl \
  --store /path/to/claims.jsonl --yes
```

`restore` verifies the manifest and both digests, validates every row and the
supersession graph, then replaces the store atomically. A non-empty destination
requires `--yes`; before replacing it, the current store is backed up again.
The restore appends an audit entry. Restoring a snapshot taken before a
redaction or deletion reintroduces that content, so treat old backups as a
separate privacy boundary.

A raw JSONL file without a manifest is rejected unless
`--allow-unverified` is passed. Prefer `claim backup` over copying the JSONL by
hand.

## Redaction

```bash
claim redact clm_... --store /path/to/claims.jsonl --yes
claim redact clm_... --store /path/to/claims.jsonl --cascade --yes
```

Redaction replaces the content of the claim in place:

- `text` becomes `[redacted]`
- `tags` becomes empty
- `topic` becomes `redacted`
- `source`, `quote` and `session_hint` become `null`
- `redacted_at` records when it happened

The claim id, timestamps, status and `superseded_by` pointer remain. That keeps
the supersession graph valid while removing content. Redacted rows are excluded
from `claims`, `brief`, `search`, conflict detection and RAG evidence resolution
by default. `claim claims --include-redacted` exposes the content-free
tombstones for audit.

`--cascade` redacts the entire supersession chain joined to the claim. Use it
when an old and a new claim both contain the sensitive material.

Redaction does **not** rewrite derived artifacts. Rebuild or purge any evidence
index that contains the original passage:

```bash
claim index status --evidence /path/to/evidence.jsonl --store /path/to/claims.jsonl
claim index build --source /path/to/evidence.jsonl --out /path/to/new-index.jsonl \
  --store /path/to/claims.jsonl
```

## Deletion

```bash
claim delete clm_... --store /path/to/claims.jsonl --yes
claim delete clm_... --store /path/to/claims.jsonl --cascade --yes
```

Deletion removes rows from the store rather than leaving tombstones. A claim
referenced by another claim's `superseded_by` cannot be deleted alone; the
command fails and names the referrer. `--cascade` removes the entire
supersession chain, preserving graph integrity.

Deletion is permanent in the store. The default pre-deletion backup still
contains the removed content; use `--no-backup` when that copy must not exist.
Older backups and external evidence indexes are not modified.

## Audit log

`redact`, `delete` and `restore` append one line to
`<store stem>.audit.jsonl` (for example `claims.audit.jsonl`):

```json
{"action":"redact","actor":"local-operator","at":"2026-10-23T17:15:00Z",
 "backup_file":"claims-....jsonl","backup_file_sha256":"...",
 "claim_ids":["clm_..."],"store_sha256_before":"...","store_sha256_after":"...",
 "kind":"claim-ledger-audit","schema_version":1}
```

The audit log records identity, action, hashes and the backup filename. It does
not record claim text, quotes, sources or a free-form reason. Set
`CLAIM_LEDGER_ACTOR` to annotate the operator or host; it is truncated to 80
characters.

If the audit entry cannot be written, the store is rolled back to its previous
state and the command fails. The pre-change backup is still available.

`claim audit` lists entries newest first; `--action redact|delete|restore`
filters, `--limit` bounds the output, and a corrupt audit line refuses service
instead of being skipped.

## Boundaries

- Backups are plaintext and local; this is not encryption or secure erase.
- Redaction removes authority-store content, not copies already exported to
  transcripts, logs, RAG indexes, shells or model providers.
- The lock is advisory; a process that ignores the lock file is not stopped.
- This is a single-file local store. Very large histories still incur a full
  read-modify-write per mutation.
- `delete --hard` is not provided: deletion is always a store rewrite with an
  audit record, not a secure erase of disk blocks.
