#!/usr/bin/env python3
"""Check repository links and execute the README examples with an installed CLI.

The demo uses handwritten synthetic cards in a temporary directory. No model,
network request, user vault, or native host-compaction event is exercised.
"""
import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
README_FILES = ("README.md", "README.zh-CN.md")


def example(text, name, language):
    pattern = r"<!-- verify:" + re.escape(name) + r" -->\s*```" + re.escape(language) + r"\n(.*?)\n```"
    matches = re.findall(pattern, text, re.S)
    if len(matches) != 1:
        raise ValueError("expected one example: " + name)
    return matches[0]


def anchors(text):
    """Heading IDs for the subset used here, plus explicit HTML anchors."""
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    found = set(re.findall(r'<[^>]+(?:id|name)=[\"\']([^\"\']+)', text))
    counts = {}
    for heading in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", text, re.M):
        heading = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", heading)
        slug = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        count = counts.get(slug, 0)
        counts[slug] = count + 1
        found.add(slug + ("-" + str(count) if count else ""))
    return found


def check_links(root, files):
    """Validate local targets/Markdown fragments; external HTTP links are not fetched."""
    root = Path(root).resolve()
    checked = 0
    external = 0
    for relative in files:
        path = root / relative
        text = path.read_text(encoding="utf-8")
        visible = re.sub(r"```.*?```", "", text, flags=re.S)
        links = re.findall(r"\]\(([^\s)]+)(?:\s+\"[^\"]*\")?\)", visible)
        links += re.findall(r'<[^>]+(?:href|src)=[\"\']([^\"\']+)', visible)
        for link in links:
            url = urlsplit(html.unescape(link.strip("<>")))
            if url.scheme or url.netloc:
                if url.scheme not in ("https", "http", "mailto"):
                    raise ValueError(f"{relative}: unexpected link scheme: {link}")
                external += 1
                continue
            target = (path.parent / unquote(url.path)).resolve() if url.path else path
            try:
                target.relative_to(root)
            except ValueError as exc:
                raise ValueError(f"{relative}: link escapes repository: {link}") from exc
            if not target.exists():
                raise ValueError(f"{relative}: missing link target: {link}")
            if url.fragment and target.suffix == ".md":
                if unquote(url.fragment) not in anchors(target.read_text(encoding="utf-8")):
                    raise ValueError(f"{relative}: missing fragment: {link}")
            checked += 1
    return {"local_links_checked": checked, "external_links_not_fetched": external}


def summarize(packet):
    return {"status": packet["status"], "intent": packet["intent"],
            "memory_count": len(packet["memories"]), "used_bytes": packet["used_bytes"],
            "budget_bytes": packet["budget_bytes"], "requires_review": packet["requires_review"],
            "expired_count": sum(m["status"] == "已过期" for m in packet["memories"])}


def demo_svg(cases):
    """Static display projection of executed results, not a terminal recording."""
    rows = []
    labels = (("current", "Current decision"), ("historical", "Earlier decision"),
              ("unknown", "Unknown question"), ("budget", "Budget too small"))
    for i, (key, label) in enumerate(labels):
        case = cases[key]
        y = 156 + i * 49
        values = ((42, label), (338, case["status"]), (622, str(case["memory_count"])),
                  (742, str(case["expired_count"])), (850, str(case["used_bytes"]) + " B"))
        rows.append(f'<path d="M32 {y+16}H1008" stroke="#293446"/>')
        for x, value in values:
            rows.append(f'<text x="{x}" y="{y}" fill="#e6edf3">{html.escape(value)}</text>')
    return '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1040 398" role="img" aria-labelledby="title desc">
