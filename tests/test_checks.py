from datetime import date, timedelta

from docuflow.check import check_certificate, check_invoice, luhn_ok
from docuflow.schema import CertificateData, InvoiceData

TODAY = date(2026, 11, 5)  
VALID_SIRET = "38908386600274"


def make_invoice(**overrides) -> InvoiceData:
    """A clean invoice; each test overrides only what it wants to break."""
    fields = dict(
        supplier_name="Laurent et Fils",
        supplier_siret=VALID_SIRET,
        invoice_number="FAC-2026-0489",
        issue_date=TODAY,
        due_date=TODAY + timedelta(days=30),
        purchase_order_ref="BC-2026-5148",
        total_excl_tax=100.0,
        vat_amount=20.0,
        total_incl_tax=120.0,
    )
    return InvoiceData(**{**fields, **overrides})


def make_certificate(valid_until) -> CertificateData:
    return CertificateData(
        issuer="URSSAF", certificate_type="URSSAF vigilance",
        company_name="Laurent et Fils", valid_until=valid_until,
    )


# --- invoices ---------------------------------------------------------------

def test_correct_invoice_has_no_flags():
    assert check_invoice(make_invoice(), today=TODAY) == []


def test_wrong_totals():
    inv = make_invoice(total_incl_tax=125.0)
    assert check_invoice(inv, today=TODAY) == ["totals_do_not_add_up"]


def test_totals_within_rounding_tolerance_pass():
    inv = make_invoice(total_incl_tax=120.02)
    assert check_invoice(inv, today=TODAY) == []


def test_totals_not_checked_when_a_total_is_missing():
    inv = make_invoice(vat_amount=None)
    assert check_invoice(inv, today=TODAY) == []


def test_due_tomorrow():
    inv = make_invoice(due_date=TODAY + timedelta(days=1))
    assert check_invoice(inv, today=TODAY) == ["due_within_7_days"]


def test_due_date_boundary_is_seven_days():
    assert check_invoice(make_invoice(due_date=TODAY + timedelta(days=7)), today=TODAY) == ["due_within_7_days"]
    assert check_invoice(make_invoice(due_date=TODAY + timedelta(days=8)), today=TODAY) == []


def test_missing_po_reference():
    inv = make_invoice(purchase_order_ref=None)
    assert check_invoice(inv, today=TODAY) == ["missing_po_reference"]


def test_missing_invoice_number():
    inv = make_invoice(invoice_number=None)
    assert check_invoice(inv, today=TODAY) == ["missing_invoice_number"]


def test_invalid_siret():
    wrong_checksum = make_invoice(supplier_siret="38908386600275")
    too_short = make_invoice(supplier_siret="3890838660027")
    assert check_invoice(wrong_checksum, today=TODAY) == ["invalid_siret"]
    assert check_invoice(too_short, today=TODAY) == ["invalid_siret"]


def test_absent_siret_is_not_flagged():
    assert check_invoice(make_invoice(supplier_siret=None), today=TODAY) == []


def test_luhn():
    assert luhn_ok(VALID_SIRET)
    assert not luhn_ok("38908386600275")


# --- certificates -----------------------------------------------------------

def test_expired_certificate():
    cert = make_certificate(TODAY - timedelta(days=1))
    assert check_certificate(cert, today=TODAY) == ["certificate_expired"]


def test_certificate_expiring_soon():
    cert = make_certificate(TODAY + timedelta(days=10))
    assert check_certificate(cert, today=TODAY) == ["certificate_expires_within_30_days"]


def test_valid_certificate():
    cert = make_certificate(TODAY + timedelta(days=90))
    assert check_certificate(cert, today=TODAY) == []


def test_certificate_without_validity_date():
    assert check_certificate(make_certificate(None), today=TODAY) == ["missing_validity_date"]
