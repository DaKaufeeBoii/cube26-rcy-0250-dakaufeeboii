"""
Tests for Evidence Contract v1.0 compliance, Multi-Tenancy Isolation,
Findings F-07/F-09/F-10/F-11, and Fail-Open Resilience in Recovery Manager.
"""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from recovery_manager import (
    handle_agent_request,
    compute_content_hash,
    canonical_json,
    EvidenceStore,
    RecoveryEngine,
    AssessmentType,
    FeeCharge,
    OperationalEvidence,
    ManagerType
)
from server import app

client = TestClient(app)


def test_tenancy_isolation_rejection():
    """Ensure mismatched or missing tenant raises LookupError."""
    # Missing org_id
    bad_req_1 = {
        "workflow_id": "WF-TEST-001",
        "stage": "recovery",
        "subject": {
            "subject_id": "UNIT-0014"
        }
    }
    with pytest.raises(LookupError):
        handle_agent_request(bad_req_1)

    # Missing subject
    bad_req_2 = {
        "workflow_id": "WF-TEST-002",
        "stage": "recovery"
    }
    with pytest.raises(LookupError):
        handle_agent_request(bad_req_2)


def test_tenancy_cross_org_evidence_isolation():
    """Ensure evidence from org_demo_alpha is never used to evaluate charges for org_demo_bravo."""
    store = EvidenceStore()
    # Evidence for Alpha
    store.add_evidence(OperationalEvidence(
        evidence_id="EVD-ALPHA-01",
        org_id="org_demo_alpha",
        manager=ManagerType.PREP,
        shipment_id="FBA-100",
        unit_id="UNIT-0001",
        timestamp="2026-06-04T12:00:00Z",
        activity="Polybag Check",
        check_type="packaging",
        status="PASS"
    ))

    # Evidence for Bravo
    store.add_evidence(OperationalEvidence(
        evidence_id="EVD-BRAVO-01",
        org_id="org_demo_bravo",
        manager=ManagerType.PREP,
        shipment_id="FBA-100",
        unit_id="UNIT-0001",
        timestamp="2026-06-04T12:00:00Z",
        activity="Polybag Check",
        check_type="packaging",
        status="FAIL"
    ))

    engine = RecoveryEngine(store)

    # Charge for Alpha
    charge_alpha = FeeCharge(
        charge_id="CHG-A",
        org_id="org_demo_alpha",
        shipment_id="FBA-100",
        unit_id="UNIT-0001",
        fee_type="Packaging defect fee",
        amount=25.00
    )
    dossier_alpha = engine.evaluate_charges([charge_alpha])
    # Should only match Alpha's PASS -> CONTRADICTED
    assert dossier_alpha.results[0].assessment == AssessmentType.CONTRADICTED
    assert dossier_alpha.total_potential_recovery == 25.00

    # Charge for Bravo
    charge_bravo = FeeCharge(
        charge_id="CHG-B",
        org_id="org_demo_bravo",
        shipment_id="FBA-100",
        unit_id="UNIT-0001",
        fee_type="Packaging defect fee",
        amount=25.00
    )
    dossier_bravo = engine.evaluate_charges([charge_bravo])
    # Should only match Bravo's FAIL -> SUPPORTED
    assert dossier_bravo.results[0].assessment == AssessmentType.SUPPORTED
    assert dossier_bravo.total_potential_recovery == 0.00


def test_evidence_contract_standard_execution():
    """Test full handle_agent_request adhering to Evidence Contract v1.0."""
    request = {
        "workflow_id": "WF-org_demo_alpha-UNIT-0014",
        "stage": "recovery",
        "subject": {
            "org_id": "org_demo_alpha",
            "subject_id": "UNIT-0014",
            "unit_id": "UNIT-0014",
            "unit_scope": "unit",
            "refs": {
                "fba_shipment_id": "FBA-DUMMY-101",
                "sku": "SKU-LAMP-LED"
            }
        },
        "inputs": [
            {
                "charge_id": "FEE-0014-1",
                "fee_type": "inbound_defect_fee",
                "reason_description": "Packaging defect reported at inbound scan",
                "amount": 38.00,
                "fba_shipment_id": "FBA-DUMMY-101",
                "sku": "SKU-LAMP-LED"
            }
        ],
        "previous_evidence": [
            {
                "record_id": "PRP-0014",
                "stage": "prep",
                "agent_id": "prep-manager@1.4.0",
                "status": "completed",
                "captured_at": "2026-06-04T12:25:00Z",
                "checks": [
                    {
                        "check_key": "packaging",
                        "verdict": "PASS",
                        "expected": "compliant polybag",
                        "observed": "sealed 2-mil polybag",
                        "detail": "Polybag verified intact and compliant with Amazon requirements.",
                        "evidence_refs": ["UNIT-0014/prep/polybag.jpg"]
                    }
                ],
                "decision": {
                    "verdict": "PASS",
                    "outcome": "compliant"
                }
            }
        ]
    }

    output = handle_agent_request(request)

    assert output["agent_id"] == "recovery-manager@1.0.0"
    assert output["stage"] == "recovery"
    assert output["status"] == "completed"
    assert output["verdict"] == "FAIL"  # FAIL in contract means CONTRADICTS -> claim recommended
    assert output["next_step_recommendation"] == "complete"

    evidence = output["evidence"]
    assert evidence["schema_version"] == "1.0"
    assert evidence["record_id"] == "RCY-UNIT-0014"
    assert evidence["decision"]["outcome"] == "claim_recommended"
    assert evidence["payload"]["claimable_usd"] == 38.00

    # Verify canonical content hash
    assert "content_hash" in evidence
    computed_hash = compute_content_hash(evidence)
    assert evidence["content_hash"] == computed_hash


