"""Optional compiled knowledge layer; atomic memory remains authoritative."""
from .store import KnowledgeStore
from .contracts import WikiIntegrityError, StaleProposalError, WikiBusyError, CommitUncertainError

__all__ = ["KnowledgeStore", "WikiIntegrityError", "StaleProposalError", "WikiBusyError", "CommitUncertainError"]
