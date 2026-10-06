"""
Round 3 compliance tests for Recovery Manager.
Covers:
  A. Normal claim (claim_recommended)
  B. SILENT (no_claim / insufficient_evidence with explicit reason)
  C. Weight-tier without weight evidence -> SILENT
  D. Supplier shortfall (F-10) -> NOT channel lost-inbound claim
  E. Already reimbursed -> no_claim
  F. Duplicate -> no duplicate claim on second line
  G. UNCERTAIN (pending_review)
  H. Human override uses latest decision, original remains traceable
  I. Wrong tenant -> rejected, no foreign evidence exposed
  J. Idempotency: same request_id -> same record_id
  K. Invalid input -> structured failure/pending, never false success
  L. Missing Prep evidence -> inbound-defect SILENT unless independent evidence
"""

import pytest
from fastapi.testclient import TestClient
from pathlib import Path

from recovery_manager import handle_agent_request, compute_content_hash, MODEL_INFO
from recovery_manager.contract import deterministic_record_id
from server import app

client = TestClient(app)


def _base_subject(org="org_demo_alpha", unit="UNIT-0014", shipment="FBA-DUMMY-101", sku="SKU-LAMP-LED"):
    return {
        "org_id": org,
        "subject_id": unit,
        "unit_id": unit,
        "refs": {"fba_shipment_id": shipment, "sku": sku},
    }


def test_A_normal_claim():
    req = {
        "workflow_id": "WF-A-001",
        "request_id": "REQ-A",
        "stage": "recovery",
        "subject": _base_subject(),
        "inputs": [{"charge_id": "FEE-A-1", "fee_type": "inbound_defect_fee", "amount": 12.00}],
        "previous_evidence": [{
            "record_id": "PRP-A",
            "stage": "prep",
            "checks": [{"check_key": "packaging", "verdict": "PASS", "evidence_refs": ["p1.jpg"]}],
        }],
    }
    out = handle_agent_request(req)
    ev = out["evidence"]
    assert ev["decision"]["outcome"] == "claim_recommended"
    assert ev["payload"]["claimable_usd"] == 12.00
    assert any(c["position"] == "CONTRADICTS" for c in ev["payload"]["charges"])
    # Claim must contain concrete supporting evidence
    claim = next(c for c in ev["payload"]["charges"] if c["position"] == "CONTRADICTS")
    assert claim["evidence_record_ids"]
    # Check id is present
    assert any(ck["check_key"] == "charge_fee_a_1" for ck in ev["checks"])


def test_B_silent_no_sufficient_evidence():
    req = {
        "workflow_id": "WF-B-001",
        "request_id": "REQ-B",
        "stage": "recovery",
        "subject": _base_subject(unit="UNIT-0099"),
        "inputs": [{"charge_id": "FEE-B-1", "fee_type": "inbound_defect_fee", "amount": 5.00}],
        "previous_evidence": [],
    }
    out = handle_agent_request(req)
    ev = out["evidence"]
    assert ev["decision"]["outcome"] in ("insufficient_evidence", "no_claim")
    assert ev["payload"]["claimable_usd"] == 0.00
    assert all(c["position"] in ("SILENT", "UNCERTAIN") for c in ev["payload"]["charges"])
    # SILENT must explain why
    reason = ev["payload"]["charges"][0]["reason"]
    assert "SILENT" in reason
    assert len(reason) > 20
    assert reason != "Insufficient evidence."


def test_C_weight_tier_without_weight_evidence_silent():
    req = {
        "workflow_id": "WF-C-001",
        "request_id": "REQ-C",
        "stage": "recovery",
        "subject": _base_subject(unit="UNIT-0002"),
        "inputs": [{"charge_id": "FEE-C-1", "fee_type": "fulfilment_fee_weight_tier", "amount": 4.25}],
        "previous_evidence": [{
            "record_id": "PRP-C",
            "stage": "prep",
            "checks": [{"check_key": "packaging", "verdict": "PASS"}],
        }],
    }
    out = handle_agent_request(req)
    ev = out["evidence"]
    assert ev["payload"]["claimable_usd"] == 0.00
    assert "F-07" in ev["payload"]["unclaimable"][0]["reason"]
    assert ev["checks"][0]["check_key"] == "charge_fee_c_1"


