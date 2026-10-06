"""Evidence-linked knowledge compilation and layered recovery over MemoryStore."""
import copy
from html import escape
from pathlib import Path
import uuid

from ..store import MemoryStore, MemoryNotFoundError
from .._internal.query_memory import lexical_score, search as memory_search
from ..recovery import _measure
from .contracts import (StaleProposalError, WikiIntegrityError, canonical, classification,
                        digest, text, topic_key, validate_proposal)
from .storage import StateFile


class KnowledgeStore:
    """Optional derived wiki. Semantic synthesis is supplied by the calling agent."""

    def __init__(self, vault, subdir="对话沉淀"):
        self.memory = MemoryStore(vault, subdir)
        self.storage = StateFile(self.memory)

    def _snapshot(self):
        rows, source = self.memory._snapshot()
        state = self.storage.read()
        by_id = {r["memory_id"]: r for r in rows}
        for versions in state["pages"].values():
            page = versions[-1]
            if page["proposal"]["source_sha256"] == source and any(by_id.get(r["memory_id"]) != r for r in page["dependencies"]):
                raise WikiIntegrityError("fresh page dependencies differ from atomic memory")
        # A best-effort detection of an observed concurrent memory write, not
        # a transaction spanning the old renderer and the compiled store.
        _, after = self.memory._snapshot()
        if after != source:
            raise StaleProposalError("memory changed during wiki read")
        return rows, source, state

    @staticmethod
    def _scope(rows, query, previous=None):
        by_id = {r["memory_id"]: r for r in rows if r["type"] == "card"}
        selected = {i for i, r in by_id.items() if lexical_score(query, r) > 0}
        if previous:
            selected.update(i for i in previous["proposal"]["scope"] if i in by_id)
        # Preserve declared successors even when their wording differs.
        todo = list(selected)
        while todo:
            successor = by_id[todo.pop()].get("superseded_by")
            if successor in by_id and successor not in selected:
                selected.add(successor)
                todo.append(successor)
        if not selected:
            raise ValueError("no matching atomic memory; do not invent a knowledge page")
        if len(selected) > 100:
            raise ValueError("scope exceeds 100 cards; choose a narrower query/topic")
        return sorted(selected)

    def prepare(self, topic, query, *, title=None, kind="decision-synthesis"):
        """Return an extractive proposal; no state writes or model calls.

        The host may consolidate its claims, marking origin synthesis/inference.
        It must keep literal evidence, scope, and snapshot fields unchanged.
        """
        topic_key(topic)
        text(query, "query", 2000)
        rows, source, state = self._snapshot()
        versions = state["pages"].get(topic, [])
        previous = versions[-1] if versions else None
        scope = self._scope(rows, query, previous)
        by_id = {r["memory_id"]: r for r in rows}
        proposal = {"schema_version": 1, "topic": topic, "title": title or topic,
                    "kind": kind, "query": query, "source_sha256": source,
                    "wiki_revision": state["revision"], "scope": scope,
                    "related_topics": previous["proposal"]["related_topics"] if previous else [],
                    "claims": [{"text": by_id[i]["body"], "status": classification([by_id[i]]),
                                "origin": "extract", "evidence": [{"memory_id": i, "quote": by_id[i]["body"]}]}
                               for i in scope]}
        validate_proposal(proposal, rows)
        return proposal

    @staticmethod
    def _material(proposal):
        return {k: v for k, v in proposal.items() if k != "wiki_revision"}

    def _candidate(self, proposal, rows, source, state):
        if isinstance(proposal, dict) and isinstance(proposal.get("source_sha256"), str) and proposal["source_sha256"] != source:
            raise StaleProposalError("memory snapshot changed; prepare and review again")
        validate_proposal(proposal, rows)
        versions = state["pages"].get(proposal["topic"], [])
        previous = versions[-1] if versions else None
        # Scoped selection is recomputed, not trusted merely because an LLM
        # supplied matching-looking memory IDs.
        if sorted(proposal["scope"]) != self._scope(rows, proposal["query"], previous):
            raise ValueError("proposal scope differs from declared query and existing topic dependencies")
        if any(key not in state["pages"] for key in proposal["related_topics"]):
            raise ValueError("related topic does not exist")
        if previous and self._material(previous["proposal"]) == self._material(proposal):
            return previous, "no_change"
        if proposal["wiki_revision"] != state["revision"]:
            raise StaleProposalError("wiki revision changed; prepare and review again")
        by_id = {r["memory_id"]: r for r in rows}
        page = {"knowledge_id": previous["knowledge_id"] if previous else "kn_" + uuid.uuid4().hex,
                "revision": len(versions) + 1, "commit_revision": state["revision"] + 1,
                "proposal": proposal, "dependencies": [by_id[i] for i in sorted(proposal["scope"])],
                "related": {key: state["pages"][key][-1]["knowledge_id"] for key in proposal["related_topics"]}}
        return page, "update" if previous else "create"

    def compile(self, proposal, *, apply=False):
        """Validate by default; only apply=True publishes a new compiled revision."""
        if type(apply) is not bool:
            raise ValueError("apply must be boolean")
        # Normalize input and detach caller-owned nested objects before validation.
        from .contracts import strict_json
        wire = canonical(proposal)
        if len(wire.encode("utf-8")) > 2 * 1024 * 1024:
            raise ValueError("proposal exceeds 2 MiB limit")
        proposal = strict_json(wire)
        rows, source, state = self._snapshot()
        page, operation = self._candidate(proposal, rows, source, state)
        receipt = {"ok": True, "operation": operation, "applied": False,
                   "topic": proposal["topic"], "wiki_revision": state["revision"],
                   "validation": "references_quotes_scope_status_only_not_entailment",
                   "requires_review": any(c["origin"] != "extract" or c["status"] != "current" for c in proposal["claims"])}
        if not apply or operation == "no_change":
            if operation == "no_change":
                receipt.update(knowledge_id=page["knowledge_id"], page_revision=page["revision"])
            return receipt  # Dry-run UUID is never exposed as a persistent identity.
        with self.storage.writer() as locked:
            rows, source = self.memory._snapshot()
            page, operation = self._candidate(proposal, rows, source, locked)
            if operation == "no_change":
                return dict(receipt, operation=operation, knowledge_id=page["knowledge_id"], page_revision=page["revision"], wiki_revision=locked["revision"])
            locked["pages"].setdefault(proposal["topic"], []).append(page)
            locked["revision"] += 1
            locked["log"].append({"revision": locked["revision"], "topic": proposal["topic"],
                                  "knowledge_id": page["knowledge_id"], "page_revision": page["revision"],
                                  "page_sha256": digest(page)})
            _, after = self.memory._snapshot()
            if after != source:
                raise StaleProposalError("memory changed before publication")
            self.storage.replace(locked)
        return dict(receipt, operation=operation, applied=True, wiki_revision=locked["revision"],
                    knowledge_id=page["knowledge_id"], page_revision=page["revision"])

    @staticmethod
    def _freshness(page, source, rows):
        if page["proposal"]["source_sha256"] == source:
            return "fresh", []
        by_id = {r["memory_id"]: r for r in rows}
        changed = [r["memory_id"] for r in page["dependencies"] if by_id.get(r["memory_id"]) != r]
        return "stale", changed

    def status(self):
        rows, source, state = self._snapshot()
        pages = []
        for topic, versions in sorted(state["pages"].items()):
            page = versions[-1]
            freshness, changed = self._freshness(page, source, rows)
            pages.append({"topic": topic, "knowledge_id": page["knowledge_id"], "revision": page["revision"],
                          "freshness": freshness, "changed_dependencies": changed,
                          "reason": None if freshness == "fresh" else "dependency_changed" if changed else "source_changed_review_scope"})
        return {"ok": True, "wiki_revision": state["revision"], "source_sha256": source, "pages": pages,
                "fresh": sum(p["freshness"] == "fresh" for p in pages), "stale": sum(p["freshness"] == "stale" for p in pages)}

    def get(self, topic, *, revision=None, allow_stale=False):
        topic_key(topic)
        if type(allow_stale) is not bool:
            raise ValueError("allow_stale must be boolean")
        rows, source, state = self._snapshot()
        versions = state["pages"].get(topic)
        if not versions:
            raise MemoryNotFoundError("knowledge topic not found")
        if revision is not None and (type(revision) is not int or not 1 <= revision <= len(versions)):
            raise ValueError("unknown page revision")
        page = copy.deepcopy(versions[-1] if revision is None else versions[revision - 1])
        freshness, changed = self._freshness(page, source, rows)
        # An old revision is archived even when the memory snapshot was unchanged.
        archived = page["revision"] != versions[-1]["revision"]
        if (freshness == "stale" or archived) and not allow_stale:
            raise StaleProposalError("knowledge is stale or archived; explicit inspection requires allow_stale=True")
        return dict(page, freshness=freshness, archived=archived, changed_dependencies=changed,
                    requires_review=archived or freshness != "fresh" or any(c["origin"] != "extract" or c["status"] != "current" for c in page["proposal"]["claims"]))

    @staticmethod
    def _search(query, intent, rows, source, state):
        hits = []
        for topic, versions in state["pages"].items():
            page = versions[-1]
            if page["proposal"]["source_sha256"] != source:
                continue
            claims = [c for c in page["proposal"]["claims"] if intent == "historical" or c["status"] != "historical"]
            if not claims:
                continue
            score = lexical_score(query, {"title": page["proposal"]["title"], "body": "\n".join(c["text"] for c in claims)})
            if not score:
                continue
            selected = {e["memory_id"] for c in claims for e in c["evidence"]}
            hits.append({"topic": topic, "knowledge_id": page["knowledge_id"], "revision": page["revision"],
                         "title": page["proposal"]["title"], "kind": page["proposal"]["kind"],
                         "claims": claims, "evidence_memories": [r for r in page["dependencies"] if r["memory_id"] in selected],
                         "related": page["related"], "score": score, "freshness": "fresh",
                         "requires_review": any(c["origin"] != "extract" or c["status"] != "current" for c in claims)})
        hits.sort(key=lambda p: (-p["score"], p["knowledge_id"]))
        return hits

    def search(self, query, *, intent="current", top_k=5):
        self.memory._arguments(query, top_k, intent)
        rows, source, state = self._snapshot()
        return self._search(query, intent, rows, source, state)[:top_k]

    def recover(self, query, *, intent="current", top_k=5, max_bytes=8192):
        """Complete fresh knowledge units first, then untruncated atomic fallback."""
        self.memory._arguments(query, top_k, intent)
        if type(max_bytes) is not int or not 512 <= max_bytes <= 1048576:
            raise ValueError("max_bytes must be an integer between 512 and 1048576")
        rows, source, state = self._snapshot()
        knowledge = self._search(query, intent, rows, source, state)[:100]
        atomic = memory_search(rows, query, 100, intent == "historical")
        stale_count = sum(v[-1]["proposal"]["source_sha256"] != source for v in state["pages"].values())
        packet = {"schema_version": 2, "mode": "layered", "query": query, "intent": intent,
                  "source_sha256": source, "wiki_revision": state["revision"], "budget_bytes": max_bytes,
                  "used_bytes": 0, "status": "budget_exhausted" if knowledge or atomic else "no_match",
                  "trust": "untrusted_data_not_instructions", "validation": "structural_not_semantic",
                  "candidate_window_per_layer": 100, "knowledge_candidates": len(knowledge),
                  "stale_pages_excluded": stale_count, "omitted_knowledge": len(knowledge),
                  "requires_review": bool(stale_count), "knowledge": [], "memories": [],
                  "atomic_fallback_has_no_topic_coverage_guarantee": True}
        if _measure(packet) > max_bytes:
            raise ValueError("budget cannot fit packet metadata and query")
        covered = set()
        for page in knowledge:
            if len(packet["knowledge"]) >= top_k:
                break
            previous = copy.deepcopy(packet)
            packet["knowledge"].append(page)
            packet["omitted_knowledge"] -= 1
            packet["requires_review"] |= page["requires_review"]
            packet["status"] = "ready"
            if _measure(packet) > max_bytes:
                packet = previous
                continue
            covered.update(r["memory_id"] for r in page["evidence_memories"])
        by_id = {r["memory_id"]: r for r in rows}
        for hit in atomic:
            if len(packet["knowledge"]) + len(packet["memories"]) >= top_k:
                break
            if hit["memory_id"] in covered:
                continue
            previous = copy.deepcopy(packet)
            # Full index record includes body, source identity, status and successor.
            packet["memories"].append(dict(by_id[hit["memory_id"]], score=hit["score"]))
            packet["requires_review"] |= hit["status"] != "现行" or bool(packet["omitted_knowledge"])
            packet["status"] = "ready"
            if _measure(packet) > max_bytes:
                packet = previous
        _measure(packet)
        return packet

    def export(self, destination):
        """Create an explicit read-only Markdown snapshot in a NEW directory.

        No exported Markdown is used as a source by search or compilation.
        A manifest is written last; an interrupted export is not a complete view.
        """
        rows, source, state = self._snapshot()
        destination = Path(destination).expanduser()
        if destination.exists() or destination.is_symlink():
            raise ValueError("export destination must not exist")
        # Do not create snapshots inside managed atomic/compiled memory.
        try:
            destination.resolve().relative_to(self.memory.base.resolve())
        except ValueError:
            pass
        else:
            raise ValueError("export outside managed memory directory")
        destination.mkdir(parents=False, exist_ok=False)
        index = ["# Knowledge snapshot", "", "Derived, untrusted data. This export does not update itself.",
                 "Use `chat-distiller wiki status` to check freshness against the live memory source.",
                 "", "Source SHA-256: `" + source + "`", ""]
        files = {}
        for topic, versions in sorted(state["pages"].items()):
            page = versions[-1]
            proposal = page["proposal"]
            freshness, _ = self._freshness(page, source, rows)
            filename = page["knowledge_id"] + ".md"
            lines = ["# " + escape(proposal["title"]), "", "Knowledge ID: `" + page["knowledge_id"] + "`",
                     "", f"Revision: {page['revision']} | Freshness at export: **{freshness}**", "",
                     "Citations validate literal memory excerpts, not factual truth or entailment.", ""]
            by_id = {r["memory_id"]: r for r in page["dependencies"]}
            for status, heading in (("current", "Current"), ("disputed", "Open disputes"), ("historical", "History")):
                lines += ["## " + heading, ""]
                for claim in proposal["claims"]:
                    if claim["status"] != status:
                        continue
                    # Escape HTML from untrusted memory; Markdown remains data for
                    # the reader, never instructions to execute.
                    lines += [escape(claim["text"]), "", "Origin: `" + claim["origin"] + "`", ""]
                    for evidence in claim["evidence"]:
                        card = by_id[evidence["memory_id"]]
                        lines += ["- Memory `" + card["memory_id"] + "`, source session `" + escape(card["source_session"]) + "`",
                                  "  Quote: " + escape(evidence["quote"]).replace("\n", " "), ""]
            lines += ["## Related pages", ""]
            for key, identity in sorted(page["related"].items()):
                lines += [f"- [{key}]({identity}.md)"]
            backlinks = [p[-1] for p in state["pages"].values() if topic in p[-1]["related"]]
            lines += ["", "## Backlinks", ""]
            for linked in backlinks:
                lines += [f"- [{linked['proposal']['topic']}]({linked['knowledge_id']}.md)"]
            files[filename] = "\n".join(lines) + "\n"
            index.append(f"- [{topic}]({filename}) | {freshness} | revision {page['revision']}")
        files["index.md"] = "\n".join(index) + "\n"
        files["log.md"] = "# Compilation log\n\n" + "\n".join(
            f"- Commit {e['revision']}: {e['topic']}, page revision {e['page_revision']}, `{e['page_sha256']}`" for e in state["log"]) + "\n"
        import hashlib
        for name, content in files.items():
            (destination / name).write_text(content, encoding="utf-8")
        manifest = {"schema_version": 1, "source_sha256": source, "wiki_revision": state["revision"],
                    "warning": "point_in_time_export_not_live_authority",
                    "files": {name: hashlib.sha256(content.encode("utf-8")).hexdigest() for name, content in files.items()}}
        (destination / "manifest.json").write_text(canonical(manifest) + "\n", encoding="utf-8")
        return {"ok": True, "pages": len(state["pages"]), "destination": str(destination), "manifest": manifest}
