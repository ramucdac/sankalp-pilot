from datetime import date, timedelta
import pytest
from agent.rules import check_submission_window


def make_claim(kind, when):
    return {"claim_type": kind, "claim_date": when.isoformat(),
            "sku_code": "PFL1104", "batch_no": "B1",
            "expiry_date_as_claimed": "30-09-2025",
            "original_invoice_ref": "INV/1", "stockist_code": "STK1",
            "cnf_code": "CF-E01"}


def batch():
    return {"sku_code": "PFL1104", "expiry_date": "2025-09-30"}


def invoice():
    return [{"values": {"invoice_no": "INV/1", "invoice_date": "15-04-2024",
            "stockist_code": "STK1", "sku_code": "PFL1104",
            "batch_no": "B1", "cnf_code": "CF-E01"}}]


@pytest.mark.parametrize("kind", ["Breakage in transit", "Short supply"])
@pytest.mark.parametrize("days,expected", [(-1, "outside_window"), (0, "within_window"),
                                         (7, "within_window"), (8, "outside_window")])
def test_invoice_boundaries(kind, days, expected):
    claim = make_claim(kind, date(2024, 4, 15) + timedelta(days=days))
    result = check_submission_window(claim, invoice_records=invoice())
    assert result["outcome"] == expected
    assert result["review"]  # Receipt-date mapping remains unconfirmed.


@pytest.mark.parametrize("kind,days,expected", [
    ("Near expiry", -91, "outside_window"),
    ("Near expiry", -90, "within_window"),
    ("Near expiry", 0, "within_window"),
    ("Near expiry", 1, "outside_window"),
    ("Expired", -1, "outside_window"),
    ("Expired", 0, "within_window"),
    ("Expired", 90, "within_window"),
    ("Expired", 91, "outside_window"),
])
def test_expiry_boundaries(kind, days, expected):
    claim = make_claim(kind, date(2025, 9, 30) + timedelta(days=days))
    assert check_submission_window(claim, batch())["outcome"] == expected


@pytest.mark.parametrize("case", ["missing_date", "unknown_type", "wrong_batch",
                                 "missing_invoice", "earlier_policy"])
def test_missing_or_unverified_evidence(case):
    claim = make_claim("Expired", date(2025, 10, 1))
    master = batch()
    if case == "missing_date":
        claim["claim_date"] = ""
    elif case == "unknown_type":
        claim["claim_type"] = "OTHER"
    elif case == "wrong_batch":
        master["sku_code"] = "PFL1105"
    elif case == "missing_invoice":
        claim["claim_type"] = "Short supply"
    elif case == "earlier_policy":
        claim["claim_date"] = "31-03-2024"
    assert check_submission_window(claim, master)["outcome"] == "needs_review"
