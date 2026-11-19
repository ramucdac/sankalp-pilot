"""Deterministic record comparisons; these do not approve claims."""
from datetime import datetime


def normalize_sku(value):
    code = (value or "").strip().upper()
    if code.startswith("PFL-") and len(code) == 8 and code[4:].isdigit():
        return "PFL" + code[4:]
    return code


def parse_date(value):
    for pattern in ("%d-%m-%Y", "%Y-%m-%d", "%d-%b-%Y"):
        try:
            return datetime.strptime((value or "").strip(), pattern).date()
        except ValueError:
            pass
    raise ValueError("Missing or unreadable date")


def compare_claim_to_batch(claim, batch):
    """Return readable checks using original records as evidence."""
    claimed_sku = normalize_sku(claim.get("sku_code"))
    master_sku = normalize_sku(batch.get("sku_code"))
    if not claimed_sku or not master_sku:
        sku_check = "SKU: missing value; needs review."
    elif claimed_sku != master_sku:
        sku_check = "SKU: mismatch; needs review."
    else:
        sku_check = "SKU: matches after known format normalization."

    try:
        claim_expiry = parse_date(claim.get("expiry_date_as_claimed"))
        master_expiry = parse_date(batch.get("expiry_date"))
        expiry_matches = claim_expiry == master_expiry
        expiry_check = (
            "Expiry: matches the batch master."
            if expiry_matches else "Expiry: mismatch; needs review."
        )
    except ValueError:
        expiry_matches = False
        expiry_check = "Expiry: missing or unreadable date; needs review."

    matched = bool(claimed_sku and master_sku and claimed_sku == master_sku
                   and expiry_matches)
    return {"matched": matched, "checks": [sku_check, expiry_check]}


def normalize_identifier(value):
    return (value or "").strip().upper()


def normalize_cfa(value):
    code = normalize_identifier(value)
    aliases = {"CFE01": "CF-E01", "CFN01": "CF-N01", "CFN02": "CF-N02",
               "CFS01": "CF-S01", "CFS02": "CF-S02", "CFW01": "CF-W01"}
    return aliases.get(code, code)


def missing_invoice_explanation(claim):
    from config import LEDGER_EXCEPTION_EFFECTIVE_FROM
    try:
        when = parse_date(claim.get("claim_date"))
    except ValueError:
        return (
            "Invoice reference: missing. Claim date is unavailable; cannot determine "
            "whether the purchase-ledger and Area Manager approval exception applies. "
            "Needs a person and historical-policy review."
        )
    if when < LEDGER_EXCEPTION_EFFECTIVE_FROM:
        return (
            "Invoice reference: missing. Recorded claim date predates the ledger "
            "exception shown in policy evidence. Do not apply that later exception "
            "automatically; a person must review the applicable historical policy "
            "and original supply evidence. No automatic rejection."
        )
    return (
        "Invoice reference: missing. Based on recorded claim date, the later "
        "purchase-ledger verification route may apply with written Area Manager "
        "approval. Neither verification nor approval is established by this extract. "
        "Confirm receipt date and applicability; needs a person."
    )


def check_invoice(claim, records):
    """Verify identity and one usable invoice date, without valuing quantities."""
    reference = normalize_identifier(claim.get("original_invoice_ref"))
    if not reference:
        return {"matched": False, "checks": [missing_invoice_explanation(claim)]}
    if not records:
        return {"matched": False, "checks": [
            "Referenced invoice not found in the supplied sales extract; needs review."
        ]}

    normalizers = {
        "invoice_no": normalize_identifier,
        "stockist_code": normalize_identifier,
        "sku_code": normalize_sku,
        "batch_no": normalize_identifier,
        "cnf_code": normalize_cfa,
    }
    claim_fields = {**claim, "invoice_no": reference}
    matched = []
    for record in records:
        sale = record["values"]
        if all(
            normalizer(claim_fields.get(field))
            and normalizer(claim_fields.get(field)) == normalizer(sale.get(field))
            for field, normalizer in normalizers.items()
        ):
            matched.append(record)

    if not matched:
        return {"matched": False, "checks": [
            "Invoice exists, but no sales row matches the claim's stockist, SKU, "
            "batch and billing CFA together; needs review."
        ]}

    try:
        dates = {parse_date(record["values"].get("invoice_date")) for record in matched}
    except ValueError:
        return {"matched": False, "checks": [
            "Invoice identity matches, but a matching row has an unreadable date; needs review."
        ]}
    if len(dates) != 1:
        return {"matched": False, "checks": [
            "Matching invoice rows have conflicting dates; needs review."
        ]}
    return {"matched": True, "checks": [
        "Invoice: stockist, SKU, batch and billing CFA match. "
        "Matching rows have one consistent readable invoice date."
    ]}


