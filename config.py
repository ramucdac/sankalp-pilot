"""Case-policy configuration. These values are not legal guidance."""
from datetime import date

CLAIM_POLICY = {
    "source_file": "02_trade_terms_and_returns_policy.pdf",
    "source_record": "Printed page 3, section 5.2; revision history on page 1",
    "values": {
        "invoice_window_days": 7,
        "near_expiry_window_days": 90,
        "expired_window_days": 90,
        "ninety_day_rule_effective_from": "2024-04-01",
        "receipt_date_assumption":
            "Recorded claim_date is used provisionally as claim receipt date. "
            "The mapping is not confirmed.",
    },
}

INVOICE_WINDOW_DAYS = CLAIM_POLICY["values"]["invoice_window_days"]
NEAR_EXPIRY_WINDOW_DAYS = CLAIM_POLICY["values"]["near_expiry_window_days"]
EXPIRED_WINDOW_DAYS = CLAIM_POLICY["values"]["expired_window_days"]
POLICY_SUPPORTED_FROM = date.fromisoformat(
    CLAIM_POLICY["values"]["ninety_day_rule_effective_from"]
)


QUANTITY_POLICY = {
    "source_file": "02_trade_terms_and_returns_policy.pdf",
    "source_record": "Printed page 3, section 5.5; printed page 4, section 5.6",
    "values": {
        "quantity_limit": "Claimed batch packs must not exceed packs invoiced to the stockist, including free packs.",
        "earlier_claim_check": "Check for an earlier claim on the same stockist and batch during verification.",
        "analysis_scope": "Compare gross matching supply in the extract on or before claim_date; preserve evidence. Do not automatically deduct earlier claims.",
    },
}


INVOICE_POLICY = {
    "source_file": "02_trade_terms_and_returns_policy.pdf",
    "source_record": "Printed page 1 revision history (v4.2); page 3 section 5.4",
    "values": {
        "effective_from": "2025-04-01",
        "exception": "Missing invoice may be verified against the stockist purchase ledger for the batch, with written Area Manager approval.",
        "historical_handling": "Do not automatically apply this exception to earlier claims; review applicable policy and original supply evidence.",
        "date_basis": "Recorded claim_date is a provisional basis; actual receipt date and policy applicability require confirmation.",
    },
}
LEDGER_EXCEPTION_EFFECTIVE_FROM = date.fromisoformat(INVOICE_POLICY["values"]["effective_from"])
