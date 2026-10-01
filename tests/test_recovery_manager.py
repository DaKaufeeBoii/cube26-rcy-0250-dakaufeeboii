"""
Comprehensive test suite verifying the Recovery Manager against the 8 required test scenarios:
1. Correct claim with full evidence
2. Claim with partial evidence
3. Claim with no evidence
4. Multiple charges same shipment
5. Fee matches evidence from different Manager
6. Ambiguous evidence
7. Duplicate charges
8. Already reimbursed charges
"""

import json
from pathlib import Path
import pytest
from recovery_manager import (
    RecoveryEngine,
    EvidenceStore,
    AssessmentType,
    ClaimStatus,
    FeeCharge,
    OperationalEvidence,
    ReimbursementRecord
)
from recovery_manager.parser import (
    parse_fee_charges_from_json,
    parse_operational_evidence_from_json,
    parse_reimbursements_from_json
)
from recovery_manager.dossier import format_dossier_markdown, generate_formal_dispute_letter


@pytest.fixture
def scenarios_data():
    path = Path(__file__).parent.parent / "data" / "scenarios" / "all_scenarios.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["scenarios"]


def test_scenario_1_full_evidence(scenarios_data):
    """Test Scenario 1: Correct claim with full evidence."""
    sc = scenarios_data["scenario_1_full_evidence"]
    charges = parse_fee_charges_from_json(sc["charges"])
    evidence = parse_operational_evidence_from_json(sc["operational_evidence"])

    store = EvidenceStore()
    store.add_evidence_batch(evidence)
    engine = RecoveryEngine(store)

    dossier = engine.evaluate_charges(charges)
    assert len(dossier.results) == 1
    res = dossier.results[0]

    assert res.assessment == AssessmentType.CONTRADICTED
    assert res.claim_status == ClaimStatus.ACTIONABLE
    assert res.potential_claim_amount == 38.00
    assert len(res.supporting_evidence) == 1
    assert "Prep Manager" in res.claim_rationale
    assert "PASS" in res.supporting_evidence[0].evidence.status
    assert len(res.supporting_evidence[0].evidence.media_references) == 3

    # Ensure dispute letter generation works
    letter = generate_formal_dispute_letter(res)
    assert "Dispute of Erroneous Fee" in letter
    assert "$38.00" in letter


def test_scenario_2_partial_evidence(scenarios_data):
    """Test Scenario 2: Claim with partial evidence -> UNCERTAIN, do not force conclusion."""
    sc = scenarios_data["scenario_2_partial_evidence"]
    charges = parse_fee_charges_from_json(sc["charges"])
    evidence = parse_operational_evidence_from_json(sc["operational_evidence"])

    store = EvidenceStore()
    store.add_evidence_batch(evidence)
    engine = RecoveryEngine(store)

    dossier = engine.evaluate_charges(charges)
    res = dossier.results[0]

    assert res.assessment == AssessmentType.UNCERTAIN
    assert res.claim_status == ClaimStatus.NOT_SUPPORTED
    assert res.potential_claim_amount == 0.00
    assert "Partial evidence" in res.claim_rationale


def test_scenario_3_no_evidence(scenarios_data):
    """Test Scenario 3: Claim with no evidence -> SILENT — insufficient evidence."""
    sc = scenarios_data["scenario_3_no_evidence"]
    charges = parse_fee_charges_from_json(sc["charges"])

    store = EvidenceStore()
    engine = RecoveryEngine(store)

    dossier = engine.evaluate_charges(charges)
    res = dossier.results[0]

    assert res.assessment == AssessmentType.SILENT
    assert res.claim_status == ClaimStatus.NOT_SUPPORTED
    assert res.potential_claim_amount == 0.00
    assert "SILENT — insufficient evidence" in res.claim_rationale
    assert len(res.supporting_evidence) == 0


def test_scenario_4_multi_charge_same_shipment(scenarios_data):
    """Test Scenario 4: Multiple charges on the same shipment."""
    sc = scenarios_data["scenario_4_multi_charge_same_shipment"]
    charges = parse_fee_charges_from_json(sc["charges"])
    evidence = parse_operational_evidence_from_json(sc["operational_evidence"])

    store = EvidenceStore()
    store.add_evidence_batch(evidence)
    engine = RecoveryEngine(store)

    dossier = engine.evaluate_charges(charges)
    assert len(dossier.results) == 2
    assert dossier.total_potential_recovery == 80.00

    # Charge 1: Packaging defect ($30)
    assert dossier.results[0].charge.charge_id == "7001"
    assert dossier.results[0].assessment == AssessmentType.CONTRADICTED
    assert dossier.results[0].potential_claim_amount == 30.00

    # Charge 2: Weight discrepancy ($50)
    assert dossier.results[1].charge.charge_id == "7002"
    assert dossier.results[1].assessment == AssessmentType.CONTRADICTED
    assert dossier.results[1].potential_claim_amount == 50.00


