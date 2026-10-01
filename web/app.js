/**
 * AI Recovery Manager — Frontend Controller
 * Autonomous Evidence-to-Recovery Dashboard
 */

let allScenarios = [];
let currentScenarioId = "scenario_1_full_evidence";
let currentDossier = null;
let currentMarkdownReport = "";
let selectedChargeId = null;
let currentFilter = "all";

// Elements
const scenariosGrid = document.getElementById("scenarios-grid");
const kpiTotalFees = document.getElementById("kpi-total-fees");
const kpiTotalRecovery = document.getElementById("kpi-total-recovery");
const kpiTotalSupported = document.getElementById("kpi-total-supported");
const kpiTotalSilent = document.getElementById("kpi-total-silent");
const kpiTotalReimbursed = document.getElementById("kpi-total-reimbursed");
const kpiChargesCount = document.getElementById("kpi-charges-count");
const kpiRecoveryRate = document.getElementById("kpi-recovery-rate");

const activeScenarioBadge = document.getElementById("active-scenario-badge");
const activeScenarioTitle = document.getElementById("active-scenario-title");
const activeScenarioDescription = document.getElementById("active-scenario-description");
const chargesCountTag = document.getElementById("charges-count-tag");
const chargesList = document.getElementById("charges-list");
const detailContent = document.getElementById("detail-content");
const selectedChargeBadge = document.getElementById("selected-charge-badge");
const btnCopyDisputeLetter = document.getElementById("btn-copy-dispute-letter");
const btnReRun = document.getElementById("btn-re-run-analysis");
const btnExportDossier = document.getElementById("btn-export-dossier");

// Modal Elements
const customModal = document.getElementById("custom-modal");
const btnOpenCustomModal = document.getElementById("btn-open-custom-modal");
const closeCustomModal = document.getElementById("close-custom-modal");
const btnSubmitCustom = document.getElementById("btn-submit-custom");
const btnLoadSampleCustom = document.getElementById("btn-load-sample-custom");
const toast = document.getElementById("toast");


// Initial Startup
document.addEventListener("DOMContentLoaded", async () => {
  setupEventListeners();
  await loadScenariosList();
  if (allScenarios.length > 0) {
    selectScenario(allScenarios[0].id);
  }
});

function setupEventListeners() {
  // Re-run
  btnReRun.addEventListener("click", () => {
    if (currentScenarioId) selectScenario(currentScenarioId);
  });

  // Filter tabs
  document.querySelectorAll(".filter-tab").forEach(tab => {
    tab.addEventListener("click", (e) => {
      document.querySelectorAll(".filter-tab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      currentFilter = tab.getAttribute("data-filter");
      renderChargesList();
    });
  });

  // Export Dossier
  btnExportDossier.addEventListener("click", () => {
    if (!currentMarkdownReport) {
      showToast("No active dossier report to export.");
      return;
    }
    const blob = new Blob([currentMarkdownReport], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `recovery_dossier_${currentScenarioId || 'analysis'}.md`;
    a.click();
    URL.revokeObjectURL(url);
    showToast("Downloaded complete Recovery Dossier (.md)");
  });

  // Copy Dispute Letter
  btnCopyDisputeLetter.addEventListener("click", async () => {
    if (!currentScenarioId || !selectedChargeId) return;
    try {
      const res = await fetch(`/api/dispute-letter/${currentScenarioId}/${selectedChargeId}`);
      if (!res.ok) throw new Error("Could not fetch dispute letter");
      const data = await res.json();
      await navigator.clipboard.writeText(data.dispute_letter);
      showToast("Copied formal dispute filing letter to clipboard!");
    } catch (err) {
      showToast("Failed to copy letter: " + err.message);
    }
  });

  // Custom Ingestion Modal
  btnOpenCustomModal.addEventListener("click", () => {
    customModal.style.display = "flex";
  });
  closeCustomModal.addEventListener("click", () => {
    customModal.style.display = "none";
  });

  document.querySelectorAll(".modal-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".modal-tab").forEach(t => t.classList.remove("active"));
      document.querySelectorAll(".tab-pane").forEach(p => p.style.display = "none");
      tab.classList.add("active");
      const paneId = tab.getAttribute("data-pane");
      document.getElementById(paneId).style.display = "block";
    });
  });

  btnLoadSampleCustom.addEventListener("click", loadCustomSampleData);
  btnSubmitCustom.addEventListener("click", submitCustomData);
}

