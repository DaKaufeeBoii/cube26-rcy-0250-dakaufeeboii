"""
Official Evidence Contract adapter for Recovery Manager (Track #5).
Conforms to CUBE Evidence Contract v1.0 specifications.
Implements handle(request) -> AgentOutput, canonical content hashing,
strict multi-tenancy validation, and fail-open resilience.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from .models import (
    FeeCharge,
    OperationalEvidence,
    ReimbursementRecord,
    AssessmentType,
    ClaimStatus,
    ManagerType
)
from .store import EvidenceStore
from .engine import RecoveryEngine
from .parser import _map_manager_type, parse_fee_charges_from_json

AGENT_ID = "recovery-manager@1.0.0"
STAGE = "recovery"
MODEL_INFO = {
    "name": "recovery-manager",
    "version": "1.0.0",
    "provider": "deterministic-rules-engine",
    "calls": 1
}

POSITION_TO_VERDICT = {
    "CONTRADICTS": "FAIL",
    "SUPPORTS": "PASS",
    "SILENT": "UNCERTAIN",
    "UNCERTAIN": "UNCERTAIN",
    "DUPLICATE": "FAIL",
    "ALREADY_REIMBURSED": "PASS"
}


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical_json(data: Any) -> str:
    """Return compact, sorted-key canonical JSON string."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_content_hash(record_dict: Dict[str, Any]) -> str:
    """
    Computes SHA-256 hash of canonical JSON excluding 'content_hash' and 'overrides'.
    Enforces Evidence Contract Section 10.
    """
    cleaned = {
        k: v for k, v in record_dict.items()
        if k not in ("content_hash", "overrides")
    }
    canonical = canonical_json(cleaned)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def convert_previous_evidence(
    previous_evidence: List[Dict[str, Any]],
    default_org_id: Optional[str] = None,
    default_unit_id: Optional[str] = None,
    default_shipment_id: Optional[str] = None
) -> List[OperationalEvidence]:
    """
    Translates upstream Evidence Records from previous stages (Receiving, Prep, Pack, Returns)
    into Recovery Manager OperationalEvidence domain models.
    """
    operational_records: List[OperationalEvidence] = []

    for item in previous_evidence:
        record_id = item.get("record_id") or item.get("evidence_id") or "EVD-UNKNOWN"
        raw_stage = item.get("stage") or item.get("agent_id") or ""
        manager = _map_manager_type(raw_stage)
        
        subj = item.get("subject", {})
        org_id = subj.get("org_id") or item.get("org_id") or default_org_id
        unit_id = subj.get("unit_id") or subj.get("subject_id") or item.get("unit_id") or default_unit_id
        
        refs = subj.get("refs", {}) if isinstance(subj, dict) else {}
        shipment_id = (
            refs.get("fba_shipment_id") or refs.get("shipment_id") or
            item.get("fba_shipment_id") or item.get("shipment_id") or default_shipment_id
        )
        order_id = refs.get("order_id") or item.get("order_id")
        sku = refs.get("sku") or item.get("sku")

        timestamp = item.get("captured_at") or item.get("produced_at") or utcnow_iso()
        details = item.get("details") or item.get("payload") or {}
        if not isinstance(details, dict):
            details = {"info": str(details)}

        media = []
        for inp in item.get("inputs", []):
            if isinstance(inp, dict) and "ref" in inp:
                media.append(inp["ref"])
            elif isinstance(inp, str):
                media.append(inp)
        if not media and "media_references" in item:
            media = item["media_references"]

        # If previous record has individual checks, convert each check into an operational evidence entry
        checks = item.get("checks", [])
        if checks:
            for ck in checks:
                check_key = ck.get("check_key") or "general"
                verdict = ck.get("verdict") or "PASS"
                check_details = dict(details)
                if ck.get("observed"):
                    check_details["observed"] = ck["observed"]
                if ck.get("detail"):
                    check_details["check_detail"] = ck["detail"]
                
                check_media = list(media)
                for ref in ck.get("evidence_refs", []):
                    if ref not in check_media:
                        check_media.append(ref)

                op_ev = OperationalEvidence(
                    evidence_id=f"{record_id}:{check_key}",
                    org_id=org_id,
                    manager=manager,
                    shipment_id=shipment_id,
                    order_id=order_id,
                    sku=sku,
                    unit_id=unit_id,
                    timestamp=timestamp,
                    activity=f"{manager.value} ({check_key})",
                    check_type=check_key,
                    status=verdict,
                    details=check_details,
                    media_references=check_media,
                    notes=ck.get("detail") or item.get("decision", {}).get("reason")
                )
                operational_records.append(op_ev)
        else:
            # Composite record fallback
            decision = item.get("decision", {})
            status = decision.get("verdict") or item.get("status") or "PASS"
            op_ev = OperationalEvidence(
                evidence_id=record_id,
                org_id=org_id,
                manager=manager,
                shipment_id=shipment_id,
                order_id=order_id,
                sku=sku,
                unit_id=unit_id,
                timestamp=timestamp,
                activity=f"{manager.value} Stage Completion",
                check_type="general",
                status=status,
                details=details,
                media_references=media,
                notes=decision.get("reason")
            )
            operational_records.append(op_ev)

    return operational_records


