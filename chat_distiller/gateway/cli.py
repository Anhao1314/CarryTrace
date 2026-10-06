"""Simple user-facing Context Gateway commands."""
import argparse
import json

from .core import ContextGateway, GatewayError

def _print(result, machine=False):
    if machine:
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)); return
    if "connected" in result and "discovered_sessions" in result and "tracked_sessions" not in result:
        print("Connected to Doubao Work"); print("  sessions:", result["discovered_sessions"]); print("  context home:", result["home"]); return
    if "changed_sessions" in result:
        print("Sync complete"); print("  changed:", result["changed_sessions"]); print("  pending review:", result["pending_sessions"])
        if result.get("unstable_sessions"): print("  skipped moving sessions:", ", ".join(result["unstable_sessions"]))
        if result.get("needs_agent_judgment"): print("  agent review bundle:", result["plan"])
        return
    if "tracked_sessions" in result:
        print("Chat Distiller Context Gateway"); print("  Doubao sessions:", result["discovered_sessions"]); print("  tracked:", result["tracked_sessions"])
        print("  pending review:", result["pending_sessions"]); print("  memory:", "ready" if result["memory"].get("ok") else "not published")
        if result["knowledge"].get("available"): print("  knowledge: %s fresh / %s stale" % (result["knowledge"].get("fresh", 0), result["knowledge"].get("stale", 0)))
        return
    print("Context")
    structured = result.get("structured") or {}
    for page in structured.get("knowledge", []):
        print("\nKnowledge · " + page.get("title", page.get("topic", "")))
        for claim in page.get("claims", []): print("  - [%s] %s" % (claim.get("status"), claim.get("text")))
    for memory in structured.get("memories", []):
        print("\nMemory · %s · %s" % (memory.get("status"), memory.get("title"))); print("  " + str(memory.get("body", "")).replace("\n", " "))
    for session in result.get("raw_sessions", []):
        print("\nRaw session · %s%s" % (session["session_id"], " · pending review" if session["status"] == "pending" else ""))
        print("  " + str(session.get("first_request") or ""))
        for excerpt in session.get("excerpts", []): print("  > " + " ".join(excerpt.split())[:500])
    if result.get("requires_review"): print("\nReview required: raw/disputed/uncompiled context is present.")

def main(argv=None):
    parser = argparse.ArgumentParser(prog="chat-distiller", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    connect = commands.add_parser("connect", help="connect a supported local agent host")
    connect.add_argument("connector", choices=["doubao"]); connect.add_argument("--sessions-root"); connect.add_argument("--vault"); connect.add_argument("--home"); connect.add_argument("--force", action="store_true"); connect.add_argument("--json", action="store_true")
    sync = commands.add_parser("sync", help="incrementally stage changed host sessions")
    sync.add_argument("--apply", help="advanced: apply a host-agent reviewed gateway proposal"); sync.add_argument("--home"); sync.add_argument("--json", action="store_true")
    context = commands.add_parser("context", help="build task context from knowledge, memory and recent raw sessions")
    context.add_argument("query"); context.add_argument("--max-bytes", type=int, default=8192); context.add_argument("--top-k", type=int, default=5); context.add_argument("--home"); context.add_argument("--json", action="store_true")
    status = commands.add_parser("status", help="show connector, sync and memory health"); status.add_argument("--home"); status.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        gateway = ContextGateway(getattr(args, "home", None))
        if args.command == "connect": result = gateway.connect(args.connector, sessions_root=args.sessions_root, vault=args.vault, force=args.force)
        elif args.command == "sync": result = gateway.sync(apply=args.apply)
        elif args.command == "context": result = gateway.context(args.query, max_bytes=args.max_bytes, top_k=args.top_k)
        else: result = gateway.status()
        _print(result, args.json); return 0
    except (GatewayError, ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error_type": type(exc).__name__, "error": str(exc)}, ensure_ascii=False)); return 1
