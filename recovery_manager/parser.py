"""
Parser and Ingestion modules for Recovery Manager.
Supports JSON, CSV, and dict structures for Fee Reports, Reimbursements, and Multi-Manager Evidence.
"""

import csv
import json
import io
from typing import List, Dict, Any, Union
from .models import FeeCharge, ReimbursementRecord, OperationalEvidence, ManagerType


def parse_fee_charges_from_json(json_data: Union[str, List[Dict[str, Any]], Dict[str, Any]]) -> List[FeeCharge]:
    """Parse fee charges from JSON string or list/dict structure."""
    if isinstance(json_data, str):
        data = json.loads(json_data)
    else:
        data = json_data

    # If wrapped in a top-level key like "charges" or "fee_report"
    if isinstance(data, dict):
        if "charges" in data:
            data = data["charges"]
        elif "fee_report" in data:
            data = data["fee_report"]
        else:
            data = [data]

    charges = []
    for item in data:
        charge = FeeCharge(
            charge_id=str(item.get("charge_id") or item.get("Charge ID") or item.get("id")),
            shipment_id=item.get("shipment_id") or item.get("Shipment") or item.get("shipment"),
            order_id=item.get("order_id") or item.get("Order ID") or item.get("order"),
            sku=item.get("sku") or item.get("SKU") or item.get("asin") or item.get("ASIN"),
            unit_id=item.get("unit_id") or item.get("Unit"),
            fee_type=item.get("fee_type") or item.get("Reason") or item.get("reason") or "Defect Fee",
            reason_description=item.get("reason_description") or item.get("description") or item.get("notes"),
            amount=float(item.get("amount") or item.get("Amount") or 0.0),
            currency=item.get("currency") or "USD",
            charge_date=item.get("charge_date") or item.get("date"),
            source_report=item.get("source_report") or "Fee Report"
        )
        charges.append(charge)
    return charges


def parse_fee_charges_from_csv(csv_content: str) -> List[FeeCharge]:
    """Parse fee charges from CSV text."""
    reader = csv.DictReader(io.StringIO(csv_content.strip()))
    raw_list = list(reader)
    return parse_fee_charges_from_json(raw_list)


def parse_reimbursements_from_json(json_data: Union[str, List[Dict[str, Any]], Dict[str, Any]]) -> List[ReimbursementRecord]:
    """Parse reimbursement records from JSON."""
    if isinstance(json_data, str):
        data = json.loads(json_data)
    else:
        data = json_data

    if isinstance(data, dict):
        if "reimbursements" in data:
            data = data["reimbursements"]
        else:
            data = [data]

    reimbursements = []
    for item in data:
        reimb = ReimbursementRecord(
            reimbursement_id=str(item.get("reimbursement_id") or item.get("Reimbursement ID") or item.get("id")),
            original_charge_id=item.get("original_charge_id") or item.get("Charge ID"),
            shipment_id=item.get("shipment_id") or item.get("Shipment"),
            order_id=item.get("order_id") or item.get("Order ID"),
            sku=item.get("sku") or item.get("SKU"),
            amount_reimbursed=float(item.get("amount_reimbursed") or item.get("amount") or item.get("Amount") or 0.0),
            currency=item.get("currency") or "USD",
            date_processed=item.get("date_processed") or item.get("date"),
            reason=item.get("reason") or item.get("Reason")
        )
        reimbursements.append(reimb)
    return reimbursements


def _map_manager_type(raw_manager: str) -> ManagerType:
    clean = (raw_manager or "").lower()
    if "prep" in clean:
        return ManagerType.PREP
    if "pack" in clean:
        return ManagerType.PACK
    if "receiv" in clean or "inbound" in clean:
        return ManagerType.RECEIVING
    if "ship" in clean or "carrier" in clean:
        return ManagerType.SHIPPING
    if "return" in clean:
        return ManagerType.RETURNS
    if "bill" in clean or "platform" in clean:
        return ManagerType.PLATFORM_BILLING
    return ManagerType.UNKNOWN


def parse_operational_evidence_from_json(json_data: Union[str, List[Dict[str, Any]], Dict[str, Any]]) -> List[OperationalEvidence]:
    """Parse operational evidence records from JSON."""
    if isinstance(json_data, str):
        data = json.loads(json_data)
    else:
        data = json_data

    if isinstance(data, dict):
        if "evidence" in data:
            data = data["evidence"]
        elif "operational_evidence" in data:
            data = data["operational_evidence"]
        else:
            data = [data]

    evidence_list = []
    for item in data:
        manager_enum = _map_manager_type(item.get("manager") or item.get("Manager") or "")
        
        # Parse media references if string or list
        media = item.get("media_references") or item.get("Evidence") or item.get("photos") or []
        if isinstance(media, str):
            media = [media]

        details = item.get("details") or {}
        if not isinstance(details, dict):
            details = {"info": str(details)}

        ev = OperationalEvidence(
            evidence_id=str(item.get("evidence_id") or item.get("Evidence ID") or item.get("id")),
            manager=manager_enum,
            shipment_id=item.get("shipment_id") or item.get("Shipment"),
            order_id=item.get("order_id") or item.get("Order ID"),
            sku=item.get("sku") or item.get("SKU") or item.get("Unit"),
            unit_id=item.get("unit_id") or item.get("Unit ID"),
            timestamp=item.get("timestamp") or item.get("Captured") or item.get("date") or "2026-09-15T00:00:00Z",
            activity=item.get("activity") or item.get("Action") or "Quality Inspection",
            check_type=item.get("check_type") or item.get("Packaging Check") or item.get("Check") or "packaging",
            status=str(item.get("status") or item.get("Packaging Check") or item.get("Result") or "PASS"),
            details=details,
            media_references=media,
            notes=item.get("notes") or item.get("Notes")
        )
        evidence_list.append(ev)
    return evidence_list
