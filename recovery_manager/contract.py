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
    "calls": 0,
    "cost_usd": 0.0
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


def deterministic_record_id(request: Dict[str, Any]) -> str:
    """
    Round 3 idempotency: same request_id -> same record_id.
    Seed includes request_id, workflow_id, stage and subject identity.
    Do NOT derive solely from unit_id.
    """
    subject = request.get("subject", {}) if isinstance(request.get("subject"), dict) else {}
    subject_id = subject.get("subject_id") or subject.get("unit_id") or "UNKNOWN"
    org_id = subject.get("org_id") or "default_org"
    workflow_id = request.get("workflow_id") or request.get("workflowId") or f"WF-{org_id}-{subject_id}"
    request_id = request.get("request_id") or request.get("requestId") or request.get("id") or workflow_id
    seed = f"{request_id}:{workflow_id}:{STAGE}:{org_id}:{subject_id}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12].upper()
    return f"RCY-{digest}-{subject_id}"


def apply_overrides(
    previous_evidence: List[Dict[str, Any]],
    overrides: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Apply upstream overrides without deleting original evidence.

    Each override must contain at minimum:
      - original record/check reference (record_id / check_key)
      - new decision / verdict
      - actor, reason, timestamp

    Returns (patched_evidence, normalized_overrides_for_output).
    Original evidence trail is preserved in the second element and later
    stored in record['overrides'].
    """
    if not overrides:
        return previous_evidence, []

    # Deep copy so original list is preserved
    patched = json.loads(json.dumps(previous_evidence))
    normalized: List[Dict[str, Any]] = []

    # Build index by record_id
    by_id: Dict[str, Dict[str, Any]] = {}
    for rec in patched:
        rid = rec.get("record_id") or rec.get("evidence_id")
        if rid:
            by_id[rid] = rec

    for ov in overrides:
        # Accept multiple naming conventions
        original_ref = ov.get("original_record_id") or ov.get("record_id") or ov.get("original_record") or ov.get("target_record_id")
        check_key = ov.get("check_key") or ov.get("original_check_key")
        new_verdict = ov.get("new_decision") or ov.get("new_verdict") or ov.get("verdict") or ov.get("decision")
        # Normalize new_verdict to string
        if isinstance(new_verdict, dict):
            new_verdict = new_verdict.get("verdict") or new_verdict.get("outcome") or str(new_verdict)
        actor = ov.get("actor") or ov.get("operator_id") or "unknown"
        reason = ov.get("reason") or ov.get("note") or ""
        ts = ov.get("timestamp") or ov.get("overridden_at") or utcnow_iso()

        if not original_ref or not new_verdict:
            # Still record it for audit but skip patching
            normalized.append({
                "original_record_id": original_ref,
                "check_key": check_key,
                "new_verdict": str(new_verdict) if new_verdict else None,
                "actor": actor,
                "reason": reason,
                "timestamp": ts,
                "applied": False,
            })
            continue

        rec = by_id.get(original_ref)
        applied = False
        original_verdict = None
        if rec is not None:
            checks = rec.get("checks")
            if checks and check_key:
                for ck in checks:
                    if ck.get("check_key") == check_key:
                        original_verdict = ck.get("verdict")
                        ck["verdict"] = str(new_verdict).upper()
                        # Keep original for traceability
                        ck["_original_verdict"] = original_verdict
                        ck["_overridden_by"] = actor
                        ck["_override_reason"] = reason
                        ck["_override_timestamp"] = ts
                        applied = True
                        break
                # If check_key not found, add a new check reflecting override
                if not applied:
                    # Do not fabricate evidence, but record override as additional decision
                    # Still preserve trail: add check
                    rec.setdefault("checks", []).append({
                        "check_key": check_key,
                        "verdict": str(new_verdict).upper(),
                        "detail": f"Override by {actor}: {reason}",
                        "evidence_refs": [],
                        "_overridden_by": actor,
                        "_override_reason": reason,
                        "_override_timestamp": ts,
                    })
                    applied = True
            elif checks is None:
                # No checks array; patch decision
                dec = rec.get("decision", {})
                original_verdict = dec.get("verdict")
                dec["verdict"] = str(new_verdict).upper()
                dec["_original_verdict"] = original_verdict
                dec["_overridden_by"] = actor
                rec["decision"] = dec
                applied = True
            else:
                # Empty checks list
                rec["checks"] = [{
                    "check_key": check_key or "general",
                    "verdict": str(new_verdict).upper(),
                    "detail": f"Override by {actor}: {reason}",
                    "evidence_refs": [],
                    "_overridden_by": actor,
                    "_override_reason": reason,
                    "_override_timestamp": ts,
                }]
                applied = True
        normalized.append({
            "original_record_id": original_ref,
            "check_key": check_key,
            "original_verdict": original_verdict,
            "new_verdict": str(new_verdict).upper(),
            "actor": actor,
            "reason": reason,
            "timestamp": ts,
            "applied": applied,
        })

    return patched, normalized


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
    upstream_refs: List[str],
    overrides: Optional[List[Dict[str, Any]]] = None,
    needs_human: bool = False,
) -> Dict[str, Any]:
    """Constructs a fully-compliant EvidenceRecord according to Section 3 of Evidence Contract."""
    subject = request.get("subject", {})
    subject_id = subject.get("subject_id") or subject.get("unit_id") or "UNKNOWN"
    org_id = subject.get("org_id") or "default_org"
    workflow_id = request.get("workflow_id") or f"WF-{org_id}-{subject_id}"

    record = {
        "schema_version": "1.0",
        "record_id": deterministic_record_id(request),
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
            "needs_human": needs_human
        },
        "payload": {
            "charges": charges_payload,
            "claimable_usd": round(claimable_usd, 2),
            "unclaimable": unclaimable_charges
        },
        "upstream_refs": sorted(list(set(upstream_refs))),
        "overrides": overrides or [],
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
    subject = request.get("subject", {}) if isinstance(request.get("subject"), dict) else {}
    subject_id = subject.get("subject_id") or subject.get("unit_id") or "UNKNOWN"
    org_id = subject.get("org_id") or "default_org"
    workflow_id = request.get("workflow_id") or f"WF-{org_id}-{subject_id}"

    record = {
        "schema_version": "1.0",
        "record_id": deterministic_record_id(request),
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
    Main entry point fulfilling handle(request) -> AgentOutput.
    Round 3 compatible:
      - reads request['subject'], request['inputs'], request['previous_evidence'],
        request['context']['overrides']
      - strict tenant isolation at agent boundary
      - deterministic record ids (idempotency)
      - overrides consume latest upstream decision while preserving original trail
      - shared Round 3 schema output with checks named charge_<line_id>
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

        # Strict tenant isolation at agent boundary:
        # request must carry the requesting org; subject must belong to it.
        context = request.get("context", {}) if isinstance(request.get("context"), dict) else {}
        requesting_org = context.get("org_id") or request.get("org_id") or org_id
        if requesting_org and org_id != requesting_org:
            # Security event: do not leak foreign evidence, do not generate claims
            raise LookupError(
                f"Tenant mismatch: requesting org '{requesting_org}' does not own subject "
                f"belonging to '{org_id}'. security_event=wrong_tenant no foreign evidence returned no claim generated"
            )

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

        # Round 3 overrides: request['context']['overrides']
        overrides = context.get("overrides", []) if isinstance(context, dict) else []
        previous_evidence, normalized_overrides = apply_overrides(previous_evidence, overrides or [])

        # Enforce tenant isolation on previous evidence: drop foreign records, do not leak
        filtered_evidence: List[Dict[str, Any]] = []
        dropped_foreign = 0
        for item in previous_evidence:
            subj = item.get("subject", {}) if isinstance(item.get("subject"), dict) else {}
            ev_org = subj.get("org_id") or item.get("org_id")
            if ev_org and ev_org != org_id:
                dropped_foreign += 1
                continue
            filtered_evidence.append(item)
        previous_evidence = filtered_evidence

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
            # Traceability: upstream record -> upstream check -> source evidence -> input/photo hash
            evidence_ids = [m.evidence.evidence_id.split(":")[0] for m in res.supporting_evidence]
            upstream_check_ids = [m.evidence.evidence_id for m in res.supporting_evidence]
            photo_hashes = []
            for m in res.supporting_evidence:
                photo_hashes.extend(m.evidence.media_references)
            if evidence_ids:
                upstream_refs.extend(evidence_ids)

            # Round 3 check naming: exactly one check per fee line: charge_<line_id>
            raw_line = str(res.charge.charge_id).lower().replace('-', '_')
            ck_key = f"charge_{raw_line}"
            checks.append({
                "check_key": ck_key,
                "verdict": verdict,
                "confidence": res.confidence,
                "expected": "charge supported by evidence",
                "observed": pos,
                "detail": res.claim_rationale,
                "evidence_refs": evidence_ids,
                "uncertain_reason": "insufficient_evidence" if verdict == "UNCERTAIN" else None,
                "trace": {
                    "fee_line": res.charge.charge_id,
                    "recovery_check": ck_key,
                    "upstream_records": evidence_ids,
                    "upstream_checks": upstream_check_ids,
                    "source_evidence": [m.evidence.evidence_id for m in res.supporting_evidence],
                    "photo_hashes": photo_hashes,
                    "assessment": res.assessment.value,
                    "claim_status": res.claim_status.value,
                }
            })

            charge_entry = {
                "line_id": res.charge.charge_id,
                "charge_type": res.charge.fee_type,
                "amount_usd": res.charge.amount,
                "position": pos,
                "reason": res.claim_rationale,
                "evidence_record_ids": evidence_ids,
                "upstream_check_ids": upstream_check_ids,
                "photo_hashes": photo_hashes,
                "assessment": res.assessment.value,
                "claim_status": res.claim_status.value,
                "potential_claim_amount": res.potential_claim_amount,
            }
            charges_payload.append(charge_entry)

            if pos == "CONTRADICTS":
                claimable_usd += res.potential_claim_amount
            else:
                unclaimable.append(charge_entry)

        # Decision Roll-Up: map SILENT/CONTRADICTED/SUPPORTED/UNCERTAIN to
        # claim_recommended / no_claim / insufficient_evidence / pending_review
        has_claim = any(c["position"] == "CONTRADICTS" for c in charges_payload)
        has_uncertain = any(c["position"] == "UNCERTAIN" for c in charges_payload)
        has_silent = any(c["position"] == "SILENT" for c in charges_payload)
        has_supported = any(c["position"] == "SUPPORTS" for c in charges_payload)

        needs_human = False
        if has_claim:
            decision_verdict = "FAIL"
            decision_outcome = "claim_recommended"
        elif has_uncertain:
            decision_verdict = "UNCERTAIN"
            decision_outcome = "pending_review"
            needs_human = True
        elif has_silent:
            decision_verdict = "UNCERTAIN"
            decision_outcome = "insufficient_evidence"
        elif has_supported:
            decision_verdict = "PASS"
            decision_outcome = "no_claim"
        else:
            decision_verdict = "UNCERTAIN"
            decision_outcome = "insufficient_evidence"

        dates = [c.charge_date for c in charges if c.charge_date]
        captured_at = max(dates) + "T00:00:00Z" if dates else utcnow_iso()

        reason = f"recovery: {len(charges_payload)} charge(s) evaluated, {sum(1 for c in charges_payload if c['position'] == 'CONTRADICTS')} contradicted"
        if dropped_foreign:
            reason += f"; dropped {dropped_foreign} foreign-tenant evidence record(s)"

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
            upstream_refs=upstream_refs,
            overrides=normalized_overrides,
            needs_human=needs_human,
        )

        return build_agent_output(evidence_record, next_step="complete")

    except LookupError:
        raise
    except Exception as exc:
        return build_pending_output(request, error_code="agent_exception", error_message=str(exc))
