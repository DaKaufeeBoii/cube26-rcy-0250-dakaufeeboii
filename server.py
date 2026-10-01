"""
FastAPI Server for AI Recovery Manager.
Exposes REST APIs for evaluating fee reports against multi-manager operational evidence,
and serves the rich web application interface.
"""

import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel

from recovery_manager import (
    RecoveryEngine,
    EvidenceStore,
    AssessmentType,
    ClaimStatus,
    FeeCharge,
    OperationalEvidence,
    ReimbursementRecord,
    RecoveryDossier
)
from recovery_manager.parser import (
    parse_fee_charges_from_json,
    parse_operational_evidence_from_json,
    parse_reimbursements_from_json
)
from recovery_manager.dossier import format_dossier_markdown, generate_formal_dispute_letter

app = FastAPI(title="AI Recovery Manager API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SCENARIOS_PATH = Path(__file__).parent / "data" / "scenarios" / "all_scenarios.json"
WEB_DIR = Path(__file__).parent / "web"


def load_all_scenarios() -> Dict[str, Any]:
    with open(SCENARIOS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["scenarios"]


@app.get("/api/scenarios")
def get_scenarios():
    """Return all pre-configured test scenarios."""
    data = load_all_scenarios()
    scenarios_list = []
    for k, v in data.items():
        scenarios_list.append({
            "id": k,
            "name": v["name"],
            "description": v["description"],
            "charges_count": len(v["charges"]),
            "evidence_count": len(v.get("operational_evidence", [])),
            "reimbursements_count": len(v.get("reimbursements", [])),
            "expected_assessment": v["expected_assessment"],
            "expected_claim_amount": v["expected_claim_amount"]
        })
    return {"scenarios": scenarios_list}


@app.get("/api/scenarios/{scenario_id}")
def get_scenario_details(scenario_id: str):
    """Get full data for a specific scenario."""
    data = load_all_scenarios()
    if scenario_id not in data:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return {"scenario": data[scenario_id]}


@app.post("/api/evaluate/scenario/{scenario_id}")
def evaluate_scenario(scenario_id: str):
    """Run autonomous recovery analysis on a scenario."""
    data = load_all_scenarios()
    if scenario_id not in data:
        raise HTTPException(status_code=404, detail="Scenario not found")

    sc = data[scenario_id]
    charges = parse_fee_charges_from_json(sc["charges"])
    evidence = parse_operational_evidence_from_json(sc.get("operational_evidence", []))
    reimbursements = parse_reimbursements_from_json(sc.get("reimbursements", []))

    store = EvidenceStore()
    store.add_evidence_batch(evidence)
    store.add_reimbursement_batch(reimbursements)

    engine = RecoveryEngine(store)
    dossier = engine.evaluate_charges(charges)

    return {
        "scenario_id": scenario_id,
        "scenario_name": sc["name"],
        "dossier": dossier.model_dump(),
        "markdown_report": format_dossier_markdown(dossier)
    }


class CustomEvaluateRequest(BaseModel):
    charges: List[Dict[str, Any]]
    operational_evidence: Optional[List[Dict[str, Any]]] = None
    reimbursements: Optional[List[Dict[str, Any]]] = None


@app.post("/api/evaluate/custom")
def evaluate_custom(request: CustomEvaluateRequest):
    """Evaluate custom user-provided charges, evidence, and reimbursements."""
    try:
        charges = parse_fee_charges_from_json(request.charges)
        evidence = parse_operational_evidence_from_json(request.operational_evidence or [])
        reimbursements = parse_reimbursements_from_json(request.reimbursements or [])

        store = EvidenceStore()
        store.add_evidence_batch(evidence)
        store.add_reimbursement_batch(reimbursements)

        engine = RecoveryEngine(store)
        dossier = engine.evaluate_charges(charges)

        return {
            "dossier": dossier.model_dump(),
            "markdown_report": format_dossier_markdown(dossier)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/dispute-letter/{scenario_id}/{charge_id}")
def get_dispute_letter(scenario_id: str, charge_id: str):
    """Generate formal platform dispute filing letter for an actionable charge."""
    data = load_all_scenarios()
    if scenario_id not in data:
        raise HTTPException(status_code=404, detail="Scenario not found")

    sc = data[scenario_id]
    charges = parse_fee_charges_from_json(sc["charges"])
    evidence = parse_operational_evidence_from_json(sc.get("operational_evidence", []))
    reimbursements = parse_reimbursements_from_json(sc.get("reimbursements", []))

    store = EvidenceStore()
    store.add_evidence_batch(evidence)
    store.add_reimbursement_batch(reimbursements)

    engine = RecoveryEngine(store)
    dossier = engine.evaluate_charges(charges)

    for res in dossier.results:
        if res.charge.charge_id == charge_id:
            letter = generate_formal_dispute_letter(res)
            return {"charge_id": charge_id, "dispute_letter": letter}

    raise HTTPException(status_code=404, detail="Charge ID not found in scenario")


# Mount static web directory
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
def serve_index():
    index_file = WEB_DIR / "index.html"
    if index_file.exists():
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Recovery Manager API is running. Web assets not found.</h1>")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
