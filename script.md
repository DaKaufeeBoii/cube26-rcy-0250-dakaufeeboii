# 🎬 Video Presentation & Demo Script
## AI Recovery Manager — Turn Evidence into Financial Recovery
**CUBE Buildathon • Track #5: Recovery Manager (RCY #5)**
*Presented by Sydon.ai x Codequesters*

> **Target Duration**: 3 – 5 Minutes  
> **Speaker Role**: Founder / Lead AI Engineer  
> **Format**: Screen Share + Voiceover (or PiP Webcam)  

---

## ⏱️ Video Timeline Overview
| Timestamp | Segment | Visual On Screen | Key Message |
| :--- | :--- | :--- | :--- |
| **0:00 – 0:40** | **Hook & Problem Statement** | Title slide / PDF Problem Statement | Why delayed fees drain ecommerce margins |
| **0:40 – 1:15** | **The Solution & 10-Step Engine** | Web Dashboard Hero & Architecture diagram | Autonomous evidence-to-recovery intelligence |
| **1:15 – 2:05** | **Live Demo: Actionable Claims** | UI Scenario 1 & Scenario 5 | Matching Packaging & Weight fees against Prep/Pack logs |
| **2:05 – 2:55** | **Live Demo: Conservative Guardrails** | UI Scenario 2, 3, & 6 | Handling Partial, Silent, and Ambiguous records without hallucination |
| **2:55 – 3:35** | **Live Demo: Edge Cases** | UI Scenario 7 & 8 | Duplicate billing detection & prior reimbursement reconciliation |
| **3:35 – 4:15** | **Dispute Dossier & CLI/Tests** | 1-Click Dispute Letter & Terminal Pytest | Audit-ready output & 100% test pass rate |
| **4:15 – 4:40** | **Conclusion & Impact** | Executive KPI Summary | Defensibility over volume |

---

## 🎙️ Full Script with Visual Cues

### [0:00 – 0:40] Segment 1: Hook & The Problem
**Visual**: Show the CUBE Buildathon challenge page or the Problem Statement PDF highlighting: *"Sellers receive fees weeks after the event... By that point, operators no longer have easy access to evidence."*

**Speaker (Voiceover)**:
> *"Hello everyone! I’m presenting **Recovery Manager**, our autonomous AI agent built for Track #5 of the CUBE Buildathon by Sydon.ai and Codequesters.*
>
> *Every year, ecommerce operators lose millions in unexpected fulfillment fees, packaging defect penalties, weight variance surcharges, and chargebacks. The biggest challenge? These fees appear weeks after the shipment was dispatched.*
>
> *By that point, operational evidence is buried across dock receiving sheets, prep station logs, and pack conveyor records. Sellers either absorb the loss or risk suspension by filing unsubstantiated disputes.*
>
> *Our challenge was to build an agent that turns scattered operational evidence into defensible financial recovery—with zero hallucination."*

---

### [0:40 – 1:15] Segment 2: The Solution & Architecture
**Visual**: Switch screen to the live web dashboard at `http://127.0.0.1:8000/`. Highlight the glowing **Recovery Manager** logo, the active guardrail badge, and the KPI cards.

**Speaker**:
> *"Here is the AI Recovery Manager dashboard.*
>
> *Unlike a generic chatbot or computer-vision workflow, our agent operates directly on structured operational telemetry across five core departments: Receiving Manager, Prep Manager, Pack Manager, Shipping Manager, and Returns Manager.*
>
> *It executes a strict 10-step autonomous protocol: parsing charges, linking multi-level identifiers, indexing candidate evidence, classifying contradictions or supports, and assembling defensible dispute packages.*
>
> *Notice our core compliance badge right at the top: **Conservative Evidence Guardrail: ENFORCED**. In this agent, UNCERTAIN is a valid outcome, and evidence is never invented."*

---

### [1:15 – 2:05] Segment 3: Live Demo — Defensible Actionable Claims
**Visual**: Click on **Scenario 01 (Correct Claim with Full Evidence)** in the carousel. The dashboard updates instantly. Then click on Charge `#48291`.

