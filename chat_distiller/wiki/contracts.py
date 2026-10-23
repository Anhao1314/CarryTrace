"""Structural knowledge contracts. Literal support is not semantic entailment."""
import hashlib
import json
import re

KINDS = {"system-state", "concept", "decision-synthesis", "playbook", "failure-mode"}
STATUS = {"现行": "current", "已过期": "historical", "有争议": "disputed"}
ORIGINS = {"extract", "synthesis", "inference"}
TOPIC = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
MEMORY_ID = re.compile(r"mem_[0-9a-f]{32}\Z")
KNOWLEDGE_ID = re.compile(r"kn_[0-9a-f]{32}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class WikiIntegrityError(ValueError):
    """The compiled store cannot be consumed; it is never silently repaired."""


class StaleProposalError(ValueError):
    """The proposal targets an older memory snapshot or wiki revision."""


class WikiBusyError(ValueError):
    """A writer lock already exists; do not steal it automatically."""


class CommitUncertainError(OSError):
    """Replacement happened but durability/cleanup failed; inspect before retrying."""


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = value
        return result
    def bad(value):
        raise ValueError("non-finite JSON value: " + value)
    return json.loads(text, object_pairs_hook=pairs, parse_constant=bad)


def fields(value, required, label):
    if not isinstance(value, dict) or set(value) != set(required):
        raise ValueError(label + " has missing or unknown fields")


def text(value, label, limit=10000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or "\x00" in value:
        raise ValueError(label + " must be nonempty text within length limit")
    # Reject lone surrogates before any filesystem operation.
    value.encode("utf-8")
    return value


def topic_key(value):
    if not isinstance(value, str) or len(value) > 64 or not TOPIC.fullmatch(value):
        raise ValueError("topic must be a lowercase ASCII slug (max 64 characters)")
    return value


def classification(cards):
    states = {STATUS[c["status"]] for c in cards}
    return "disputed" if "disputed" in states else "historical" if "historical" in states else "current"


def validate_proposal(proposal, rows):
    fields(proposal, {"schema_version", "topic", "title", "kind", "query", "source_sha256",
                      "wiki_revision", "scope", "claims", "related_topics"}, "proposal")
    if type(proposal["schema_version"]) is not int or proposal["schema_version"] != 1:
        raise ValueError("unsupported proposal schema")
    topic_key(proposal["topic"])
    title = text(proposal["title"], "title", 200)
    if "\n" in title or "\r" in title:
        raise ValueError("title must be one line")
    text(proposal["query"], "query", 2000)
    if not isinstance(proposal["kind"], str) or proposal["kind"] not in KINDS:
        raise ValueError("unknown knowledge kind")
    if not isinstance(proposal["source_sha256"], str) or not DIGEST.fullmatch(proposal["source_sha256"]):
        raise ValueError("invalid source fingerprint")
    if type(proposal["wiki_revision"]) is not int or proposal["wiki_revision"] < 0:
        raise ValueError("wiki_revision must be a nonnegative integer")
    scope = proposal["scope"]
    if not isinstance(scope, list) or not 1 <= len(scope) <= 100:
        raise ValueError("scope must contain 1..100 memory IDs")
    if any(not isinstance(i, str) or not MEMORY_ID.fullmatch(i) for i in scope) or len(set(scope)) != len(scope):
        raise ValueError("invalid or duplicate memory ID in scope")
    by_id = {r["memory_id"]: r for r in rows if r.get("type") == "card"}
    if any(i not in by_id for i in scope):
        raise ValueError("scope references a missing or retired card")
    related = proposal["related_topics"]
    if not isinstance(related, list) or len(related) > 50:
        raise ValueError("related_topics must be a list (max 50)")
    for key in related:
        topic_key(key)
    if len(set(related)) != len(related) or proposal["topic"] in related:
        raise ValueError("duplicate or self-related topic")
    claims = proposal["claims"]
    if not isinstance(claims, list) or not 1 <= len(claims) <= 100:
        raise ValueError("claims must contain 1..100 records")
    represented = set()
    fingerprints = set()
    for claim in claims:
        fields(claim, {"text", "status", "origin", "evidence"}, "claim")
        text(claim["text"], "claim text")
        if not isinstance(claim["origin"], str) or claim["origin"] not in ORIGINS:
            raise ValueError("unknown claim origin")
        evidence = claim["evidence"]
        if not isinstance(evidence, list) or not 1 <= len(evidence) <= 100:
            raise ValueError("each claim needs literal evidence")
        ids = []
        for item in evidence:
            fields(item, {"memory_id", "quote"}, "evidence")
            identity = item["memory_id"]
            if not isinstance(identity, str) or identity not in scope:
                raise ValueError("evidence must reference an in-scope memory, never a wiki page")
            quote = text(item["quote"], "quote")
            if quote not in by_id[identity].get("body", ""):
                raise ValueError("quote is absent from the cited memory body")
            ids.append(identity)
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate evidence memory within claim")
        expected = classification([by_id[i] for i in ids])
        if claim["status"] != expected:
            raise ValueError("claim status would hide historical or disputed support")
        if claim["origin"] == "extract" and (len(evidence) != 1 or claim["text"] != evidence[0]["quote"]):
            raise ValueError("extract must reproduce one literal evidence quote")
        signature = digest(claim)
        if signature in fingerprints:
            raise ValueError("duplicate claim")
        fingerprints.add(signature)
        represented.update(ids)
    if represented != set(scope):
        raise ValueError("all scoped memories must be represented, including disputes and history")
    return proposal
