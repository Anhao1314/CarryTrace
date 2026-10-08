"""Install the packaged, instruction-only Agent Skill with local-only side effects.

This does not install model services, read conversations, configure hooks,
connect to a provider or publish memory.
"""
import argparse
import hashlib
from importlib import resources
import json
import os
from pathlib import Path
import shutil
import tempfile


SKILL_NAME = "chat-distiller"
MARKER = ".chat-distiller-managed.json"
BUNDLE = ("SKILL.md", "references/WORKFLOWS.md", "references/BOUNDARIES.md")
HOSTS = {"codex": ".agents", "claude": ".claude"}
MANAGED_BY = "chat-distiller-skill-installer-v1"


class SkillInstallError(ValueError):
    pass


def _hash(blob):
    return hashlib.sha256(blob).hexdigest()


def bundle_files():
    base = resources.files("chat_distiller").joinpath("skills", SKILL_NAME)
    try:
        found = {p: base.joinpath(*p.split("/")).read_bytes() for p in BUNDLE}
    except (OSError, FileNotFoundError) as exc:
        raise SkillInstallError("installed package is missing its Agent Skill bundle") from exc
    doc = found["SKILL.md"].decode("utf-8")
    if not doc.startswith("---\nname: chat-distiller\n"):
        raise SkillInstallError("packaged Skill frontmatter is invalid")
    return found


def _manifest(bundle):
    return {"schema_version": 1, "managed_by": MANAGED_BY,
            "files": {name: _hash(data) for name, data in sorted(bundle.items())}}


def _target(host, scope, project_dir):
    if scope == "user":
        if project_dir is not None:
            raise SkillInstallError("--project-dir is only valid with --scope project")
        base = Path.home().expanduser().resolve()
    else:
        base = Path(project_dir or Path.cwd()).expanduser().resolve()
        if not base.is_dir():
            raise SkillInstallError("project directory must already exist")
    parent = base / HOSTS[host] / "skills"
    for path in (base / HOSTS[host], parent):
        if path.is_symlink():
            raise SkillInstallError("refusing to install through a symlinked skill directory")
        if path.exists() and not path.is_dir():
            raise SkillInstallError("skill parent is not a directory: " + str(path))
    return parent / SKILL_NAME


def _current_state(destination, wanted):
    if destination.is_symlink():
        return "unsafe_symlink"
    if not destination.exists():
        return "missing"
    if not destination.is_dir():
        return "unmanaged"
    marker = destination / MARKER
    if marker.is_symlink() or not marker.is_file():
        return "unmanaged"
    try:
        installed = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return "unmanaged"
    if not isinstance(installed, dict) or installed.get("schema_version") != 1:
        return "unmanaged"
    if installed.get("managed_by") != MANAGED_BY:
        return "unmanaged"
    declared = installed.get("files")
    if not isinstance(declared, dict) or set(declared) != set(BUNDLE):
        return "unmanaged"
    if any(not isinstance(v, str) or len(v) != 64 for v in declared.values()):
        return "unmanaged"
    actual = {}
    for name in BUNDLE:
        file = destination.joinpath(*name.split("/"))
        if file.is_symlink() or not file.is_file():
            return "modified"
        actual[name] = _hash(file.read_bytes())
    # Unexpected files could contain user data; never replace the directory.
    expected_files = set(BUNDLE) | {MARKER}
    present = {p.relative_to(destination).as_posix() for p in destination.rglob("*") if p.is_file() or p.is_symlink()}
    if present != expected_files:
        return "modified"
    if actual != declared:
        return "modified"
    if actual == wanted["files"]:
        return "current"
    return "update_available"


def _write_install(destination, bundle, manifest, replace):
    parent = destination.parent
    if not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)
    # Recheck after creating directories; never traverse symlinked skill parents.
    for p in (parent.parent, parent):
        if p.is_symlink():
            raise SkillInstallError("refusing a symlinked skill parent")
    staging = Path(tempfile.mkdtemp(prefix=".chat-distiller-stage-", dir=str(parent)))
    candidate = staging / SKILL_NAME
    try:
        candidate.mkdir()
        for name, content in bundle.items():
            file = candidate.joinpath(*name.split("/"))
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(content)
        (candidate / MARKER).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if replace:
            backup = staging / "previous"
            os.replace(str(destination), str(backup))
            try:
                os.replace(str(candidate), str(destination))
            except OSError:
                os.replace(str(backup), str(destination))
                raise
        else:
            os.replace(str(candidate), str(destination))
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def manage(action, *, host, scope="user", project_dir=None, dry_run=False, force=False):
    if host not in ("codex", "claude", "both"):
        raise SkillInstallError("host must be codex, claude or both")
    if scope not in ("user", "project"):
        raise SkillInstallError("scope must be user or project")
    bundle = bundle_files()
    wanted = _manifest(bundle)
    hosts = ("codex", "claude") if host == "both" else (host,)
    targets = [(_host, _target(_host, scope, project_dir)) for _host in hosts]
    planned = [(h, dest, _current_state(dest, wanted)) for h, dest in targets]
    if action == "install":
        # Validate the entire batch before writing either destination.
        for h, dest, status in planned:
            if status in ("unsafe_symlink", "modified", "unmanaged"):
                raise SkillInstallError("{} target is {}; refusing to overwrite: {}".format(h, status, dest))
            if status == "update_available" and not force:
                raise SkillInstallError("{} has a managed older Skill; use --force for an explicit upgrade".format(h))
        if not dry_run:
            for h, dest, status in planned:
                if status != "current":
                    _write_install(dest, bundle, wanted, replace=status == "update_available")
    outcome = []
    for h, dest, before in planned:
        state = before
        if action == "install":
            if before == "missing":
                state = "would_install" if dry_run else "installed"
            elif before == "update_available":
                state = "would_upgrade" if dry_run else "upgraded"
            elif before == "current":
                state = "up_to_date"
        outcome.append({"host": h, "scope": scope, "destination": str(dest),
                        "state": state})
    return {"ok": True, "action": action, "dry_run": bool(dry_run),
            "bundled_files": len(BUNDLE), "installations": outcome}


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="chat-distiller skill", description="Install a portable Agent Skill for a local shell-capable host.")
    parser.add_argument("action", choices=("install", "status"))
    parser.add_argument("--host", choices=("codex", "claude", "both"), required=True)
    parser.add_argument("--scope", choices=("user", "project"), default="user")
    parser.add_argument("--project-dir")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = manage(args.action, host=args.host, scope=args.scope,
                        project_dir=args.project_dir, dry_run=args.dry_run, force=args.force)
    except (SkillInstallError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for item in result["installations"]:
            print("{}: {} ({})".format(item["host"], item["state"], item["destination"]))
        if args.action == "install" and not args.dry_run:
            print("Skill instructions installed; CLI runtime must be on the host PATH.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
