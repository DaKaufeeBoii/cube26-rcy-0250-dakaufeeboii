"""
Recovery Manager package
Turn evidence into financial recovery.
"""

from .models import (
    ManagerType,
    AssessmentType,
    ClaimStatus,
    FeeCharge,
    ReimbursementRecord,
    OperationalEvidence,
    EvidenceMatch,
    RecoveryResult,
    RecoveryDossier
)
from .store import EvidenceStore
from .engine import RecoveryEngine
from .contract import handle_agent_request, compute_content_hash, canonical_json

__all__ = [
    "ManagerType",
    "AssessmentType",
    "ClaimStatus",
    "FeeCharge",
    "ReimbursementRecord",
    "OperationalEvidence",
    "EvidenceMatch",
    "RecoveryResult",
    "RecoveryDossier",
    "EvidenceStore",
    "RecoveryEngine",
    "handle_agent_request",
    "compute_content_hash",
    "canonical_json"
]