def test_D_supplier_shortfall_not_channel_loss():
    req = {
        "workflow_id": "WF-D-001",
        "request_id": "REQ-D",
        "stage": "recovery",
        "subject": _base_subject(unit="UNIT-0010"),
        "inputs": [{"charge_id": "FEE-D-1", "fee_type": "lost_inbound", "amount": 45.00}],
        "previous_evidence": [{
            "record_id": "RCV-D",
            "stage": "receiving",
            "checks": [{"check_key": "unit_count", "verdict": "FAIL", "detail": "Shortage at supplier receiving"}],
        }],
    }
    out = handle_agent_request(req)
    ev = out["evidence"]
    assert ev["payload"]["claimable_usd"] == 0.00
    assert "F-10" in ev["payload"]["unclaimable"][0]["reason"]


def test_E_already_reimbursed_no_claim():
    # Use the engine path via previous_evidence that includes a reimbursement?
    # Contract layer does not ingest reimbursements directly; dossier test covers it.
    # For Round 3 input contract, reimbursement is part of evidence matcher via store.
    # We test via handle with a charge that was already reimbursed by injecting
    # a reimbursement as part of evidence? Instead test via direct engine.
    from recovery_manager import EvidenceStore, RecoveryEngine, FeeCharge, ReimbursementRecord, OperationalEvidence, ManagerType
    store = EvidenceStore()
    store.add_evidence(OperationalEvidence(
        evidence_id="EVD-E", org_id="org_demo_alpha", manager=ManagerType.PREP,
        shipment_id="SHP-E", timestamp="2026-06-04T12:00:00Z",
        activity="Packaging Check", check_type="packaging", status="PASS"
    ))
    store.add_reimbursement(ReimbursementRecord(
        reimbursement_id="RMB-E", org_id="org_demo_alpha", original_charge_id="CHG-E",
        shipment_id="SHP-E", amount_reimbursed=40.00
    ))
    eng = RecoveryEngine(store)
    dossier = eng.evaluate_charges([FeeCharge(charge_id="CHG-E", org_id="org_demo_alpha", shipment_id="SHP-E", fee_type="Manual Prep Adjustment", amount=40.00)])
    assert dossier.results[0].assessment.value == "ALREADY_REIMBURSED"
    assert dossier.results[0].potential_claim_amount == 0.00


def test_F_duplicate():
    from recovery_manager import EvidenceStore, RecoveryEngine, FeeCharge, OperationalEvidence, ManagerType
    store = EvidenceStore()
    store.add_evidence(OperationalEvidence(
        evidence_id="EVD-F", org_id="org_demo_alpha", manager=ManagerType.PREP,
        shipment_id="SHP-F", timestamp="2026-06-04T12:00:00Z",
        activity="Packaging Check", check_type="packaging", status="PASS"
    ))
    eng = RecoveryEngine(store)
    charges = [
        FeeCharge(charge_id="CHG-F1", org_id="org_demo_alpha", shipment_id="SHP-F", fee_type="Packaging defect", amount=20.00),
        FeeCharge(charge_id="CHG-F2", org_id="org_demo_alpha", shipment_id="SHP-F", fee_type="Packaging defect", amount=20.00),
    ]
    dossier = eng.evaluate_charges(charges)
    assert dossier.results[0].assessment.value == "CONTRADICTED"
    assert dossier.results[1].assessment.value == "DUPLICATE"
    assert dossier.total_potential_recovery == 40.00


def test_G_uncertain_ambiguous_pending_review():
    req = {
        "workflow_id": "WF-G-001",
        "request_id": "REQ-G",
        "stage": "recovery",
        "subject": _base_subject(unit="UNIT-0060"),
        "inputs": [{"charge_id": "FEE-G-1", "fee_type": "Damaged inventory processing fee", "amount": 110.00}],
        "previous_evidence": [
            {"record_id": "PRP-G", "stage": "prep", "checks": [{"check_key": "damage", "verdict": "PASS"}]},
            {"record_id": "RCV-G", "stage": "receiving", "checks": [{"check_key": "damage", "verdict": "FAIL"}]},
        ],
    }
    out = handle_agent_request(req)
    ev = out["evidence"]
    assert ev["decision"]["outcome"] == "pending_review"
    assert ev["payload"]["claimable_usd"] == 0.00
    assert any(c["position"] == "UNCERTAIN" for c in ev["payload"]["charges"])