<title id="title">chat-distiller: executed recovery demo</title>
<desc id="desc">A synthetic example distinguishes current and historical lookup, no match, and an exhausted byte budget. This is a display projection of actual CLI output, not a model evaluation.</desc>
<rect width="1040" height="398" rx="18" fill="#101824"/>
<text x="42" y="43" fill="#91a4b9" font-family="sans-serif" font-size="12" letter-spacing="2">CHAT-DISTILLER / EXECUTED DEMO</text>
<text x="42" y="79" fill="#ffffff" font-family="sans-serif" font-size="26" font-weight="600">A changed decision. An inspectable trail.</text>
<g font-family="ui-monospace, monospace" font-size="15">
<g fill="#91a4b9"><text x="42" y="119">SCENARIO</text><text x="338" y="119">PACKET STATUS</text><text x="622" y="119">RECORDS</text><text x="742" y="119">EXPIRED</text><text x="850" y="119">SIZE</text></g>
''' + "\n".join(rows) + '''
</g>
<text x="42" y="367" fill="#91a4b9" font-family="sans-serif" font-size="14">Handwritten synthetic cards. CLI execution, not automatic distillation or host recovery.</text>
</svg>
'''


def verify_demo(root):
    texts = [(root / f).read_text(encoding="utf-8") for f in README_FILES]
    for name, language in (("quickstart", "bash"), ("sdk", "python"), ("expected", "json"), ("wiki", "bash")):
        if example(texts[0], name, language) != example(texts[1], name, language):
            raise ValueError("bilingual example drift: " + name)
    entry = shutil.which("chat-distiller")
    python = shutil.which("python")
    if not entry or not python or not shutil.which("bash"):
        raise ValueError("activate an installed chat-distiller environment with Python and Bash")
    with tempfile.TemporaryDirectory(prefix="readme-proof-") as tmp:
        env = dict(os.environ, TMPDIR=tmp, RECEIPT_DIR=tmp)
        env.pop("PYTHONPATH", None)
        # Run the literal Markdown shell block and Python block in the same shell.
        # Source checkout is cwd for the relative example fixture, not the SDK import.
        script = example(texts[0], "quickstart", "bash")
        script += '\n' + example((root / 'docs/ingestion.md').read_text(encoding='utf-8'), 'ingestion', 'bash') + '\n'
        script += "\n" + example(texts[0], "wiki", "bash") + "\n"
        script += '\nprintf "%s" "$DEMO_DIR" > "$RECEIPT_DIR/demo-path"\n'
        script += 'cd "$DEMO_DIR"\npython - <<\'README_PY\'\n'
        script += example(texts[0], "sdk", "python") + '\nREADME_PY\n'
        proc = subprocess.run(["bash", "-euo", "pipefail", "-c", script], cwd=root,
                              env=env, capture_output=True, text=True, timeout=90)
        if proc.returncode:
            raise AssertionError(proc.stdout + proc.stderr)
        base = Path((Path(tmp) / "demo-path").read_text()).resolve()
        base.relative_to(Path(tmp).resolve())
        knowledge = json.loads((base / "knowledge.json").read_text(encoding="utf-8"))
        if knowledge["schema_version"] != 2 or not knowledge["knowledge"]:
            raise AssertionError("wiki README example did not return knowledge")
        if not (base / "wiki-view/manifest.json").is_file():
            raise AssertionError("wiki README export is incomplete")
        # Verify that subprocesses use the installed distribution, not cwd or PYTHONPATH.
        imported = subprocess.check_output([python, "-c", "import chat_distiller; print(chat_distiller.__file__)"],
                                           cwd=base, env=env, text=True).strip()
        if root in Path(imported).resolve().parents:
            raise AssertionError("example imported source checkout instead of installed package")
        lint = json.loads((base / "lint.json").read_text(encoding="utf-8"))
        if not lint["ok"] or lint["structure_issues"] or lint["index_issues"]:
            raise AssertionError("ingestion example failed validation")
        packets = {"current": json.loads((base / "recovery.json").read_text(encoding="utf-8"))}
        def recover(query, *options):
            run = subprocess.run([entry, "recover", "--vault", str(base / "vault"), "--query", query,
                                  *options], cwd=base, env=env, capture_output=True, text=True, timeout=60)
            if run.returncode:
                raise AssertionError(run.stdout + run.stderr)
            packet = json.loads(run.stdout)
            if len(run.stdout.encode("utf-8")) != packet["used_bytes"]:
                raise AssertionError("wire byte count does not match")
            if packet["used_bytes"] > packet["budget_bytes"]:
                raise AssertionError("wire exceeds budget")
            return packet
        packets["historical"] = recover("database", "--intent", "historical", "--max-bytes", "4096")
        packets["unknown"] = recover("quasarzzz", "--max-bytes", "4096")
        packets["budget"] = recover("database", "--max-bytes", "800")
        old = next(m for m in packets["historical"]["memories"] if m["status"] == "已过期")
        current_ids = {m["memory_id"] for m in packets["current"]["memories"] if m["is_current"]}
        if old["superseded_by"] not in current_ids:
            raise AssertionError("historical example lost its successor")
        actual = packets["current"]
        expected = json.loads(example(texts[0], "expected", "json"))
        if expected != {k: actual[k] for k in expected}:
            raise AssertionError("README output excerpt differs from executed result")
        if packets["unknown"]["status"] != "no_match" or packets["budget"]["status"] != "budget_exhausted":
            raise AssertionError("demo no longer demonstrates distinct recovery outcomes")
        return {"fixture_sha256": hashlib.sha256((root / "examples/recovery/distill.json").read_bytes()).hexdigest(),
                "scope": "synthetic CLI display projection; no model or host compaction",
                "cases": {k: summarize(v) for k, v in packets.items()}}


def lifecycle_projection(root, run):
    """Project stable facts from raw CLI receipts, not from a claimed summary alone."""
    root, run = Path(root), Path(run)
    def read(name):
        return json.loads((run / name).read_text(encoding="utf-8"))
    report = read("summary.json")
    expected_steps = ["01-register", "02-render", "03-prepare", "04-validate", "05-publish",
                      "06-current", "07-history", "08-recovery", "09-export", "10-update-memory",
                      "11-stale", "12-fallback", "13-prepare-refresh", "14-refresh", "15-archive", "16-export"]
    if (report.get("ok") is not True or report.get("model_calls") != 0
            or report.get("commands_executed") != len(expected_steps)
            or report.get("receipts") != expected_steps
            or len(report.get("checks", {})) != 12
            or not all(value is True for value in report["checks"].values())):
        raise AssertionError("Wiki lifecycle summary changed or contains a failed check")
    for name in expected_steps:
        read(name + ".json")
    published, current = read("05-publish.json"), read("06-current.json")
    stale, fallback = read("11-stale.json"), read("12-fallback.json")
    refreshed, archive = read("14-refresh.json"), read("15-archive.json")
    if read("04-validate.json")["applied"] is not False:
        raise AssertionError("Wiki validation unexpectedly wrote state")
    page = current["results"][0]
    if (published["page_revision"] != 1 or published["applied"] is not True
            or published["requires_review"] is not True
            or page["freshness"] != "fresh"
            or {c["status"] for c in page["claims"]} != {"current", "disputed"}
            or not any("SQLite" in c["text"] for c in page["claims"] if c["status"] == "current")):
        raise AssertionError("Wiki publication no longer matches the illustrated fixture")
    if (stale["stale"] != 1 or fallback["knowledge"] != []
            or fallback["stale_pages_excluded"] != 1
            or not any("PostgreSQL" in m["body"] for m in fallback["memories"] if m["status"] == "现行")):
        raise AssertionError("Wiki fallback failed freshness or updated-memory checks")
    if (refreshed["applied"] is not True or refreshed["page_revision"] != 2
            or published["knowledge_id"] != refreshed["knowledge_id"]
            or archive["knowledge_id"] != published["knowledge_id"]
            or archive["revision"] != 1 or archive["archived"] is not True):
        raise AssertionError("Wiki refresh lost the identity or old revision")
    for name in ("08-recovery.json", "12-fallback.json"):
        packet = read(name)
        if len((run / name).read_bytes()) != packet["used_bytes"] or packet["used_bytes"] > packet["budget_bytes"]:
            raise AssertionError("Wiki demo packet violates its byte contract")
    for folder in ("wiki-v1", "wiki-v2"):
        manifest = read(folder + "/manifest.json")
        for filename, digest in manifest["files"].items():
            path = (run / folder / filename).resolve()
            path.relative_to((run / folder).resolve())
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise AssertionError("Wiki export digest mismatch: " + filename)
    return {
        "scope": "synthetic CLI lifecycle; prewritten synthesis; extractive refresh; no model evaluation",
        "inputs_sha256": {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                          for name in ("examples/recovery/distill.json", "examples/wiki/synthesis.json")},
        "commands_executed": report["commands_executed"], "checks_passed": len(report["checks"]),
        "model_calls": report["model_calls"],
        "published": {"revision": published["page_revision"], "current_value": "SQLite", "dispute_retained": True},
        "source_changed": {"stale_pages": stale["stale"]},
        "fallback": {"current_value": "PostgreSQL", "stale_wiki_returned": len(fallback["knowledge"])},
        "refreshed": {"revision": refreshed["page_revision"], "identity_preserved": True,
                      "old_revision_retained": archive["archived"]},
    }


def verify_lifecycle(root):
    """Execute the literal README lifecycle block in an isolated temporary directory."""
    root = Path(root)
    texts = [(root / name).read_text(encoding="utf-8") for name in README_FILES]
    for name, language in (("lifecycle", "bash"), ("lifecycle-expected", "json")):
        if example(texts[0], name, language) != example(texts[1], name, language):
            raise ValueError("bilingual example drift: " + name)
    with tempfile.TemporaryDirectory(prefix="wiki-readme-proof-") as tmp:
        env = dict(os.environ, TMPDIR=tmp, RECEIPT_DIR=tmp)
        env.pop("PYTHONPATH", None)
        script = example(texts[0], "lifecycle", "bash")
        script += '\nprintf "%s" "$WIKI_DEMO_PARENT" > "$RECEIPT_DIR/lifecycle-path"\n'
        proc = subprocess.run(["bash", "-euo", "pipefail", "-c", script], cwd=root,
                              env=env, capture_output=True, text=True, timeout=90)
        if proc.returncode:
            raise AssertionError(proc.stdout + proc.stderr)
        run = Path((Path(tmp) / "lifecycle-path").read_text()).resolve() / "run"
        run.relative_to(Path(tmp).resolve())
        report = json.loads((run / "summary.json").read_text(encoding="utf-8"))
        expected = json.loads(example(texts[0], "lifecycle-expected", "json"))
        if not expected or expected != {key: report[key] for key in expected}:
            raise AssertionError("README lifecycle excerpt differs from execution")
        return lifecycle_projection(root, run)


def lifecycle_svg(receipt, language="en"):
    """Bilingual, script-free presentation of the checked lifecycle receipt."""
    if language not in ("en", "zh-CN"):
        raise ValueError("unsupported lifecycle illustration language")
    if (receipt["refreshed"]["identity_preserved"] is not True
            or receipt["refreshed"]["old_revision_retained"] is not True
            or receipt["published"]["dispute_retained"] is not True):
        raise ValueError("receipt does not support lifecycle illustration")
    published, changed, fallback, refreshed = [receipt[k] for k in ("published", "source_changed", "fallback", "refreshed")]
    if language == "en":
        title = "Source changes. The old Wiki steps aside."
        desc = "Executed synthetic lifecycle: publish, mark stale, fall back to updated memory, and recompile. No model evaluation."
        heading = "Knowledge changes. Keep the trail."
        rows = [("01 / PUBLISH", f'{published["current_value"]} · rev {published["revision"]}', "Citations + dispute"),
                ("02 / SOURCE UPDATE", f'{changed["stale_pages"]} stale page', "Recheck before reuse"),
                ("03 / FALLBACK", fallback["current_value"], f'{fallback["stale_wiki_returned"]} stale Wiki pages served'),
                ("04 / RECOMPILE", f'rev {refreshed["revision"]} · same ID', "Old revision retained")]
        footer = f'{receipt["commands_executed"]} CLI steps · {receipt["checks_passed"]} checks · synthetic data'
    else:
        title = "知识更新后，旧 Wiki 不再冒充当前结论。"
        desc = "实跑的合成生命周期：发布、标记失效、回退到最新记忆、重新编译。不是模型评测。"
        heading = "知识会变化，来路不丢失。"
        rows = [("01 / 发布知识", f'{published["current_value"]} · 版本 {published["revision"]}', "保留引用与未决争议"),
                ("02 / 来源更新", f'{changed["stale_pages"]} 个旧页失效', "复核之前不默认复用"),
                ("03 / 原子回退", fallback["current_value"], f'返回 {fallback["stale_wiki_returned"]} 个过时 Wiki 页'),
                ("04 / 重新编译", f'版本 {refreshed["revision"]} · 身份不变', "旧版本仍可检查")]
        footer = f'{receipt["commands_executed"]} 步 CLI · {receipt["checks_passed"]} 项检查 · 合成数据'
    parts = [f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 680 440" role="img" aria-labelledby="title desc" lang="{language}">
<title id="title">{html.escape(title)}</title>
<desc id="desc">{html.escape(desc)}</desc>
<rect width="680" height="440" rx="18" fill="#101824"/>
<g font-family="system-ui, -apple-system, 'Noto Sans CJK SC', sans-serif">
<text x="28" y="38" fill="#a7b8cb" font-size="16" letter-spacing="1.5">CHAT-DISTILLER / KNOWLEDGE WIKI</text>
<text x="28" y="78" fill="#ffffff" font-size="29" font-weight="600">{html.escape(heading)}</text>''']
    for index, (label, value, note) in enumerate(rows):
        x, y = 20 + (index % 2) * 328, 104 + (index // 2) * 142
        parts += [f'<rect x="{x}" y="{y}" width="312" height="130" rx="12" fill="#192534" stroke="#334459"/>',
                  f'<text x="{x+18}" y="{y+29}" fill="#a7c8f0" font-size="16" font-weight="600">{html.escape(label)}</text>',
                  f'<text x="{x+18}" y="{y+70}" fill="#ffffff" font-size="28" font-weight="600">{html.escape(value)}</text>',
                  f'<text x="{x+18}" y="{y+106}" fill="#c1cedd" font-size="19">{html.escape(note)}</text>']
    parts += [f'<text x="28" y="412" fill="#a7b8cb" font-size="19">{html.escape(footer)}</text>', '</g>\n</svg>\n']
    return "\n".join(parts)


def check_evidence_tables(root):
    """Keep both README metric tables synchronized with the inspectable reports."""
    root = Path(root)
    bench = json.loads((root / "benchmarks/wiki/results.json").read_text(encoding="utf-8"))
    summary = bench["summary"]
    rows = [(summary["invalid_proposals_blocked"], summary["invalid_proposals_total"]),
            (summary["exact_budget_passes"], summary["exact_budget_total"]),
            (summary["stale_served_gate_disabled"], summary["topics"]),
            (summary["stale_served_gate_enabled"], summary["topics"]),
            (sum(c["identity_preserved_after_refresh"] and c["old_revision_inspectable"] for c in bench["cases"]), summary["topics"])]
    retrieval = json.loads((root / "benchmarks/benchmark-results.json").read_text(encoding="utf-8"))
    expected_retrieval = []
    for method in ("Baseline", "Structured Memory", "Status-aware Memory"):
        values = retrieval["results"][method]["metrics"]
        expected_retrieval.append([f'{values[k]:.4f}' for k in ("Recall@1", "Recall@5", "MRR", "stale-hit@5")])
    for name in README_FILES:
        text = (root / name).read_text(encoding="utf-8")
        observed = [(int(a), int(b)) for a, b in re.findall(r'^\|[^\n]*\|\s*(\d+) / (\d+)\s*\|$', text, re.M)]
        if observed != rows:
            raise AssertionError(name + ": Wiki metric table differs from committed report")
        observed_retrieval = []
        for line in text.splitlines():
            if line.startswith("|") and len(re.findall(r'\d+\.\d{4}', line)) == 4:
                observed_retrieval.append(re.findall(r'\d+\.\d{4}', line))
        if observed_retrieval != expected_retrieval:
            raise AssertionError(name + ": retrieval metric table differs from committed report")
    return {"metric_tables_checked": 4}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write-demo", action="store_true", help="regenerate fixture-derived JSON/SVG after execution")
    args = ap.parse_args()
    files = ["README.md", "README.zh-CN.md", "CONTRIBUTING.md", "CHANGELOG.md"]
    files += [str(p.relative_to(ROOT)) for folder in ("docs", "references") for p in sorted((ROOT / folder).glob("*.md"))]
    demo = verify_demo(ROOT)
    lifecycle = verify_lifecycle(ROOT)
    metrics = check_evidence_tables(ROOT)
    outputs = {"examples/recovery/expected.json": json.dumps(demo, ensure_ascii=False, indent=2) + "\n",
               "assets/recovery-demo.svg": demo_svg(demo["cases"]),
               "examples/wiki/lifecycle.expected.json": json.dumps(lifecycle, ensure_ascii=False, indent=2) + "\n",
               "assets/wiki-lifecycle.svg": lifecycle_svg(lifecycle),
               "assets/wiki-lifecycle.zh-CN.svg": lifecycle_svg(lifecycle, "zh-CN")}
    for name, content in outputs.items():
        path = ROOT / name
        if args.write_demo:
            path.write_text(content, encoding="utf-8")
        elif path.read_text(encoding="utf-8") != content:
            raise AssertionError("stale demo artifact: " + name)
    report = dict(ok=True, **check_links(ROOT, files), **metrics, readme_languages=2,
                  executed_examples=["quickstart", "ingestion", "wiki", "sdk", "lifecycle"], recovery_scenarios=len(demo["cases"]),
                  wiki_lifecycle_commands=lifecycle["commands_executed"], wiki_lifecycle_checks=lifecycle["checks_passed"],
                  generated_assets_match=True, data=demo["scope"])
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
