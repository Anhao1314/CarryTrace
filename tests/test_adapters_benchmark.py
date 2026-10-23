import json
import sys
import tempfile
import unittest
from pathlib import Path
from test_pipeline import ROOT, EXTRACT, run
import test_pipeline

sys.path.insert(0, str(ROOT / 'scripts'))
from source_adapters.generic_jsonl import extract
sys.path.insert(0, str(ROOT / 'benchmarks'))
from evaluate import evaluate, load_fixtures, metrics


class AdapterTests(unittest.TestCase):
    def records(self):
        return [dict(session_id='session-1', timestamp='2026-01-01T00:00:00Z', role='user', content='需求'),
                dict(session_id='session-1', timestamp='2026-01-01T00:00:00Z', role='assistant', content='结论')]

    def test_generic_equivalent_message_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); source = base/'source.jsonl'
            source.write_text('\n'.join(json.dumps(r) for r in self.records()), encoding='utf-8')
            generic = base/'generic'
            self.assertEqual(run(EXTRACT, '--source', 'generic_jsonl', '--input', source, '--out', generic).returncode, 0)
            test_pipeline.ExtractTests.make_session(base/'sessions', 'session-1', assignment='## [2026-01-01T00:00:00Z] 需求\n需求\n', trajectory=json.dumps(dict(role='assistant', content='结论')))
            self.assertEqual(run(EXTRACT, '--source', 'doubao_work', '--sessions-root', base/'sessions', '--out', base/'doubao').returncode, 0)
            a = (generic/'transcripts/session-1.transcript.md').read_text(encoding='utf-8')
            b = (base/'doubao/transcripts/session-1.transcript.md').read_text(encoding='utf-8')
            self.assertEqual(a.split('## 一、')[1], b.split('## 一、')[1])

    def test_malformed_record_line_error_no_partial_write(self):
        bad = [dict(content=None),dict(role='unknown'),dict(session_id='../escape'),dict(timestamp='yesterday'),dict(timestamp='2026-01-01T00:00:00')]
        for over in bad:
            with self.subTest(over=over), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp); source = base/'source.jsonl'
                rows = self.records(); rows[1].update(over)
                source.write_text('\n'.join(json.dumps(r) for r in rows), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'line 2'):
                    extract(source, base/'out')
                self.assertFalse((base/'out').exists())

    def test_generic_discards_tool_and_system_noise(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); source = base/'source.jsonl'
            rows = self.records()+[dict(self.records()[0],role=role,content='SECRET_NOISE') for role in ['tool','system']]
            source.write_text('\n'.join(json.dumps(r) for r in rows), encoding='utf-8')
            extract(source, base/'out')
            self.assertNotIn('SECRET_NOISE', (base/'out/transcripts/session-1.transcript.md').read_text(encoding='utf-8'))

    def test_generic_repeat_is_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp); source=base/'source.jsonl'
            source.write_text('\n'.join(json.dumps(r) for r in self.records()), encoding='utf-8')
            extract(source,base/'out')
            before={p.name:p.read_bytes() for p in (base/'out').rglob('*') if p.is_file()}
            extract(source,base/'out')
            self.assertEqual(before,{p.name:p.read_bytes() for p in (base/'out').rglob('*') if p.is_file()})


class BenchmarkTests(unittest.TestCase):
    def test_fixtures_valid_expected_ids_exist(self):
        data, cases, raw = load_fixtures(ROOT/'benchmarks/fixtures')
        self.assertEqual(len(cases),24)
        self.assertEqual(len(raw),40)
        self.assertEqual(len({c['scenario'] for c in cases}),6)

    def test_deterministic_and_saved_results_match(self):
        a=evaluate(ROOT/'benchmarks/fixtures'); b=evaluate(ROOT/'benchmarks/fixtures')
        self.assertEqual(a,b)
        self.assertEqual(a,json.loads((ROOT/'benchmarks/benchmark-results.json').read_text(encoding='utf-8')))

    def test_result_schema_and_status_metrics(self):
        result=evaluate(ROOT/'benchmarks/fixtures')
        self.assertEqual(result['schema_version'],1)
        self.assertEqual(set(result['results']),{'Baseline','Structured Memory','Status-aware Memory'})
        for run in result['results'].values():
            self.assertEqual(len(run['metrics']),10)
            self.assertEqual(len(run['cases']),24)
        self.assertEqual(result['results']['Status-aware Memory']['metrics']['stale-hit@5'],0)

    def test_metric_arithmetic(self):
        runs=[dict(ids=['old','good'],expected=['good']),dict(ids=[],expected=['good'])]
        result=metrics(runs,{'old':'已过期','good':'现行'})
        self.assertEqual(result['Recall@1'],0)
        self.assertEqual(result['Recall@3'],.5)
        self.assertEqual(result['MRR'],.25)
        self.assertEqual(result['stale-hit@1'],.5)