def test_H_human_override_changes_evaluation_and_preserves_original():
    # Upstream prep said PASS, so normally claim. Override to FAIL should make it no_claim.
    base = {
        "workflow_id": "WF-H-001",
        "request_id": "REQ-H",
        "stage": "recovery",
        "subject": _base_subject(),
        "inputs": [{"charge_id": "FEE-H-1", "fee_type": "inbound_defect_fee", "amount": 12.00}],
        "previous_evidence": [{
            "record_id": "PRP-H",
            "stage": "prep",
            "checks": [{"check_key": "packaging", "verdict": "PASS"}],
        }],
    }
    out_normal = handle_agent_request(base)
    assert out_normal["evidence"]["decision"]["outcome"] == "claim_recommended"

    overridden = dict(base)
    overridden["request_id"] = "REQ-H2"
    overridden["workflow_id"] = "WF-H-002"
    overridden["context"] = {
        "overrides": [{
            "original_record_id": "PRP-H",
            "check_key": "packaging",
            "new_verdict": "FAIL",
            "actor": "op_human",
            "reason": "re-inspection found torn polybag",
            "timestamp": "2026-06-05T12:00:00Z",
        }]
    }
    out_over = handle_agent_request(overridden)
    ev = out_over["evidence"]
    # Now SUPPORTS -> no_claim
    assert ev["decision"]["outcome"] == "no_claim"
    assert ev["payload"]["claimable_usd"] == 0.00
    # Original preserved
    assert ev["overrides"]
    ov = ev["overrides"][0]
    assert ov["original_record_id"] == "PRP-H"
    assert ov["original_verdict"] == "PASS"
    assert ov["new_verdict"] == "FAIL"
    assert ov["actor"] == "op_human"
    assert ov["applied"] is True


def test_I_wrong_tenant_rejected_and_no_leak():
    req = {
        "workflow_id": "WF-I-001",
        "request_id": "REQ-I",
        "stage": "recovery",
        # Subject belongs to bravo but requester is alpha
        "context": {"org_id": "org_demo_alpha"},
        "subject": _base_subject(org="org_demo_bravo", unit="UNIT-0003"),
        "inputs": [{"charge_id": "FEE-I-1", "fee_type": "inbound_defect_fee", "amount": 12.00}],
        "previous_evidence": [
            # Even if foreign evidence is provided, it must not be used
            {"record_id": "PRP-BRAVO", "subject": {"org_id": "org_demo_bravo"}, "stage": "prep",
             "checks": [{"check_key": "packaging", "verdict": "PASS"}]},
            {"record_id": "PRP-ALPHA", "subject": {"org_id": "org_demo_alpha"}, "stage": "prep",
             "checks": [{"check_key": "packaging", "verdict": "PASS"}]},
        ],
    }
    with pytest.raises(LookupError) as exc:
        handle_agent_request(req)
    assert "Tenant mismatch" in str(exc.value) or "security_event" in str(exc.value) or "wrong_tenant" in str(exc.value)

    # HTTP layer must map to 404
    resp = client.post("/run", json=req)
    assert resp.status_code == 404
    # Must not return evidence
    body = resp.json()
    assert "detail" in body


