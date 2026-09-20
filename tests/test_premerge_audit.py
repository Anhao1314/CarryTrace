"""Regressions for the pre-merge authority / relation / CLI audit."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from test_pipeline import ROOT, RENDER, LINT, EXAMPLE, run, report, conv

sys.path.insert(0, str(ROOT / 'scripts'))
from memory_identity import prepare, validate, json_text
from render_notes import safe_filename
MIGRATE = ROOT / 'scripts/migrate_memory.py'
QUERY = ROOT / 'scripts/query_memory.py'


class AuditTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.vault = self.root / 'vault'; self.vault.mkdir()
        self.base = self.vault / '对话沉淀'
        self.input = self.root / 'input.json'
        self.data, _ = prepare(json.loads(EXAMPLE.read_text(encoding='utf-8')), safe_filename)

    def write_source(self, data=None):
        self.input.write_text(json_text(data or self.data), encoding='utf-8')

    def render(self):
        self.write_source()
        proc = run(RENDER, '--distill', self.input, '--vault', self.vault)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return report(proc)

    def file(self, rel, text='# External document\n'):
        path = self.vault / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def assert_consumers_reject_drift(self):
        before = {p.relative_to(self.vault): p.read_bytes() for p in self.vault.rglob('*') if p.is_file()}
        out = run(RENDER, '--distill', self.input, '--vault', self.vault)
        self.assertEqual(out.returncode, 1, out.stdout)
        self.assertIn('identity', out.stdout)
        query = run(QUERY, '--vault', self.vault, '--query', '备份')
        self.assertEqual(query.returncode, 1, query.stdout)
        self.assertEqual(report(query)['results'], [])
        lint_proc = run(LINT, '--vault', self.vault)
        self.assertEqual(lint_proc.returncode, 1)
        lint = report(lint_proc)
        self.assertFalse(lint['ok'])
        self.assertTrue(lint['structure_issues'])
        self.assertEqual(before, {p.relative_to(self.vault): p.read_bytes() for p in self.vault.rglob('*') if p.is_file()})

    def test_mixed_internal_and_external_relations_render_and_lint(self):
        external = self.file('Research/C99 - External.md')
        original = external.read_bytes()
        a, b = self.data['conversations'][0]['cards']
        a.update(related=[b['memory_id']], external_related=['Research/C99 - External.md'])
        out = self.render()
        self.assertEqual(out['dead_links'], [])
        note = (self.base / '知识卡片' / (a['note_name'] + '.md')).read_text(encoding='utf-8')
        self.assertIn('[[' + b['note_name'] + ']]', note)
        self.assertIn('[[Research/C99 - External]]', note)
        self.assertIn('external_related:', note)
        self.assertEqual(external.read_bytes(), original)
        self.assertEqual(len(self.data['identity_registry']), 7)
        self.assertEqual(report(run(LINT, '--vault', self.vault))['structure_issues'], [])
        rows = [json.loads(line) for line in (self.base/'知识索引.jsonl').read_text(encoding='utf-8').splitlines()]
        row = next(r for r in rows if r['memory_id'] == a['memory_id'])
        self.assertEqual(row['related'], [b['memory_id']])
        self.assertEqual(row['external_related'], ['Research/C99 - External.md'])

    def test_external_names_preserve_literal_quotes(self):
        for name in ('Study "A"', 'Topic: "B"'):
            self.file(name + '.md')
        self.data['conversations'][0]['external_related'] = ['Study "A"', 'Topic: "B"']
        self.render()
        self.assertEqual(report(run(LINT, '--vault', self.vault))['structure_issues'], [])

    def test_legacy_external_numbered_note_is_not_given_identity(self):
        external = self.file('C99 - External.md')
        legacy = dict(conversations=[conv('A', related=['C99 - External'], cards=[dict(title='内存', body='正文')])])
        self.write_source(legacy)
        proc = run(RENDER, '--distill', self.input, '--vault', self.vault)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        destination = self.root / 'v2.json'
        proc = run(MIGRATE, '--mode', 'upgrade', '--distill', self.input, '--vault', self.vault, '--out', destination)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        result = json.loads(destination.read_text(encoding='utf-8'))
        self.assertEqual(result['conversations'][0]['related'], [])
        self.assertEqual(result['conversations'][0]['external_related'], ['C99 - External'])
        self.assertEqual(len(result['identity_registry']), 2)
        self.assertNotIn('memory_id', external.read_text(encoding='utf-8'))
        self.assertEqual(len(report(proc)['external_relations']), 1)

    def test_legacy_internal_path_maps_to_identity(self):
        data = dict(conversations=[conv('A', cards=[dict(title='first'), dict(title='second', related=['对话沉淀/知识卡片/C01 - first'])])])
        result, _ = prepare(data, safe_filename)
        a, b = result['conversations'][0]['cards']
        self.assertEqual(b['related'], [a['memory_id']])

    def test_external_note_name_cannot_be_used_as_internal_id(self):
        self.data['conversations'][0]['related'] = ['Research Note']
        with self.assertRaisesRegex(ValueError, 'dangling'):
            validate(self.data)

    def test_managed_memory_cannot_be_disguised_as_external_path(self):
        self.render()
        a, b = self.data['conversations'][0]['cards']
        a['external_related'] = ['对话沉淀/知识卡片/' + b['note_name']]
        self.write_source()
        out = run(RENDER, '--distill', self.input, '--vault', self.vault)
        self.assertEqual(out.returncode, 1)
        self.assertIn('managed memory', out.stdout)

    def test_missing_external_target_reported_by_lint(self):
        external = self.file('Research/Reference.md')
        self.data['conversations'][0]['external_related'] = ['Research/Reference']
        self.render(); external.unlink()
        issues = report(run(LINT, '--vault', self.vault))['structure_issues']
        self.assertTrue(any(i['kind'] == 'external_link' and 'missing' in i['detail'] for i in issues))

    def test_ambiguous_external_basename_requires_path(self):
        self.file('A/Reference.md'); self.file('B/Reference.md')
        self.data['conversations'][0]['external_related'] = ['Reference']
        self.write_source()
        out = run(RENDER, '--distill', self.input, '--vault', self.vault)
        self.assertEqual(out.returncode, 1)
        self.assertIn('ambiguous', out.stdout)
        self.assertFalse((self.base/'.chat-distiller').exists())
        self.data['conversations'][0]['external_related'] = ['A/Reference']
        self.assertEqual(self.render()['dead_links'], [])

    def test_migration_refuses_ambiguous_external_basename(self):
        self.file('A/Reference.md'); self.file('B/Reference.md')
        legacy = dict(conversations=[conv('a', related=['Reference'])])
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            prepare(legacy, safe_filename, self.vault)

    def test_vault_mirror_drift_never_silently_overwritten(self):
        self.render()
        path = self.base/'.chat-distiller/identity-registry.json'
        value = json.loads(path.read_text(encoding='utf-8'))
        next(iter(value.values()))['active'] = False
        path.write_text(json_text(value), encoding='utf-8')
        self.assert_consumers_reject_drift()

    def test_published_source_object_drift_never_silently_overwritten(self):
        self.render()
        path = self.base/'.chat-distiller/distill.json'
        value = json.loads(path.read_text(encoding='utf-8'))
        value['conversations'][0]['display_id'] = 'S99'
        path.write_text(json_text(value), encoding='utf-8')
        self.assert_consumers_reject_drift()

    def test_published_embedded_registry_drift_is_rejected(self):
        self.render()
        path = self.base/'.chat-distiller/distill.json'
        value = json.loads(path.read_text(encoding='utf-8'))
        cv = value['conversations'][0]
        cv['display_id'] = 'S99'; cv['note_name'] = 'S99 - changed'
        value['identity_registry'][cv['memory_id']].update(display_id='S99', note_name='S99 - changed')
        path.write_text(json_text(value), encoding='utf-8')
        self.assert_consumers_reject_drift()

    def test_published_note_display_drift_is_rejected(self):
        self.render()
        path = next((self.base/'知识卡片').glob('C01*.md'))
        path.write_text(path.read_text(encoding='utf-8').replace('display_id: C01', 'display_id: C99'), encoding='utf-8')
        self.assert_consumers_reject_drift()

    def test_published_snapshot_missing_is_rejected(self):
        self.render()
        (self.base/'.chat-distiller/distill.json').unlink()
        self.assert_consumers_reject_drift()

    def test_candidate_coherent_identity_reassignment_is_rejected(self):
        self.render()
        cv = self.data['conversations'][0]
        cv.update(display_id='S99', note_name='S99 - changed')
        self.data['identity_registry'][cv['memory_id']].update(display_id='S99', note_name='S99 - changed')
        self.write_source()
        out = run(RENDER, '--distill', self.input, '--vault', self.vault)
        self.assertEqual(out.returncode, 1)
        self.assertIn('registry history', out.stdout)

    def test_register_does_not_repair_missing_source_identity(self):
        del self.data['conversations'][0]['cards'][0]['source_memory_id']
        with self.assertRaisesRegex(ValueError, 'source_memory_id'):
            prepare(self.data, safe_filename)

    def test_register_does_not_reallocate_partial_identity(self):
        del self.data['conversations'][0]['cards'][0]['memory_id']
        with self.assertRaisesRegex(ValueError, 'partial identity'):
            prepare(self.data, safe_filename)

    def test_register_checks_published_copies_before_writing(self):
        self.render()
        (self.base/'.chat-distiller/identity-registry.json').write_text('{}', encoding='utf-8')
        dest = self.root/'registered.json'
        out = run(MIGRATE, '--mode', 'register', '--distill', self.input, '--vault', self.vault, '--out', dest)
        self.assertEqual(out.returncode, 1)
        self.assertFalse(dest.exists())

    def test_init_mode_does_not_require_existing_vault(self):
        dest = self.root/'initialized.json'
        out = run(MIGRATE, '--mode', 'init', '--distill', EXAMPLE, '--out', dest)
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertEqual(report(out)['operation'], 'init')
        self.assertTrue(dest.exists())
        self.assertFalse(self.base.exists())

    def test_upgrade_requires_existing_vault_argument(self):
        out = run(MIGRATE, '--mode', 'upgrade', '--distill', EXAMPLE, '--dry-run')
        self.assertEqual(out.returncode, 1)
        self.assertIn('--vault', out.stdout)

    def test_incompatible_mode_is_rejected(self):
        self.write_source()
        for mode in ('init', 'upgrade'):
            out = run(MIGRATE, '--mode', mode, '--distill', self.input, '--dry-run')
            self.assertEqual(out.returncode, 1)
        out = run(MIGRATE, '--mode', 'register', '--distill', EXAMPLE, '--dry-run')
        self.assertEqual(out.returncode, 1)

    def test_mode_omission_remains_compatible(self):
        out = run(MIGRATE, '--distill', EXAMPLE, '--dry-run')
        self.assertEqual(out.returncode, 0)
        self.assertEqual(report(out)['operation'], 'init')


class IntentAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT/'benchmarks'))
        from evaluate import evaluate
        cls.result = evaluate(ROOT/'benchmarks/fixtures')

    def test_fixture_fingerprint_unchanged(self):
        self.assertEqual(self.result['fixture_sha256'], '94aaade788c6ff76ffe19d8ade10b25473700fc680cc58e7fab7895a9d7d2579')

    def test_intents_cover_all_queries_once(self):
        ids = [i for group in self.result['per_intent'].values() for i in group['case_ids']]
        self.assertEqual(len(ids), 24)
        self.assertEqual(len(set(ids)), 24)
        self.assertEqual(set(self.result['per_intent']), {'current-state', 'historical/superseded', 'conflict/controversial', 'cross-session', 'compaction-recovery'})

    def test_current_recall_and_contamination_are_explicit(self):
        group = self.result['per_intent']['current-state']
        self.assertEqual(group['query_count'], 5)
        self.assertEqual(group['methods']['Status-aware Memory']['current_memory_recall'], {'Recall@1':1, 'Recall@3':1, 'Recall@5':1})
        self.assertEqual(group['methods']['Status-aware Memory']['stale_contamination']['@5'], 0)

    def test_history_enabled_does_not_claim_expired_target_recall(self):
        group = self.result['per_intent']['historical/superseded']
        self.assertEqual(group['expected_expired_query_count'], 0)
        self.assertIsNone(group['expired_target_recall'])
        self.assertEqual(group['noncurrent_enabled']['metrics'], group['methods']['Structured Memory']['metrics'])

    def test_conflict_failure_not_hidden(self):
        group = self.result['per_intent']['conflict/controversial']['methods']
        self.assertEqual(group['Status-aware Memory']['expected_controversial_recall']['@5'], .5)
        self.assertEqual(group['Structured Memory']['expected_controversial_recall']['@5'], 1)

    def test_aggregate_metrics_remain_unchanged(self):
        expected = {'Baseline':(.416667,.875,.958333,.652778),
                    'Structured Memory':(.541667,.958333,1,.760417),
                    'Status-aware Memory':(.708333,.875,.916667,.793056)}
        for name, values in expected.items():
            metrics = self.result['results'][name]['metrics']
            self.assertEqual(tuple(metrics[k] for k in ('Recall@1','Recall@3','Recall@5','MRR')), values)
