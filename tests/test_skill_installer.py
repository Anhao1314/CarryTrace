"""Portable Agent Skill packaging, safety and local installation contracts."""
import contextlib
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from chat_distiller import cli
from chat_distiller.skill_installer import (
    BUNDLE, MANAGED_BY, MARKER, SkillInstallError, bundle_files, manage,
)


class SkillInstallerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.project = self.root / "project"
        self.project.mkdir()

    def skill_dir(self, host="codex"):
        folder = ".agents" if host == "codex" else ".claude"
        return self.project / folder / "skills" / "chat-distiller"

    def test_packaged_metadata_and_local_references(self):
        bundle = bundle_files()
        self.assertEqual(set(bundle), set(BUNDLE))
        text = bundle["SKILL.md"].decode("utf-8")
        self.assertRegex(text, r"\A---\nname: chat-distiller\n")
        match = re.search(r'^description: "(.+)"$', text, re.M)
        self.assertIsNotNone(match)
        self.assertLessEqual(len(match.group(1)), 1024)
        self.assertIn("continue a previous project", match.group(1))
        self.assertIn("恢复上下文", match.group(1))
        self.assertIn("references/WORKFLOWS.md", text)
        self.assertIn("references/BOUNDARIES.md", text)
        self.assertLess(len(text.splitlines()), 500)

    def test_both_hosts_project_install_matches_packaged_bytes(self):
        response = manage("install", host="both", scope="project", project_dir=self.project)
        self.assertEqual(len(response["installations"]), 2)
        for host in ("codex", "claude"):
            dest = self.skill_dir(host)
            self.assertTrue(dest.is_dir())
            for name, content in bundle_files().items():
                self.assertEqual((dest / name).read_bytes(), content)
            self.assertEqual(json.loads((dest / MARKER).read_text())["managed_by"], MANAGED_BY)
        self.assertEqual(manage("status", host="both", scope="project",
                                project_dir=self.project)["installations"][0]["state"], "current")

    def test_repeated_install_is_idempotent(self):
        manage("install", host="both", scope="project", project_dir=self.project)
        old = {p: p.read_bytes() for p in self.project.rglob("*") if p.is_file()}
        response = manage("install", host="both", scope="project", project_dir=self.project)
        self.assertTrue(all(x["state"] == "up_to_date" for x in response["installations"]))
        self.assertEqual(old, {p: p.read_bytes() for p in self.project.rglob("*") if p.is_file()})

    def test_status_and_dry_run_do_not_create_any_files(self):
        first = manage("status", host="both", scope="project", project_dir=self.project)
        self.assertTrue(all(x["state"] == "missing" for x in first["installations"]))
        result = manage("install", host="both", scope="project",
                        project_dir=self.project, dry_run=True)
        self.assertEqual([i["state"] for i in result["installations"]], ["would_install", "would_install"])
        self.assertEqual(list(self.project.iterdir()), [])

    def test_foreign_skill_is_not_overwritten_even_with_force(self):
        target = self.skill_dir()
        target.mkdir(parents=True)
        original = target / "SKILL.md"
        original.write_text("custom skill", encoding="utf-8")
        with self.assertRaisesRegex(SkillInstallError, "refusing to overwrite"):
            manage("install", host="codex", scope="project", project_dir=self.project, force=True)
        self.assertEqual(original.read_text(), "custom skill")

    def test_user_modifications_are_not_overwritten(self):
        manage("install", host="codex", scope="project", project_dir=self.project)
        readme = self.skill_dir() / "SKILL.md"
        readme.write_text(readme.read_text(encoding="utf-8") + "\nuser edit\n", encoding="utf-8")
        self.assertEqual(manage("status", host="codex", scope="project",
                                project_dir=self.project)["installations"][0]["state"], "modified")
        with self.assertRaisesRegex(SkillInstallError, "refusing to overwrite"):
            manage("install", host="codex", scope="project", project_dir=self.project, force=True)

    def test_extra_files_in_managed_skill_are_never_deleted(self):
        manage("install", host="codex", scope="project", project_dir=self.project)
        extra = self.skill_dir() / "notes.txt"
        extra.write_text("local notes", encoding="utf-8")
        with self.assertRaises(SkillInstallError):
            manage("install", host="codex", scope="project", project_dir=self.project, force=True)
        self.assertEqual(extra.read_text(), "local notes")

    def test_explicit_force_updates_an_intact_managed_old_bundle(self):
        manage("install", host="codex", scope="project", project_dir=self.project)
        changed = dict(bundle_files())
        changed["SKILL.md"] += b"\n# Updated version\n"
        with patch("chat_distiller.skill_installer.bundle_files", return_value=changed):
            state = manage("status", host="codex", scope="project", project_dir=self.project)
            self.assertEqual(state["installations"][0]["state"], "update_available")
            with self.assertRaisesRegex(SkillInstallError, "use --force"):
                manage("install", host="codex", scope="project", project_dir=self.project)
            upgraded = manage("install", host="codex", scope="project",
                             project_dir=self.project, force=True)
            self.assertEqual(upgraded["installations"][0]["state"], "upgraded")
            self.assertEqual((self.skill_dir() / "SKILL.md").read_bytes(), changed["SKILL.md"])

    def test_symlinked_skill_target_is_rejected(self):
        alternative = self.project / "alternate"
        alternative.mkdir()
        parent = self.skill_dir().parent
        parent.mkdir(parents=True)
        try:
            self.skill_dir().symlink_to(alternative, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not supported here")
        with self.assertRaisesRegex(SkillInstallError, "refusing to overwrite"):
            manage("install", host="codex", scope="project", project_dir=self.project)
        self.assertEqual(list(alternative.iterdir()), [])

    def test_symlinked_parent_is_rejected(self):
        replacement = self.root / "elsewhere"
        replacement.mkdir()
        try:
            (self.project / ".agents").symlink_to(replacement, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not supported here")
        with self.assertRaisesRegex(SkillInstallError, "symlinked"):
            manage("install", host="codex", scope="project", project_dir=self.project)
        self.assertEqual(list(replacement.iterdir()), [])

    def test_missing_project_dir_is_rejected(self):
        with self.assertRaisesRegex(SkillInstallError, "must already exist"):
            manage("install", host="codex", scope="project",
                   project_dir=self.root / "nonexistent")

    def test_user_scope_installs_in_home_locations(self):
        home = self.root / "fake-home"
        home.mkdir()
        with patch("chat_distiller.skill_installer.Path.home", return_value=home):
            result = manage("install", host="both", scope="user")
            self.assertEqual(len(result["installations"]), 2)
            self.assertTrue((home / ".agents/skills/chat-distiller/SKILL.md").is_file())
            self.assertTrue((home / ".claude/skills/chat-distiller/SKILL.md").is_file())

    def test_explicit_project_dir_not_allowed_with_user_scope(self):
        with self.assertRaisesRegex(SkillInstallError, "only valid"):
            manage("install", host="codex", scope="user", project_dir=self.project)

    def test_cli_json_status_install_and_error_are_machine_readable(self):
        out = io.StringIO()
        arguments = ["skill", "install", "--host", "codex", "--scope", "project",
                     "--project-dir", str(self.project), "--json"]
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(arguments), 0)
        self.assertEqual(json.loads(out.getvalue())["installations"][0]["state"], "installed")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["skill", "status", "--host", "codex",
                                       "--scope", "project", "--project-dir", str(self.project),
                                       "--json"]), 0)
        self.assertEqual(json.loads(out.getvalue())["installations"][0]["state"], "current")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["skill", "install", "--host", "codex",
                                       "--scope", "user", "--project-dir", str(self.project),
                                       "--json"]), 1)
        self.assertFalse(json.loads(out.getvalue())["ok"])


if __name__ == "__main__":
    unittest.main()
