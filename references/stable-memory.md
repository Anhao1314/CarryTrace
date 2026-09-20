# Stable memory v2 contract

`memory_id: mem_<32 lowercase UUID4 hex digits>` is allocated **once**, by
`migrate_memory.py`, never by the renderer and never derived from content/order.
Conversation notes and cards both have identities. Threads are sections, not
independently addressable memories. Preserve IDs when editing existing objects.

## Canonical identity authority

There is **one logical authority: the complete v2 source document**. Its embedded
`identity_registry` owns ID allocation/reservation and immutable bindings
(`type`, `session_id`, `display_id`, `note_name`). Source objects reference that
registry; their repeated identity fields are checked assertions, not a second ledger.
`source_memory_id` and internal relations live in source objects and are validated
against the source's registry and conversation membership.

Before the first render, the initialized source is the sole source version. Once
published, `<vault>/<subdir>/.chat-distiller/distill.json` is the authoritative
**published version** for that vault. An external file passed via `--distill` is a
candidate next source version, not a competing authority for what is currently
published. Edit a working copy; do not independently edit the published projections.

| Location | Role / trust rule |
| --- | --- |
| Candidate `--distill` document | Proposed next version; validate object/registry agreement and immutable history against the published source before accepting it |
| Published `.chat-distiller/distill.json` | Last accepted complete source version; canonical for current vault reads |
| Published `identity-registry.json` | Derived mirror; must equal the published source registry exactly, including inactive entries |
| Note identity frontmatter | Derived projection; must match the corresponding published source version |
| JSONL index | Derived retrieval view; must equal the index rebuilt from the published source |

**No conflict resolution by preference or overwrite.** Renderer first validates the
published source, exact mirror equality and existing note identity projections. It
then validates the candidate and checks that existing identity bindings/history are
preserved. Only a consistent candidate may be rendered. New registrations and
explicit retirements are source-version transitions, not repairs to drifting copies.
Title/body/status/related edits in a valid candidate are ordinary content changes;
identity edits are not. A missing identity field on an existing object fails rather
than being filled or reallocated.

Query trusts only the internally valid published source, then verifies its mirror,
note identities and derived index. It does not open a path to an external authoring
file and does not see unpublished edits. Lint uses the same published authority,
reports projection/relationship drift as T1, and exits nonzero for identity or
external-link integrity problems. Renderer/query also exit nonzero on identity
inconsistency; none chooses a surviving copy and silently rewrites another.

If copies disagree or one is missing, stop and restore a **known consistent version**
from backup after review. Rerender is not an identity-conflict repair command. Keep
source and projections together when moving the vault. There is no external
cryptographic authority: coordinated manual rewriting of every copy cannot be
identified as tampering by consistency checks alone.

Every conversation/card has `memory_id`, `display_id` and `note_name`. Every card
has `source_memory_id` pointing to its parent conversation. A registry entry contains
`type`, `session_id`, `display_id`, `note_name`, `active`.

S/C numbers are assigned monotonically and retained, including after removal.
`note_name` pins the initial filename; title edits change the heading/index title,
not the filename. Reordered conversations/cards are rendered in display order.
Editing body, tags, categories, title or status preserves identity. Adding a card
without identity requires running the explicit registration command again.
The renderer rejects missing identities rather than guessing a correspondence.

## Internal memory relations vs external documents

| Field in v2 source | Target | Machine identity |
| --- | --- | --- |
| `related` | Other registered chat-distiller memories | Stable memory IDs only |
| `source_memory_id` | Registered source conversation | Stable memory ID |
| `superseded_by` | Registered successor card | Stable memory ID |
| `external_related` | Unmanaged Markdown document in the vault, or derived MOC | Note name or vault-relative path; no fabricated ID |

Example (IDs abbreviated here only):

```json
{"related": ["mem_<existing-id>"], "external_related": ["Research/C99 - Design rationale.md"]}
```

External paths may include or omit `.md`; Markdown links omit the suffix. An
unqualified name must resolve uniquely; use a vault-relative path for duplicate
basenames. A real external document named `C99 - ...` is allowed: the prefix does
not make it a managed memory. External fields pointing into managed memory are
rejected; use that memory's stable ID instead. External notes are never assigned
identities or rewritten. Links may break when users rename external files; no
external identity stability is claimed. Remote URLs and heading/block anchors are
outside this Markdown-note contract.

Migration maps exact internal names/display IDs/qualified managed paths to IDs.
With `--vault`, it checks real external targets and preserves them in
`external_related`; ambiguous targets fail. Without a vault it cannot disambiguate
S/C-looking legacy links, so those must be explicitly classified or checked through
upgrade mode. Migration reports external targets separately. Render validates their
existence/uniqueness before writes; lint reports missing/ambiguous/external-to-managed
links. The generated MOC is allowed as a planned target before its first render.

Machine index and frontmatter keep internal and external relations separate.
Markdown resolves internal IDs to familiar wikilinks. Frontmatter includes
`source_memory_id`, `related_memory_ids`, `superseded_by_memory_id`, and, when present,
`external_related`, alongside legacy human-readable `source`/`superseded_by` fields.

