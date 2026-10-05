"""Stable identity invariants; no semantic matching or content-derived IDs."""
import copy
import json
import re
import uuid
from pathlib import Path

ID_RE = re.compile(r"mem_[0-9a-f]{32}\Z")
STATUSES = {"现行", "已过期", "有争议"}


def objects(data):
    for conv in data.get("conversations", []):
        yield conv, "conversation", conv
        if conv.get("threads") and conv.get("cards"):
            raise ValueError("cards and threads cannot both contain cards")
        for seg in conv.get("threads") or [conv]:
            for card in seg.get("cards") or []:
                yield card, "card", conv


def stable(data):
    return data.get("schema_version") == 2


def validate(data, previous=None):
    if not stable(data):
        if data.get("schema_version") is not None or any("memory_id" in o for o, _, _ in objects(data)):
            raise ValueError("mixed/unknown schema: run migrate_memory.py explicitly")
        return
    registry = data.get("identity_registry")
    if not isinstance(registry, dict):
        raise ValueError("missing identity_registry")
    displays, paths = set(), set()
    internal_names = {r['note_name'] for r in registry.values()}
    for mid, rec in registry.items():
        if not ID_RE.fullmatch(mid):
            raise ValueError(f"invalid memory_id: {mid}")
        prefix = "S" if rec.get("type") == "conversation" else "C"
        if rec.get("type") not in {"conversation", "card"} or not re.fullmatch(prefix + r"[0-9]{2,}", rec.get("display_id", "")):
            raise ValueError(f"invalid display_id/type: {mid}")
        name = rec.get("note_name", "")
        if not name.startswith(rec["display_id"] + " - ") or any(c in name for c in '/\\\n\r') or not isinstance(rec.get("active"), bool):
            raise ValueError(f"invalid registry path/state: {mid}")
        if rec["display_id"] in displays or name.casefold() in paths:
            raise ValueError(f"display ID/path collision: {mid}")
        displays.add(rec["display_id"])
        paths.add(name.casefold())
    seen, sessions = set(), set()
    for obj, kind, conv in objects(data):
        mid = obj.get("memory_id")
        if mid in seen:
            raise ValueError(f"duplicate memory_id: {mid}")
        seen.add(mid)
        rec = registry.get(mid)
        if not rec or not rec["active"] or rec["type"] != kind:
            raise ValueError(f"missing/inactive registry identity: {mid}")
        if any(obj.get(k) != rec[k] for k in ("display_id", "note_name")):
            raise ValueError(f"registry inconsistency: {mid}")
        if rec.get("session_id") != conv.get("session_id"):
            raise ValueError(f"source session changed: {mid}")
        if kind == "conversation":
            sid = conv.get("session_id")
            if not isinstance(sid, str) or not sid.strip() or sid in sessions:
                raise ValueError("duplicate/missing session_id")
            sessions.add(sid)
        if kind == "card":
            if obj.get("source_memory_id") != conv.get("memory_id"):
                raise ValueError(f"broken source_memory_id: {mid}")
            if obj.get("status", "现行") not in STATUSES:
                raise ValueError(f"invalid status: {mid}")
        related = obj.get("related", [])
        if not isinstance(related, list):
            raise ValueError(f"related must be a list: {mid}")
        for ref in related + ([obj["superseded_by"]] if obj.get("superseded_by") else []):
            target = registry.get(ref)
            if not target or not target["active"]:
                raise ValueError(f"dangling stable relation: {mid} -> {ref}")
            if ref == mid:
                raise ValueError(f"self relation: {mid}")
        if obj.get("superseded_by"):
            if registry[obj["superseded_by"]]["type"] != "card" or obj.get("status", "现行") != "已过期":
                raise ValueError(f"supersession requires expired card and card target: {mid}")
        ext = obj.get("external_related", [])
        if not isinstance(ext, list) or any(not isinstance(x, str) or x.startswith("mem_") or (x[:-3] if x.endswith(".md") else x) in internal_names for x in ext):
            raise ValueError(f"internal relation disguised as external: {mid}")
    if seen != {m for m, r in registry.items() if r["active"]}:
        raise ValueError("registry active set differs from source; run migrate_memory.py to register removals/additions")
    by_id = {o["memory_id"]: o for o, _, _ in objects(data)}
    for mid in by_id:
        chain, cursor = set(), mid
        while cursor and cursor in by_id:
            if cursor in chain:
                raise ValueError(f"supersession cycle: {mid}")
            chain.add(cursor)
            cursor = by_id[cursor].get("superseded_by")
    if previous:
        for mid, old in previous.items():
            rec = registry.get(mid)
            if not rec or any(rec.get(k) != old.get(k) for k in ("display_id", "note_name", "type", "session_id")):
                raise ValueError(f"registry history lost/changed: {mid}")
            if not old["active"] and rec["active"]:
                raise ValueError(f"retired identity cannot be reused: {mid}")


