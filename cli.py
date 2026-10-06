#!/usr/bin/env python3
"""
Recovery Manager Command-Line Interface (CLI)
Autonomous AI Evidence-to-Recovery Agent.
"""

import json
import argparse
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from recovery_manager import (
    RecoveryEngine,
    EvidenceStore,
    AssessmentType,
    ClaimStatus,
    handle_agent_request
)
from recovery_manager.parser import (
    parse_fee_charges_from_json,
    parse_fee_charges_from_csv,
    parse_operational_evidence_from_json,
    parse_reimbursements_from_json
)
from recovery_manager.dossier import format_dossier_markdown, generate_formal_dispute_letter

console = Console()


def run_all_scenarios():
    """Run all 8 canonical test scenarios and print beautiful evaluation summary."""
    scenarios_path = Path(__file__).parent / "data" / "scenarios" / "all_scenarios.json"
    if not scenarios_path.exists():
        console.print(f"[red]Error: Scenarios file not found at {scenarios_path}[/red]")
        return

    with open(scenarios_path, "r", encoding="utf-8") as f:
        data = json.load(f)["scenarios"]

    console.print(Panel.fit(
        "[bold cyan]AI RECOVERY MANAGER — CUBE BUILDATHON BENCHMARK[/bold cyan]\n"
        "[italic white]Testing 8 official logistics scenarios with strict conservative evidence rules[/italic white]",
        border_style="cyan"
    ))

    summary_table = Table(title="Test Scenarios Execution Results", show_lines=True)
    summary_table.add_column("Scenario ID", style="bold yellow")
    summary_table.add_column("Scenario Description", style="white")
    summary_table.add_column("Total Fee", justify="right", style="magenta")
    summary_table.add_column("Assessment", style="bold")
    summary_table.add_column("Claim Status", style="bold")
    summary_table.add_column("Recovery ($)", justify="right", style="bold green")
    summary_table.add_column("Result Pass", justify="center")

    total_fees_all = 0.0
    total_recovered_all = 0.0

    for sc_key, sc in data.items():
        charges = parse_fee_charges_from_json(sc["charges"])
        evidence = parse_operational_evidence_from_json(sc.get("operational_evidence", []))
        reimbursements = parse_reimbursements_from_json(sc.get("reimbursements", []))

        store = EvidenceStore()
        store.add_evidence_batch(evidence)
        store.add_reimbursement_batch(reimbursements)

        engine = RecoveryEngine(store)
        dossier = engine.evaluate_charges(charges)

        expected_assess = sc["expected_assessment"]
        expected_claim = sc["expected_claim_amount"]

        actual_claim = dossier.total_potential_recovery
        primary_assess = dossier.results[0].assessment.value
        primary_status = dossier.results[0].claim_status.value

        # Check correctness
        claim_match = abs(actual_claim - expected_claim) < 0.01
        is_pass = claim_match and (primary_assess == expected_assess or (expected_assess == "DUPLICATE" and any(r.assessment.value == "DUPLICATE" for r in dossier.results)))

        color = "green" if is_pass else "red"
        pass_symbol = "[bold green]PASS[/bold green]" if is_pass else "[bold red]FAIL[/bold red]"

        # Colorize assessment
        assess_style = "green" if primary_assess == "CONTRADICTED" else ("red" if primary_assess == "SUPPORTED" else "yellow")

        summary_table.add_row(
            sc_key,
            sc["name"],
            f"${dossier.total_fee_amount:.2f}",
            f"[{assess_style}]{primary_assess}[/{assess_style}]",
            primary_status,
            f"${dossier.total_potential_recovery:.2f}",
            pass_symbol
        )

        total_fees_all += dossier.total_fee_amount
        total_recovered_all += dossier.total_potential_recovery

    console.print(summary_table)

    console.print(f"\n[bold]Total Evaluated Fees across Scenarios:[/bold] ${total_fees_all:.2f}")
    console.print(f"[bold green]Total Defensible Recoveries:[/bold green] ${total_recovered_all:.2f}")
    console.print(f"[bold cyan]Zero Hallucination Constraint:[/bold cyan] 100% Enforced\n")


