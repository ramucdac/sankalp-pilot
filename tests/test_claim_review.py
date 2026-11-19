"""Tests for the new claim-review path. No API key required."""
import pytest
import agent.graph as g
from agent.rules import compare_claim_to_batch


def evidence(values, filename="expiry_claims.csv", number=1):
    return {"source_file": filename, "source_record": number, "values": values}


@pytest.mark.parametrize("sku,expiry,matched", [
    ("PFL1104", "30-09-2025", True),
    ("pfl-1104", "2025-09-30", True),
    ("PFL1105", "30-09-2025", False),
    ("PFL1104", "31-10-2025", False),
    ("PFL1104", "", False),
    ("", "30-09-2025", False),
])
def test_comparisons(sku, expiry, matched):
    result = compare_claim_to_batch(
        {"sku_code": sku, "expiry_date_as_claimed": expiry},
        {"sku_code": "PFL1104", "expiry_date": "30-Sep-2025"},
    )
    assert result["matched"] is matched


@pytest.mark.parametrize("case,status,evidence_count", [
    ("match", "needs_review", 6),
    ("missing_batch", "needs_review", 5),
    ("ambiguous_batch", "needs_review", 7),
    ("conflicting_claim", "needs_review", 2),
    ("missing_claim", "not_found", 0),
])
def test_graph_routes(monkeypatch, case, status, evidence_count):
    claim = {"claim_no": "CLM-2404-04177", "batch_no": "K2310408",
             "sku_code": "PFL1104", "expiry_date_as_claimed": "30-09-2025",
             "original_invoice_ref": "INV/1", "stockist_code": "STK1", "cnf_code": "CF-E01",
             "claim_date": "18-04-2024", "qty_claimed": "1", "claim_type": "Breakage in transit"}
    batch = {"batch_no": "K2310408", "sku_code": "PFL1104",
             "expiry_date": "2025-09-30"}
    claims = [evidence(claim)]
    batches = [evidence(batch, "batch_master.csv")]
    if case == "missing_claim":
        claims = []
    if case == "missing_batch":
        batches = []
    if case == "ambiguous_batch":
        batches.append(evidence(batch, "batch_master.csv", 2))
    if case == "conflicting_claim":
        claims.append(evidence({**claim, "sku_code": "PFL1105"}, number=2))
    monkeypatch.setattr(g, "load_claim_index", lambda: {claim["claim_no"]: claims})
    monkeypatch.setattr(g, "load_batch_index", lambda: {"K2310408": batches})
    sale = {"invoice_no": "INV/1", "invoice_date": "18-04-2024",
            "stockist_code": "STK1", "cnf_code": "CF-E01",
            "sku_code": "PFL1104", "batch_no": "K2310408", "invoiced_qty": "10", "free_qty": "1"}
    monkeypatch.setattr(g, "load_sales_index", lambda: {"INV/1": [evidence(sale, "primary_sales.csv")]})
    result = g.run_question(claim["claim_no"])
    assert result["status"] == status
    assert len(result["evidence"]) == evidence_count
    assert result["model_calls"] == 0
    assert "approval" in result["answer"] or status == "not_found"


def test_invalid_claim_input():
    assert g.run_question("CLM-bad")["status"] == "invalid_input"
