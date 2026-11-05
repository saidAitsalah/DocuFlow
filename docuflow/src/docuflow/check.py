from datetime import date, timedelta

"""siret validator"""
def luhn_ok(number: str) -> bool:
    digits = [int(c) for c in number][::-1]
    total = sum(d if i % 2 == 0 else (d * 2 - 9 if d * 2 > 9 else d * 2) for i, d in enumerate(digits))
    return total % 10 == 0


def check_invoice(inv, today: date | None = None) -> list[str]:
    today = today or date.today()
    flags = []
    if not inv.invoice_number:
        flags.append("missing_invoice_number")
    if not inv.purchase_order_ref:
        flags.append("missing_po_reference")
    if None not in (inv.total_excl_tax, inv.vat_amount, inv.total_incl_tax):
        if abs(inv.total_excl_tax + inv.vat_amount - inv.total_incl_tax) > 0.02:
            flags.append("totals_do_not_add_up")
    if inv.due_date and inv.due_date <= today + timedelta(days=7):
        flags.append("due_within_7_days")
    if inv.supplier_siret and not (len(inv.supplier_siret) == 14 and luhn_ok(inv.supplier_siret)):
        flags.append("invalid_siret")
    return flags


def check_certificate(cert, today: date | None = None) -> list[str]:
    today = today or date.today()
    if cert.valid_until is None:
        return ["missing_validity_date"]
    if cert.valid_until < today:
        return ["certificate_expired"]
    if cert.valid_until < today + timedelta(days=30):
        return ["certificate_expires_within_30_days"]
    return []