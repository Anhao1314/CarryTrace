"""Read-only Doubao Work session discovery and fingerprinting."""
from __future__ import annotations

import hashlib
import os
import platform
from pathlib import Path


class SourceChangedError(OSError):
    """A source file changed while it was being fingerprinted."""


class DoubaoConnector:
    name = "doubao"

    @staticmethod
    def default_candidates(home=None, system=None):
        home = Path(home or Path.home()).expanduser()
        system = system or platform.system()
        candidates = []
        env = os.environ.get("DOUBAO_WORK_SESSIONS")
        if env:
            candidates.append(Path(env).expanduser())
        if system == "Darwin":
            candidates.append(home / "Library/Application Support/DoubaoWork/Default/.doubaowork/agent_mode/workspace/.sessions")
        elif system == "Windows":
            local = os.environ.get("LOCALAPPDATA")
            if local:
                candidates.append(Path(local) / "DoubaoWork/Default/.doubaowork/agent_mode/workspace/.sessions")
        else:
            candidates.append(home / ".config/DoubaoWork/Default/.doubaowork/agent_mode/workspace/.sessions")
        out, seen = [], set()
        for path in candidates:
            key = str(path.expanduser())
            if key not in seen:
                out.append(path.expanduser())
                seen.add(key)
        return out

    @classmethod
    def discover(cls, sessions_root=None):
        if sessions_root:
            root = Path(sessions_root).expanduser()
            if not root.is_dir():
                raise ValueError("Doubao Work sessions directory does not exist: " + str(root))
            return root.resolve()
        for candidate in cls.default_candidates():
            if candidate.is_dir():
                return candidate.resolve()
        raise ValueError("Doubao Work sessions were not found; pass --sessions-root once during connect")

    @staticmethod
    def _inside(root, path):
        try:
            Path(path).resolve().relative_to(Path(root).resolve())
        except ValueError as exc:
            raise ValueError("Doubao source path escapes sessions root") from exc

    @classmethod
    def sessions(cls, root):
        root = Path(root).resolve()
        if not root.is_dir():
            raise ValueError("configured Doubao Work sessions directory is missing")
        result = []
        for path in sorted(root.iterdir(), key=lambda p: p.name):
            if path.is_symlink():
                continue
            if path.is_dir():
                cls._inside(root, path)
                result.append(path)
        return result

    @classmethod
    def fingerprint(cls, root, session_dir):
        """Hash only the two files the existing extractor consumes."""
        root = Path(root).resolve()
        session_dir = Path(session_dir)
        cls._inside(root, session_dir)
        files = []
        agents = session_dir / "agents"
        if agents.is_dir() and not agents.is_symlink():
            for agent in sorted(agents.iterdir(), key=lambda p: p.name):
                system = agent / "system"
                for name in ("assignment.md", "trajectory.jsonl"):
                    path = system / name
                    if path.is_file() and not path.is_symlink():
                        cls._inside(root, path)
                        files.append(path)
        h = hashlib.sha256()
        h.update(("session:" + session_dir.name + "\n").encode("utf-8"))
        for path in files:
            rel = path.relative_to(root).as_posix()
            before = path.stat()
            h.update(rel.encode("utf-8") + b"\0")
            with path.open("rb") as f:
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    h.update(chunk)
            after = path.stat()
            if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
                raise SourceChangedError("Doubao session changed during read: " + session_dir.name)
        return h.hexdigest()
