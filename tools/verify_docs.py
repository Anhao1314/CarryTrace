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
    for name, language in (("quickstart", "bash"), ("sdk", "python"), ("expected", "json")):
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
        script += '\nprintf "%s" "$DEMO_DIR" > "$RECEIPT_DIR/demo-path"\n'
        script += 'cd "$DEMO_DIR"\npython - <<\'README_PY\'\n'
        script += example(texts[0], "sdk", "python") + '\nREADME_PY\n'
        proc = subprocess.run(["bash", "-euo", "pipefail", "-c", script], cwd=root,
                              env=env, capture_output=True, text=True, timeout=90)
        if proc.returncode:
            raise AssertionError(proc.stdout + proc.stderr)
        base = Path((Path(tmp) / "demo-path").read_text()).resolve()
        base.relative_to(Path(tmp).resolve())
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


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write-demo", action="store_true", help="regenerate fixture-derived JSON/SVG after execution")
    args = ap.parse_args()
    files = ["README.md", "README.zh-CN.md", "CONTRIBUTING.md", "CHANGELOG.md"]
    files += [str(p.relative_to(ROOT)) for folder in ("docs", "references") for p in sorted((ROOT / folder).glob("*.md"))]
    demo = verify_demo(ROOT)
    outputs = {"examples/recovery/expected.json": json.dumps(demo, ensure_ascii=False, indent=2) + "\n",
               "assets/recovery-demo.svg": demo_svg(demo["cases"])}
    for name, content in outputs.items():
        path = ROOT / name
        if args.write_demo:
            path.write_text(content, encoding="utf-8")
        elif path.read_text(encoding="utf-8") != content:
            raise AssertionError("stale demo artifact: " + name)
    report = dict(ok=True, **check_links(ROOT, files), readme_languages=2,
                  executed_examples=["quickstart", "ingestion", "sdk"], recovery_scenarios=len(demo["cases"]),
                  generated_assets_match=True, data=demo["scope"])
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
