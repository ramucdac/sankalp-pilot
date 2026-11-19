import pytest
import agent.graph as g
from agent.rules import check_invoice


def claim():
    return {"original_invoice_ref": "INV/1", "stockist_code": "STK0001",
            "sku_code": "PFL1104", "batch_no": "B1", "cnf_code": "CF-E01"}


def row(**changes):
    values = {"invoice_no": "INV/1", "stockist_code": "stk0001",
              "sku_code": "PFL-1104", "batch_no": "b1", "cnf_code": "CFE01",
              "invoice_date": "18-Apr-2024"}
    values.update(changes)
    return {"source_file": "primary_sales.csv", "source_record": 9, "values": values}


def test_normalized_invoice_identity():
    assert check_invoice(claim(), [row()])["matched"]


@pytest.mark.parametrize("field", ["invoice_no", "stockist_code", "sku_code", "batch_no", "cnf_code"])
def test_wrong_identity(field):
    assert not check_invoice(claim(), [row(**{field: "WRONG"})])["matched"]


def test_missing_reference_routes_to_person():
    result = check_invoice({**claim(), "original_invoice_ref": ""}, [])
    assert not result["matched"]
    assert "Area Manager" in result["checks"][0]


def test_missing_invoice():
    assert not check_invoice(claim(), [])["matched"]


def test_invalid_date():
    assert not check_invoice(claim(), [row(invoice_date="bad")])["matched"]


def test_conflicting_dates():
    assert not check_invoice(claim(), [row(), row(invoice_date="19-04-2024")])["matched"]


def test_equivalent_dates_and_repeated_evidence():
    assert check_invoice(claim(), [row(), row(invoice_date="2024-04-18")])["matched"]


def test_invoice_failure_does_not_erase_batch_review():
    state = {"records": [{"values": claim()}], "checks": ["Batch issue"], "review": True}
    original = g.load_sales_index
    try:
        g.load_sales_index = lambda: {"INV/1": [row()]}
        result = g.verify_invoice(state)
    finally:
        g.load_sales_index = original
    assert result["review"]
    assert result["checks"][0] == "Batch issue"
    assert result["invoice_records"][0]["source_record"] == 9