def test_scenario_5_cross_manager_evidence(scenarios_data):
    """Test Scenario 5: Fee matches evidence from different Manager (Pack Manager scale)."""
    sc = scenarios_data["scenario_5_cross_manager_evidence"]
    charges = parse_fee_charges_from_json(sc["charges"])
    evidence = parse_operational_evidence_from_json(sc["operational_evidence"])

    store = EvidenceStore()
    store.add_evidence_batch(evidence)
    engine = RecoveryEngine(store)

    dossier = engine.evaluate_charges(charges)
    res = dossier.results[0]

    assert res.assessment == AssessmentType.CONTRADICTED
    assert res.potential_claim_amount == 65.00
    assert res.supporting_evidence[0].evidence.manager.value == "Pack Manager"


def test_scenario_6_ambiguous_evidence(scenarios_data):
    """Test Scenario 6: Ambiguous evidence -> UNCERTAIN, do not force conclusion."""
    sc = scenarios_data["scenario_6_ambiguous_evidence"]
    charges = parse_fee_charges_from_json(sc["charges"])
    evidence = parse_operational_evidence_from_json(sc["operational_evidence"])

    store = EvidenceStore()
    store.add_evidence_batch(evidence)
    engine = RecoveryEngine(store)

    dossier = engine.evaluate_charges(charges)
    res = dossier.results[0]

    assert res.assessment == AssessmentType.UNCERTAIN
    assert res.claim_status == ClaimStatus.INCONCLUSIVE
    assert res.potential_claim_amount == 0.00
    assert "Ambiguous evidence" in res.claim_rationale
    assert "Conflicting operational records" in res.claim_rationale


def test_scenario_7_duplicate_charges(scenarios_data):
    """Test Scenario 7: Duplicate charges in same report."""
    sc = scenarios_data["scenario_7_duplicate_charges"]
    charges = parse_fee_charges_from_json(sc["charges"])
    evidence = parse_operational_evidence_from_json(sc["operational_evidence"])

    store = EvidenceStore()
    store.add_evidence_batch(evidence)
    engine = RecoveryEngine(store)

    dossier = engine.evaluate_charges(charges)
    assert len(dossier.results) == 2

    # First charge: evaluated with evidence -> CONTRADICTED ($20)
    assert dossier.results[0].assessment == AssessmentType.CONTRADICTED
    assert dossier.results[0].potential_claim_amount == 20.00

    # Second charge: flagged as duplicate -> DUPLICATE ($20)
    assert dossier.results[1].assessment == AssessmentType.DUPLICATE
    assert dossier.results[1].potential_claim_amount == 20.00
    assert dossier.total_potential_recovery == 40.00


def test_scenario_8_already_reimbursed(scenarios_data):
    """Test Scenario 8: Fee already reimbursed."""
    sc = scenarios_data["scenario_8_already_reimbursed"]
    charges = parse_fee_charges_from_json(sc["charges"])
    evidence = parse_operational_evidence_from_json(sc["operational_evidence"])
    reimbursements = parse_reimbursements_from_json(sc["reimbursements"])

    store = EvidenceStore()
    store.add_evidence_batch(evidence)
    store.add_reimbursement_batch(reimbursements)
    engine = RecoveryEngine(store)

    dossier = engine.evaluate_charges(charges)
    res = dossier.results[0]

    assert res.assessment == AssessmentType.ALREADY_REIMBURSED
    assert res.claim_status == ClaimStatus.RESOLVED
    assert res.potential_claim_amount == 0.00
    assert "already credited" in res.claim_rationale
    assert dossier.total_already_reimbursed == 40.00


def test_dossier_markdown_generation(scenarios_data):
    """Test markdown dispute dossier generation."""
    sc = scenarios_data["scenario_1_full_evidence"]
    charges = parse_fee_charges_from_json(sc["charges"])
    evidence = parse_operational_evidence_from_json(sc["operational_evidence"])

    store = EvidenceStore()
    store.add_evidence_batch(evidence)
    engine = RecoveryEngine(store)

    dossier = engine.evaluate_charges(charges)
    md = format_dossier_markdown(dossier)
    assert "# 📋 AI Recovery Manager — Dispute & Recovery Dossier" in md
    assert "Total Charges Evaluated" in md
    assert "CONTRADICTED" in md
