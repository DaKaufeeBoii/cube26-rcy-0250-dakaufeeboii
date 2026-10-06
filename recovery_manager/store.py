"""
Evidence Store for Recovery Manager.
Indexes operational evidence from multiple operational managers (Receiving, Prep, Pack, Shipping, Returns)
and past reimbursement records.
"""

from typing import List, Dict, Optional, Set
from collections import defaultdict
from .models import OperationalEvidence, ReimbursementRecord, FeeCharge, ManagerType


class EvidenceStore:
    def __init__(self):
        self.evidence_by_id: Dict[str, OperationalEvidence] = {}
        self.by_shipment: Dict[str, List[str]] = defaultdict(list)
        self.by_order: Dict[str, List[str]] = defaultdict(list)
        self.by_sku: Dict[str, List[str]] = defaultdict(list)
        self.by_unit: Dict[str, List[str]] = defaultdict(list)
        self.by_org: Dict[str, List[str]] = defaultdict(list)
        self.by_manager: Dict[ManagerType, List[str]] = defaultdict(list)

        self.reimbursements: List[ReimbursementRecord] = []
        self.reimbursements_by_charge_id: Dict[str, List[ReimbursementRecord]] = defaultdict(list)
        self.reimbursements_by_shipment: Dict[str, List[ReimbursementRecord]] = defaultdict(list)
        self.reimbursements_by_org: Dict[str, List[ReimbursementRecord]] = defaultdict(list)

    def add_evidence(self, record: OperationalEvidence) -> None:
        """Add an operational evidence record and update all indices."""
        self.evidence_by_id[record.evidence_id] = record
        if record.org_id:
            self.by_org[record.org_id.strip()].append(record.evidence_id)
        if record.shipment_id:
            self.by_shipment[record.shipment_id.strip()].append(record.evidence_id)
        if record.order_id:
            self.by_order[record.order_id.strip()].append(record.evidence_id)
        if record.sku:
            self.by_sku[record.sku.strip()].append(record.evidence_id)
        if record.unit_id:
            self.by_unit[record.unit_id.strip()].append(record.evidence_id)
        self.by_manager[record.manager].append(record.evidence_id)

    def add_evidence_batch(self, records: List[OperationalEvidence]) -> None:
        for r in records:
            self.add_evidence(r)

    def add_reimbursement(self, record: ReimbursementRecord) -> None:
        """Add a reimbursement record and update lookup indices."""
        self.reimbursements.append(record)
        if record.org_id:
            self.reimbursements_by_org[record.org_id.strip()].append(record)
        if record.original_charge_id:
            self.reimbursements_by_charge_id[record.original_charge_id.strip()].append(record)
        if record.shipment_id:
            self.reimbursements_by_shipment[record.shipment_id.strip()].append(record)

    def add_reimbursement_batch(self, records: List[ReimbursementRecord]) -> None:
        for r in records:
            self.add_reimbursement(r)

    def has_subject(self, subject_id: str, org_id: Optional[str] = None) -> bool:
        """Check if any evidence exists for subject_id under optional org_id."""
        clean_subj = subject_id.strip()
        matched_ids = self.by_unit.get(clean_subj, []) or self.by_shipment.get(clean_subj, [])
        if not matched_ids:
            return False
        if not org_id:
            return True
        clean_org = org_id.strip()
        return any(self.evidence_by_id[eid].org_id == clean_org for eid in matched_ids if eid in self.evidence_by_id and self.evidence_by_id[eid].org_id)

    def query_evidence_for_charge(self, charge: FeeCharge, strict_tenancy: bool = True) -> List[OperationalEvidence]:
        """
        Retrieve all operational evidence matching the charge's identifiers:
        shipment_id, order_id, sku, or unit_id.
        Enforces strict multi-tenant isolation when charge.org_id is present.
        """
        candidate_ids: Set[str] = set()

        if charge.shipment_id and charge.shipment_id.strip() in self.by_shipment:
            candidate_ids.update(self.by_shipment[charge.shipment_id.strip()])

        if charge.order_id and charge.order_id.strip() in self.by_order:
            candidate_ids.update(self.by_order[charge.order_id.strip()])

        if charge.unit_id and charge.unit_id.strip() in self.by_unit:
            candidate_ids.update(self.by_unit[charge.unit_id.strip()])

        # Retrieve matched records
        matched_records = [self.evidence_by_id[eid] for eid in candidate_ids if eid in self.evidence_by_id]
        
        # Enforce tenancy isolation: Never match records belonging to a different tenant!
        if charge.org_id:
            clean_org = charge.org_id.strip()
            matched_records = [
                r for r in matched_records
                if r.org_id is None or r.org_id.strip() == clean_org
            ]
        
        # Sort by timestamp
        matched_records.sort(key=lambda x: x.timestamp)
        return matched_records

    def find_reimbursements_for_charge(self, charge: FeeCharge) -> List[ReimbursementRecord]:
        """
        Check if this charge or shipment was already reimbursed.
        Guarantees tenant isolation if org_id is present.
        """
        matches = []
        if charge.charge_id and charge.charge_id.strip() in self.reimbursements_by_charge_id:
            matches.extend(self.reimbursements_by_charge_id[charge.charge_id.strip()])

        # Also check by shipment_id + matching amount if not directly linked by charge_id
        if not matches and charge.shipment_id and charge.shipment_id.strip() in self.reimbursements_by_shipment:
            for r in self.reimbursements_by_shipment[charge.shipment_id.strip()]:
                if abs(r.amount_reimbursed - charge.amount) < 0.01:
                    matches.append(r)

        # Enforce tenancy isolation on reimbursements
        if charge.org_id:
            clean_org = charge.org_id.strip()
            matches = [
                r for r in matches
                if r.org_id is None or r.org_id.strip() == clean_org
            ]

        return matches
