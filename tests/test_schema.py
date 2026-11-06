import pytest

from docuflow.check import check_invoice
from docuflow.schema import InvoiceData, PurchaseOrderData, QuoteData


@pytest.mark.parametrize("model", [InvoiceData, QuoteData, PurchaseOrderData])
@pytest.mark.parametrize("raw", [
    "552 100 554 00025",
    " 55210055400025 ",
    "552 100 554 00025",  # non-breaking spaces from French typography
])
def test_siret_spaces_are_stripped(model, raw):
    assert model(supplier_name="X", supplier_siret=raw).supplier_siret == "55210055400025"


@pytest.mark.parametrize("model", [InvoiceData, QuoteData, PurchaseOrderData])
def test_absent_siret_stays_none(model):
    assert model(supplier_name="X").supplier_siret is None


def test_spaced_siret_no_longer_crashes_the_check():
    inv = InvoiceData(
        supplier_name="X", supplier_siret="389 083 866 00274",
        invoice_number="F1", purchase_order_ref="BC1",
    )
    assert check_invoice(inv) == []
