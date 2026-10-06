"""Structured Agent Memory and optional compiled knowledge API. No model service or import-time I/O."""
from .store import MemoryStore, MemoryIntegrityError, MemoryNotFoundError
from .recovery import serialize_packet

__version__ = "0.4.0"
__all__ = ["MemoryStore", "MemoryIntegrityError", "MemoryNotFoundError", "serialize_packet"]

from .wiki import KnowledgeStore, WikiIntegrityError, StaleProposalError, WikiBusyError, CommitUncertainError
__all__ += ["KnowledgeStore", "WikiIntegrityError", "StaleProposalError", "WikiBusyError", "CommitUncertainError"]

from .gateway import ContextGateway, GatewayError
__all__ += ["ContextGateway", "GatewayError"]
