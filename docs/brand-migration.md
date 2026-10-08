# CarryTrace migration / 续迹品牌迁移

**Baseline:** `ef8014d2c1cf69b0ab1e80a0f1019a17ca997d88`. This changes the public brand and optional Skill installation, not the memory authority or data format. No source chats, credentials, host configuration or private vault are part of the migration.

## Names that change; interfaces that remain

| Surface | Current name | Compatibility |
| --- | --- | --- |
| Product / repository | CarryTrace / `Anhao1314/CarryTrace` | Historical records keep their original names. |
| Preferred CLI | `carrytrace` | `chat-distiller` stays installed and usable. |
| New Skill identity and ZIP root | `carrytrace` | Legacy bundle/export remains `chat-distiller`. |
| Python distribution / import | `chat-distiller` / `chat_distiller` | Unchanged; do not install an unrelated PyPI name. |
| Runtime version | `0.4.0` | Brand pilot only; v0.5 stable release is not claimed. |
| Data home / environment | `~/.chat-distiller` / `CHAT_DISTILLER_HOME` | Unchanged; no new context store. |
| Memory and Wiki identities | Existing IDs, status and source hashes | No reinitialization, renumbering or rerender needed. |

## Existing installation: preview before moving anything

Update the **same** checkout and Python environment without discarding local changes. GitHub repository renaming does not rename a local checkout directory. Set its remote explicitly when needed:

```bash
git remote set-url origin https://github.com/Anhao1314/CarryTrace.git
python -m pip install .
carrytrace skill status --host both --scope user --json
carrytrace skill migrate --host both --scope user --json
```

`migrate` without `--apply` is a read-only preview. Review the paths and pending operations. Stop active Agent sessions before explicitly applying the move:

```bash
carrytrace skill migrate --host both --scope user --apply --json
```

For project scope use `--scope project --project-dir /your/existing/project` instead. Only selected hosts and the selected scope are inspected. User-level and project-level installs in other scopes are **not** automatically discovered or deleted. Check those separately before reloading the host to avoid duplicate activation across scopes.

The migration verifies the old managed manifest and all instruction bytes, refuses user edits, extra files/directories, symbolic links and duplicate names, and moves the old directory outside Skill discovery **before** publishing the new Skill. The old CLI's installer refuses to recreate its alias when a `carrytrace/` directory exists in that same host/scope. Normal old CLI reads and Python imports remain available.

## Backups, failures and manual recovery

Backups and an operation receipt are retained at:

```text
<user-home-or-project>/.carrytrace-skill-backups/<operation-id>/
    receipt.json
    codex/previous/        # Original Skill bytes, when present
    claude/previous/
```

This directory is outside `.agents/skills` and `.claude/skills`; it is not a second active Skill. Receipts contain source/destination paths, before-state hashes and the phase. Keep them private if your local paths are sensitive.

Cooperative operations use `<root>/.carrytrace-skill-lock`. Detected concurrent changes block publication. An ordinary publication error attempts to roll back all selected hosts. If restoration itself fails, backups remain and the lock is retained; the command returns `rollback_required` with the receipt path. **Do not delete the lock, retry installation or remove a backup just to make the error disappear.**

For manual recovery, first stop all installers/host reloads, inspect the receipt and compare the backup files against its recorded snapshot. Back up any current target. Restore the original `previous/` directory only when its original path is free, and never overwrite user edits. Remove a surviving cooperative lock only after both host directories and the receipt are reconciled. A hard process kill may leave a prepared transaction requiring this inspection. This is not a filesystem-wide transaction or protection against malicious concurrent filesystem changes.

The installer does not include an automatic uninstall or a blind rollback command. Retained originals are the recovery source; memory/vault files are not involved.

## New users and ZIP consumers

With no old Skill in the selected scope:

```bash
carrytrace skill install --host codex --scope user
carrytrace skill export --out carrytrace-skill.zip
```

The new ZIP contains `carrytrace/SKILL.md` and two reference Markdown files only. The legacy command still exports its legacy ZIP for existing integrations. Neither archive embeds the Python runtime or grants cross-host data access. Import, trigger selection and real Agent task quality still require host-specific validation.

## Verification scope

Run all existing tests without replacing gold labels, then the new installation/migration cases. Build a wheel and run `tools/verify_brand.py` from an isolated installed environment; source-checkout imports are rejected. It checks both CLI outputs on the same synthetic context, two-host migration, exact retained backups, idempotence, duplicate protection and ZIP determinism. Unit fault injections cover publication failure and failed rollback.

Frozen `benchmarks/`, `examples/`, evidence SVGs and historical verification documents must remain byte-identical. Test counts belong to the actual CI run, not a new quality claim. No true Codex/Claude Skill activation or private-device installation is established by these tests.
