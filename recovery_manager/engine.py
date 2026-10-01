"""
Recovery Engine for CUBE Buildathon.
Implements the 10-step autonomous recovery decision workflow:
1. Ingest fee/reimbursement report
2. Parse individual charges
3. Identify shipment/unit/order
4. Retrieve relevant operational evidence
5. Match charge against evidence (cross-record matching)
6. Determine CONTRADICTS, SUPPORTS, SILENT, or UNCERTAIN
7. Assemble potential claim where appropriate
8. Attach supporting evidence
9. Calculate/state relevant amount
10. Explain why charge cannot be claimed when evidence is insufficient
"""

from typing import List, Dict, Tuple, Optional, Set
import re
from .models import (
    FeeCharge,
    ReimbursementRecord,
    OperationalEvidence,
    EvidenceMatch,
    RecoveryResult,
    RecoveryDossier,
    AssessmentType,
    ClaimStatus,
    ManagerType
)
from .store import EvidenceStore


# Keyword mappings for fee types to relevant operational checks and managers
FEE_CHECK_MAPPINGS = {
    "packaging": {
        "check_types": ["packaging", "polybag", "bubblewrap", "box_condition", "seal", "prep_inspection"],
        "managers": [ManagerType.PREP, ManagerType.PACK, ManagerType.RECEIVING]
    },
    "label": {
        "check_types": ["labeling", "barcode", "fnsku", "barcode_verification", "scannability"],
        "managers": [ManagerType.PREP, ManagerType.RECEIVING]
    },
    "weight": {
        "check_types": ["weight", "dimension", "scale_check", "volumetric_weight"],
        "managers": [ManagerType.PACK, ManagerType.SHIPPING, ManagerType.RECEIVING]
    },
    "dimension": {
        "check_types": ["dimension", "box_size", "volumetric_weight", "dws_scan"],
        "managers": [ManagerType.PACK, ManagerType.SHIPPING]
    },
    "quantity": {
        "check_types": ["unit_count", "carton_count", "manifest_reconciliation", "shortage_check"],
        "managers": [ManagerType.RECEIVING, ManagerType.PACK]
    },
    "shortage": {
        "check_types": ["unit_count", "carton_count", "manifest_reconciliation", "shortage_check"],
        "managers": [ManagerType.RECEIVING, ManagerType.PACK]
    },
    "damage": {
        "check_types": ["damage", "condition_grade", "damage_inspection", "box_condition", "inbound_integrity"],
        "managers": [ManagerType.RECEIVING, ManagerType.RETURNS, ManagerType.PACK]
    },
    "return": {
        "check_types": ["return_inspection", "disposition", "condition_grade", "customer_fault"],
        "managers": [ManagerType.RETURNS, ManagerType.RECEIVING]
    }
}


