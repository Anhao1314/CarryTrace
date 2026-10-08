# CarryTrace brand migration: verification record

Baseline commit: `ef8014d2c1cf69b0ab1e80a0f1019a17ca997d88`.
Baseline tree: `7df97488db2e1fcaef55c99681acb9be9fcfc476`.

## Local execution, 2026-10-08

A source archive was recovered from the baseline's GitHub Actions evidence artifact.
Its file tree matched the baseline tree exactly before edits. Linux / Python 3.13.5:

- The original suite passed **262/262** tests. An initial short process timeout was
  an incomplete run, not a failed assertion; the complete replay was retained separately.
- The candidate suite passed **289/289** tests, adding 24 migration/compatibility
  tests and three deterministic visual-asset checks. Existing tests were not removed.
- The installed wheel passed **18** new brand checks outside the source checkout:
  new/old CLI output equality, source/home immutability, two-host migration,
  exact retained backups, duplicate protection, idempotence and deterministic ZIP export.
- Existing installed checks passed: Memory 16, Wiki lifecycle 12, Gateway 9, Skill 25.
- Atomic and Wiki benchmarks were replayed twice with their prior results unchanged.
  Gateway still records the previously audited 1,241-to-892-byte delta, not a new metric gain.
- A local Chromium Markdown preview passed **27** checks across English/Chinese,
  light/dark, static/motion sources, disclosure panels and desktop layout. The
  decorative animation runs once and settles; the default image is static.

The final README was shortened after the complete suite; its 16 documentation
regressions were rerun. Remote CI must execute the complete final candidate.

## Negative paths retained

Tests inject second-host publication failure and confirm rollback of both selected
hosts. A separate test also fails restoration: original bytes remain in backup,
`rollback_required` is reported, and the operation lock is retained. User edits,
extra directories, symlinks and occupied destinations are rejected rather than deleted.

## Verification limits

Local preview images are **not live GitHub screenshots**. Direct browser navigation
was blocked; preview used in-memory HTML and repository SVGs, with external badges
replaced by text rather than fabricated results. Asset delivery through GitHub's
image proxy and a real host's Skill activation were not established here.

The connected local Runner reported `tunnel_client_not_seen`, so no user-device
installation, live Codex/Claude session, private-history access or Agent-task
quality measurement was performed. There is no v0.5 stable or PyPI release claim.

The migration lock coordinates this new installer. Stop host reloads and older
installer processes before migration; it is not a transaction across arbitrary
third-party writers. See [backup and recovery boundaries](brand-migration.md).

The PR and GitHub Actions for the final commit are authoritative for remote CI.
Historical benchmark files, examples and evidence artwork are not rebranded in place.