// Fetch list of scenarios
async function loadScenariosList() {
  try {
    const res = await fetch("/api/scenarios");
    const data = await res.json();
    allScenarios = data.scenarios;
    renderScenariosCarousel();
  } catch (err) {
    console.error("Failed to load scenarios:", err);
    showToast("Error connecting to Recovery Manager server.");
  }
}

function renderScenariosCarousel() {
  scenariosGrid.innerHTML = "";
  allScenarios.forEach((sc, idx) => {
    const card = document.createElement("div");
    card.className = `scenario-card ${sc.id === currentScenarioId ? "active" : ""}`;
    card.id = `card-${sc.id}`;

    const badgeClass = getAssessmentBadgeClass(sc.expected_assessment);

    card.innerHTML = `
      <div class="scenario-card-header">
        <span class="scenario-idx">SCENARIO 0${idx + 1}</span>
        <span class="expected-badge ${badgeClass}">${sc.expected_assessment}</span>
      </div>
      <div class="scenario-name">${sc.name}</div>
      <div class="scenario-snippet">${sc.description}</div>
    `;

    card.addEventListener("click", () => selectScenario(sc.id));
    scenariosGrid.appendChild(card);
  });
}

function getAssessmentBadgeClass(assessment) {
  switch (assessment) {
    case "CONTRADICTED": return "badge-contradicted";
    case "SUPPORTED": return "badge-supported";
    case "SILENT": return "badge-silent";
    case "UNCERTAIN": return "badge-uncertain";
    case "DUPLICATE": return "badge-duplicate";
    case "ALREADY_REIMBURSED": return "badge-reimbursed";
    default: return "";
  }
}

// Select and evaluate scenario
async function selectScenario(scenarioId) {
  currentScenarioId = scenarioId;

  // Update active state in cards
  document.querySelectorAll(".scenario-card").forEach(c => c.classList.remove("active"));
  const activeCard = document.getElementById(`card-${scenarioId}`);
  if (activeCard) activeCard.classList.add("active");

  const scInfo = allScenarios.find(s => s.id === scenarioId);
  if (scInfo) {
    activeScenarioBadge.textContent = scenarioId.replace(/_/g, " ").toUpperCase();
    activeScenarioTitle.textContent = scInfo.name;
    activeScenarioDescription.textContent = scInfo.description;
  }

  // Trigger evaluation
  try {
    const res = await fetch(`/api/evaluate/scenario/${scenarioId}`, { method: "POST" });
    if (!res.ok) throw new Error("Evaluation request failed");
    const data = await res.json();
    currentDossier = data.dossier;
    currentMarkdownReport = data.markdown_report;

    updateKPIs(currentDossier);
    renderChargesList();

    // Auto-select first charge
    if (currentDossier.results.length > 0) {
      selectCharge(currentDossier.results[0].charge.charge_id);
    }
  } catch (err) {
    console.error("Evaluation error:", err);
    showToast("Evaluation failed: " + err.message);
  }
}

function updateKPIs(dossier) {
  kpiTotalFees.textContent = `$${dossier.total_fee_amount.toFixed(2)}`;
  kpiTotalRecovery.textContent = `$${dossier.total_potential_recovery.toFixed(2)}`;
  kpiTotalSupported.textContent = `$${dossier.total_supported_fees.toFixed(2)}`;
  kpiTotalSilent.textContent = `$${dossier.total_silent_or_inconclusive.toFixed(2)}`;
  kpiTotalReimbursed.textContent = `$${dossier.total_already_reimbursed.toFixed(2)}`;

  kpiChargesCount.textContent = `${dossier.total_charges_evaluated} Line Item(s) Processed`;

  const rate = dossier.total_fee_amount > 0 
    ? ((dossier.total_potential_recovery / dossier.total_fee_amount) * 100).toFixed(1)
    : "0.0";
  kpiRecoveryRate.textContent = `${rate}% Recovery Rate`;
}

