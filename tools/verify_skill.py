#!/usr/bin/env python3
"""Installed-wheel Skill checks outside repository root; no model or host access."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import chat_distiller
from chat_distiller.skill_installer import bundle_files

ROOT = Path(__file__).resolve().parents[1]
PKG = Path(chat_distiller.__file__).resolve()
if ROOT in PKG.parents:
    raise RuntimeError("Skill smoke imported checkout, not installed wheel")

checks = []
def require(ok, name):
    if not ok:
        raise AssertionError(name)
    checks.append(name)

with tempfile.TemporaryDirectory(prefix="chat-distiller-skill-installed-") as tmp:
    project = Path(tmp) / "project"
    project.mkdir()
    def run(action, *args, expected=0):
        proc = subprocess.run([sys.executable, "-m", "chat_distiller", "skill", action,
                              "--host", "both", "--scope", "project",
                              "--project-dir", str(project), "--json", *args],
                              cwd=str(project), capture_output=True, text=True, timeout=45)
        require(proc.returncode == expected, "CLI " + action + " returns " + str(expected))
        return json.loads(proc.stdout)
    contents = bundle_files()
    require(len(contents) == 3, "wheel packages complete portable Skill")
    require(contents["SKILL.md"].startswith(b"---\nname: chat-distiller\n"), "installed frontmatter")
    before = run("status")
    require(all(x["state"] == "missing" for x in before["installations"]), "status before install")
    dry = run("install", "--dry-run")
    require(all(x["state"] == "would_install" for x in dry["installations"]), "dry run reports changes")
    require(list(project.iterdir()) == [], "dry run has no side effects")
    installed = run("install")
    require(all(x["state"] == "installed" for x in installed["installations"]), "Codex and Claude install")
    for folder in (".agents", ".claude"):
        for name, data in contents.items():
            dest = project / folder / "skills" / "chat-distiller" / name
            require(dest.is_file() and dest.read_bytes() == data, "installed byte content " + folder + " / " + name)
    again = run("install")
    require(all(x["state"] == "up_to_date" for x in again["installations"]), "repeat install is no-op")
    status = run("status")
    require(all(x["state"] == "current" for x in status["installations"]), "status after install")
    edited = project / ".agents/skills/chat-distiller/SKILL.md"
    edited.write_bytes(edited.read_bytes() + b"\nchanged by local user\n")
    denied = run("install", "--force", expected=1)
    require(not denied["ok"] and "refusing to overwrite" in denied["error"],
            "modified skill blocks batch overwrite")

print(json.dumps({"ok": True, "package_version": chat_distiller.__version__,
                  "installed_package": str(PKG), "checks_passed": len(checks),
                  "checks": checks, "notes": "local instruction/installer smoke only; no agent invoked"},
                 ensure_ascii=False, indent=2))
