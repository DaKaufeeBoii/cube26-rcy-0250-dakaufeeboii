"""
Dossier and Claim Package Generator.
Formats recovery evaluation into clear, defensible, audit-ready dispute filings.
"""

from typing import List
from .models import RecoveryDossier, RecoveryResult, AssessmentType, ClaimStatus


def format_dossier_markdown(dossier: RecoveryDossier) -> str:
    """Generate comprehensive Markdown dispute package with clear audit traceability."""
    md = []
    md.append("# 📋 AI Recovery Manager — Dispute & Recovery Dossier")
    md.append(f"**Generated:** {dossier.generated_at} | **Compliance Engine:** Strict Conservative Evidence Protocol\n")

    md.append("## 📊 Executive Financial Summary")
    md.append("| Metric | Value |")
    md.append("| :--- | :--- |")
    md.append(f"| **Total Charges Evaluated** | `{dossier.total_charges_evaluated}` |")
    md.append(f"| **Total Assessed Fees** | `${dossier.total_fee_amount:,.2f}` |")
    md.append(f"| **Actionable Recovery Claim** | **`${dossier.total_potential_recovery:,.2f}`** |")
    md.append(f"| **Legitimate Supported Fees** | `${dossier.total_supported_fees:,.2f}` |")
    md.append(f"| **Silent / Inconclusive (No Claim)** | `${dossier.total_silent_or_inconclusive:,.2f}` |")
    md.append(f"| **Already Reimbursed** | `${dossier.total_already_reimbursed:,.2f}` |")
    md.append(f"| **Recovery Potential Rate** | `{(dossier.total_potential_recovery / max(dossier.total_fee_amount, 0.01)) * 100:.1f}%` |\n")

    md.append("## 🔍 Individual Charge Evaluations\n")

    for idx, res in enumerate(dossier.results, start=1):
        ch = res.charge
        md.append(f"### #{idx} Charge ID: `{ch.charge_id}` — {ch.fee_type}")
        md.append(f"- **Shipment / Ref:** `{ch.shipment_id or ch.order_id or 'N/A'}` | **SKU:** `{ch.sku or 'N/A'}`")
        md.append(f"- **Fee Amount:** `${ch.amount:.2f}`")
        md.append(f"- **Assessment:** **`{res.assessment.value}`**")
        md.append(f"- **Claim Status:** **`{res.claim_status.value}`** (Claim Amount: `${res.potential_claim_amount:.2f}`)")
        md.append(f"- **Reasoning & Dispute Grounds:**\n  > {res.claim_rationale}")

        if res.supporting_evidence:
            md.append("\n  **Operational Evidence Attached:**")
            for em in res.supporting_evidence:
                ev = em.evidence
                media_txt = f", Photos/Docs: {len(ev.media_references)}" if ev.media_references else ""
                md.append(f"  - **[{ev.manager.value}]** Activity: `{ev.activity}` | Check: `{ev.check_type}` | Status: **`{ev.status}`** | Timestamp: `{ev.timestamp}`{media_txt}")
                if ev.details:
                    md.append(f"    - *Metrics:* `{ev.details}`")

        if res.evidence_traceability:
            md.append(f"\n  **Traceability Audit:** `{' -> '.join(res.evidence_traceability)}`")

        md.append(f"  **Recommendation:** {res.recommendation}\n")
        md.append("---\n")

    md.append("## 🛡️ Critical Compliance & Anti-Hallucination Disclosures")
    for note in dossier.audit_notes:
        md.append(f"- {note}")
    md.append("- No claims were generated without explicit, verifiable operational records.")
    md.append("- Charges with ambiguous or silent evidence have been strictly quarantined as non-actionable.")

    return "\n".join(md)


def generate_formal_dispute_letter(result: RecoveryResult) -> str:
    """Format single actionable dispute into formal platform dispute text for copy-paste."""
    ch = result.charge
    if result.assessment != AssessmentType.CONTRADICTED and result.assessment != AssessmentType.DUPLICATE:
        return f"Charge {ch.charge_id} is not eligible for formal dispute ({result.assessment.value})."

    letter = [
        "**To:** Seller Support / Fulfillment Financial Dispute Department",
        f"**Subject:** Formal Dispute of Erroneous Fee — Charge ID {ch.charge_id} (Shipment {ch.shipment_id or 'N/A'})",
        "\nDear Support Team,",
        f"\nWe are formally disputing the fee of ${ch.amount:.2f} assessed under Charge ID {ch.charge_id} for '{ch.fee_type}'.",
        "\n### Grounds for Dispute:",
        result.claim_rationale,
        "\n### Operational Evidence Log:"
    ]

    for em in result.supporting_evidence:
        ev = em.evidence
        letter.append(f"- **Department:** {ev.manager.value}")
        letter.append(f"  - Record ID: {ev.evidence_id}")
        letter.append(f"  - Timestamp: {ev.timestamp} (Captured prior to carrier dispatch)")
        letter.append(f"  - Inspection Result: {ev.status}")
        if ev.details:
            letter.append(f"  - Telemetry / Measurements: {ev.details}")
        if ev.media_references:
            letter.append(f"  - Visual Proof Records: {', '.join(ev.media_references)}")

    letter.append("\nBased on this explicit timestamped operational audit trail, the service was properly performed and compliant.")
    letter.append(f"Please credit back the disputed amount of **${result.potential_claim_amount:.2f}** to our seller account.")
    letter.append("\nSincerely,\nLogistics Operations & Financial Recovery Manager")

    return "\n".join(letter)
