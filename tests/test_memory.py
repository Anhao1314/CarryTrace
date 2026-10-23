"""Identity, migration, lookup and recovery regression tests (offline, disposable vaults)."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from test_pipeline import ROOT, RENDER, LINT, EXAMPLE, conv, run, report

sys.path.insert(0, str(ROOT / 'scripts'))
from memory_identity import prepare, validate, objects, json_text
from render_notes import safe_filename
from query_memory import load_index, search
from test_compact_hook import fire, make_vault

MIGRATE = ROOT / 'scripts/migrate_memory.py'
QUERY = ROOT / 'scripts/query_memory.py'


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.vault = self.base / 'vault'; self.vault.mkdir()
        self.path = self.base / 'source.json'
        self.data, _ = prepare(json.loads(EXAMPLE.read_text(encoding='utf-8')), safe_filename)

    def render(self, data=None):
        self.path.write_text(json_text(self.data if data is None else data), encoding='utf-8')
        proc = run(RENDER, '--distill', self.path, '--vault', self.vault)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return report(proc)

    def snapshots(self):
        return {str(p.relative_to(self.vault)): p.read_bytes() for p in self.vault.rglob('*') if p.is_file()}

    def ids(self, data=None):
        return {o['note_name']: o['memory_id'] for o, _, _ in objects(data or self.data)}

    def test_reorder_conversations_is_noop(self):
        self.render(); before = self.snapshots()
        self.data['conversations'].reverse()
        self.assertIsNone(self.render()['log_entry'])
        self.assertEqual(before, self.snapshots())

    def test_reorder_cards_is_noop(self):
        self.render(); before = self.snapshots()
        self.data['conversations'][0]['cards'].reverse()
        self.assertIsNone(self.render()['log_entry'])
        self.assertEqual(before, self.snapshots())

    def test_edit_identity_and_filename_survive(self):
        self.render(); ids = self.ids()
        card = self.data['conversations'][0]['cards'][0]
        card.update(title='新的标题', body='新的正文', tags=['new'], categories=['技术开发/开发环境'], status='有争议')
        out = self.render()
        self.assertEqual(ids, self.ids())
        self.assertEqual(out['created'], [])
        self.assertEqual(out['orphans'], [])
        self.assertIn('知识卡片/' + card['note_name'] + '.md', out['updated'])
        self.assertIn('00 · 对话沉淀 MOC.md', out['updated'])

    def test_add_historical_session(self):
        self.render(); old = self.ids()
        self.data['conversations'].insert(0, conv('older', date='2000-01-01', cards=[dict(title='历史', body='历史正文')]))
        self.data, changes = prepare(self.data, safe_filename)
        self.assertEqual(len(changes['allocated']), 2)
        self.render()
        self.assertTrue(all(self.ids()[k] == v for k, v in old.items()))

    def test_add_new_card(self):
        old = self.ids()
        self.data['conversations'][0]['cards'].insert(0, dict(title='新增', body='新'))
        self.data, changes = prepare(self.data, safe_filename)
        self.assertEqual(len(changes['allocated']), 1)
        self.assertTrue(all(self.ids()[k] == v for k, v in old.items()))
        self.render()

    def test_duplicate_identity_fails_before_write(self):
        self.data['conversations'][0]['cards'][1]['memory_id'] = self.data['conversations'][0]['cards'][0]['memory_id']
        self.path.write_text(json_text(self.data), encoding='utf-8')
        proc = run(RENDER, '--distill', self.path, '--vault', self.vault)
        self.assertEqual(proc.returncode, 1)
        self.assertIn('duplicate memory_id', proc.stdout)
        self.assertEqual(self.snapshots(), {})

    def test_missing_identity_fails(self):
        del self.data['conversations'][0]['cards'][0]['memory_id']
        with self.assertRaisesRegex(ValueError, 'missing'):
            validate(self.data)

    def test_broken_relation_fails(self):
        self.data['conversations'][0]['cards'][0]['related'] = ['mem_' + '0'*32]
        with self.assertRaisesRegex(ValueError, 'dangling'):
            validate(self.data)

    def test_display_collision_fails(self):
        reg = self.data['identity_registry']
        records = [r for r in reg.values() if r['type'] == 'card']
        records[1].update(display_id=records[0]['display_id'], note_name=records[0]['note_name'])
        with self.assertRaisesRegex(ValueError, 'collision'):
            validate(self.data)

    def test_deleted_ids_and_display_numbers_not_reused(self):
        old = self.data['conversations'][0]['cards'].pop(0)
        self.data, _ = prepare(self.data, safe_filename)
        self.assertFalse(self.data['identity_registry'][old['memory_id']]['active'])
        self.data['conversations'][0]['cards'].append(dict(title=old['title'], body=old['body']))
        self.data, _ = prepare(self.data, safe_filename)
        new = self.data['conversations'][0]['cards'][-1]
        self.assertNotEqual(old['memory_id'], new['memory_id'])
        self.assertNotEqual(old['display_id'], new['display_id'])
        self.data['conversations'][0]['cards'].append(old)
        with self.assertRaises(ValueError):
            prepare(self.data, safe_filename)

    def test_stable_supersession_resolves_to_display(self):
        old, new = self.data['conversations'][0]['cards']
        old.update(status='已过期', superseded_by=new['memory_id'], related=[new['memory_id']])
        self.render()
        text = (self.vault / '对话沉淀/知识卡片' / (old['note_name'] + '.md')).read_text(encoding='utf-8')
        self.assertIn('superseded_by_memory_id: ' + new['memory_id'], text)
        self.assertIn('[[' + new['note_name'] + ']]', text)
        self.assertEqual(report(run(LINT, '--vault', self.vault))['structure_issues'], [])

    def test_supersession_cycle_rejected(self):
        a, b = self.data['conversations'][0]['cards']
        a.update(status='已过期', superseded_by=b['memory_id'])
        b.update(status='已过期', superseded_by=a['memory_id'])
        with self.assertRaisesRegex(ValueError, 'cycle'):
            validate(self.data)

    def test_lint_detects_duplicate_and_missing_ids(self):
        self.render()
        a, b = self.data['conversations'][0]['cards']
        p = self.vault / '对话沉淀/知识卡片' / (b['note_name'] + '.md')
        p.write_text(p.read_text(encoding='utf-8').replace(b['memory_id'], a['memory_id']), encoding='utf-8')
        out = report(run(LINT, '--vault', self.vault))
        self.assertTrue(any(p['kind'] == 'identity' for p in out['structure_issues']))

    def test_registry_cannot_be_forgotten(self):
        self.render()
        self.data['identity_registry'].pop(self.data['conversations'][0]['cards'][0]['memory_id'])
        with self.assertRaises(ValueError):
            validate(self.data)

    def test_legacy_cannot_overwrite_v2(self):
        self.render(); before = self.snapshots()
        proc = run(RENDER, '--distill', EXAMPLE, '--vault', self.vault)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(before, self.snapshots())

    def test_migrate_legacy_fixture_and_relations(self):
        legacy = json.loads(EXAMPLE.read_text(encoding='utf-8'))
        a = legacy['conversations'][0]['cards'][0]
        a.update(status='已过期', superseded_by='C02', related=['S02'])
        migrated, _ = prepare(legacy, safe_filename)
        a = migrated['conversations'][0]['cards'][0]
        self.assertTrue(a['superseded_by'].startswith('mem_'))
        self.assertTrue(a['related'][0].startswith('mem_'))

    def test_migration_dry_run_never_mutates(self):
        out = self.base / 'migrated.json'; rp = self.base / 'report.json'
        before = EXAMPLE.read_bytes()
        proc = run(MIGRATE, '--distill', EXAMPLE, '--out', out, '--report', rp, '--dry-run')
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertFalse(out.exists()); self.assertFalse(rp.exists())
        self.assertEqual(before, EXAMPLE.read_bytes())

    def test_migration_is_idempotent(self):
        self.path.write_text(json_text(self.data), encoding='utf-8'); before = self.path.read_bytes()
        proc = run(MIGRATE, '--distill', self.path, '--out', self.path)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertFalse(report(proc)['changed'])
        self.assertEqual(before, self.path.read_bytes())

    def test_ambiguous_or_unresolved_relationship_fails(self):
        data = json.loads(EXAMPLE.read_text(encoding='utf-8'))
        data['conversations'][0]['cards'][0]['superseded_by'] = 'C99 - 不存在'
        with self.assertRaisesRegex(ValueError, 'unresolved'):
            prepare(data, safe_filename)

    def test_existing_vault_migration_preserves_paths_taxonomy_and_log(self):
        self.assertEqual(run(RENDER, '--distill', EXAMPLE, '--vault', self.vault).returncode, 0)
        paths = {p.relative_to(self.vault) for p in self.vault.rglob('*.md')}
        taxonomy = self.vault / '对话沉淀/.chat-distiller/taxonomy.md'
        tax = taxonomy.read_bytes()
        log = self.vault / '对话沉淀/操作日志.md'; old_log = log.read_text(encoding='utf-8')
        proc = run(MIGRATE, '--distill', EXAMPLE, '--vault', self.vault, '--out', self.path)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.data = json.loads(self.path.read_text(encoding='utf-8'))
        self.render()
        self.assertEqual(paths, {p.relative_to(self.vault) for p in self.vault.rglob('*.md')})
        self.assertEqual(tax, taxonomy.read_bytes())
        self.assertTrue(log.read_text(encoding='utf-8').startswith(old_log))
        self.assertIsNone(self.render()['log_entry'])

    def test_migration_rejects_drift_and_orphans(self):
        run(RENDER, '--distill', EXAMPLE, '--vault', self.vault)
        note = next(self.vault.rglob('C01*.md')); note.write_text('manually edited', encoding='utf-8')
        proc = run(MIGRATE, '--distill', EXAMPLE, '--vault', self.vault, '--out', self.path)
        self.assertEqual(proc.returncode, 1)
        self.assertFalse(self.path.exists())

    def test_stable_render_rejects_unverified_legacy_vault(self):
        run(RENDER, '--distill', EXAMPLE, '--vault', self.vault)
        self.path.write_text(json_text(self.data), encoding='utf-8')
        self.assertEqual(run(RENDER, '--distill', self.path, '--vault', self.vault).returncode, 1)

    def test_lookup_current_chinese_and_history(self):
        a, b = self.data['conversations'][0]['cards']
        a.update(title='Docker Docker', body='Docker 开发环境 Docker', status='已过期', superseded_by=b['memory_id'])
        b.update(title='开发环境', body='Docker 已移除，使用 venv')
        self.render(); rows = load_index(self.vault / '对话沉淀')
        hits = search(rows, 'Docker 开发环境')
        self.assertEqual(hits[0]['memory_id'], b['memory_id'])
        self.assertNotIn(a['memory_id'], [r['memory_id'] for r in hits])
        self.assertIn(a['memory_id'], [r['memory_id'] for r in search(rows, 'Docker 开发环境', include_noncurrent=True)])

    def test_lookup_deterministic_and_empty_unknown_safe(self):
        self.render(); rows = load_index(self.vault / '对话沉淀')
        self.assertEqual(search(rows, '备份'), search(rows, '备份'))
        for q in ('', '  !!!', 'zxqvzzzz'):
            self.assertEqual(search(rows, q), [])
        with self.assertRaises(ValueError):
            search(rows, '备份', top_k=0)

    def test_disputed_exposed(self):
        card = self.data['conversations'][0]['cards'][0]
        card.update(status='有争议', title='TTL', body='TTL 尚未确定')
        self.render(); hits = search(load_index(self.vault / '对话沉淀'), 'TTL')
        self.assertTrue(hits[0]['disputed'])
        self.assertEqual(hits[0]['status'], '有争议')

    def test_index_corruption_fails_closed(self):
        self.render()
        idx = self.vault / '对话沉淀/知识索引.jsonl'
        idx.write_text(idx.read_text(encoding='utf-8').replace('现行', '已过期'), encoding='utf-8')
        proc = run(QUERY, '--vault', self.vault, '--query', '备份')
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(report(proc)['results'], [])

    def test_hook_routes_lookup_without_dumping_memory(self):
        self.render()
        out = fire({'hook_event_name':'SessionStart', 'source':'compact'}, self.vault)
        self.assertIn('query_memory.py', out.stdout)
        self.assertIn('memory_id', out.stdout)
        self.assertNotIn(self.data['conversations'][0]['cards'][0]['body'], out.stdout)
        self.assertLess(len(out.stdout), 1500)

    def test_hook_missing_tool_falls_back(self):
        import shutil
        hook = self.base / 'compact_hook.py'
        shutil.copy(ROOT / 'scripts/compact_hook.py', hook)
        self.render()
        proc = subprocess.run([sys.executable, str(hook), '--vault', str(self.vault)], input=json.dumps(dict(hook_event_name='SessionStart',source='compact')), capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertNotIn('query_memory.py', proc.stdout)
        self.assertIn('知识索引.md', proc.stdout)

    def test_hook_invalid_arguments_exit_zero(self):
        out = fire({}, self.vault, '--not-an-option')
        self.assertEqual(out.returncode, 0)

    def test_registry_missing_cannot_downgrade_vault(self):
        self.render()
        (self.vault / '对话沉淀/.chat-distiller/identity-registry.json').unlink()
        before = self.snapshots()
        proc = run(RENDER, '--distill', EXAMPLE, '--vault', self.vault)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(before, self.snapshots())

    def test_lint_missing_registry_reports(self):
        self.render()
        (self.vault / '对话沉淀/.chat-distiller/identity-registry.json').unlink()
        self.assertTrue(report(run(LINT, '--vault', self.vault))['structure_issues'])

    def test_lint_status_and_dangling_stable_reference(self):
        self.render()
        p = next(self.vault.rglob('C01*.md'))
        p.write_text(p.read_text(encoding='utf-8').replace('status: 现行', 'status: 有争议').replace('source_memory_id: ', 'source_memory_id: broken_'), encoding='utf-8')
        issues = report(run(LINT, '--vault', self.vault))['structure_issues']
        self.assertTrue(any('dangling stable' in issue['detail'] for issue in issues))
        self.assertTrue(any('status' in issue['detail'] for issue in issues))

    def test_stable_dry_run_preserves_source_and_vault(self):
        self.path.write_text(json_text(self.data), encoding='utf-8')
        original = self.path.read_bytes()
        proc = run(RENDER, '--distill', self.path, '--vault', self.vault, '--dry-run')
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(original, self.path.read_bytes())
        self.assertEqual(self.snapshots(), {})
        self.assertEqual(len(report(proc)['state_changed']), 2)

    def test_render_never_rewrites_input(self):
        self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding='utf-8')
        original = self.path.read_bytes()
        self.assertEqual(run(RENDER, '--distill', self.path, '--vault', self.vault).returncode, 0)
        self.assertEqual(original, self.path.read_bytes())

    def test_source_relationship_is_immutable(self):
        self.data['conversations'][1]['threads'][0]['cards'].append(self.data['conversations'][0]['cards'].pop())
        with self.assertRaisesRegex(ValueError, 'source session changed'):
            validate(self.data)

    def test_ambiguous_title_only_relation_fails(self):
        data = dict(conversations=[conv('a', cards=[dict(title='same'), dict(title='same')], related=['same'])])
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            prepare(data, safe_filename)

    def test_migration_report_cannot_overwrite_source(self):
        self.path.write_text(json_text(self.data), encoding='utf-8')
        before = self.path.read_bytes()
        proc = run(MIGRATE, '--distill', self.path, '--out', self.path, '--report', self.path)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(before, self.path.read_bytes())