def check_submission_window(claim, batch=None, invoice_records=None):
    """Provisional calendar-day comparison; receipt-date mapping is unconfirmed."""
    from config import (INVOICE_WINDOW_DAYS, NEAR_EXPIRY_WINDOW_DAYS,
                        EXPIRED_WINDOW_DAYS, POLICY_SUPPORTED_FROM)

    def result(outcome, message):
        return {"outcome": outcome, "checks": [message], "review": True}

    try:
        recorded_date = parse_date(claim.get("claim_date"))
    except ValueError:
        return result("needs_review", "Submission window: claim date is missing or unreadable.")
    if recorded_date < POLICY_SUPPORTED_FROM:
        return result("needs_review", "Submission window: earlier policy version needs review.")

    kind = normalize_identifier(claim.get("claim_type"))
    if kind in {"BREAKAGE IN TRANSIT", "SHORT SUPPLY"}:
        invoice_records = invoice_records or []
        verification = check_invoice(claim, invoice_records)
        if not verification["matched"]:
            return result("needs_review", "Submission window: a verified invoice date is required.")
        matching = [
            record for record in invoice_records
            if check_invoice(claim, [record])["matched"]
        ]
        reference_date = parse_date(matching[0]["values"].get("invoice_date"))
        elapsed = (recorded_date - reference_date).days
        within = 0 <= elapsed <= INVOICE_WINDOW_DAYS
        comparison = (
            f"{elapsed} calendar days from invoice; allowed range is "
            f"0 to {INVOICE_WINDOW_DAYS} days inclusive."
        )
    elif kind in {"NEAR EXPIRY", "EXPIRED"}:
        if batch is None or not compare_claim_to_batch(claim, batch)["matched"]:
            return result("needs_review", "Submission window: a matching verified batch expiry is required.")
        reference_date = parse_date(batch.get("expiry_date"))
        elapsed = (recorded_date - reference_date).days
        if kind == "NEAR EXPIRY":
            low, high = -NEAR_EXPIRY_WINDOW_DAYS, 0
        else:
            low, high = 0, EXPIRED_WINDOW_DAYS
        within = low <= elapsed <= high
        comparison = (
            f"Signed calendar days from expiry: {elapsed}; "
            f"allowed range is {low} to {high} inclusive."
        )
    else:
        return result("needs_review", "Submission window: unsupported claim type; needs a person.")

    label = "within window" if within else "outside window"
    return result(
        "within_window" if within else "outside_window",
        f"Submission window: provisionally {label}. {comparison} "
        "Assumption: recorded claim_date is receipt date; not confirmed. "
        "Policy reference: see policy evidence below. A person must confirm receipt."
    )


def claim_identity(record):
    return (normalize_identifier(record.get("stockist_code")),
            normalize_sku(record.get("sku_code")),
            normalize_identifier(record.get("batch_no")))


def pack_number(value):
    from decimal import Decimal, InvalidOperation
    try:
        number = Decimal((value or "").strip().replace(",", ""))
    except InvalidOperation:
        raise ValueError("Missing or unreadable pack quantity")
    if not number.is_finite() or number < 0 or number != number.to_integral_value():
        raise ValueError("Pack quantity must be a nonnegative whole number")
    return number


def check_claim_quantity(claim, supplies, other_claims):
    """Historical gross supply comparison; earlier claims are not auto-deducted."""
    from decimal import Decimal
    import json
    checks, evidence, summary = [], [], {}
    review = False
    identity = claim_identity(claim)
    try:
        if not all(identity):
            raise ValueError("Missing stockist, SKU or batch identifier")
        when = parse_date(claim.get("claim_date"))
        claimed = pack_number(claim.get("qty_claimed"))
        if claimed == 0:
            raise ValueError("Claim quantity is zero; needs review")
    except ValueError as error:
        return {"review": True, "checks": [f"Quantity: {error}."],
                "evidence": [], "summary": {}}

    total = Decimal("0")
    seen = set()
    supply_problem = False
    for record in supplies:
        sale = record["values"]
        if claim_identity(sale) != identity:
            continue
        try:
            invoice_date = parse_date(sale.get("invoice_date"))
        except ValueError:
            supply_problem = True
            evidence.append(record)
            continue
        if invoice_date > when:
            continue
        evidence.append(record)
        # Exact duplicates retain all evidence references but contribute once.
        key = json.dumps(sale, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        try:
            total += pack_number(sale.get("invoiced_qty")) + pack_number(sale.get("free_qty"))
        except ValueError:
            supply_problem = True

    if supply_problem:
        review = True
        checks.append("Quantity: matching sales contain unreadable dates or quantities; total is incomplete and not compared.")
    elif not seen:
        review = True
        checks.append("Quantity: no matching supply on or before recorded claim date was found; archived or missing records may be needed.")
    else:
        summary = {"claimed_packs": str(claimed),
                   "gross_supplied_packs_in_extract": str(total),
                   "formula": "Sum invoiced_qty + free_qty for matching stockist/SKU/batch, on or before claim_date; exact repeats counted once",
                   "supply_source_records": ", ".join(str(r["source_record"]) for r in evidence),
                   "claim_reference": claim.get("claim_no", ""),
                   "scope": "Gross supply in the supplied extract; not remaining return entitlement"}
        if claimed > total:
            review = True
            checks.append("Quantity: claimed packs exceed matched gross supply in the extract; needs review. See calculation evidence.")
        else:
            checks.append("Quantity: claimed packs do not exceed matched gross supply in the extract. See calculation evidence; this is not remaining entitlement.")

    earlier_ids = set()
    uncertain = False
    for record in other_claims:
        previous = record["values"]
        if claim_identity(previous) != identity:
            continue
        number = normalize_identifier(previous.get("claim_no"))
        if number == normalize_identifier(claim.get("claim_no")):
            continue
        try:
            previous_date = parse_date(previous.get("claim_date"))
        except ValueError:
            uncertain = True
            evidence.append(record)
            continue
        if previous_date <= when:
            earlier_ids.add(number or "[missing claim number]")
            evidence.append(record)
    if earlier_ids or uncertain:
        review = True
        checks.append("Earlier-claim review: other claims for this stockist/SKU/batch are earlier, same-day, or undated. Inspect their status and evidence; no automatic duplicate decision or deduction is made.")
    else:
        checks.append("Earlier-claim review: no other earlier or same-day matching claim found in the supplied register; this does not establish complete claim history.")
    return {"review": review, "checks": checks, "evidence": evidence, "summary": summary}