function renderChargesList() {
  if (!currentDossier) return;

  chargesList.innerHTML = "";
  let results = currentDossier.results;

  // Filter
  if (currentFilter === "actionable") {
    results = results.filter(r => r.claim_status === "ACTIONABLE");
  } else if (currentFilter === "silent") {
    results = results.filter(r => r.assessment === "SILENT" || r.assessment === "UNCERTAIN");
  } else if (currentFilter === "supported") {
    results = results.filter(r => r.assessment === "SUPPORTED");
  }

  chargesCountTag.textContent = results.length;

  if (results.length === 0) {
    chargesList.innerHTML = `<div style="padding: 1.5rem; text-align: center; color: var(--text-muted); font-size: 0.85rem;">No charges matching filter criteria.</div>`;
    return;
  }

  results.forEach(res => {
    const ch = res.charge;
    const isSelected = ch.charge_id === selectedChargeId;

    const card = document.createElement("div");
    card.className = `charge-card ${isSelected ? "selected" : ""}`;
    card.id = `charge-card-${ch.charge_id}`;

    const badgeClass = getAssessmentBadgeClass(res.assessment);
    const claimClass = getClaimStatusClass(res.claim_status);

    card.innerHTML = `
      <div class="charge-card-top">
        <div class="charge-id-title">
          <span>#${ch.charge_id}</span>
          ${ch.shipment_id ? `<span style="color: var(--accent-cyan)">[${ch.shipment_id}]</span>` : ''}
        </div>
        <span class="expected-badge ${badgeClass}">${res.assessment}</span>
      </div>
      <div class="charge-fee-type">${ch.fee_type}</div>
      <div class="charge-meta-row">
        <span>SKU: ${ch.sku || 'N/A'}</span>
        <span>Date: ${ch.charge_date || 'N/A'}</span>
      </div>
      <div class="charge-card-bottom">
        <span class="charge-amount-badge">$${ch.amount.toFixed(2)}</span>
        <span class="claim-indicator ${claimClass}">
          ${res.claim_status === 'ACTIONABLE' ? `Claim: $${res.potential_claim_amount.toFixed(2)}` : res.claim_status}
        </span>
      </div>
    `;

    card.addEventListener("click", () => selectCharge(ch.charge_id));
    chargesList.appendChild(card);
  });
}

function getClaimStatusClass(status) {
  switch (status) {
    case "ACTIONABLE": return "claim-actionable";
    case "NOT_SUPPORTED": return "claim-not-supported";
    case "RESOLVED": return "claim-resolved";
    case "INCONCLUSIVE": return "claim-inconclusive";
    default: return "";
  }
}

function selectCharge(chargeId) {
  selectedChargeId = chargeId;

  // Highlight card
  document.querySelectorAll(".charge-card").forEach(c => c.classList.remove("selected"));
  const card = document.getElementById(`charge-card-${chargeId}`);
  if (card) card.classList.add("selected");

  selectedChargeBadge.textContent = `Charge ID: #${chargeId}`;

  const res = currentDossier.results.find(r => r.charge.charge_id === chargeId);
  if (!res) return;

  renderChargeDetail(res);
}

