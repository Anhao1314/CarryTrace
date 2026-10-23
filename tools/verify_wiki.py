#!/usr/bin/env python3
"""Verify the installed knowledge layer outside the repository checkout."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import chat_distiller

ROOT = Path(__file__).resolve().parents[1]
if ROOT in Path(chat_distiller.__file__).resolve().parents:
    raise RuntimeError("wiki smoke check imported source instead of installed wheel")

with tempfile.TemporaryDirectory(prefix="chat-distiller-wiki-installed-") as tmp:
    proc = subprocess.run([sys.executable, str(ROOT / "tools/wiki_demo.py"), "--out", str(Path(tmp) / "demo")],
                          cwd=tmp, capture_output=True, text=True, timeout=120)
    if proc.returncode:
        raise RuntimeError(proc.stdout + proc.stderr)
    demo = json.loads(proc.stdout)
    spec = importlib.util.spec_from_file_location("compilebench", ROOT / "benchmarks/wiki/evaluate.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    results = module.evaluate()
    saved = json.loads((ROOT / "benchmarks/wiki/results.json").read_text(encoding="utf-8"))
    if results != saved:
        raise AssertionError("installed compiler benchmark differs from committed result")
    print(json.dumps({"ok": demo["ok"] and not results["summary"]["failures"], "version": chat_distiller.__version__,
                      "installed_package": chat_distiller.__file__, "cli_commands_executed": demo["commands_executed"],
                      "demo_checks_passed": sum(demo["checks"].values()), "compilebench": results["summary"],
                      "model_calls": 0}, ensure_ascii=False, indent=2))