def test_findings_f07_weight_tier_silent():
    """F-07: fulfilment_fee_weight_tier without scale telemetry must be SILENT."""
    request = {
        "workflow_id": "WF-org_demo_alpha-UNIT-0002",
        "stage": "recovery",
        "subject": {
            "org_id": "org_demo_alpha",
            "subject_id": "UNIT-0002",
            "unit_id": "UNIT-0002",
            "refs": {"fba_shipment_id": "FBA-DUMMY-100"}
        },
        "inputs": [
            {
                "charge_id": "FEE-0002-1",
                "fee_type": "fulfilment_fee_weight_tier",
                "amount": 4.25
            }
        ],
        "previous_evidence": [
            {
                "record_id": "PRP-0002",
                "stage": "prep",
                "checks": [
                    {"check_key": "polybag", "verdict": "PASS"}
                ]
            }
        ]
    }

    output = handle_agent_request(request)
    assert output["verdict"] == "UNCERTAIN"
    ev = output["evidence"]
    assert ev["decision"]["outcome"] == "insufficient_evidence"
    assert ev["payload"]["claimable_usd"] == 0.00
    assert len(ev["payload"]["unclaimable"]) == 1
    assert "F-07" in ev["payload"]["unclaimable"][0]["reason"]


def test_findings_f09_zero_amount_silent():
    """F-09: $0.00 charges are non-claimable and marked SILENT."""
    request = {
        "workflow_id": "WF-org_demo_bravo-UNIT-0003",
        "stage": "recovery",
        "subject": {
            "org_id": "org_demo_bravo",
            "subject_id": "UNIT-0003"
        },
        "inputs": [
            {
                "charge_id": "FEE-0003-1",
                "fee_type": "lost_inbound",
                "amount": 0.00
            }
        ],
        "previous_evidence": []
    }

    output = handle_agent_request(request)
    assert output["verdict"] == "UNCERTAIN"
    ev = output["evidence"]
    assert ev["payload"]["claimable_usd"] == 0.00
    assert "F-09" in ev["payload"]["unclaimable"][0]["reason"]


def test_findings_f10_receiving_shortfall_silent():
    """F-10: Receiving shortfall is supplier-side, not channel-side loss -> SILENT."""
    request = {
        "workflow_id": "WF-org_demo_alpha-UNIT-0010",
        "stage": "recovery",
        "subject": {
            "org_id": "org_demo_alpha",
            "subject_id": "UNIT-0010"
        },
        "inputs": [
            {
                "charge_id": "FEE-0010-1",
                "fee_type": "lost_inbound",
                "amount": 45.00
            }
        ],
        "previous_evidence": [
            {
                "record_id": "RCV-0010",
                "stage": "receiving",
                "checks": [
                    {"check_key": "unit_count", "verdict": "FAIL", "detail": "Shortage at supplier receiving"}
                ]
            }
        ]
    }

    output = handle_agent_request(request)
    assert output["verdict"] == "UNCERTAIN"
    ev = output["evidence"]
    assert ev["payload"]["claimable_usd"] == 0.00
    assert "F-10" in ev["payload"]["unclaimable"][0]["reason"]


def test_findings_f11_returns_intact_contradicts():
    """F-11: Returns record showing PASS contradicts refund_issued_item_not_returned."""
    request = {
        "workflow_id": "WF-org_demo_alpha-UNIT-0014",
        "stage": "recovery",
        "subject": {
            "org_id": "org_demo_alpha",
            "subject_id": "UNIT-0014"
        },
        "inputs": [
            {
                "charge_id": "FEE-0014-RET",
                "fee_type": "refund_issued_item_not_returned",
                "amount": 30.00
            }
        ],
        "previous_evidence": [
            {
                "record_id": "RTN-0014",
                "stage": "returns",
                "checks": [
                    {"check_key": "return_inspection", "verdict": "PASS", "detail": "Item received intact in original box"}
                ]
            }
        ]
    }

    output = handle_agent_request(request)
    assert output["verdict"] == "FAIL"  # CONTRADICTS -> claim recommended
    ev = output["evidence"]
    assert ev["decision"]["outcome"] == "claim_recommended"
    assert ev["payload"]["claimable_usd"] == 30.00


def test_api_agent_handle_endpoint():
    """Test FastAPI /api/agent/handle endpoint integration."""
    payload = {
        "workflow_id": "WF-org_demo_alpha-UNIT-0014",
        "stage": "recovery",
        "subject": {
            "org_id": "org_demo_alpha",
            "subject_id": "UNIT-0014",
            "unit_id": "UNIT-0014"
        },
        "inputs": [
            {
                "charge_id": "FEE-0014-1",
                "fee_type": "Packaging defect fee",
                "amount": 20.00
            }
        ],
        "previous_evidence": [
            {
                "record_id": "PRP-0014",
                "stage": "prep",
                "checks": [
                    {"check_key": "packaging", "verdict": "PASS"}
                ]
            }
        ]
    }

    resp = client.post("/api/agent/handle", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["stage"] == "recovery"
    assert data["status"] == "completed"
    assert data["verdict"] == "FAIL"
    assert data["evidence"]["payload"]["claimable_usd"] == 20.00
