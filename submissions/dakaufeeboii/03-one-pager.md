# One-Pager: Recovery Manager (Track #5)

**Participant:** dakaufeeboii (Seat #46) · **Target:** Amazon FBA / WFS Defect & Surcharge Recovery

---

## 1. Problem & Value Proposition

Sellers lose 1.5% to 4.2% of GMV to automated platform chargebacks because settlement fees appear 6–8 weeks post-shipment when physical proof is inaccessible. Recovery Manager ingests platform fee reports, joins them with physical evidence records from Receiving, Prep, Pack, and Returns, and deterministically outputs defensible financial dispute dossiers.

```
Fee Report (Platform Charge) + Upstream Operational Evidence
                     ↓
         [Recovery Manager Engine]
                     ↓
[CONTRADICTED] → Defensible Claim ($) + Evidence Dossier
[SUPPORTED]    → Legitimate Fee ($0 claim)
[SILENT]       → Insufficient Evidence ($0 claim, no hallucination)
[UNCERTAIN]    → Ambiguous Logs ($0 claim, supervisor review)
```

---

## 2. Benchmark Metrics Table (8 Canonical Scenarios)

| Scenario ID | Name & Description | Total Fee | Assessment | Claim Status | Recovered | Precision | Defensible? |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **01** | Correct Claim (Full Evidence) | $38.00 | `CONTRADICTED` | `ACTIONABLE` | $38.00 | **100%** | Yes (Prep Cert) |
| **02** | Claim with Partial Evidence | $45.00 | `UNCERTAIN` | `NOT_SUPPORTED` | $0.00 | **N/A** | Safe Decline |
| **03** | Claim with No Evidence | $25.00 | `SILENT` | `NOT_SUPPORTED` | $0.00 | **N/A** | Safe Decline |
| **04** | Multiple Charges Same Shipment | $80.00 | `CONTRADICTED` | `ACTIONABLE` | $80.00 | **100%** | Yes (Prep + Pack) |
| **05** | Cross-Manager Evidence Match | $65.00 | `CONTRADICTED` | `ACTIONABLE` | $65.00 | **100%** | Yes (DWS Scale) |
| **06** | Ambiguous Conflicting Evidence | $110.00 | `UNCERTAIN` | `INCONCLUSIVE` | $0.00 | **N/A** | Escalate to Human |
| **07** | Duplicate Fee Charges | $40.00 | `CONTRADICTED` | `ACTIONABLE` | $40.00 | **100%** | Yes (Double Bill) |
| **08** | Already Reimbursed Charges | $40.00 | `ALREADY_REIMB` | `RESOLVED` | $0.00 | **N/A** | Concession Settled |
| **TOTAL** | **Full Benchmark Portfolio** | **$443.00** | — | — | **$223.00** | **100.0%** | **Zero False Claims** |

---

## 3. Unit Economics & ROI

- **Average Fee Disputed:** $48.50 per erroneous line item.
- **Estimated Erroneous Fee Volume:** 140 fees/month for a mid-tier $5M GMV brand.
- **Monthly Recoverable Capital:** $6,790 / month ($81,480 / year).
- **Inference & Execution Cost:** <$0.002 per charge evaluation (batch structured processing).
- **Net Margin Improvement:** +1.4% directly to brand bottom-line.

---

## 4. Engineering Guardrails

1. **Multi-Tenancy Isolation:** Row-Level Security (RLS) forced by `org_id` on all storage and indexes.
2. **Batch Model Processing:** Evaluates full shipment portfolios in single-pass pipelines.
3. **Fail-Open Policy:** Network or API timeouts push records to `pending_review` without dropping data.
4. **Zero-Hallucination Conservative Rule:** Never infer or create evidence when upstream records are silent.
5. **Authoritative Rules:** Direct alignment with Amazon FBA Inbound Performance thresholds.

---

## 5. Explicit Kill Condition

> **Hard Kill Condition:**  
> If the automated Claim Precision drops below **95.0%** on audited dispute submissions, or if the agent ever generates a claim without traceable upstream evidence references (`evidence_traceability == []`), **automated claim generation is instantly severed**, triggering a fail-safe supervisor audit.
