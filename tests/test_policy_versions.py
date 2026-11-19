import pytest
from agent.rules import check_invoice
import agent.graph as g


@pytest.mark.parametrize("when", ["22-04-2024", "31-03-2025"])
def test_pre_exception_claim_needs_historical_review(when):
    result = check_invoice({"original_invoice_ref": "", "claim_date": when}, [])
    assert not result["matched"]
    assert "predates" in result["checks"][0]
    assert "No automatic rejection" in result["checks"][0]


@pytest.mark.parametrize("when", ["01-04-2025", "02-04-2025", "2025-04-01"])
def test_exception_effective_date_and_after(when):
    result = check_invoice({"original_invoice_ref": "", "claim_date": when}, [])
    assert not result["matched"]
    assert "may apply" in result["checks"][0]
    assert "Neither verification nor approval is established" in result["checks"][0]


@pytest.mark.parametrize("when", ["", "bad"])
def test_unknown_date_does_not_assume_version(when):
    message = check_invoice({"original_invoice_ref": "", "claim_date": when}, [])["checks"][0]
    assert "cannot determine" in message


def test_graph_attaches_missing_invoice_policy_without_guessing_invoice(monkeypatch):
    claim = {"claim_no": "CLM-2404-04181", "original_invoice_ref": "", "claim_date": "22-04-2024"}
    state = {"records": [{"source_file": "expiry_claims.csv", "source_record": 2,
                          "values": claim}], "checks": [], "review": False}
    def unexpected_lookup():
        raise AssertionError("Missing invoice must not trigger an invoice guess")
    monkeypatch.setattr(g, "load_sales_index", unexpected_lookup)
    result = g.verify_invoice(state)
    assert result["review"]
    assert result["invoice_records"] == []
    assert result["invoice_policy_evidence"][0]["values"]["effective_from"] == "2025-04-01"
