"""Single-file compiled state with cooperative locking and atomic replacement.

This is not a transaction with the pre-existing multi-file memory renderer.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import tempfile

from .contracts import (CommitUncertainError, WikiBusyError, WikiIntegrityError,
                        KNOWLEDGE_ID, canonical, digest, fields, strict_json,
                        validate_proposal)

MAX_STATE_BYTES = 64 * 1024 * 1024


def empty_state():
    return {"schema_version": 1, "revision": 0, "pages": {}, "log": []}


def validate_state(state):
    fields(state, {"schema_version", "revision", "pages", "log"}, "wiki state")
    if type(state["schema_version"]) is not int or state["schema_version"] != 1:
        raise ValueError("unsupported wiki schema")
    if type(state["revision"]) is not int or state["revision"] < 0:
        raise ValueError("invalid wiki revision")
    if not isinstance(state["pages"], dict) or not isinstance(state["log"], list):
        raise ValueError("malformed page registry or log")
    if len(state["log"]) != state["revision"]:
        raise ValueError("wiki log/revision mismatch")
    identities, revisions = set(), {}
    for topic, versions in state["pages"].items():
        if not isinstance(versions, list) or not versions:
            raise ValueError("empty page history")
        identity = versions[0]["knowledge_id"]
        if not isinstance(identity, str) or not KNOWLEDGE_ID.fullmatch(identity) or identity in identities:
            raise ValueError("invalid or duplicate knowledge identity")
        identities.add(identity)
        previous_commit = 0
        for n, page in enumerate(versions, 1):
            fields(page, {"knowledge_id", "revision", "commit_revision", "proposal", "dependencies", "related"}, "page")
            if type(page["revision"]) is not int or page["revision"] != n or page["knowledge_id"] != identity:
                raise ValueError("page identity/revision drift")
            if type(page["commit_revision"]) is not int or not previous_commit < page["commit_revision"] <= state["revision"]:
                raise ValueError("invalid page commit revision")
            previous_commit = page["commit_revision"]
            proposal = page["proposal"]
            dependencies = page["dependencies"]
            if not isinstance(dependencies, list):
                raise ValueError("malformed dependency snapshots")
            validate_proposal(proposal, dependencies)
            if proposal["wiki_revision"] != page["commit_revision"] - 1:
                raise ValueError("proposal/commit revision mismatch")
            if proposal["topic"] != topic or sorted(r["memory_id"] for r in dependencies) != sorted(proposal["scope"]):
                raise ValueError("dependency snapshot/scope mismatch")
            for row in dependencies:
                if row["type"] != "card" or not isinstance(row["source_session"], str) or not isinstance(row["source_memory_id"], str):
                    raise ValueError("dependency provenance missing")
            if not isinstance(page["related"], dict) or set(page["related"]) != set(proposal["related_topics"]):
                raise ValueError("related topic mapping differs from proposal")
            if page["commit_revision"] in revisions:
                raise ValueError("duplicate commit revision")
            revisions[page["commit_revision"]] = (topic, page)
    if set(revisions) != set(range(1, state["revision"] + 1)):
        raise ValueError("page history/log gap")
    for n, event in enumerate(state["log"], 1):
        topic, page = revisions[n]
        expected = {"revision": n, "topic": topic, "knowledge_id": page["knowledge_id"],
                    "page_revision": page["revision"], "page_sha256": digest(page)}
        if event != expected:
            raise ValueError("compilation log differs from page history")
    for versions in state["pages"].values():
        for page in versions:
            for topic, identity in page["related"].items():
                if topic not in state["pages"] or state["pages"][topic][0]["knowledge_id"] != identity:
                    raise ValueError("dangling related knowledge page")
    return state


class StateFile:
    def __init__(self, memory):
        self.memory = memory
        self.root = memory.base / ".chat-distiller" / "wiki"
        self.path = self.root / "state.json"
        self.lock = self.root / "writer.lock"

    def check_paths(self):
        for path in (self.root.parent, self.root, self.path, self.lock):
            self.memory._inside(path)
            if path.is_symlink():
                raise WikiIntegrityError("wiki managed paths must not be symlinks")

    def read(self):
        try:
            self.check_paths()
            if not self.root.exists():
                return empty_state()
            # An existing wiki directory with no state could be a failed first
            # publication or deleted authority. Never silently initialize it.
            if not self.path.is_file():
                raise WikiIntegrityError("wiki state missing; inspect interrupted initialization or restore backup")
            if self.path.stat().st_size > MAX_STATE_BYTES:
                raise WikiIntegrityError("wiki state exceeds supported 64 MiB limit")
            envelope = strict_json(self.path.read_text(encoding="utf-8"))
            fields(envelope, {"payload", "sha256"}, "wiki envelope")
            if digest(envelope["payload"]) != envelope["sha256"]:
                raise WikiIntegrityError("wiki checksum mismatch")
            return validate_state(envelope["payload"])
        except (ValueError, OSError, KeyError, TypeError, AttributeError, UnicodeError) as exc:
            raise WikiIntegrityError(str(exc)) from exc

    @contextmanager
    def writer(self):
        self.check_paths()
        created = False
        if not self.root.exists():
            try:
                self.root.mkdir()
                created = True
            except FileExistsError:
                pass
        fd = None
        try:
            fd = os.open(str(self.lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise WikiBusyError("wiki writer lock exists; do not remove while a writer is active") from exc
        self._published = False
        try:
            os.write(fd, (str(os.getpid()) + "\n").encode("ascii"))
            os.close(fd)
            fd = None
            # The only legitimate empty state in an existing directory is the
            # directory this writer itself created under an exclusive lock.
            yield empty_state() if created else self.read()
        finally:
            if fd is not None:
                os.close(fd)
            try:
                self.lock.unlink()
            except OSError as exc:
                if self._published:
                    raise CommitUncertainError("wiki was published but writer-lock cleanup failed; inspect before retrying") from exc
                raise
            if created and not self.path.exists():
                try:
                    self.root.rmdir()
                except OSError:
                    pass  # Unexpected leftovers are retained for inspection.

    def replace(self, state):
        self.check_paths()
        validate_state(state)
        data = (canonical({"payload": state, "sha256": digest(state)}) + "\n").encode("utf-8")
        if len(data) > MAX_STATE_BYTES:
            raise ValueError("compiled wiki exceeds supported 64 MiB limit")
        fd, name = tempfile.mkstemp(prefix="candidate-", suffix=".tmp", dir=self.root)
        temporary = Path(name)
        published = False
        try:
            with os.fdopen(fd, "wb") as file:
                file.write(data)
                file.flush()
                os.fsync(file.fileno())
            os.replace(str(temporary), str(self.path))
            published = True
            self._published = True
            if os.name == "posix":
                directory = os.open(str(self.root), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
        except OSError as exc:
            if published:
                raise CommitUncertainError("wiki replacement occurred; durability unconfirmed; inspect state before retrying") from exc
            raise
        finally:
            if temporary.exists():
                temporary.unlink()