class RecoveryEngine:
    def __init__(self, evidence_store: Optional[EvidenceStore] = None):
        self.evidence_store = evidence_store or EvidenceStore()

    def load_operational_evidence(self, records: List[OperationalEvidence]) -> None:
        """Step 4 preparation: Register operational evidence into indexed store."""
        self.evidence_store.add_evidence_batch(records)

    def load_reimbursements(self, records: List[ReimbursementRecord]) -> None:
        """Register past reimbursements for cross-checking."""
        self.evidence_store.add_reimbursement_batch(records)

    def evaluate_charges(self, charges: List[FeeCharge]) -> RecoveryDossier:
        """
        Main execution pipeline for all charges in a fee report.
        """
        results: List[RecoveryResult] = []
        seen_charge_signatures: Dict[str, str] = {}  # signature -> original_charge_id
        
        total_fee = 0.0
        total_recovery = 0.0
        total_supported = 0.0
        total_silent = 0.0
        total_already_reimbursed = 0.0

        for charge in charges:
            total_fee += charge.amount
            
            # Step 1-3: Identify identifiers and check duplicate charges in the same report
            # Signature: shipment_id + fee_type + amount
            norm_fee_type = charge.fee_type.strip().lower()
            norm_shipment = (charge.shipment_id or "").strip().lower()
            charge_sig = f"{norm_shipment}:{norm_fee_type}:{charge.amount:.2f}"

            # Check if this exact charge was already in this report
            if charge_sig in seen_charge_signatures:
                orig_id = seen_charge_signatures[charge_sig]
                res = self._handle_duplicate_charge(charge, orig_id)
                results.append(res)
                total_recovery += res.potential_claim_amount
                continue
            else:
                seen_charge_signatures[charge_sig] = charge.charge_id

            # Check if already reimbursed from reimbursement reports
            reimbursements = self.evidence_store.find_reimbursements_for_charge(charge)
            if reimbursements:
                res = self._handle_already_reimbursed(charge, reimbursements)
                results.append(res)
                total_already_reimbursed += charge.amount
                continue

            # Step 4: Retrieve relevant operational evidence
            candidate_evidence = self.evidence_store.query_evidence_for_charge(charge)

            if not candidate_evidence:
                # Step 6 & 10: SILENT — Insufficient Evidence
                res = self._handle_silent(charge)
                results.append(res)
                total_silent += charge.amount
                continue

            # Step 5 & 6: Match charge against evidence and determine classification
            res = self._analyze_charge_against_evidence(charge, candidate_evidence)
            results.append(res)

            if res.assessment == AssessmentType.CONTRADICTED:
                total_recovery += res.potential_claim_amount
            elif res.assessment == AssessmentType.SUPPORTED:
                total_supported += charge.amount
            elif res.assessment in (AssessmentType.SILENT, AssessmentType.UNCERTAIN):
                total_silent += charge.amount

        dossier = RecoveryDossier(
            total_charges_evaluated=len(charges),
            total_fee_amount=round(total_fee, 2),
            total_potential_recovery=round(total_recovery, 2),
            total_supported_fees=round(total_supported, 2),
            total_silent_or_inconclusive=round(total_silent, 2),
            total_already_reimbursed=round(total_already_reimbursed, 2),
            results=results,
            audit_notes=[
                "Processed under conservative evidence-to-recovery compliance rules.",
                "Zero evidence hallucination constraint enforced: only explicit operational logs utilized.",
                "Uncertainty flag retained where records are incomplete or conflicting."
            ]
        )
        return dossier

    def _handle_duplicate_charge(self, charge: FeeCharge, original_charge_id: str) -> RecoveryResult:
        """Handle duplicate fee line items."""
        return RecoveryResult(
            charge=charge,
            assessment=AssessmentType.DUPLICATE,
            claim_status=ClaimStatus.ACTIONABLE,
            potential_claim_amount=charge.amount,
            supporting_evidence=[],
            claim_rationale=(
                f"Duplicate billing detected: Fee Charge {charge.charge_id} duplicates earlier charge "
                f"{original_charge_id} for shipment {charge.shipment_id or 'N/A'} "
                f"({charge.fee_type} of ${charge.amount:.2f}). Billed twice for the exact same event."
            ),
            evidence_traceability=[f"Original Charge: {original_charge_id}", f"Duplicate Charge: {charge.charge_id}"],
            confidence=1.0,
            recommendation="Dispute second charge as erroneous duplicate billing with zero operational basis."
        )

    def _handle_already_reimbursed(self, charge: FeeCharge, reimbursements: List[ReimbursementRecord]) -> RecoveryResult:
        """Handle fee charges that have already been refunded/credited."""
        reimb_ids = [r.reimbursement_id for r in reimbursements]
        total_reimbursed = sum(r.amount_reimbursed for r in reimbursements)
        return RecoveryResult(
            charge=charge,
            assessment=AssessmentType.ALREADY_REIMBURSED,
            claim_status=ClaimStatus.RESOLVED,
            potential_claim_amount=0.0,
            supporting_evidence=[],
            claim_rationale=(
                f"Charge {charge.charge_id} (${charge.amount:.2f}) was already credited via "
                f"reimbursement(s) {', '.join(reimb_ids)} for a total of ${total_reimbursed:.2f}. "
                f"No double-recovery permissible."
            ),
            evidence_traceability=[f"Reimbursement IDs: {', '.join(reimb_ids)}"],
            confidence=1.0,
            recommendation="Do not file dispute. Financial concession already settled."
        )

    def _handle_silent(self, charge: FeeCharge) -> RecoveryResult:
        """Step 10: Explain why a charge cannot be claimed when evidence is insufficient."""
        return RecoveryResult(
            charge=charge,
            assessment=AssessmentType.SILENT,
            claim_status=ClaimStatus.NOT_SUPPORTED,
            potential_claim_amount=0.0,
            supporting_evidence=[],
            claim_rationale=(
                f"SILENT — insufficient evidence. No operational records found matching "
                f"Shipment: '{charge.shipment_id or 'N/A'}', Order: '{charge.order_id or 'N/A'}', "
                f"or SKU: '{charge.sku or 'N/A'}'. In accordance with strict recovery rules, "
                f"evidence is never invented; claim cannot be defended."
            ),
            evidence_traceability=[],
            confidence=1.0,
            recommendation="Do not file claim without verified upstream operational documentation."
        )

    def _analyze_charge_against_evidence(self, charge: FeeCharge, evidence_list: List[OperationalEvidence]) -> RecoveryResult:
        """
        Step 5 & 6: Cross-record matching between the charge and operational records.
        Evaluates contradiction vs support vs uncertainty.
        """
        fee_text = f"{charge.fee_type} {charge.reason_description or ''}".lower()

        # Identify fee intent
        target_check_types: Set[str] = set()
        for key, mapping in FEE_CHECK_MAPPINGS.items():
            if key in fee_text:
                target_check_types.update(mapping["check_types"])

        # Match evidence records
        matches: List[EvidenceMatch] = []
        contradictory_matches: List[EvidenceMatch] = []
        supporting_matches: List[EvidenceMatch] = []
        ambiguous_matches: List[EvidenceMatch] = []

        for ev in evidence_list:
            ev_check = ev.check_type.lower()
            ev_status = ev.status.upper()
            ev_activity = ev.activity.lower()

            # Check relevance
            is_relevant = False
            relevance = 0.5
            aspect = ev.check_type

            # Check if this record addresses the fee
            if any(tct in ev_check or tct in ev_activity for tct in target_check_types):
                is_relevant = True
                relevance = 0.95
            elif not target_check_types:
                # Generic fallback if fee description didn't match keyword
                is_relevant = True
                relevance = 0.6

            if not is_relevant:
                continue

            # Determine whether this specific record contradicts or supports the fee
            # CONTRADICTION: Manager logged PASS/COMPLIANT/INTACT, but platform charged a penalty/defect
            is_contra = False
            is_supp = False
            is_ambi = False
            rationale = ""

            if ev_status in ("PASS", "COMPLIANT", "INTACT", "OK", "VERIFIED", "MATCH"):
                # Evidence proves the operator did their job properly or condition was fine
                is_contra = True
                contra_details = []
                if ev.details:
                    contra_details = [f"{k}: {v}" for k, v in ev.details.items()]
                details_str = f" ({', '.join(contra_details)})" if contra_details else ""
                media_str = f" [{len(ev.media_references)} media records attached]" if ev.media_references else ""
                rationale = (
                    f"{ev.manager.value} logged '{ev.activity}' with status {ev_status} "
                    f"at {ev.timestamp}{details_str}{media_str}. "
                    f"This directly contradicts the assessed fee '{charge.fee_type}'."
                )
            elif ev_status in ("FAIL", "NON_COMPLIANT", "DAMAGED", "DEFECT", "MISSING"):
                # Evidence confirms the issue occurred
                is_supp = True
                supp_details = [f"{k}: {v}" for k, v in ev.details.items()] if ev.details else []
                rationale = (
                    f"{ev.manager.value} logged '{ev.activity}' with status {ev_status} "
                    f"at {ev.timestamp} ({', '.join(supp_details)}). "
                    f"This confirms the platform's defect finding; fee is legitimate."
                )
            elif ev_status in ("PARTIAL", "UNCERTAIN", "SUSPECT", "PENDING", "INCOMPLETE"):
                is_ambi = True
                rationale = (
                    f"{ev.manager.value} recorded inconclusive status '{ev_status}' for {ev.activity}. "
                    f"Evidence is incomplete."
                )
            else:
                is_ambi = True
                rationale = f"{ev.manager.value} record has ambiguous status '{ev_status}'."

            match_obj = EvidenceMatch(
                evidence=ev,
                relevance_score=relevance,
                match_aspect=aspect,
                is_contradictory=is_contra,
                is_supporting=is_supp,
                is_ambiguous=is_ambi,
                rationale=rationale
            )
            matches.append(match_obj)
            if is_contra:
                contradictory_matches.append(match_obj)
            elif is_supp:
                supporting_matches.append(match_obj)
            else:
                ambiguous_matches.append(match_obj)

        # Step 6: Decide assessment based on aggregated evidence
        if not matches:
            # We had candidate records (e.g. for same shipment), but NONE covered this check type (Partial Evidence scenario)
            return RecoveryResult(
                charge=charge,
                assessment=AssessmentType.UNCERTAIN,
                claim_status=ClaimStatus.NOT_SUPPORTED,
                potential_claim_amount=0.0,
                supporting_evidence=[],
                claim_rationale=(
                    f"Partial evidence available: Records exist for shipment {charge.shipment_id}, "
                    f"but none cover the specific check required for '{charge.fee_type}'. "
                    f"Per conservative guidelines, UNCERTAIN is the valid outcome. "
                    f"Cannot defend claim without explicit verification records."
                ),
                evidence_traceability=[f"Shipment records inspected: {len(evidence_list)}"],
                confidence=0.85,
                recommendation="Do not file claim unless specific verification records are obtained."
            )

        # Check for ambiguity: conflicting signals (both contradictory and supporting evidence)
        if contradictory_matches and supporting_matches:
            trace = [f"{m.evidence.manager.value} ({m.evidence.status}) at {m.evidence.timestamp}" for m in matches]
            return RecoveryResult(
                charge=charge,
                assessment=AssessmentType.UNCERTAIN,
                claim_status=ClaimStatus.INCONCLUSIVE,
                potential_claim_amount=0.0,
                supporting_evidence=matches,
                claim_rationale=(
                    f"Ambiguous evidence: Conflicting operational records found. "
                    f"{len(contradictory_matches)} record(s) indicate compliance while "
                    f"{len(supporting_matches)} record(s) report defects. "
                    f"Under the strict rule 'UNCERTAIN is a valid outcome — do not force a conclusion', "
                    f"this dispute cannot be filed automatically."
                ),
                evidence_traceability=trace,
                confidence=0.9,
                recommendation="Manual escalation: Audit discrepancy between conflicting manager logs."
            )

        if ambiguous_matches and not contradictory_matches and not supporting_matches:
            trace = [f"{m.evidence.manager.value} ({m.evidence.status})" for m in ambiguous_matches]
            return RecoveryResult(
                charge=charge,
                assessment=AssessmentType.UNCERTAIN,
                claim_status=ClaimStatus.INCONCLUSIVE,
                potential_claim_amount=0.0,
                supporting_evidence=ambiguous_matches,
                claim_rationale=(
                    f"Ambiguous evidence: The matched records from "
                    f"{', '.join(set(m.evidence.manager.value for m in ambiguous_matches))} "
                    f"contain incomplete or inconclusive status. Cannot ascertain liability."
                ),
                evidence_traceability=trace,
                confidence=0.85,
                recommendation="Hold claim pending clarification of operational logs."
            )

        # Clear Contradiction -> Full Defensible Claim!
        if contradictory_matches:
            trace = [
                f"{m.evidence.manager.value} (ID: {m.evidence.evidence_id}, Status: {m.evidence.status}, Time: {m.evidence.timestamp})"
                for m in contradictory_matches
            ]
            primary_manager = contradictory_matches[0].evidence.manager.value
            media_total = sum(len(m.evidence.media_references) for m in contradictory_matches)
            media_note = f" accompanied by {media_total} digital evidence records/photos" if media_total > 0 else ""
            
            dossier_text = (
                f"Assessment: CONTRADICTED. Operational evidence from {primary_manager} definitively "
                f"proves full compliance with platform standards prior to dispatch{media_note}. "
                f"The fee of ${charge.amount:.2f} for '{charge.fee_type}' is erroneous and should be reimbursed in full."
            )
            
            return RecoveryResult(
                charge=charge,
                assessment=AssessmentType.CONTRADICTED,
                claim_status=ClaimStatus.ACTIONABLE,
                potential_claim_amount=charge.amount,
                supporting_evidence=contradictory_matches,
                claim_rationale=dossier_text,
                evidence_traceability=trace,
                confidence=0.98,
                recommendation="File dispute immediately with attached operational inspection certificates."
            )

        # Clear Support -> Fee is valid
        if supporting_matches:
            trace = [
                f"{m.evidence.manager.value} (ID: {m.evidence.evidence_id}, Status: {m.evidence.status}, Time: {m.evidence.timestamp})"
                for m in supporting_matches
            ]
            primary_manager = supporting_matches[0].evidence.manager.value
            return RecoveryResult(
                charge=charge,
                assessment=AssessmentType.SUPPORTED,
                claim_status=ClaimStatus.NOT_SUPPORTED,
                potential_claim_amount=0.0,
                supporting_evidence=supporting_matches,
                claim_rationale=(
                    f"Assessment: SUPPORTED. Internal evidence from {primary_manager} logs an operational failure "
                    f"matching the platform charge. Fee of ${charge.amount:.2f} is legitimate; no claim can be raised."
                ),
                evidence_traceability=trace,
                confidence=0.96,
                recommendation="Accept fee. Correct internal root cause at operational manager station."
            )

        # Fallback
        return self._handle_silent(charge)
