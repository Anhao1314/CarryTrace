"""CarryTrace branding compatibility and opt-in migration failure experiments."""
import contextlib
import copy
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from chat_distiller import skill_installer as old
from chat_distiller import brand_skill as new
from chat_distiller import brand_cli


def files(root):
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in root.rglob('*') if p.is_file() and not p.is_symlink()}


class BrandMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.kw = dict(host='both', scope='project', project_dir=self.base)

    def dest(self, host='codex', name='carrytrace'):
        return self.base / old.HOSTS[host] / 'skills' / name

    def legacy(self):
        old.manage('install', **self.kw)
        return files(self.base)

    def test_bundle_name_and_self_contained_references(self):
        data = new.bundle_files()
        self.assertEqual(set(data), set(old.BUNDLE))
        self.assertTrue(data['SKILL.md'].startswith(b'---\nname: carrytrace\n'))
        self.assertIn(b'~/.chat-distiller', data['SKILL.md'])
        self.assertIn(b'references/BOUNDARIES.md', data['SKILL.md'])

    def test_status_does_not_create_state(self):
        result = new.manage('status', **self.kw)
        self.assertTrue(all(i['current']['state'] == 'missing' for i in result['installations']))
        self.assertEqual(list(self.base.iterdir()), [])

    def test_new_install_dry_run_and_repeat(self):
        new.manage('install', dry_run=True, **self.kw)
        self.assertEqual(list(self.base.iterdir()), [])
        result = new.manage('install', **self.kw)
        self.assertTrue(Path(result['receipt']).is_file())
        for h in ('codex', 'claude'):
            self.assertTrue((self.dest(h) / 'SKILL.md').is_file())
            self.assertFalse(self.dest(h, 'chat-distiller').exists())
        before = files(self.base)
        self.assertIsNone(new.manage('install', **self.kw)['receipt'])
        self.assertEqual(files(self.base), before)

    def test_old_detected_install_refuses_without_writes(self):
        before = self.legacy()
        with self.assertRaisesRegex(new.Error, 'preview'):
            new.manage('install', force=True, **self.kw)
        self.assertEqual(before, files(self.base))

    def test_migration_default_is_read_only_preview(self):
        before = self.legacy()
        result = new.manage('migrate', **self.kw)
        self.assertTrue(result['dry_run'])
        self.assertTrue(all(i['operation'] == 'migrate' for i in result['installations']))
        self.assertEqual(before, files(self.base))
        self.assertFalse((self.base / '.carrytrace-skill-backups').exists())

    def test_migrate_retains_exact_backup_outside_discovery_and_is_idempotent(self):
        self.legacy()
        originals = {h: files(self.dest(h, 'chat-distiller')) for h in ('codex', 'claude')}
        result = new.manage('migrate', apply=True, **self.kw)
        journal = json.loads(Path(result['receipt']).read_text())
        self.assertEqual(journal['phase'], 'committed')
        for entry in journal['entries']:
            self.assertEqual(files(Path(entry['backup'])), originals[entry['host']])
            self.assertNotIn('.agents', Path(entry['backup']).relative_to(self.base).parts)
            self.assertNotIn('.claude', Path(entry['backup']).relative_to(self.base).parts)
            self.assertFalse(Path(entry['legacy_path']).exists())
            self.assertTrue((Path(entry['destination']) / 'SKILL.md').is_file())
        before = files(self.base)
        self.assertIsNone(new.manage('migrate', apply=True, **self.kw)['receipt'])
        self.assertEqual(before, files(self.base))

    def test_old_command_cannot_reinstall_second_active_alias(self):
        self.legacy()
        new.manage('migrate', apply=True, **self.kw)
        before = files(self.base)
        with self.assertRaisesRegex(old.SkillInstallError, 'CarryTrace'):
            old.manage('install', force=True, **self.kw)
        self.assertEqual(before, files(self.base))

    def test_modified_legacy_blocks_entire_batch(self):
        self.legacy()
        p = self.dest('claude', 'chat-distiller') / 'SKILL.md'
        p.write_bytes(p.read_bytes() + b'\nlocal edit\n')
        before = files(self.base)
        with self.assertRaisesRegex(new.Error, 'manual review'):
            new.manage('migrate', apply=True, **self.kw)
        self.assertEqual(before, files(self.base))
        self.assertFalse(self.dest().exists())

    def test_unmanaged_legacy_is_not_migrated(self):
        self.legacy()
        (self.dest('codex', 'chat-distiller') / old.MARKER).unlink()
        before = files(self.base)
        with self.assertRaises(new.Error):
            new.manage('migrate', apply=True, **self.kw)
        self.assertEqual(before, files(self.base))

    def test_extra_empty_directory_is_not_silently_deleted(self):
        self.legacy()
        (self.dest('codex', 'chat-distiller') / 'my-private-notes').mkdir()
        with self.assertRaises(new.Error):
            new.manage('migrate', apply=True, **self.kw)
        self.assertTrue((self.dest('codex', 'chat-distiller') / 'my-private-notes').is_dir())

    def test_nested_symlink_is_refused(self):
        self.legacy()
        refs = self.dest('codex', 'chat-distiller') / 'references'
        moved = self.base / 'external-references'
        shutil.move(refs, moved)
        try:
            refs.symlink_to(moved, target_is_directory=True)
        except OSError:
            self.skipTest('no symlink capability')
        before = files(moved)
        with self.assertRaisesRegex(new.Error, 'manual review'):
            new.manage('migrate', apply=True, **self.kw)
        self.assertEqual(before, files(moved))

    def test_duplicate_names_are_not_silently_resolved(self):
        self.legacy()
        shutil.copytree(self.dest('codex', 'chat-distiller'), self.dest())
        before = files(self.base)
        with self.assertRaises(new.Error):
            new.manage('migrate', apply=True, **self.kw)
        self.assertEqual(before, files(self.base))

    def test_force_never_overwrites_modified_new_skill(self):
        new.manage('install', **self.kw)
        p = self.dest() / 'SKILL.md'
        p.write_bytes(p.read_bytes() + b'\ncustom\n')
        before = files(self.base)
        with self.assertRaises(new.Error):
            new.manage('install', force=True, **self.kw)
        self.assertEqual(before, files(self.base))

    def test_intact_update_requires_force_and_retains_backup(self):
        new.manage('install', **self.kw)
        data = new.bundle_files()
        data['SKILL.md'] += b'\nnew instructions\n'
        with patch.object(new, 'bundle_files', return_value=data):
            with self.assertRaisesRegex(new.Error, '--force'):
                new.manage('install', **self.kw)
            receipt = new.manage('install', force=True, **self.kw)['receipt']
        self.assertTrue(Path(receipt).is_file())
        self.assertTrue((Path(receipt).parent / 'codex/previous/SKILL.md').is_file())

    def test_publication_failure_rolls_back_both_hosts(self):
        originals = self.legacy()
        real = new.os.replace
        def fail_second(src, dst):
            if Path(src).name == 'candidate' and '.claude' in str(dst):
                raise OSError('injected second-host publication failure')
            return real(src, dst)
        with patch.object(new.os, 'replace', side_effect=fail_second):
            with self.assertRaisesRegex(new.Error, 'rolled_back'):
                new.manage('migrate', apply=True, **self.kw)
        live = {k: v for k, v in files(self.base).items() if k.startswith(('.agents/', '.claude/'))}
        self.assertEqual(originals, live)
        self.assertFalse(self.dest().exists())
        self.assertFalse((self.base / '.carrytrace-skill-lock').exists())

    def test_failed_rollback_keeps_backup_and_lock(self):
        self.legacy()
        original = files(self.dest('codex', 'chat-distiller'))
        real = new.os.replace
        def fail(src, dst):
            if Path(src).name in ('candidate', 'previous'):
                raise OSError('injected publish and restore failures')
            return real(src, dst)
        with patch.object(new.os, 'replace', side_effect=fail):
            with self.assertRaisesRegex(new.Error, 'rollback_required'):
                new.manage('migrate', apply=True, **self.kw)
        backups = list((self.base / '.carrytrace-skill-backups').glob('*/codex/previous'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(files(backups[0]), original)
        self.assertTrue((self.base / '.carrytrace-skill-lock').exists())

    def test_existing_lock_and_unsafe_backup_parent_block_writes(self):
        before = self.legacy()
        lock = self.base / '.carrytrace-skill-lock'; lock.mkdir()
        with self.assertRaisesRegex(new.Error, 'lock exists'):
            new.manage('migrate', apply=True, **self.kw)
        self.assertEqual(files(self.base), before)
        lock.rmdir()
        (self.base / '.carrytrace-skill-backups').write_text('foreign file')
        with self.assertRaisesRegex(new.Error, 'unsafe backup'):
            new.manage('migrate', apply=True, **self.kw)

    def test_legacy_installer_respects_brand_operation_lock(self):
        before = self.legacy()
        (self.base / '.carrytrace-skill-lock').mkdir()
        with self.assertRaisesRegex(old.SkillInstallError, 'lock exists'):
            old.manage('install', **self.kw)
        self.assertEqual(before, files(self.base))

    def test_edit_during_staging_is_not_migrated(self):
        self.legacy()
        real = new._stage
        path = self.dest('claude', 'chat-distiller') / 'SKILL.md'
        def change(path_arg, data, wanted):
            real(path_arg, data, wanted)
            if path_arg.parent.name == 'claude':
                path.write_bytes(path.read_bytes() + b'\nconcurrent user edit\n')
        with patch.object(new, '_stage', side_effect=change):
            with self.assertRaisesRegex(new.Error, 'rolled_back'):
                new.manage('migrate', apply=True, **self.kw)
        self.assertIn(b'concurrent user edit', path.read_bytes())
        self.assertTrue(self.dest('codex', 'chat-distiller').is_dir())
        self.assertFalse(self.dest().exists())

    def test_user_scope_uses_correct_host_directories(self):
        with patch.object(old.Path, 'home', return_value=self.base):
            result = new.manage('install', host='both')
        self.assertTrue(all(Path(i['destination']).parents[2] == self.base for i in result['installations']))

    def test_invalid_options_fail(self):
        for overrides in ({'host': 'unknown'}, {'scope': 'unknown'}, {'apply': True},
                          {'project_dir': self.base / 'missing'}):
            kw = dict(self.kw, **overrides)
            with self.assertRaises(new.Error):
                new.manage('install', **kw)
        with self.assertRaises(new.Error):
            new.manage('migrate', apply=True, dry_run=True, **self.kw)
        with self.assertRaises(new.Error):
            new.manage('migrate', force=True, **self.kw)

    def test_export_deterministic_name_and_bytes(self):
        a, b = self.base / 'a.zip', self.base / 'b.zip'
        new.export_bundle(a); new.export_bundle(b)
        self.assertEqual(a.read_bytes(), b.read_bytes())
        with zipfile.ZipFile(a) as z:
            self.assertEqual(set(z.namelist()), {'carrytrace/' + f for f in old.BUNDLE})
            self.assertEqual(z.read('carrytrace/SKILL.md'), new.bundle_files()['SKILL.md'])
        with self.assertRaises(new.Error):
            new.export_bundle(a)

    def test_brand_entry_delegates_unchanged_engine_arguments(self):
        for args in (['context', '机器人', '--json'], ['recover', '--vault', 'v', '--query', 'q'],
                     ['sync', '--json'], ['wiki', 'status', '--vault', 'v']):
            with patch.object(brand_cli, 'legacy_main', return_value=13) as delegated:
                self.assertEqual(brand_cli.main(args), 13)
                delegated.assert_called_once_with(args)

    def test_brand_cli_version_and_error_json(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(brand_cli.main(['--version']), 0)
        self.assertIn('CarryTrace', out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(brand_cli.main(['skill', 'install', '--json']), 1)
        self.assertFalse(json.loads(out.getvalue())['ok'])


if __name__ == '__main__':
    unittest.main()