def build_evidence_record(
    request: Dict[str, Any],
    checks: List[Dict[str, Any]],
    charges_payload: List[Dict[str, Any]],
    claimable_usd: float,
    unclaimable_charges: List[Dict[str, Any]],
    verdict: str,
    outcome: str,
    reason: str,
    captured_at: str,
    upstream_refs: List[str]
) -> Dict[str, Any]:
    """Constructs a fully-compliant EvidenceRecord according to Section 3 of Evidence Contract."""
    subject = request.get("subject", {})
    subject_id = subject.get("subject_id") or subject.get("unit_id") or "UNKNOWN"
    org_id = subject.get("org_id") or "default_org"
    workflow_id = request.get("workflow_id") or f"WF-{org_id}-{subject_id}"

    record = {
        "schema_version": "1.0",
        "record_id": f"RCY-{subject_id}",
        "workflow_id": workflow_id,
        "stage": STAGE,
        "agent_id": AGENT_ID,
        "subject": subject,
        "status": "completed",
        "captured_at": captured_at,
        "produced_at": utcnow_iso(),
        "latency_ms": 15,
        "model": MODEL_INFO,
        "inputs": request.get("inputs", []),
        "checks": checks,
        "decision": {
            "verdict": verdict,
            "outcome": outcome,
            "confidence": 1.0,
            "reason": reason,
            "needs_human": False
        },
        "payload": {
            "charges": charges_payload,
            "claimable_usd": round(claimable_usd, 2),
            "unclaimable": unclaimable_charges
        },
        "upstream_refs": sorted(list(set(upstream_refs))),
        "overrides": [],
        "error": None
    }
    record["content_hash"] = compute_content_hash(record)
    return record


def build_agent_output(
    record: Dict[str, Any],
    next_step: str = "complete"
) -> Dict[str, Any]:
    """Wraps EvidenceRecord into AgentOutput envelope."""
    decision = record.get("decision", {})
    return {
        "agent_id": AGENT_ID,
        "stage": STAGE,
        "status": record.get("status", "completed"),
        "verdict": decision.get("verdict", "UNCERTAIN"),
        "confidence": decision.get("confidence", 1.0),
        "timestamp": record.get("produced_at", utcnow_iso()),
        "model": MODEL_INFO,
        "error": record.get("error"),
        "next_step_recommendation": next_step,
        "evidence": record
    }


def build_pending_output(
    request: Dict[str, Any],
    error_code: str,
    error_message: str,
    retryable: bool = True
) -> Dict[str, Any]:
    """Fail-open error handler returning a pending review AgentOutput."""
    subject = request.get("subject", {})
    subject_id = subject.get("subject_id") or subject.get("unit_id") or "UNKNOWN"
    org_id = subject.get("org_id") or "default_org"
    workflow_id = request.get("workflow_id") or f"WF-{org_id}-{subject_id}"

    record = {
        "schema_version": "1.0",
        "record_id": f"RCY-{subject_id}",
        "workflow_id": workflow_id,
        "stage": STAGE,
        "agent_id": AGENT_ID,
        "subject": subject,
        "status": "pending",
        "captured_at": utcnow_iso(),
        "produced_at": utcnow_iso(),
        "latency_ms": 0,
        "model": MODEL_INFO,
        "inputs": request.get("inputs", []),
        "checks": [],
        "decision": {
            "verdict": "UNCERTAIN",
            "outcome": "pending_review",
            "confidence": 0.0,
            "reason": f"Agent exception: {error_message}",
            "needs_human": True
        },
        "payload": {
            "error_code": error_code,
            "error_message": error_message,
            "charges": [],
            "claimable_usd": 0.0,
            "unclaimable": []
        },
        "upstream_refs": [],
        "overrides": [],
        "error": {
            "code": error_code,
            "message": error_message,
            "retryable": retryable
        }
    }
    record["content_hash"] = compute_content_hash(record)
    return {
        "agent_id": AGENT_ID,
        "stage": STAGE,
        "status": "pending",
        "verdict": "UNCERTAIN",
        "confidence": 0.0,
        "timestamp": record["produced_at"],
        "model": MODEL_INFO,
        "error": record["error"],
        "next_step_recommendation": "review",
        "evidence": record
    }


