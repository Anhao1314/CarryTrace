"""Read-only facade over the existing identity authority and lexical retrieval.

Every operation revalidates published state. This is a single-writer local store,
not a transactional database or an authenticated integrity boundary.
"""
import hashlib
from pathlib import Path

from ._internal.query_memory import load_index, search as lexical_search
from .recovery import build_packet


class MemoryIntegrityError(ValueError):
    """Published source, registry, notes or index cannot be safely consumed."""


class MemoryNotFoundError(LookupError):
    """The requested stable identity is absent from the active index."""


class MemoryStore:
    """Validated read-only access to an existing v2 vault; never creates a vault."""

    def __init__(self, vault, subdir="对话沉淀"):
        self.vault = Path(vault).expanduser().resolve()
        if not isinstance(subdir, str):
            raise ValueError("subdir must be a string")
        part = Path(subdir)
        if (not subdir or part.is_absolute()
                or ".." in part.parts or str(part) == "." or "\\" in subdir):
            raise ValueError("subdir must be a non-empty vault-relative directory")
        self.base = self.vault / part
        if not self.vault.is_dir():
            raise MemoryIntegrityError("vault directory does not exist")
        self._inside(self.base)

    def _inside(self, path):
        try:
            Path(path).resolve().relative_to(self.vault)
        except ValueError as exc:
            raise MemoryIntegrityError("managed path escapes vault") from exc

    def _snapshot(self):
        try:
            self._inside(self.base)
            # Inspect only managed paths. External references are not opened by this API.
            for rel in (".chat-distiller/distill.json", ".chat-distiller/identity-registry.json", "知识索引.jsonl"):
                self._inside(self.base / rel)
            for folder in ("会话笔记", "知识卡片"):
                self._inside(self.base / folder)
                for path in (self.base / folder).glob("*.md"):
                    self._inside(path)
            source_path = self.base / ".chat-distiller/distill.json"
            before = source_path.read_bytes()
            rows = load_index(self.base)
            if before != source_path.read_bytes():
                raise MemoryIntegrityError("source changed during read; retry with writer stopped")
            return rows, hashlib.sha256(before).hexdigest()
        except (ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
            raise MemoryIntegrityError(str(exc)) from exc

    @staticmethod
    def _arguments(query, top_k, intent):
        if not isinstance(query, str):
            raise ValueError("query must be a string")
        if type(top_k) is not int or not 1 <= top_k <= 100:
            raise ValueError("top_k must be an integer between 1 and 100")
        if intent not in ("current", "historical"):
            raise ValueError("intent must be current or historical")

    def search(self, query, *, top_k=5, intent="current", kind=None, category=None):
        """Current uses the unchanged status policy; historical permits expired cards."""
        self._arguments(query, top_k, intent)
        rows, _ = self._snapshot()
        return lexical_search(rows, query, top_k, intent == "historical", kind, category)

    def get(self, memory_id):
        """Explicit inspection may return a non-current card; always retains its status."""
        if not isinstance(memory_id, str) or not memory_id.startswith("mem_"):
            raise ValueError("get requires a stable memory_id, not a filename or display ID")
        rows, _ = self._snapshot()
        for row in rows:
            if row["memory_id"] == memory_id:
                return row
        raise MemoryNotFoundError("memory_id is not in the active index")

    def inspect(self):
        """Report validated counts, not a semantic correctness verdict."""
        rows, digest = self._snapshot()
        cards = [r for r in rows if r["type"] == "card"]
        return {
            "ok": True, "schema_version": 2, "source_sha256": digest,
            "conversations": sum(r["type"] == "conversation" for r in rows),
            "cards": len(cards),
            "statuses": {s: sum(r["status"] == s for r in cards) for s in ("现行", "已过期", "有争议")},
            "validation": "structural_consistency_only_not_truth",
        }

    def recover(self, query, *, top_k=5, max_bytes=8192, intent="current"):
        """Return complete evidence records fitting a canonical UTF-8 JSON budget.

        Does not infer a mission, generate an answer, execute stored instructions,
        run a model, or automatically inject anything into a host agent.
        """
        self._arguments(query, top_k, intent)
        rows, digest = self._snapshot()
        hits = lexical_search(rows, query, 100, intent == "historical")
        return build_packet(query, intent, hits, rows, digest, top_k, max_bytes)