Expired cards remain stored and are excluded from default lookup. Disputed cards
need not have a successor: unresolved disagreement is not supersession. Supersession
requires an expired source and a card target; dangling references, self-relations
and cycles are rejected. The successor can itself be superseded: historical chains
are retained. Whether the new claim actually refutes the old claim remains T3.

## Initialize identity vs upgrade legacy memory

The existing script name is retained for CLI compatibility; `--mode` makes the
operation explicit. These are not three new pipelines:

- `--mode init`: first identity allocation for a new source; no existing vault is
  required. Does not accept `--vault`. Example:
  `python3 scripts/migrate_memory.py --mode init --distill distill.json --out memory-v2.json`.
- `--mode upgrade`: legacy v1 source already rendered in a vault; `--vault` is
  required to verify its files before upgrading.
- `--mode register`: existing v2 source with new objects or retirements; optional
  `--vault` verifies the current published source before registration.

Mode omission retains the previous behavior: v2 → register; v1 + vault → upgrade;
v1 without vault → init. JSON reports `operation`. Dry-run works in all three modes.

## Explicit migration of an existing vault

1. Back up the vault and the actual source used for its last render. v1 did **not**
   automatically save a source snapshot despite older README claims.
2. Do not reorder/edit the legacy source before migration. Preview:

   ```bash
   python3 scripts/migrate_memory.py --mode upgrade --distill old.json --vault /path/to/vault --dry-run
   ```

3. Persist a separate upgraded source and mapping report:

   ```bash
   python3 scripts/migrate_memory.py --mode upgrade --distill old.json --vault /path/to/vault \
     --out memory-v2.json --report migration-report.json
   python3 scripts/render_notes.py --distill memory-v2.json --vault /path/to/vault --dry-run
   python3 scripts/render_notes.py --distill memory-v2.json --vault /path/to/vault
   ```

The migration command does not render. Its vault check compares a legacy preview
against real files; drift, orphan files and unresolved links stop migration. The
upgraded source records file hashes, checked again on first v2 render. If you cannot
recover the exact source, reconcile explicitly in a separate copy; there is no
heuristic title/body matching or automatic recovery from Markdown.

Exact legacy S/C names and display IDs resolve through a unique mapping. Title-only
ambiguous relationships fail. External note names remain external, listed in the
output source. Dry-run writes nothing, including no report file: stdout is its report.
UUIDs printed in dry-run are provisional and will differ on a later allocation.

After migration use the upgraded source as the next input. Re-running migration on
that source is idempotent. Re-running the **old** source is a new migration and cannot
overwrite an already migrated vault. Existing destination files with different
content are rejected unless `--out` explicitly equals the input path.

First v2 render adds identity metadata to notes and records one `identity-migration`
log entry. It preserves filenames, taxonomy, status and the previous log; no full
renumbering. Subsequent unchanged renders append nothing. Source snapshot/registry
writes are reported separately in `state_changed`. Legacy render still works on
legacy vaults and is explicitly reported as legacy mode; it has no identity guarantee.

## Incremental ingestion and retirement

Edit the latest v2 source. Preserve all existing identities. Add new conversations
or cards without identity fields, then register them explicitly:

```bash
python3 scripts/migrate_memory.py --mode register --distill updated.json --vault /path/to/vault --dry-run
python3 scripts/migrate_memory.py --mode register --distill updated.json --vault /path/to/vault --out registered.json
python3 scripts/render_notes.py --distill registered.json --vault /path/to/vault
```

Normal lifecycle changes use `status`, retaining the old object. If an object is
removed from source, registration marks its identity inactive and reserves its ID,
display number and path permanently. References to that object must first be resolved
explicitly. Markdown is not deleted: it is an orphan, not a current lookup candidate.
Lint reports retained orphan files for review. Reactivating retired IDs is rejected;
there is no restore command in v2. Never strip registry history or copy an existing
ID onto a new fact. Identity cannot establish semantic sameness or prevent dishonest
manual replacement of content; the agent owns that judgment.

## Integrity and limitations

T1 checks unique identities/display numbers, registry/source consistency, stable
sources/relations and derived index equality. T2 literal absence still means suspect,
not false. T3 judges truth, supersession, duplication, importance and expiry.

Lookup requires a valid source snapshot, registry and index. Missing/corrupt/stale
state returns JSON with `ok: false`, not guessed results. Note identities are checked,
but Markdown bodies are not semantically compared; direct Markdown edits are not
ingested. Restore a consistent published identity version before accepting new edits.

Only one writer per vault is supported. Individual state writes are atomic, but a
whole render is not a filesystem transaction and there is no lock/daemon. An
interrupted update can leave inconsistent projections; restore a consistent backup
before retrying rather than asking the renderer to choose an authority. If the first
v1-to-v2 migration is interrupted before its registry is saved, restore the backed-up
legacy vault before retrying (its verified file hashes have changed). Keep
backups; do not merge independently migrated copies by matching titles.