def handle_agent_request(
    request: Dict[str, Any],
    sample_fee_csv_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Main entry point fulfilling the Evidence Contract handle(request) -> AgentOutput.
    Supports tenancy verification, upstream evidence matching, zero-amount detection,
    and fail-open fault tolerance.
    """
    try:
        subject = request.get("subject")
        if not subject or not isinstance(subject, dict):
            raise LookupError("Malformed request: 'subject' must be a non-empty dictionary.")

        org_id = subject.get("org_id")
        subject_id = subject.get("subject_id") or subject.get("unit_id")
        if not org_id or not subject_id:
            raise LookupError(f"Tenancy error: subject missing 'org_id' or 'subject_id' in {subject}")

        # Extract charge fee lines from request inputs or fallback sample CSV
        raw_inputs = request.get("inputs", [])
        charges: List[FeeCharge] = []

        if raw_inputs:
            charges = parse_fee_charges_from_json(raw_inputs)
        elif sample_fee_csv_path and sample_fee_csv_path.exists():
            from .parser import parse_fee_charges_from_csv
            all_charges = parse_fee_charges_from_csv(sample_fee_csv_path.read_text(encoding="utf-8"))
            # Filter charges for this subject and tenant
            charges = [
                c for c in all_charges
                if (c.unit_id == subject_id or c.shipment_id == subject_id) and
                   (c.org_id is None or c.org_id == org_id)
            ]

        # Ingest upstream evidence
        refs = subject.get("refs", {}) if isinstance(subject.get("refs"), dict) else {}
        fba_shipment = refs.get("fba_shipment_id") or refs.get("shipment_id") or subject.get("fba_shipment_id") or subject.get("shipment_id")
        previous_evidence = request.get("previous_evidence", [])
        
        operational_records = convert_previous_evidence(
            previous_evidence,
            default_org_id=org_id,
            default_unit_id=subject_id,
            default_shipment_id=fba_shipment
        )

        # Build store and evaluate
        store = EvidenceStore()
        store.add_evidence_batch(operational_records)
        engine = RecoveryEngine(store)

        # Ensure charges have org_id, unit_id, and shipment_id populated from subject if omitted on line item
        for c in charges:
            if not c.org_id:
                c.org_id = org_id
            if not c.unit_id:
                c.unit_id = subject.get("unit_id") or subject.get("subject_id")
            if not c.shipment_id:
                c.shipment_id = fba_shipment

        dossier = engine.evaluate_charges(charges)

        # Convert RecoveryResults to Contract Checks
        checks: List[Dict[str, Any]] = []
        charges_payload: List[Dict[str, Any]] = []
        claimable_usd = 0.0
        unclaimable: List[Dict[str, Any]] = []
        upstream_refs: List[str] = []

        for item in previous_evidence:
            rec_id = item.get("record_id")
            if rec_id:
                upstream_refs.append(rec_id)

        for res in dossier.results:
            pos = "SILENT"
            if res.assessment in (AssessmentType.CONTRADICTED, AssessmentType.DUPLICATE):
                pos = "CONTRADICTS"
            elif res.assessment in (AssessmentType.SUPPORTED, AssessmentType.ALREADY_REIMBURSED):
                pos = "SUPPORTS"
            elif res.assessment == AssessmentType.UNCERTAIN:
                pos = "UNCERTAIN"

            verdict = POSITION_TO_VERDICT.get(pos, "UNCERTAIN")
            evidence_ids = [m.evidence.evidence_id.split(":")[0] for m in res.supporting_evidence]
            if evidence_ids:
                upstream_refs.extend(evidence_ids)

            ck_key = f"charge_{res.charge.charge_id.lower().replace('-', '_')}"
            checks.append({
                "check_key": ck_key,
                "verdict": verdict,
                "confidence": res.confidence,
                "expected": "charge supported by evidence",
                "observed": pos,
                "detail": res.claim_rationale,
                "evidence_refs": evidence_ids,
                "uncertain_reason": "insufficient_evidence" if verdict == "UNCERTAIN" else None
            })

            charge_entry = {
                "line_id": res.charge.charge_id,
                "charge_type": res.charge.fee_type,
                "amount_usd": res.charge.amount,
                "position": pos,
                "reason": res.claim_rationale,
                "evidence_record_ids": evidence_ids
            }
            charges_payload.append(charge_entry)

            if pos == "CONTRADICTS":
                claimable_usd += res.potential_claim_amount
            else:
                unclaimable.append(charge_entry)

        # Decision Roll-Up according to Evidence Contract Section 8
        has_claim = any(c["position"] == "CONTRADICTS" for c in charges_payload)
        has_silent = any(c["position"] in ("SILENT", "UNCERTAIN") for c in charges_payload)

        if has_claim:
            decision_verdict = "FAIL"
            decision_outcome = "claim_recommended"
        elif has_silent:
            decision_verdict = "UNCERTAIN"
            decision_outcome = "insufficient_evidence"
        else:
            decision_verdict = "PASS" if charges_payload else "UNCERTAIN"
            decision_outcome = "no_claim" if charges_payload else "insufficient_evidence"

        dates = [c.charge_date for c in charges if c.charge_date]
        captured_at = max(dates) + "T00:00:00Z" if dates else utcnow_iso()

        reason = f"recovery: {len(charges_payload)} charge(s) evaluated, {sum(1 for c in charges_payload if c['position'] == 'CONTRADICTS')} contradicted"

        evidence_record = build_evidence_record(
            request=request,
            checks=checks,
            charges_payload=charges_payload,
            claimable_usd=claimable_usd,
            unclaimable_charges=unclaimable,
            verdict=decision_verdict,
            outcome=decision_outcome,
            reason=reason,
            captured_at=captured_at,
            upstream_refs=upstream_refs
        )

        return build_agent_output(evidence_record, next_step="complete")

    except LookupError:
        raise
    except Exception as exc:
        return build_pending_output(request, error_code="agent_exception", error_message=str(exc))
