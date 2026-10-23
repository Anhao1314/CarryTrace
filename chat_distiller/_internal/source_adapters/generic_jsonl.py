"""Strict public JSONL adapter. Validate entire input before writing staging files."""
import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from .transcript import CN_TZ, clean_text, slug_preview, build_transcript, write_index


def read_records(path):
    sessions = {}
    with open(path, encoding='utf-8') as f:
        for number, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError('record must be an object')
                sid = row.get('session_id')
                if not isinstance(sid, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,119}', sid):
                    raise ValueError('session_id must be 1-120 safe ASCII filename characters, starting with a letter/digit')
                if row.get('role') not in {'user', 'assistant', 'tool', 'system'}:
                    raise ValueError('role must be user/assistant/tool/system')
                if not isinstance(row.get('content'), str):
                    raise ValueError('content must be a string')
                ts = row.get('timestamp')
                if not isinstance(ts, str):
                    raise ValueError('timestamp must be an ISO 8601 string with timezone')
                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    raise ValueError('timestamp requires timezone')
                sessions.setdefault(sid, []).append((dt, number, row))
            except (ValueError, TypeError) as exc:
                raise ValueError(f'{path}: line {number}: {exc}') from exc
    if not sessions:
        raise ValueError(f'{path}: no records')
    return sessions


def extract(path, out, only=''):
    sessions = read_records(path)
    if only and only not in sessions:
        raise ValueError('session_id not found: ' + only)
    out = Path(out)
    records = []
    for sid in sorted(sessions):
        if only and sid != only:
            continue
        messages = sorted(sessions[sid], key=lambda x: (x[0], x[1]))
        turns, replies = [], []
        for dt, _, row in messages:
            if row['role'] in {'system', 'tool'}:
                continue
            txt = clean_text(row['content'])
            if not txt:
                continue
            if row['role'] == 'user':
                turns.append((dt.isoformat(), dt.astimezone(CN_TZ).strftime('%Y-%m-%d %H:%M'), txt))
            else:
                replies.append(txt)
        created, updated = [messages[i][0].astimezone(CN_TZ).strftime('%Y-%m-%d %H:%M') for i in (0, -1)]
        md = build_transcript(sid, created, updated, turns, replies, [], ['generic'], 0, 'generic_jsonl/' + sid, [])
        target = out / 'transcripts' / (sid + '.transcript.md')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(md, encoding='utf-8')
        records.append(dict(session_id=sid, created=created, updated=updated,
                            first_request=slug_preview(turns[0][2]) if turns else '',
                            user_turns=len(turns), assistant_replies=len(replies),
                            chars=sum(len(t[2]) for t in turns)+sum(map(len, replies)),
                            agents=['generic'], degraded=[], transcript='transcripts/' + target.name,
                            empty=not turns and not replies))
    write_index(records, str(out))
    return records


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--only', default='')
    args = ap.parse_args()
    try:
        records = extract(args.input, args.out, args.only)
        print(json.dumps(dict(ok=True, source='generic_jsonl', total=len(records),
                              total_chars=sum(r['chars'] for r in records)), ensure_ascii=False))
        return 0
    except (OSError, ValueError) as exc:
        print(json.dumps(dict(ok=False, error=str(exc)), ensure_ascii=False))
        return 1
