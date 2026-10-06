"""Explicit wiki preparation, reviewed compilation, inspection and recovery."""
import argparse
import json
from pathlib import Path

from ..recovery import serialize_packet
from ..store import MemoryNotFoundError
from .contracts import CommitUncertainError, strict_json
from .store import KnowledgeStore


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, prog="chat-distiller wiki")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "compile", "search", "get", "status", "lint", "recover", "export"):
        sub = commands.add_parser(name)
        sub.add_argument("--vault", required=True)
        sub.add_argument("--subdir", default="对话沉淀")
        if name in ("prepare", "get"):
            sub.add_argument("--topic", required=True)
        if name in ("prepare", "search", "recover"):
            sub.add_argument("--query", required=True)
        if name == "prepare":
            sub.add_argument("--title")
            sub.add_argument("--kind", default="decision-synthesis")
        if name == "compile":
            sub.add_argument("--proposal", required=True)
            sub.add_argument("--apply", action="store_true", help="publish; default only validates")
        if name in ("search", "recover"):
            sub.add_argument("--intent", choices=["current", "historical"], default="current")
            sub.add_argument("--top-k", type=int, default=5)
        if name == "recover":
            sub.add_argument("--max-bytes", type=int, default=8192)
        if name == "get":
            sub.add_argument("--revision", type=int)
            sub.add_argument("--allow-stale", action="store_true")
        if name == "export":
            sub.add_argument("--out", required=True, help="new destination directory")
    args = parser.parse_args(argv)
    try:
        store = KnowledgeStore(args.vault, args.subdir)
        if args.command == "prepare":
            result = store.prepare(args.topic, args.query, title=args.title, kind=args.kind)
        elif args.command == "compile":
            path = Path(args.proposal).expanduser()
            if path.stat().st_size > 2 * 1024 * 1024:
                raise ValueError("proposal exceeds 2 MiB limit")
            result = store.compile(strict_json(path.read_text(encoding="utf-8")), apply=args.apply)
        elif args.command in ("status", "lint"):
            result = store.status()
        elif args.command == "get":
            result = store.get(args.topic, revision=args.revision, allow_stale=args.allow_stale)
        elif args.command == "search":
            result = {"ok": True, "results": store.search(args.query, intent=args.intent, top_k=args.top_k)}
        elif args.command == "recover":
            import sys
            packet = store.recover(args.query, intent=args.intent, top_k=args.top_k, max_bytes=args.max_bytes)
            sys.stdout.write(serialize_packet(packet))
            return 0
        else:
            result = store.export(args.out)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ValueError, OSError, MemoryNotFoundError, KeyError, TypeError) as exc:
        print(json.dumps({"ok": False, "error_type": type(exc).__name__, "error": str(exc), "results": [],
                          "commit_may_have_succeeded": isinstance(exc, CommitUncertainError)}, ensure_ascii=False))
        return 1