function renderChargeDetail(res) {
  const ch = res.charge;
  const isActionable = res.claim_status === "ACTIONABLE";

  btnCopyDisputeLetter.style.display = isActionable ? "inline-flex" : "none";

  const badgeClass = getAssessmentBadgeClass(res.assessment);
  let rationaleClass = "contra";
  if (res.assessment === "SUPPORTED") rationaleClass = "supp";
  else if (res.assessment === "UNCERTAIN" || res.assessment === "SILENT") rationaleClass = "ambi";

  let html = `
    <div class="detail-summary-box">
      <div class="detail-row-grid">
        <div>
          <div class="detail-prop-label">Charge ID</div>
          <div class="detail-prop-val mono">#${ch.charge_id}</div>
        </div>
        <div>
          <div class="detail-prop-label">Shipment / Reference</div>
          <div class="detail-prop-val mono" style="color: var(--accent-cyan);">${ch.shipment_id || 'N/A'}</div>
        </div>
        <div>
          <div class="detail-prop-label">Billed Amount</div>
          <div class="detail-prop-val mono">$${ch.amount.toFixed(2)}</div>
        </div>
        <div>
          <div class="detail-prop-label">Assessment</div>
          <span class="assessment-pill-lg ${badgeClass}">${res.assessment}</span>
        </div>
        <div>
          <div class="detail-prop-label">Claim Status</div>
          <div class="detail-prop-val ${getClaimStatusClass(res.claim_status)}">${res.claim_status}</div>
        </div>
        <div>
          <div class="detail-prop-label">Eligible Recovery</div>
          <div class="detail-prop-val mono text-emerald">$${res.potential_claim_amount.toFixed(2)}</div>
        </div>
      </div>

      <div style="margin-top: 0.85rem;">
        <div class="detail-prop-label">Structured Reasoning & Dispute Grounds</div>
        <div class="rationale-quote-box ${rationaleClass}">${res.claim_rationale}</div>
      </div>

      <div style="margin-top: 0.85rem; font-size: 0.8rem; color: var(--text-muted); display: flex; align-items: center; gap: 0.4rem;">
        <strong>Recommended Action:</strong>
        <span style="color: var(--text-primary);">${res.recommendation}</span>
      </div>
    </div>
  `;

  // Supporting Evidence List
  html += `
    <div class="timeline-title">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
      Operational Evidence & Cross-Manager Records (${res.supporting_evidence.length})
    </div>
  `;

  if (res.supporting_evidence.length === 0) {
    if (res.assessment === "SILENT") {
      html += `
        <div style="background: rgba(15, 23, 42, 0.4); border: 1px dashed var(--border-subtle); border-radius: 8px; padding: 1.5rem; text-align: center; color: var(--text-muted); font-size: 0.85rem;">
          <strong>No operational records exist for this shipment in any upstream manager store.</strong><br>
          Strict zero-hallucination constraint invoked: claim rejected as SILENT.
        </div>
      `;
    } else if (res.assessment === "DUPLICATE") {
      html += `
        <div style="background: rgba(139, 92, 246, 0.1); border: 1px dashed rgba(139, 92, 246, 0.3); border-radius: 8px; padding: 1.2rem; font-size: 0.85rem; color: #c084fc;">
          <strong>Duplicate Billing Record:</strong> Second charge billed for the identical shipment event and fee category. Claim eligible purely on billing redundancy.
        </div>
      `;
    } else if (res.assessment === "ALREADY_REIMBURSED") {
      html += `
        <div style="background: rgba(6, 182, 212, 0.1); border: 1px dashed rgba(6, 182, 212, 0.3); border-radius: 8px; padding: 1.2rem; font-size: 0.85rem; color: #67e8f9;">
          <strong>Settled Concession:</strong> Reconciled against prior reimbursement credit. Double-claiming strictly prevented.
        </div>
      `;
    } else {
      html += `
        <div style="background: rgba(245, 158, 11, 0.1); border: 1px dashed rgba(245, 158, 11, 0.3); border-radius: 8px; padding: 1.2rem; font-size: 0.85rem; color: #fbbf24;">
          <strong>Partial Evidence Available:</strong> Records exist for this shipment, but none document the specific check required. Claim quarantined as UNCERTAIN.
        </div>
      `;
    }
  } else {
    html += `<div class="evidence-items-list">`;
    res.supporting_evidence.forEach(match => {
      const ev = match.evidence;
      const mgrClass = getManagerBadgeClass(ev.manager);
      const statusClass = getStatusClass(ev.status);

      html += `
        <div class="evidence-card">
          <div class="ev-header">
            <span class="ev-manager-badge ${mgrClass}">
              ● ${ev.manager}
            </span>
            <span class="ev-status-tag ${statusClass}">
              ${ev.status}
            </span>
          </div>

          <div style="font-weight: 600; font-size: 0.9rem; margin-bottom: 0.3rem;">
            ${ev.activity}
          </div>

          <div class="ev-meta-line">
            <span>Check: <strong>${ev.check_type}</strong></span>
            <span>Timestamp: <strong>${ev.timestamp}</strong></span>
            <span>Record ID: <code>${ev.evidence_id}</code></span>
          </div>

          <div style="font-size: 0.83rem; color: #cbd5e1; margin-bottom: 0.4rem;">
            ${match.rationale}
          </div>
      `;

      if (ev.details && Object.keys(ev.details).length > 0) {
        html += `
          <div class="ev-telemetry-box">
            <strong>Telemetry / Inspection Log:</strong><br>
            ${JSON.stringify(ev.details, null, 2)}
          </div>
        `;
      }

      if (ev.media_references && ev.media_references.length > 0) {
        html += `<div class="ev-media-chips">`;
        ev.media_references.forEach(m => {
          html += `
            <span class="media-chip">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline></svg>
              ${m}
            </span>
          `;
        });
        html += `</div>`;
      }

      html += `</div>`;
    });
    html += `</div>`;
  }

  // Traceability trail
  if (res.evidence_traceability && res.evidence_traceability.length > 0) {
    html += `
      <div style="margin-top: 1.25rem; padding: 0.75rem 1rem; background: rgba(0,0,0,0.3); border-radius: 8px; border: 1px solid var(--border-subtle); font-size: 0.78rem;">
        <span style="color: var(--text-muted); font-weight: 600;">AUDIT TRACEABILITY:</span>
        <div style="font-family: var(--font-mono); color: var(--accent-cyan); margin-top: 0.25rem;">
          ${res.evidence_traceability.join(" &bull; ")}
        </div>
      </div>
    `;
  }

  detailContent.innerHTML = html;
}