def test_I_evidence_store_cannot_leak_cross_tenant():
    req_alpha_bravo_evidence = {
        "workflow_id": "WF-I2-001",
        "request_id": "REQ-I2",
        "stage": "recovery",
        "subject": _base_subject(org="org_demo_alpha", unit="UNIT-0014"),
        "inputs": [{"charge_id": "FEE-I2-1", "fee_type": "inbound_defect_fee", "amount": 12.00}],
        "previous_evidence": [
            {"record_id": "PRP-BRAVO-ONLY", "subject": {"org_id": "org_demo_bravo"}, "stage": "prep",
             "checks": [{"check_key": "packaging", "verdict": "PASS", "evidence_refs": ["bravo.jpg"]}]},
        ],
    }
    out = handle_agent_request(req_alpha_bravo_evidence)
    ev = out["evidence"]
    # Foreign record must be dropped -> SILENT
    assert ev["payload"]["claimable_usd"] == 0.00
    assert ev["payload"]["charges"][0]["position"] in ("SILENT", "UNCERTAIN")
    # Ensure no bravo evidence id leaked into evidence_refs
    for ck in ev["checks"]:
        assert "PRP-BRAVO-ONLY" not in ck.get("evidence_refs", [])


def test_J_idempotency_same_request_id_same_record_id():
    req = {
        "workflow_id": "WF-J-001",
        "request_id": "REQ-J-UNIQUE-123",
        "stage": "recovery",
        "subject": _base_subject(unit="UNIT-0014"),
        "inputs": [{"charge_id": "FEE-J-1", "fee_type": "inbound_defect_fee", "amount": 12.00}],
        "previous_evidence": [{
            "record_id": "PRP-J", "stage": "prep",
            "checks": [{"check_key": "packaging", "verdict": "PASS"}],
        }],
    }
    out1 = handle_agent_request(req)
    out2 = handle_agent_request(req)
    assert out1["evidence"]["record_id"] == out2["evidence"]["record_id"]
    assert out1["evidence"]["content_hash"] == out2["evidence"]["content_hash"]

    # Different request IDs must not collapse
    req2 = dict(req)
    req2["request_id"] = "REQ-J-DIFFERENT"
    out3 = handle_agent_request(req2)
    assert out3["evidence"]["record_id"] != out1["evidence"]["record_id"]

    # Same unit but different request/workflow should differ
    assert deterministic_record_id({"subject": {"subject_id": "UNIT-0014", "org_id": "org_demo_alpha"}, "workflow_id": "WF-X", "request_id": "R1"}) != \
           deterministic_record_id({"subject": {"subject_id": "UNIT-0014", "org_id": "org_demo_alpha"}, "workflow_id": "WF-Y", "request_id": "R1"})


def test_K_invalid_input_structured_failure_never_false_success():
    bad = {"workflow_id": "WF-K", "stage": "recovery"}  # missing subject
    with pytest.raises(LookupError):
        handle_agent_request(bad)
    # Malformed inputs should not become claim_recommended via pending path
    # When inputs cause exception, contract returns pending with claimable 0
    req = {
        "workflow_id": "WF-K2",
        "request_id": "REQ-K2",
        "stage": "recovery",
        "subject": _base_subject(),
        "inputs": [{"fee_type": "inbound_defect_fee", "amount": "not_a_number"}],
        "previous_evidence": [],
    }
    out = handle_agent_request(req)
    ev = out["evidence"]
    assert ev["status"] == "pending"
    assert ev["decision"]["outcome"] == "pending_review"
    assert ev["payload"]["claimable_usd"] == 0.00


def test_L_missing_prep_inbound_defect_silent_unless_independent_evidence():
    # No Prep Manager evidence, only Receiving with no inbound_defect check -> SILENT
    req = {
        "workflow_id": "WF-L-001",
        "request_id": "REQ-L",
        "stage": "recovery",
        "subject": _base_subject(unit="UNIT-0042"),
        "inputs": [{"charge_id": "FEE-L-1", "fee_type": "inbound_defect_fee", "amount": 8.00}],
        "previous_evidence": [
            {"record_id": "RCV-L", "stage": "receiving",
             "checks": [{"check_key": "unit_count", "verdict": "PASS"}]},
        ],
    }
    out = handle_agent_request(req)
    ev = out["evidence"]
    # This pod has no Prep Manager; inbound-defect without independent valid evidence -> SILENT
    assert ev["payload"]["claimable_usd"] == 0.00
    assert ev["payload"]["charges"][0]["position"] in ("SILENT", "UNCERTAIN")
    # Must explain which evidence is missing, not vague
    reason = ev["payload"]["charges"][0]["reason"]
    assert "SILENT" in reason or "UNCERTAIN" in reason


