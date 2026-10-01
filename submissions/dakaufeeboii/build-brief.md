# Build Brief: Recovery Manager System Architecture

**Track:** 05 · Recovery Manager  
**Author:** dakaufeeboii  
**Version:** 1.0.0 (Round 2 Final)

---

## 1. Executive Summary

Recovery Manager is an autonomous evidence-to-recovery system designed for high-volume multichannel commerce. In supply chain environments, Amazon, Walmart, and 3PL platforms frequently charge inbound defect fees, mis-calculated weight surcharges, and inventory damage adjustments weeks after shipment. 

Recovery Manager evaluates these charges by cross-referencing multi-manager operational evidence records produced across four upstream warehouse stations (Receiving, Prep, Pack, Returns).

---

## 2. 10-Step Operational Execution Pipeline

In compliance with the official specification, the agent executes the following deterministic 10 steps:

1. **Ingest Report:** Ingest fee reports, reimbursement schedules, or settlement CSV/JSON.
2. **Parse Charges:** Normalize individual fee lines (charge ID, shipment ID, SKU, amount, date, fee type).
3. **Identify Entities:** Extract shipment identifiers (`SHP-XXXX`), carton IDs, order IDs, and SKUs.
4. **Retrieve Evidence:** Query the tenancy-isolated `EvidenceStore` across all 4 upstream managers.
5. **Match Charge to Evidence:** Cross-match charge parameters against operational verification checkpoints.
6. **Classify Assessment:**
   - **`CONTRADICTED`**: Upstream evidence proves compliance prior to dispatch (actionable claim).
   - **`SUPPORTED`**: Upstream evidence confirms operator fault (legitimate fee, no claim).
   - **`SILENT`**: No matching operational evidence exists (insufficient evidence, no claim).
   - **`UNCERTAIN`**: Evidence is incomplete, suspect, or conflicting (route for supervisor review).
7. **Assemble Potential Claim:** Calculate dispute amount and assign `ClaimStatus` (`ACTIONABLE`, `NOT_SUPPORTED`, `INCONCLUSIVE`, `RESOLVED`).
8. **Attach Supporting Evidence:** Bind raw operational logs, sensor readings, and inspection timestamps.
9. **State Relevant Amount:** Explicitly state the potential recovery figure down to the exact cent.
10. **Explain Ineligibility:** Provide explicit legal and operational rationales when claims are declined.

---

## 3. Technology Stack

- **Core Engine:** Python 3.10+ (Pydantic v2 data validation, typing, robust parsing)
- **Multi-Tenancy Store:** Scoped in-memory indexed store with Row-Level Security (RLS) simulation
- **Web UI & Dashboard:** Modern Vanilla CSS & JavaScript, real-time KPI cards, scenario switcher, timeline inspection, 1-click dispute dossier viewer
- **API Server:** FastAPI + Uvicorn with asynchronous endpoints
- **CLI Runner:** Rich terminal interface with interactive tables and formatting
- **Test Framework:** Pytest with automated test coverage across all 8 canonical test scenarios
