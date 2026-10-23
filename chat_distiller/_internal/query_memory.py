#!/usr/bin/env python3
"""Offline deterministic lexical/structured lookup; not semantic retrieval."""
import argparse
import json
import math
import re
import sys
from pathlib import Path
from .memory_identity import json_text, load_published_source, note_identity_issues


def features(text):
    text = str(text).lower()
    out = set(re.findall(r'[a-z0-9]+', text))
    for run in re.findall(r'[\u3400-\u9fff]+', text):
        out.update(run[i:i+2] for i in range(len(run)-1))
        if len(run) == 1:
            out.add(run)
    return out


def lexical_score(query, row, structured=True):
    q = features(query)
    if not q:
        return 0.0
    fields = {'title': 4, 'body': 1, 'tags': 3, 'categories': 2, 'kind': .5} if structured else {'text': 1}
    score = 0.0
    for field, weight in fields.items():
        value = row.get(field, '')
        if isinstance(value, list):
            value = ' '.join(value)
        f = features(value)
        # Set overlap: repetition/tool retries do not increase a term's weight.
        score += weight * len(q & f) / math.sqrt(max(1, len(f)))
    return round(score, 8)


def search(rows, query, top_k=5, include_noncurrent=False, kind=None, category=None):
    if not 1 <= top_k <= 100:
        raise ValueError('top-k must be between 1 and 100')
    if not features(query):
        return []
    candidates = []
    for row in rows:
        if row.get('type') != 'card':
            continue  # Session summaries may contain stale claims without claim-level status.
        status = row.get('status')
        if status not in {'现行', '已过期', '有争议'}:
            raise ValueError('unknown status in index')
        if not include_noncurrent and status == '已过期':
            continue
        if kind and row.get('kind') != kind:
            continue
        if category and category not in row.get('categories', []):
            continue
        score = lexical_score(query, row)
        if score > 0:
            candidates.append((row, score))
    candidates.sort(key=lambda x: (0 if include_noncurrent or x[0]['status'] == '现行' else 1,
                                   -x[1], x[0]['memory_id']))
    return [dict(memory_id=r['memory_id'], display_id=r['display_id'], title=r['title'],
                 kind=r['kind'], status=r['status'], disputed=r['status'] == '有争议',
                 categories=r['categories'], source_session=r['source_session'],
                 source_memory_id=r['source_memory_id'], path=r['file'], score=s,
                 short_excerpt=r.get('body', '')[:240], superseded_by=r.get('superseded_by'))
            for r, s in candidates[:top_k]]


def load_index(base):
    """Reject stale/corrupt derived state instead of silently retrieving from it."""
    base = Path(base)
    data = load_published_source(base)
    if data is None:
        raise ValueError('stable source missing: initialize identity or upgrade legacy memory, then render')
    problems = note_identity_issues(base, data)
    if problems:
        raise ValueError('; '.join(problems))
    rows = [json.loads(line) for line in (base / '知识索引.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    # Use the same deterministic index builder, without filesystem writes.
    from .render_notes import Renderer, build_plan
    renderer = Renderer(str(base.parent), base.name, [], [], dry=True)
    captured = {}
    renderer._write = lambda path, text: captured.update({path: text})
    plan = build_plan(data['conversations'], renderer)
    names = {cv['session_id']: cv['note_name'] for cv in data['conversations']}
    renderer.render_index(plan, names)
    expected = [json.loads(line) for line in captured['知识索引.jsonl'].splitlines()]
    if rows != expected:
        raise ValueError('memory index differs from source; rerender before querying')
    for row in rows:
        path = base / row['file']
        if not path.is_file():
            raise ValueError(f"indexed note missing: {row['file']}")
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--vault', required=True)
    ap.add_argument('--subdir', default='对话沉淀')
    ap.add_argument('--query', required=True)
    ap.add_argument('--top-k', type=int, default=5)
    ap.add_argument('--include-noncurrent', action='store_true', help='Historical analysis: lexical ranking across all statuses')
    ap.add_argument('--kind')
    ap.add_argument('--category')
    args = ap.parse_args()
    try:
        result = search(load_index(Path(args.vault) / args.subdir), args.query, args.top_k,
                        args.include_noncurrent, args.kind, args.category)
        print(json_text(dict(ok=True, method='deterministic-lexical-structured', results=result)))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json_text(dict(ok=False, error=str(exc), results=[])))
        return 1


if __name__ == '__main__':
    sys.exit(main())
