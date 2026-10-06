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
from .contract import (
    handle_agent_request,
    compute_content_hash,
    canonical_json,
    deterministic_record_id,
    apply_overrides,
    STAGE,
    AGENT_ID,
    MODEL_INFO,
)

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
    "canonical_json",
    "deterministic_record_id",
    "apply_overrides",
    "STAGE",
    "AGENT_ID",
    "MODEL_INFO",
]


# Round 3 agent interface: handle(request: dict) -> dict
# Thin adapter around the existing RecoveryEngine; orchestrator must not
# depend on internal classes or DB implementation.
def handle(request: dict) -> dict:
    return handle_agent_request(request)
