"""Opt-in CarryTrace Skill placement and reversible legacy migration.

Only instruction directories are touched. Context homes, memory identities and
host settings stay unchanged. Locks are cooperative, not hostile-filesystem isolation.
"""
import argparse
import contextlib
import hashlib
import io
from importlib import resources
import json
import os
from pathlib import Path
import uuid
import zipfile

from . import skill_installer as legacy

NAME = "carrytrace"
MARKER = ".carrytrace-managed.json"
OWNER = "carrytrace-skill-installer-v1"
FILES = legacy.BUNDLE
Error = legacy.SkillInstallError


def digest(data):
    return hashlib.sha256(data).hexdigest()


def bundle_files():
    root = resources.files("chat_distiller").joinpath("skills", NAME)
    data = {name: root.joinpath(*name.split("/")).read_bytes() for name in FILES}
    if not data["SKILL.md"].startswith(b"---\nname: carrytrace\n"):
        raise Error("invalid CarryTrace Skill frontmatter")
    return data


def manifest(data):
    return {"schema_version": 1, "managed_by": OWNER,
            "files": {name: digest(blob) for name, blob in sorted(data.items())}}


def inspect(path, wanted, old=False):
    """Inspect every managed file and directory; never follow nested symlinks."""
    marker = legacy.MARKER if old else MARKER
    owner = legacy.MANAGED_BY if old else OWNER
    if path.is_symlink():
        return {"state": "unsafe_symlink"}
    if not path.exists():
        return {"state": "missing"}
    if not path.is_dir():
        return {"state": "unmanaged"}
    actual, dirs = {}, set()
    for root, folders, files in os.walk(path, followlinks=False):
        for name in folders + files:
            p = Path(root) / name
            if p.is_symlink():
                return {"state": "unsafe_symlink"}
            rel = p.relative_to(path).as_posix()
            if p.is_dir():
                dirs.add(rel)
            elif p.is_file():
                actual[rel] = digest(p.read_bytes())
            else:
                return {"state": "unmanaged"}
    if set(actual) != set(FILES) | {marker} or dirs != {"references"}:
        return {"state": "modified"}
    try:
        record = json.loads((path / marker).read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {"state": "unmanaged"}
    if (not isinstance(record, dict) or record.get("schema_version") != 1
            or record.get("managed_by") != owner or not isinstance(record.get("files"), dict)
            or set(record["files"]) != set(FILES)):
        return {"state": "unmanaged"}
    if any(actual[name] != record["files"][name] for name in FILES):
        return {"state": "modified"}
    state = "current" if record["files"] == wanted["files"] else "update_available"
    return {"state": state, "snapshot": actual}


def targets(host, scope, project_dir):
    if host not in ("codex", "claude", "both") or scope not in ("user", "project"):
        raise Error("invalid host or scope")
    hosts = ("codex", "claude") if host == "both" else (host,)
    return [(h, legacy._target(h, scope, project_dir).with_name(NAME)) for h in hosts]


def plan(action, host, scope, project_dir, force):
    data = bundle_files()
    wanted = manifest(data)
    previous = legacy._manifest(legacy.bundle_files())
    items = []
    for h, dest in targets(host, scope, project_dir):
        old = dest.with_name(legacy.SKILL_NAME)
        now, before = inspect(dest, wanted), inspect(old, previous, old=True)
        operation = "none"
        if action != "status":
            if now["state"] not in ("missing", "current", "update_available"):
                raise Error("refusing to overwrite {}: {}".format(dest, now["state"]))
            if action == "install":
                if before["state"] != "missing":
                    raise Error("legacy Skill detected; preview `carrytrace skill migrate` first")
                if now["state"] == "update_available" and not force:
                    raise Error("managed update requires --force; edited files are never overwritten")
                operation = "install" if now["state"] == "missing" else "upgrade" if now["state"] == "update_available" else "none"
            elif action == "migrate":
                if before["state"] != "missing":
                    if before["state"] not in ("current", "update_available"):
                        raise Error("legacy Skill requires manual review: " + before["state"])
                    if now["state"] != "missing":
                        raise Error("both names exist; resolve duplicate installs explicitly")
                    operation = "migrate"
                elif now["state"] != "current":
                    raise Error("no intact legacy Skill to migrate; use install or review the existing target")
            else:
                raise Error("unknown operation")
        items.append({"host": h, "destination": str(dest), "legacy_path": str(old),
                      "current": now, "legacy": before, "operation": operation})
    return data, wanted, previous, items


def _safe_parent(dest):
    for p in (dest.parents[1], dest.parent):
        if p.is_symlink() or (p.exists() and not p.is_dir()):
            raise Error("unsafe skill parent: " + str(p))


def _write_record(path, value):
    # Atomic receipt update; retain prior phase if an update fails.
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def _stage(path, data, wanted):
    path.mkdir()
    for name, blob in data.items():
        dest = path / name
        dest.parent.mkdir(exist_ok=True)
        dest.write_bytes(blob)
    _write_record(path / MARKER, wanted)


def _apply(data, wanted, old_wanted, items):
    """All-host preflight, per-root lock, retained backups and exception rollback."""
    actionable = [i for i in items if i["operation"] != "none"]
    if not actionable:
        return None
    bases = {Path(i["destination"]).parents[2] for i in items}
    if len(bases) != 1:
        raise Error("batch must share one explicit user/project root")
    base = next(iter(bases))
    lock = base / ".carrytrace-skill-lock"
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise Error("Skill operation lock exists; inspect the previous operation before retrying") from exc
    keep_lock = False
    try:
        # Revalidate after locking. Changes since preview are not silently accepted.
        for i in items:
            dest = Path(i["destination"])
            _safe_parent(dest)
            if (inspect(dest, wanted) != i["current"]
                    or inspect(Path(i["legacy_path"]), old_wanted, old=True) != i["legacy"]):
                raise Error("installation changed after preflight; inspect and retry")
        backup_root = base / ".carrytrace-skill-backups"
        if backup_root.is_symlink() or (backup_root.exists() and not backup_root.is_dir()):
            raise Error("unsafe backup directory")
        backup_root.mkdir(mode=0o700, exist_ok=True)
        txn = backup_root / uuid.uuid4().hex
        txn.mkdir(mode=0o700)
        journal = {"schema_version": 1, "phase": "prepared", "entries": []}
        for i in actionable:
            folder = txn / i["host"]
            folder.mkdir()
            candidate = folder / "candidate"
            _stage(candidate, data, wanted)
            dest = Path(i["destination"])
            source = Path(i["legacy_path"]) if i["operation"] == "migrate" else dest
            journal["entries"].append(dict(i, source=str(source), candidate=str(candidate),
                                          backup=str(folder / "previous"), moved=False, published=False))
        receipt = txn / "receipt.json"
        _write_record(receipt, journal)
        try:
            for entry in journal["entries"]:
                dest, source = Path(entry["destination"]), Path(entry["source"])
                _safe_parent(dest)
                expected = entry["legacy"] if entry["operation"] == "migrate" else entry["current"]
                observed = inspect(source, old_wanted if entry["operation"] == "migrate" else wanted,
                                   old=entry["operation"] == "migrate")
                if observed != expected:
                    raise Error("source changed during staging; refusing to migrate user edits")
                dest.parent.mkdir(parents=True, exist_ok=True)
                if entry["operation"] != "install":
                    os.replace(source, entry["backup"])
                    entry["moved"] = True
                    _write_record(receipt, journal)
                # Source has left auto-discovery before the new Skill is published.
                if dest.exists() or dest.is_symlink():
                    raise Error("destination appeared during installation")
                os.replace(entry["candidate"], dest)
                entry["published"] = True
                _write_record(receipt, journal)
            journal["phase"] = "committed"
            _write_record(receipt, journal)
        except Exception as original:
            errors = []
            for entry in reversed(journal["entries"]):
                dest, source = Path(entry["destination"]), Path(entry["source"])
                try:
                    if entry["published"]:
                        if inspect(dest, wanted)["state"] != "current":
                            raise Error("new files changed; refusing automatic rollback")
                        os.replace(dest, entry["candidate"])
                        entry["published"] = False
                    if entry["moved"]:
                        if source.exists() or source.is_symlink():
                            raise Error("original path occupied; backup retained")
                        os.replace(entry["backup"], source)
                        entry["moved"] = False
                except Exception as exc:
                    errors.append(str(exc))
            keep_lock = bool(errors)
            journal.update(phase="rollback_required" if errors else "rolled_back", errors=errors)
            with contextlib.suppress(OSError):
                _write_record(receipt, journal)
            raise Error("operation failed; {}. Inspect {}".format(journal["phase"], receipt)) from original
        return str(receipt)
    finally:
        if not keep_lock:
            lock.rmdir()


def manage(action, *, host, scope="user", project_dir=None, dry_run=False, apply=False, force=False):
    if action not in ("install", "status", "migrate"):
        raise Error("unknown Skill operation")
    if apply and action != "migrate":
        raise Error("--apply is only valid for migration")
    if apply and dry_run:
        raise Error("--apply and --dry-run cannot be combined")
    if force and action != "install":
        raise Error("--force is only for an intact managed installation update")
    data, wanted, old_wanted, items = plan(action, host, scope, project_dir, force)
    preview = dry_run or (action == "migrate" and not apply)
    receipt = None
    if action != "status" and not preview:
        receipt = _apply(data, wanted, old_wanted, items)
        for item in items:
            item["after"] = {"current": inspect(Path(item["destination"]), wanted)["state"],
                             "legacy": inspect(Path(item["legacy_path"]), old_wanted, old=True)["state"]}
    return {"ok": True, "brand": "CarryTrace", "action": action, "dry_run": preview,
            "receipt": receipt, "installations": items,
            "scope_note": "selected host/scope only; other scopes and host activation are not scanned"}


def export_bundle(output):
    dest = Path(output).expanduser()
    if dest.suffix.lower() != ".zip" or not dest.parent.is_dir():
        raise Error("export requires a .zip file in an existing directory")
    if dest.exists() or dest.is_symlink():
        raise Error("refusing to overwrite an export")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for name, data in sorted(bundle_files().items()):
            info = zipfile.ZipInfo(NAME + "/" + name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    body = buf.getvalue()
    with dest.open("xb") as stream:
        stream.write(body)
    return {"ok": True, "action": "export", "archive": str(dest.resolve()),
            "sha256": digest(body), "bytes": len(body), "included_files": len(FILES)}


def main(argv=None):
    p = argparse.ArgumentParser(prog="carrytrace skill", description=__doc__)
    p.add_argument("action", choices=("install", "status", "migrate", "export"))
    p.add_argument("--host", choices=("codex", "claude", "both"))
    p.add_argument("--scope", choices=("user", "project"), default="user")
    p.add_argument("--project-dir")
    p.add_argument("--out")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    try:
        if args.action == "export":
            if (not args.out or args.host or args.project_dir or args.dry_run
                    or args.apply or args.force or args.scope != "user"):
                raise Error("export accepts only --out and --json")
            result = export_bundle(args.out)
        else:
            if not args.host or args.out:
                raise Error("install/status/migrate require --host and do not accept --out")
            result = manage(args.action, host=args.host, scope=args.scope, project_dir=args.project_dir,
                            dry_run=args.dry_run, apply=args.apply, force=args.force)
    except (ValueError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("CarryTrace / " + args.action + (" / preview only" if result.get("dry_run") else ""))
        for item in result.get("installations", []):
            print("{}: {} | current={} | legacy={}".format(item["host"], item["operation"],
                  item.get("after", {}).get("current", item["current"]["state"]),
                  item.get("after", {}).get("legacy", item["legacy"]["state"])))
        if result.get("receipt"):
            print("Retained backup and operation receipt: " + result["receipt"])
        if result.get("archive"):
            print(result["archive"])
    return 0