def prepare(data, filename, vault=None, subdir="对话沉淀"):
    """Explicit migration/registration; allocate once, persist returned document."""
    out = copy.deepcopy(data)
    legacy = not stable(out)
    if legacy:
        validate(out)
    reg = out.setdefault("identity_registry", {})
    previous = copy.deepcopy(reg)
    counters = {p: max([int(r["display_id"][1:]) for r in reg.values() if r["display_id"].startswith(p)] or [0]) for p in "SC"}
    aliases, added = {}, []
    bare_titles = {filename(o.get("title", "")) for o, _, _ in objects(out)}
    for obj, kind, conv in objects(out):
        mid = obj.get("memory_id")
        newly_allocated = not mid
        if newly_allocated and any(k in obj for k in ('display_id', 'note_name', 'source_memory_id')):
            raise ValueError('partial identity: missing memory_id on an existing projection; do not reallocate')
        if not mid:
            mid = "mem_" + uuid.uuid4().hex
            while mid in reg:
                mid = "mem_" + uuid.uuid4().hex
            p = "S" if kind == "conversation" else "C"
            counters[p] += 1
            display = f"{p}{counters[p]:02d}"
            name = f"{display} - {filename(obj.get('title') or (conv['session_id'] if kind == 'conversation' else '未命名卡片'))}"
            obj.update(memory_id=mid, display_id=display, note_name=name)
            reg[mid] = dict(display_id=display, note_name=name, type=kind, session_id=conv["session_id"], active=True)
            added.append(mid)
        elif mid not in reg:
            raise ValueError(f"unregistered supplied identity: {mid}")
        if kind == "card" and newly_allocated:
            obj["source_memory_id"] = conv["memory_id"]
        folder = '会话笔记' if kind == 'conversation' else '知识卡片'
        name = obj.get('note_name')
        for alias in (obj.get("display_id"), name, name + '.md',
                      f'{subdir}/{folder}/{name}', f'{subdir}/{folder}/{name}.md'):
            aliases.setdefault(alias, []).append(mid)
    active = {o["memory_id"] for o, _, _ in objects(out)}
    retired = []
    for mid, rec in reg.items():
        if mid not in active and rec["active"]:
            retired.append(mid)
            rec["active"] = False
    if legacy:
        def resolve(ref):
            matches = aliases.get(ref, [])
            if len(matches) != 1:
                raise ValueError(f"ambiguous/unresolved legacy relationship: {ref!r}")
            return matches[0]
        for obj, _, _ in objects(out):
            internal, external = [], list(obj.get("external_related", []))
            for ref in obj.get("related", []):
                targets = vault_link_paths(vault, ref) if vault else []
                if len(targets) > 1:
                    raise ValueError(f'ambiguous legacy relationship: {ref!r}; use vault-relative path')
                external_target = bool(targets and targets[0].parent not in
                    {Path(vault) / subdir / '会话笔记', Path(vault) / subdir / '知识卡片'})
                if ref in aliases:
                    if external_target:
                        raise ValueError(f'ambiguous legacy memory/external relationship: {ref!r}')
                    internal.append(resolve(ref))
                elif external_target:
                    external.append(ref)
                elif re.match(r"[SC]\d+", ref):
                    internal.append(resolve(ref))
                elif ref in bare_titles:
                    raise ValueError(f"ambiguous title-only legacy relationship: {ref!r}; use exact C/S filename")
                else:
                    external.append(ref)
            obj["related"] = internal
            if external:
                obj["external_related"] = external
            if obj.get("superseded_by"):
                obj["superseded_by"] = resolve(obj["superseded_by"])
    out["schema_version"] = 2
    validate(out, previous)
    if vault:
        problems = external_relation_issues(out, vault, subdir)
        if problems:
            raise ValueError('; '.join(problems))
    return out, {"legacy": legacy, "allocated": added, "retired": retired, "mapping": reg,
                 "external_relations": [{"memory_id": o["memory_id"], "targets": o['external_related']}
                                        for o, _, _ in objects(out) if o.get('external_related')]}


def json_text(data):
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    import os
    import tempfile
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".memory-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load_published_source(base):
    """The published source's embedded registry is authoritative; mirror must match exactly."""
    config = Path(base) / '.chat-distiller'
    source, mirror = config / 'distill.json', config / 'identity-registry.json'
    if not source.exists() and not mirror.exists():
        return None
    if not source.is_file() or not mirror.is_file():
        raise ValueError('identity drift: published source/registry missing; restore a consistent pair, do not rerender over it')
    data = json.loads(source.read_text(encoding='utf-8'))
    if not stable(data):
        raise ValueError('identity drift: published source is not v2')
    try:
        validate(data)
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError(f'identity drift in published source: {exc}') from exc
    if json.loads(mirror.read_text(encoding='utf-8')) != data['identity_registry']:
        raise ValueError('identity drift: vault registry differs from published source authority')
    return data