function getManagerBadgeClass(mgr) {
  const m = mgr.toLowerCase();
  if (m.includes("prep")) return "manager-prep";
  if (m.includes("pack")) return "manager-pack";
  if (m.includes("receiv") || m.includes("inbound")) return "manager-receiving";
  if (m.includes("return")) return "manager-returns";
  if (m.includes("ship")) return "manager-shipping";
  return "manager-prep";
}

function getStatusClass(status) {
  const s = status.toUpperCase();
  if (["PASS", "COMPLIANT", "INTACT", "OK", "VERIFIED"].includes(s)) return "status-pass";
  if (["FAIL", "NON_COMPLIANT", "DAMAGED", "DEFECT", "MISSING"].includes(s)) return "status-fail";
  return "status-partial";
}

function showToast(message) {
  toast.textContent = message;
  toast.style.display = "block";
  setTimeout(() => {
    toast.style.display = "none";
  }, 3500);
}

// Custom Sample Ingestion
function loadCustomSampleData() {
  document.getElementById("input-custom-charges").value = JSON.stringify([
    {
      "charge_id": "CUSTOM-01",
      "shipment_id": "SHP-ALPHA",
      "sku": "SKU-9900",
      "fee_type": "Packaging defect",
      "amount": 55.00,
      "charge_date": "2026-09-28"
    },
    {
      "charge_id": "CUSTOM-02",
      "shipment_id": "SHP-BETA",
      "sku": "SKU-8800",
      "fee_type": "Inbound weight variance",
      "amount": 72.00,
      "charge_date": "2026-09-28"
    }
  ], null, 2);

  document.getElementById("input-custom-evidence").value = JSON.stringify([
    {
      "evidence_id": "EVD-CUST-1",
      "manager": "Prep Manager",
      "shipment_id": "SHP-ALPHA",
      "sku": "SKU-9900",
      "timestamp": "2026-09-10T12:00:00Z",
      "activity": "Unit Packaging Check",
      "check_type": "packaging",
      "status": "PASS",
      "details": {"polybag": "compliant", "seal": "intact"},
      "media_references": ["sample_photo_alpha.jpg"]
    },
    {
      "evidence_id": "EVD-CUST-2",
      "manager": "Pack Manager",
      "shipment_id": "SHP-BETA",
      "sku": "SKU-8800",
      "timestamp": "2026-09-11T14:30:00Z",
      "activity": "Certified Conveyor Scale Weighing",
      "check_type": "weight",
      "status": "PASS",
      "details": {"certified_weight_lbs": 14.5, "billed_variance_flag": false},
      "media_references": ["scale_cert.pdf"]
    }
  ], null, 2);

  document.getElementById("input-custom-reimbursements").value = "[]";
  showToast("Loaded complex sample data into modal.");
}

async function submitCustomData() {
  try {
    const rawCharges = document.getElementById("input-custom-charges").value.trim();
    const rawEvidence = document.getElementById("input-custom-evidence").value.trim();
    const rawReimb = document.getElementById("input-custom-reimbursements").value.trim();

    const charges = rawCharges ? JSON.parse(rawCharges) : [];
    const evidence = rawEvidence ? JSON.parse(rawEvidence) : [];
    const reimbursements = rawReimb ? JSON.parse(rawReimb) : [];

    if (charges.length === 0) {
      alert("Please provide at least one fee charge in the Fee Report pane.");
      return;
    }

    const res = await fetch("/api/evaluate/custom", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        charges: charges,
        operational_evidence: evidence,
        reimbursements: reimbursements
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Server error");
    }

    const data = await res.json();
    currentDossier = data.dossier;
    currentMarkdownReport = data.markdown_report;
    currentScenarioId = "custom_ingestion";

    document.querySelectorAll(".scenario-card").forEach(c => c.classList.remove("active"));
    activeScenarioBadge.textContent = "CUSTOM INGESTION";
    activeScenarioTitle.textContent = "Custom Ingested Multi-Manager Data";
    activeScenarioDescription.textContent = `Evaluated ${charges.length} fee charge(s) against ${evidence.length} operational evidence record(s).`;

    updateKPIs(currentDossier);
    renderChargesList();
    if (currentDossier.results.length > 0) {
      selectCharge(currentDossier.results[0].charge.charge_id);
    }

    customModal.style.display = "none";
    showToast("Successfully evaluated custom dataset!");
  } catch (err) {
    alert("Invalid JSON or evaluation error: " + err.message);
  }
}
