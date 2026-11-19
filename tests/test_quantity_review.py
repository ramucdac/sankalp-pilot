import pytest
from agent.rules import check_claim_quantity


def claim(**changes):
    value = {"claim_no": "CLM-2404-00001", "claim_date": "18-04-2024",
             "stockist_code": "STK1", "sku_code": "PFL1104",
             "batch_no": "B1", "qty_claimed": "11"}
    value.update(changes)
    return value


def sale(number=1, **changes):
    value = {"invoice_no": "INV/1", "invoice_date": "15-04-2024",
             "stockist_code": "stk1", "sku_code": "PFL-1104", "batch_no": "b1",
             "invoiced_qty": "10", "free_qty": "1"}
    value.update(changes)
    return {"source_file": "primary_sales.csv", "source_record": number, "values": value}


@pytest.mark.parametrize("quantity,review", [("10", False), ("11", False), ("12", True)])
def test_quantity_boundaries(quantity, review):
    result = check_claim_quantity(claim(qty_claimed=quantity), [sale()], [])
    assert result["review"] is review
    assert result["summary"]["gross_supplied_packs_in_extract"] == "11"


def test_exact_repeat_counted_once_but_sources_retained():
    result = check_claim_quantity(claim(), [sale(1), sale(2)], [])
    assert result["summary"]["gross_supplied_packs_in_extract"] == "11"
    assert len(result["evidence"]) == 2


def test_distinct_split_rows_added():
    result = check_claim_quantity(claim(), [sale(), sale(2, invoiced_qty="5", free_qty="0")], [])
    assert result["summary"]["gross_supplied_packs_in_extract"] == "16"


def test_future_and_other_stockist_supplies_excluded():
    result = check_claim_quantity(claim(), [sale(), sale(2, invoice_date="19-04-2024"),
                                           sale(3, stockist_code="STK2")], [])
    assert result["summary"]["gross_supplied_packs_in_extract"] == "11"


@pytest.mark.parametrize("changes", [{"free_qty": "bad"}, {"invoice_date": "bad"}])
def test_incomplete_supply_does_not_produce_comparison(changes):
    result = check_claim_quantity(claim(), [sale(**changes)], [])
    assert result["review"] and not result["summary"]


def test_missing_supply_requires_review():
    assert check_claim_quantity(claim(), [], [])["review"]


@pytest.mark.parametrize("status", ["Credited", "Pending", "Rejected"])
def test_prior_claim_flagged_without_deducting(status):
    earlier = {"source_file": "expiry_claims.csv", "source_record": 2,
               "values": claim(claim_no="CLM-2404-00000", claim_date="17-04-2024", status=status)}
    result = check_claim_quantity(claim(), [sale()], [earlier])
    assert result["review"]
    assert result["summary"]["gross_supplied_packs_in_extract"] == "11"


def test_future_claim_is_not_earlier():
    future = {"source_file": "expiry_claims.csv", "source_record": 2,
              "values": claim(claim_no="CLM-2404-00002", claim_date="19-04-2024")}
    assert not check_claim_quantity(claim(), [sale()], [future])["review"]


@pytest.mark.parametrize("value", ["", "0", "-1", "1.5", "NaN"])
def test_unusable_claim_quantity(value):
    assert check_claim_quantity(claim(qty_claimed=value), [sale()], [])["review"]