def note_identity_issues(base, data):
    """Compare existing note identity projections to their published source version."""
    from .lint_notes import parse_frontmatter
    issues = []
    reg = data['identity_registry']
    source_objects = {o['memory_id']: o for o, _, _ in objects(data)}
    expected_paths = {}
    for mid, rec in reg.items():
        folder = '会话笔记' if rec['type'] == 'conversation' else '知识卡片'
        expected_paths[Path(base) / folder / (rec['note_name'] + '.md')] = (mid, rec)
    actual = {p for folder in ('会话笔记', '知识卡片') for p in (Path(base) / folder).glob('*.md')}
    for path in sorted(actual | {p for p, (_, r) in expected_paths.items() if r['active']}):
        if path not in expected_paths:
            issues.append(f'identity drift: unregistered note {path.name}')
            continue
        mid, rec = expected_paths[path]
        if not path.is_file():
            issues.append(f'identity drift: note missing {path.name}')
            continue
        fm, _ = parse_frontmatter(path.read_text(encoding='utf-8'))
        fields = {'memory_id': mid, 'display_id': rec['display_id'], 'session_id': rec['session_id'],
                  'type': 'conversation-note' if rec['type'] == 'conversation' else 'atomic-card',
                  'sid' if rec['type'] == 'conversation' else 'cid': rec['display_id']}
        obj = source_objects.get(mid)
        if obj is not None:
            if rec['type'] == 'card':
                # Status/type projections must not contradict the published source.
                fields['status'] = str(obj.get('status') or '现行').strip() or '现行'
                fields['kind'] = (obj.get('kind') or 'fact').lower()
                fields['source_memory_id'] = obj['source_memory_id']
                fields['source'] = reg[obj['source_memory_id']]['note_name']
                fields['superseded_by'] = reg[obj['superseded_by']]['note_name'] if obj.get('superseded_by') else None
            # These relations are mutable in a candidate source, never in a rendered projection.
            fields['related_memory_ids'] = obj.get('related', [])
            fields['superseded_by_memory_id'] = obj.get('superseded_by')
        for key, expected in fields.items():
            value = fm.get(key, [] if isinstance(expected, list) else None)
            if value != expected:
                issues.append(f'identity drift: {path.name}: {key} differs from published source')
    return issues


def vault_link_paths(vault, ref):
    """Resolve a Markdown name or vault-relative path; never guess between duplicate basenames."""
    if not isinstance(ref, str) or not ref.strip() or ref != ref.strip() or any(c in ref for c in '\\[]#|\n\r'):
        raise ValueError(f'invalid external Markdown link: {ref!r}')
    part = Path(ref)
    if part.is_absolute() or '..' in part.parts or any(p.startswith('.') and p != part.name for p in part.parts):
        raise ValueError(f'external link must stay inside vault: {ref!r}')
    name = ref[:-3] if ref.endswith('.md') else ref
    if '/' in name:
        p = Path(vault) / (name + '.md')
        return [p] if p.is_file() else []
    return sorted(p for p in Path(vault).rglob('*.md')
                  if p.stem == name and not any(x.startswith('.') for x in p.relative_to(vault).parts))


def external_relation_issues(data, vault, subdir):
    """External notes have no fabricated IDs. Validate existence, ambiguity and management boundary."""
    from .lint_notes import parse_frontmatter
    problems = []
    base = Path(vault) / subdir
    managed = {base / ('会话笔记' if rec['type'] == 'conversation' else '知识卡片') / (rec['note_name'] + '.md')
               for rec in data.get('identity_registry', {}).values()}
    for obj, _, _ in objects(data):
        for ref in obj.get('external_related', []):
            try:
                paths = vault_link_paths(vault, ref)
                if not paths and ref in {'00 · 对话沉淀 MOC', f'{subdir}/00 · 对话沉淀 MOC'}:
                    continue  # Derived navigation will be rendered in this operation.
                if len(paths) != 1:
                    raise ValueError(f'external link {ref!r}: {"missing" if not paths else "ambiguous; use vault-relative path"}')
                fm, _ = parse_frontmatter(paths[0].read_text(encoding='utf-8'))
                if paths[0] in managed or fm.get('memory_id') or fm.get('type') in {'atomic-card', 'conversation-note'}:
                    raise ValueError(f'external link {ref!r} targets managed memory; use related with stable ID')
            except (ValueError, OSError) as exc:
                problems.append(f'{obj.get("memory_id", obj.get("title", ""))}: {exc}')
    return problems
