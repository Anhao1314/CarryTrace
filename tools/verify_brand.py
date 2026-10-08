#!/usr/bin/env python3
"""Installed-wheel CarryTrace/legacy integration. Synthetic data; no live Agent."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

import chat_distiller
from chat_distiller.brand_skill import bundle_files

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path(chat_distiller.__file__).resolve()
if ROOT in PACKAGE.parents:
    raise RuntimeError('brand smoke must import the installed wheel, not the checkout')
checks = []


def require(value, name):
    if not value:
        raise AssertionError(name)
    checks.append(name)


def snapshot(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


with tempfile.TemporaryDirectory(prefix='carrytrace-brand-check-') as temp:
    root = Path(temp); project = root / 'project'; project.mkdir()
    sessions = root / '.sessions'
    system = sessions / 'db/agents/agent-1/system'; system.mkdir(parents=True)
    (system / 'assignment.md').write_text('## [2026-10-01T01:00:00Z] 需求\n\nDatabase migration.\n', encoding='utf-8')
    (system / 'trajectory.jsonl').write_text(json.dumps({'role': 'assistant', 'content': 'Use PostgreSQL; preserve API v1.'}) + '\n', encoding='utf-8')
    home = root / 'context'
    def run(name, *args, expected=0):
        entry = Path(sys.executable).with_name(name + ('.exe' if os.name == 'nt' else ''))
        p = subprocess.run([str(entry), *map(str,args)], cwd=root, capture_output=True, text=True, timeout=45)
        if p.returncode != expected:
            raise AssertionError(f'{name} {args}: exit {p.returncode}\n{p.stdout}\n{p.stderr}')
        return p.stdout
    require('chat-distiller' in run('chat-distiller', '--version'), 'legacy entry still installed')
    require('CarryTrace' in run('carrytrace', '--version'), 'new branded entry installed')
    run('chat-distiller', 'connect', 'doubao', '--sessions-root', sessions, '--home', home, '--json')
    run('chat-distiller', 'sync', '--home', home, '--json')
    before_source, before_home = snapshot(sessions), snapshot(home)
    for args in (('status', '--home', home, '--json'),
                 ('context', 'PostgreSQL', '--home', home, '--json')):
        require(run('carrytrace', *args) == run('chat-distiller', *args), 'both entry points emit identical ' + args[0] + ' JSON')
    require(snapshot(home) == before_home, 'alias reads do not mutate legacy context home')
    scope = ('--host', 'both', '--scope', 'project', '--project-dir', project, '--json')
    run('chat-distiller', 'skill', 'install', *scope)
    originals = snapshot(project)
    preview = json.loads(run('carrytrace', 'skill', 'migrate', *scope))
    require(preview['dry_run'] and snapshot(project) == originals, 'migration previews without writes')
    result = json.loads(run('carrytrace', 'skill', 'migrate', *scope, '--apply'))
    receipt = json.loads(Path(result['receipt']).read_text())
    require(receipt['phase'] == 'committed', 'migration commits and retains receipt')
    for entry in receipt['entries']:
        require(not Path(entry['legacy_path']).exists(), 'legacy active alias removed from ' + entry['host'])
        dest = Path(entry['destination'])
        require((dest / 'SKILL.md').read_bytes() == bundle_files()['SKILL.md'], 'new ' + entry['host'] + ' Skill matches wheel')
        backup = Path(entry['backup'])
        prefix = ('.agents' if entry['host'] == 'codex' else '.claude') + '/skills/chat-distiller/'
        expected = {name[len(prefix):]: value for name, value in originals.items() if name.startswith(prefix)}
        require(snapshot(backup) == expected, entry['host'] + ' original instruction bytes preserved')
    migrated = snapshot(project)
    run('carrytrace', 'skill', 'migrate', *scope, '--apply')
    require(snapshot(project) == migrated, 'repeat migration is no-op')
    require(not json.loads(run('chat-distiller', 'skill', 'install', *scope, expected=1))['ok'], 'legacy installer cannot create duplicate active alias')
    one, two = root / 'one.zip', root / 'two.zip'
    run('carrytrace', 'skill', 'export', '--out', one, '--json')
    run('carrytrace', 'skill', 'export', '--out', two, '--json')
    require(one.read_bytes() == two.read_bytes(), 'CarryTrace ZIP is deterministic')
    with zipfile.ZipFile(one) as z:
        require(set(z.namelist()) == {'carrytrace/' + p for p in bundle_files()}, 'ZIP root matches new Skill name')
    require(snapshot(sessions) == before_source and snapshot(home) == before_home, 'instruction migration does not touch source or memory data')

print(json.dumps({'ok': True, 'runtime_version': chat_distiller.__version__,
                  'checks_passed': len(checks), 'checks': checks,
                  'scope': 'installed-wheel CLI/synthetic local context; no real host activation'}, indent=2))