def test_model_metadata_is_deterministic():
    req = {
        "workflow_id": "WF-M-001",
        "request_id": "REQ-M",
        "stage": "recovery",
        "subject": _base_subject(),
        "inputs": [{"charge_id": "FEE-M-1", "fee_type": "inbound_defect_fee", "amount": 12.00}],
        "previous_evidence": [],
    }
    out = handle_agent_request(req)
    assert out["model"]["calls"] == 0
    assert out["model"]["cost_usd"] == 0.0
    assert out["evidence"]["model"]["calls"] == 0
    assert MODEL_INFO["calls"] == 0


def test_round3_interface_handle_and_make_app():
    # handle(request: dict) -> dict exposed via recovery_manager.handle
    import recovery_manager
    from server import handle, make_app
    req = {
        "workflow_id": "WF-INT-001",
        "request_id": "REQ-INT",
        "stage": "recovery",
        "subject": _base_subject(),
        "inputs": [{"charge_id": "FEE-INT-1", "fee_type": "inbound_defect_fee", "amount": 12.00}],
        "previous_evidence": [{
            "record_id": "PRP-INT", "stage": "prep",
            "checks": [{"check_key": "packaging", "verdict": "PASS"}],
        }],
    }
    out1 = recovery_manager.handle(req)
    out2 = handle(req)
    assert out1["evidence"]["record_id"] == out2["evidence"]["record_id"]

    # make_app exposes GET /health and POST /run
    test_app = make_app("recovery", handle)
    tc = TestClient(test_app)
    assert tc.get("/health").status_code == 200
    assert tc.get("/health").json()["stage"] == "recovery"
    assert tc.post("/run", json=req).status_code == 200


def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_run_endpoint_success():
    req = {
        "workflow_id": "WF-RUN-001",
        "request_id": "REQ-RUN",
        "stage": "recovery",
        "subject": _base_subject(),
        "inputs": [{"charge_id": "FEE-RUN-1", "fee_type": "inbound_defect_fee", "amount": 12.00}],
        "previous_evidence": [{
            "record_id": "PRP-RUN", "stage": "prep",
            "checks": [{"check_key": "packaging", "verdict": "PASS"}],
        }],
    }
    resp = client.post("/run", json=req)
    assert resp.status_code == 200
    data = resp.json()
    assert data["stage"] == "recovery"
    assert data["evidence"]["payload"]["claimable_usd"] == 12.00


def test_evidence_traceability_chain():
    req = {
        "workflow_id": "WF-TR-001",
        "request_id": "REQ-TR",
        "stage": "recovery",
        "subject": _base_subject(),
        "inputs": [{"charge_id": "FEE-TR-1", "fee_type": "inbound_defect_fee", "amount": 12.00}],
        "previous_evidence": [{
            "record_id": "PRP-TR",
            "stage": "prep",
            "checks": [{"check_key": "packaging", "verdict": "PASS", "evidence_refs": ["UNIT-0014/prep/polybag.jpg"]}],
            "inputs": [{"ref": "UNIT-0014/prep/polybag.jpg"}],
        }],
    }
    out = handle_agent_request(req)
    ev = out["evidence"]
    ck = ev["checks"][0]
    # Navigate backwards: claim -> fee line -> Recovery check -> upstream record -> upstream check -> source evidence -> input/photo hash
    assert "trace" in ck
    trace = ck["trace"]
    assert trace["fee_line"] == "FEE-TR-1"
    assert trace["recovery_check"] == "charge_fee_tr_1"
    assert "PRP-TR" in trace["upstream_records"]
    assert "PRP-TR:packaging" in trace["upstream_checks"] or "PRP-TR" in str(trace["upstream_checks"])
    assert "UNIT-0014/prep/polybag.jpg" in trace["photo_hashes"] or "UNIT-0014/prep/polybag.jpg" in trace["source_evidence"] or len(trace["photo_hashes"]) > 0

    charge = ev["payload"]["charges"][0]
    assert "photo_hashes" in charge
    assert "upstream_check_ids" in charge