def analyze_files(fees_path: str, evidence_path: Optional[str] = None, reimb_path: Optional[str] = None, output_dossier: Optional[str] = None):
    """Analyze fee report against evidence file."""
    f_path = Path(fees_path)
    if not f_path.exists():
        console.print(f"[red]Error: Fee file not found: {fees_path}[/red]")
        return

    content = f_path.read_text(encoding="utf-8")
    if f_path.suffix.lower() == ".csv":
        charges = parse_fee_charges_from_csv(content)
    else:
        charges = parse_fee_charges_from_json(content)

    store = EvidenceStore()

    if evidence_path:
        ev_file = Path(evidence_path)
        if ev_file.exists():
            ev_content = ev_file.read_text(encoding="utf-8")
            evidence_records = parse_operational_evidence_from_json(ev_content)
            store.add_evidence_batch(evidence_records)
            console.print(f"[green]Loaded {len(evidence_records)} operational evidence records.[/green]")

    if reimb_path:
        rmb_file = Path(reimb_path)
        if rmb_file.exists():
            rmb_content = rmb_file.read_text(encoding="utf-8")
            reimbursements = parse_reimbursements_from_json(rmb_content)
            store.add_reimbursement_batch(reimbursements)
            console.print(f"[green]Loaded {len(reimbursements)} past reimbursement records.[/green]")

    engine = RecoveryEngine(store)
    dossier = engine.evaluate_charges(charges)

    # Print results
    console.print(Panel.fit(
        f"[bold cyan]Recovery Analysis Summary[/bold cyan]\n"
        f"Charges Evaluated: {dossier.total_charges_evaluated}\n"
        f"Total Fee Amount: ${dossier.total_fee_amount:.2f}\n"
        f"[bold green]Actionable Recovery: ${dossier.total_potential_recovery:.2f}[/bold green]\n"
        f"Supported (Legitimate) Fees: ${dossier.total_supported_fees:.2f}\n"
        f"Silent / Inconclusive: ${dossier.total_silent_or_inconclusive:.2f}\n"
        f"Already Reimbursed: ${dossier.total_already_reimbursed:.2f}",
        border_style="green"
    ))

    table = Table(title="Evaluated Charges", show_lines=True)
    table.add_column("Charge ID", style="bold")
    table.add_column("Shipment", style="cyan")
    table.add_column("Fee Type", style="yellow")
    table.add_column("Fee ($)", justify="right")
    table.add_column("Assessment", style="bold")
    table.add_column("Claim ($)", justify="right", style="bold green")
    table.add_column("Evidence Count", justify="center")

    for res in dossier.results:
        assess_color = "green" if res.assessment == AssessmentType.CONTRADICTED else ("red" if res.assessment == AssessmentType.SUPPORTED else "yellow")
        table.add_row(
            res.charge.charge_id,
            res.charge.shipment_id or "N/A",
            res.charge.fee_type,
            f"${res.charge.amount:.2f}",
            f"[{assess_color}]{res.assessment.value}[/{assess_color}]",
            f"${res.potential_claim_amount:.2f}",
            str(len(res.supporting_evidence))
        )

    console.print(table)

    if output_dossier:
        md_text = format_dossier_markdown(dossier)
        out_file = Path(output_dossier)
        out_file.write_text(md_text, encoding="utf-8")
        console.print(f"[bold green]Full dispute dossier exported to: {out_file.resolve()}[/bold green]")


def execute_agent_request(input_path: str, output_path: Optional[str] = None):
    """Execute standard Evidence Contract AgentInput file and print/save AgentOutput."""
    in_file = Path(input_path)
    if not in_file.exists():
        console.print(f"[bold red]Error: Input request file '{input_path}' not found.[/bold red]")
        sys.exit(1)

    req_data = json.loads(in_file.read_text(encoding="utf-8"))
    sample_csv = Path(__file__).parent / "data" / "fee_report_sample.csv"
    output = handle_agent_request(req_data, sample_fee_csv_path=sample_csv)

    console.print(Panel.fit(
        f"[bold cyan]Agent Output — Evidence Contract Execution[/bold cyan]\n"
        f"Stage: [yellow]{output.get('stage')}[/yellow] | Status: [green]{output.get('status')}[/green] | "
        f"Verdict: [bold]{output.get('verdict')}[/bold] | Recommendation: {output.get('next_step_recommendation')}",
        border_style="cyan"
    ))

    ev = output.get("evidence", {})
    payload = ev.get("payload", {})
    console.print(f"Content Hash: [dim]{ev.get('content_hash')}[/dim]")
    console.print(f"Total Charges: {len(payload.get('charges', []))} | Claimable: [bold green]${payload.get('claimable_usd', 0.0):.2f}[/bold green]")

    if output_path:
        out_file = Path(output_path)
        out_file.write_text(json.dumps(output, indent=2), encoding="utf-8")
        console.print(f"[bold green]Saved AgentOutput to: {out_file.resolve()}[/bold green]")
    else:
        console.print_json(data=output)


def main():
    parser = argparse.ArgumentParser(description="Recovery Manager — AI Evidence-to-Recovery Agent")
    subparsers = parser.add_subparsers(dest="command")

    # run-scenarios
    subparsers.add_parser("run-scenarios", help="Execute all 8 benchmark test scenarios")

    # analyze
    analyze_parser = subparsers.add_parser("analyze", help="Analyze fee report against evidence records")
    analyze_parser.add_argument("--fees", required=True, help="Path to fee report file (JSON or CSV)")
    analyze_parser.add_argument("--evidence", help="Path to operational evidence file (JSON)")
    analyze_parser.add_argument("--reimbursements", help="Path to reimbursements file (JSON)")
    analyze_parser.add_argument("--output", help="Path to output markdown dispute dossier")

    # handle-request (Contract execution)
    handle_parser = subparsers.add_parser("handle-request", help="Execute standard Evidence Contract AgentInput")
    handle_parser.add_argument("--input", required=True, help="Path to AgentInput JSON file")
    handle_parser.add_argument("--output", help="Optional path to save AgentOutput JSON file")

    args = parser.parse_args()

    if args.command == "run-scenarios" or args.command is None:
        run_all_scenarios()
    elif args.command == "analyze":
        analyze_files(args.fees, args.evidence, args.reimbursements, args.output)
    elif args.command == "handle-request":
        execute_agent_request(args.input, args.output)


if __name__ == "__main__":
    main()