**Speaker**:
> *"Let’s test this live with Scenario 1 from the official specification.*
>
> *Here, the platform charged a $38 packaging defect fee claiming an unsealed polybag on shipment `SHP-10291`.*
>
> *Our agent queried the operational store and matched a certified inspection record from the **Prep Manager**. The Prep Manager logged `PASS` with 1.5 mil polybag thickness and 100% tape integrity before shipment dispatch, backed by three verified photographs.*
>
> *The agent classifies this as **CONTRADICTED**, marks the claim as **ACTIONABLE**, and calculates an exact recovery amount of $38.00.*
>
> *Now watch Scenario 5—**Cross-Manager Evidence**. The platform billed an overweight penalty on carton `SHP-7721`. The agent cross-referenced records from the **Pack Manager’s automated Dimension-and-Weight scanner**, proving the box weighed 14.2 lbs, not 28 lbs. Another $65 recovered!"*

---

### [2:05 – 2:55] Segment 4: Live Demo — Conservative Guardrails (Zero Hallucination)
**Visual**: Click on **Scenario 03 (No Evidence)**, then **Scenario 02 (Partial Evidence)**, and **Scenario 06 (Ambiguous Evidence)**.

**Speaker**:
> *"Now, what happens when evidence is incomplete or missing? This is where standard AI agents fail and hallucinate.*
>
> *Let's look at Scenario 3: **Claim with No Evidence**. A $25 unplanned bubblewrap fee was assessed, but no operational records exist. The agent strictly returns: **`SILENT — insufficient evidence`**, generating zero claims. It explains why: 'Evidence is never invented; claim cannot be defended.'*
>
> *Next, Scenario 2: **Partial Evidence**. Dock receipt exists, but no barcode scannability check was recorded. The agent does not guess. It classifies the claim as **UNCERTAIN** and holds filing.*
>
> *And in Scenario 6: **Ambiguous Evidence**. Prep Manager logged `PASS`, but Receiving Manager noted a crushed corner upon arrival. With conflicting signals between managers, the agent refuses to force a conclusion, quarantining the charge as **UNCERTAIN** for supervisor review."*

---

### [2:55 – 3:35] Segment 5: Live Demo — Duplicate Charges & Prior Reimbursements
**Visual**: Click on **Scenario 07 (Duplicate Charges)** and **Scenario 08 (Already Reimbursed)**.

**Speaker**:
> *"The Recovery Manager also reconciles complex billing states.*
>
> *In Scenario 7: **Duplicate Charges**, the platform mistakenly billed the exact same packaging fee twice. The agent evaluates the first charge with evidence, and flags the second charge as **`DUPLICATE`**, unlocking the full $40 recovery.*
>
> *In Scenario 8: **Already Reimbursed**, the operator was billed a $40 adjustment, but our engine cross-references the past reimbursement ledger, finding credit `RMB-9910`. The charge is classified as **`ALREADY_REIMBURSED`**, preventing embarrassing and costly double-claims."*

---

### [3:35 – 4:15] Segment 6: Exporting Dispute Dossiers & Terminal Verification
**Visual**: On Scenario 1 or 4, click **Copy Dispute Letter**, show the toast notification, and paste it into a text view. Then click **Export Dossier (.md)**. Then switch to terminal and run `python cli.py run-scenarios` and `pytest`.

**Speaker**:
> *"When a claim is ready, operators don't need to write letters manually. With one click, they can copy a complete, formal dispute letter—ready for Amazon Seller Support or 3PL claims departments, complete with department timestamps, record IDs, and telemetry.*
>
> *They can also export a full Markdown recovery dossier for their accounting team.*
>
> *For automated workflows, everything can be executed via our command-line tool. Running `python cli.py run-scenarios` executes all 8 canonical scenarios with rich formatted output in milliseconds.*
>
> *And running `python -m pytest tests/` validates 9 comprehensive tests with a 100% pass rate."*

---

### [4:15 – 4:40] Segment 7: Conclusion
**Visual**: Switch back to the dashboard, showing the overall KPI metrics: Total Fees, Defensible Recovery, and the 100% No-Hallucination pill.

**Speaker**:
> *"In summary: the AI Recovery Manager bridges the gap between chaotic fulfillment reality and delayed platform chargebacks.*
>
> *It protects ecommerce margins, enforces strict defensibility over claim volume, and turns operational proof into hard financial recovery.*
>
> *Thank you to Sydon.ai and Codequesters for an incredible buildathon track!"*

---

## 🎬 Tips for Recording Your Demo Video
1. **Resolution**: Record at 1080p (1920x1080) for crisp typography.
2. **Audio**: Use a dedicated microphone or headset with minimal room echo.
3. **Pacing**: Pause for 1-2 seconds after clicking each scenario to let the UI update sink in.
4. **Hosting**: Upload the video as an unlisted YouTube video, Loom link, or Google Drive link (make sure permissions are set to "Anyone with the link can view").
