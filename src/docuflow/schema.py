from datetime import date
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class DocType(str, Enum):
    INVOICE = "invoice"
    QUOTE = "quote"
    CONTRACT = "contract"
    PURCHASE_ORDER = "purchase_order"
    SUPPLIER_CERTIFICATE = "supplier_certificate"
    OTHER = "other"


class Classification(BaseModel):
    doc_type: DocType
    confidence: float = Field(ge=0, le=1, description="0 to 1; below 0.7 means unsure")
    reason: str = Field(description="One sentence quoting the words that decided the type")
    
    
def _strip_whitespace(value):
    """'552 100 554 00025' -> '55210055400025'. Also removes non-breaking spaces."""
    return "".join(value.split()) if isinstance(value, str) else value


class LineItem(BaseModel):
    description: str
    quantity: float | None = None
    unit_price: float | None = None
    amount: float | None = None


class InvoiceData(BaseModel):
    supplier_name: str
    supplier_siret: str | None = Field(None, description="14-digit French SIRET, digits only")
    supplier_vat: str | None = Field(None, description="Intra-EU VAT number, e.g. FR12345678901")
    invoice_number: str | None = None
    issue_date: date | None = None
    due_date: date | None = None
    purchase_order_ref: str | None = None
    currency: str = "EUR"
    total_excl_tax: float | None = Field(None, description="Total HT")
    vat_amount: float | None = Field(None, description="Total TVA")
    total_incl_tax: float | None = Field(None, description="Total TTC / net à payer")
    line_items: list[LineItem] = []

    _clean_siret = field_validator("supplier_siret", mode="before")(_strip_whitespace)


class QuoteData(BaseModel):
    supplier_name: str
    supplier_siret: str | None = Field(None, description="14-digit French SIRET, digits only")
    supplier_vat: str | None = Field(None, description="Intra-EU VAT number, e.g. FR12345678901")
    client_name: str | None = None
    quote_number: str | None = None
    issue_date: date | None = None
    valid_until: date | None = Field(None, description="Date until which the quote is valid")
    currency: str | None = None
    total_excl_tax: float | None = Field(None, description="Total HT")
    vat_amount: float | None = Field(None, description="Total TVA")
    total_incl_tax: float | None = Field(None, description="Total TTC")
    line_items: list[LineItem] = []

    _clean_siret = field_validator("supplier_siret", mode="before")(_strip_whitespace)


class PurchaseOrderData(BaseModel):
    supplier_name: str
    supplier_siret: str | None = Field(None, description="14-digit French SIRET, digits only")
    supplier_vat: str | None = Field(None, description="Intra-EU VAT number, e.g. FR12345678901")
    buyer_name: str | None = None
    po_number: str | None = None
    order_date: date | None = None
    delivery_date: date | None = None
    delivery_address: str | None = None
    currency: str | None = None
    total_excl_tax: float | None = Field(None, description="Total HT")
    vat_amount: float | None = Field(None, description="Total TVA")
    total_incl_tax: float | None = Field(None, description="Total TTC")
    line_items: list[LineItem] = []

    _clean_siret = field_validator("supplier_siret", mode="before")(_strip_whitespace)


class ContractData(BaseModel):
    counterparty: str
    subject: str = Field(description="What the contract covers, in under 15 words")
    start_date: date | None = None
    end_date: date | None = None
    auto_renewal: bool | None = None
    notice_period_days: int | None = None
    amount_per_period: float | None = None


class CertificateData(BaseModel):
    issuer: str
    certificate_type: str = Field(description="e.g. Kbis, URSSAF vigilance, insurance")
    company_name: str
    valid_until: date | None = None