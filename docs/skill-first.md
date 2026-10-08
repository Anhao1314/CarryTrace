# CarryTrace Skill | 本地 Agent 上下文连续性

**Status:** instruction-only portable Skill over the existing package 0.4.0. This does not
imply that real host activation, compaction recovery or downstream Agent utility was measured.

**Upgrading from chat-distiller?** Follow the [preview-first brand migration](brand-migration.md). Python distribution/import and `~/.chat-distiller` remain unchanged; never create a second memory store.

## What it is

An [Agent Skills](https://agentskills.io/specification) directory at
[chat_distiller/skills/carrytrace/](../chat_distiller/skills/carrytrace/SKILL.md),
bundled in the installed Python wheel. Its frontmatter describes when to activate the
workflow. The host must have local shell access and the Python CLI installed.
Detailed flows and safety notes are loaded on demand from the Skill references.

## Install once; then request naturally

From an authorized checkout (Python 3.9+):

```bash
python -m pip install .
carrytrace skill install --host both --scope user
```

Locations for the personal scope:

| Host | Skill path |
| --- | --- |
| Local Codex | `~/.agents/skills/carrytrace/` |
| Local Claude Code | `~/.claude/skills/carrytrace/` |

Then ask a shell-capable host, for example:

- `Continue the last project and recover earlier constraints before editing.`
- `继续上次的项目，先找之前的关键决定和失败原因。`
- `What did we decide about PostgreSQL last week? Include superseded decisions.`
- `Build a bounded, source-linked handoff for the next Agent, but don't publish private data.`

First use still requires user-authorized connection to Doubao Work or an explicitly
provided existing vault. Installing a Skill does **not** scan every history source.
From the authorized host, a supported first-time flow is:

```bash
carrytrace connect doubao
carrytrace sync
carrytrace context "continue the previous project" --json
```

These are host-executed commands; the user can request them in natural language
after the Skill is available. Automatic Doubao cache discovery is conditional on
the supported local layout; other paths may need `--sessions-root` explicitly.

## Project scope, dry-run and updates

```bash
carrytrace skill install --host codex --scope project --project-dir . --dry-run --json
carrytrace skill install --host codex --scope project --project-dir .
carrytrace skill status --host codex --scope project --project-dir . --json
```

Project scope uses `.agents/skills` for Codex and `.claude/skills` for Claude Code.
Repeat installation is a no-op if the files are identical. A **managed** previous
version can be updated with explicit `--force`; unmanaged installations, symlinks
and user-modified files are never overwritten. The installer does not change
host settings, run background processes or touch personal conversation files.

## Export a portable Skill archive for other compatible hosts

```bash
carrytrace skill export --out ./carrytrace-skill.zip
```

The archive contains a single top-level `carrytrace/` directory and just three
Markdown instruction/reference files. It has deterministic contents and is safe from
silent overwrites. Some other Agent Skills-capable clients accept such archives,
but **host upload, activation and tool execution have not been validated here**.
Uploading a Skill does not upload your memory or grant the host access to a local CLI.

## What can actually work

| Use case | Supported path | Boundary |
| --- | --- | --- |
| Resume long Doubao Work sessions | `status`, `sync`, `context` | Only authorized local Doubao cache auto-discovery |
| Bring prior task evidence to Codex/Claude | Same CLI on destination host | Needs local access to user-authorized source or explicit packet |
| Check old / superseded decisions | `recover --intent historical` with user-provided vault | Expired evidence isn't current truth |
| Work with exported Generic JSONL | `extract --source generic_jsonl` | Review/register/render are still separate |
| Review stale Wiki pages | `wiki status` with existing vault | Structural freshness is not semantic correctness |

## Technical validation

CI must verify the installed wheel includes the bundle, both target scopes,
no-op repeat installs, dry-run behavior, rejection of foreign/edited skills and
byte-accurate content. The Skill has **no capability** to autonomously read
cloud ChatGPT/Codex/Claude history. Real-host Agent trigger/effectiveness needs
a separate opt-in end-to-end pilot; the repository tests do not imply it works.

## Trust

Source content is untrusted text. `ready` reports data, not truth; `no_match`
reports no candidate in the searched source; `recent_fallback` is not relevant
evidence. Agent interpretation and memory publication remain explicitly guarded.
Never upload private transcripts or commit them to the public repository.
