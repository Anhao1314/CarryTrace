#!/usr/bin/env python3
"""Initialize identity (--mode init), upgrade legacy memory (--mode upgrade), or register additions (--mode register)."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from .memory_identity import (prepare, stable, validate, atomic_write, json_text,
                             load_published_source, note_identity_issues)
from .render_notes import safe_filename, duplicate_session_ids


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--distill', required=True)
    ap.add_argument('--mode', choices=['init', 'upgrade', 'register'], help='init: first allocation for new source; upgrade: v1 existing vault (requires --vault); register: v2 additions. Omit for compatible auto detection.')
    ap.add_argument('--out', help='Explicit destination; may equal source after backup')
    ap.add_argument('--vault', help='Existing vault: verify legacy render matches before migration')
    ap.add_argument('--subdir', default='对话沉淀')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--report', help='Optional report file (not written during dry-run)')
    args = ap.parse_args()
    try:
        if args.report and Path(args.report).resolve() in {Path(args.distill).resolve(), Path(args.out or args.distill).resolve()}:
            raise ValueError('--report must differ from source and destination')
        data = json.loads(Path(args.distill).read_text(encoding='utf-8'))
        mode = args.mode or ('register' if stable(data) else ('upgrade' if args.vault else 'init'))
        if mode == 'init' and (stable(data) or args.vault):
            raise ValueError('init is for a new source without --vault; use upgrade or register')
        if mode == 'upgrade' and (stable(data) or not args.vault):
            raise ValueError('upgrade requires a legacy source and --vault; use init for a new source')
        if mode == 'register' and not stable(data):
            raise ValueError('register requires v2; use init or upgrade first')
        published = load_published_source(Path(args.vault) / args.subdir) if args.vault else None
        if published is not None:
            problems = note_identity_issues(Path(args.vault) / args.subdir, published)
            if problems:
                raise ValueError('; '.join(problems))
        if duplicate_session_ids(data.get('conversations', [])):
            raise ValueError('duplicate/missing session_id')
        if not args.dry_run and not args.out:
            raise ValueError('--out is required; source is never implicitly rewritten')
        if args.vault and not stable(data):
            proc = subprocess.run([sys.executable, str(Path(__file__).with_name('render_notes.py')),
                                   '--distill', args.distill, '--vault', args.vault, '--subdir', args.subdir, '--dry-run'],
                                  capture_output=True, text=True)
            check = json.loads(proc.stdout)
            if proc.returncode or check.get('created') or check.get('updated') or check.get('orphans') or check.get('dead_links'):
                raise ValueError('legacy source does not exactly match vault; restore matching source or resolve drift/orphans/links before migration')
        out, report = prepare(data, safe_filename, args.vault, args.subdir)
        if args.vault and not stable(data):
            base = Path(args.vault) / args.subdir
            out["migration_baseline"] = {str(p.relative_to(base)): hashlib.sha256(p.read_bytes()).hexdigest()
                for folder in ("会话笔记", "知识卡片") for p in sorted((base / folder).glob("*.md"))}
        if published is not None:
            validate(out, published['identity_registry'])
        report.update(ok=True, operation=mode, dry_run=args.dry_run, changed=out != data,
                      note='UUIDs in dry-run are provisional; only persisted output establishes identity.')
        if not args.dry_run:
            dest = Path(args.out)
            if dest.exists() and dest.resolve() != Path(args.distill).resolve() and dest.read_text(encoding='utf-8') != json_text(out):
                raise ValueError('destination exists with different content; choose a new --out')
            atomic_write(dest, json_text(out))
            if args.report:
                atomic_write(args.report, json_text(report))
        print(json_text(report))
        return 0
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print(json_text(dict(ok=False, error=str(exc))))
        return 1


if __name__ == '__main__':
    sys.exit(main())
