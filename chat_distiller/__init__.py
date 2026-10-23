"""Structured Agent Memory and optional compiled knowledge API. No model service or import-time I/O."""
from .store import MemoryStore, MemoryIntegrityError, MemoryNotFoundError
from .recovery import serialize_packet

__version__ = "0.6.0"
__all__ = ["MemoryStore", "MemoryIntegrityError", "MemoryNotFoundError", "serialize_packet"]

from .wiki import KnowledgeStore, WikiIntegrityError, StaleProposalError, WikiBusyError, CommitUncertainError
__all__ += ["KnowledgeStore", "WikiIntegrityError", "StaleProposalError", "WikiBusyError", "CommitUncertainError"]

from .gateway import ContextGateway, GatewayError
__all__ += ["ContextGateway", "GatewayError"]

from .claims import ClaimStore, ClaimStoreBusy, ClaimStoreError
__all__ += ["ClaimStore", "ClaimStoreBusy", "ClaimStoreError"]

from .context import (
    ContextError, EvidenceHit, EvidenceRetriever, JsonlEvidenceIndex,
    StatusAwareRetriever, build_context, serialize_context, suggest_claim,
)
__all__ += ["ContextError", "EvidenceHit", "EvidenceRetriever", "JsonlEvidenceIndex",
            "StatusAwareRetriever", "build_context", "serialize_context", "suggest_claim"]
