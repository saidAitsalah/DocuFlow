"""Ingestion pipeline: labelled Gmail messages -> Drive + register sheet.

"""

import hashlib
import logging
import re
import tempfile
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from email.utils import parseaddr
from pathlib import Path

from pydantic import BaseModel

from docuflow.check import check_certificate, check_invoice
from docuflow.classifier import classify
from docuflow.config import settings
from docuflow.extract import INVALID_OUTPUT, extract
from docuflow.gworkspace import auth, drive, gmail, sheets
from docuflow.loaders import load_pdf
from docuflow.schema import DocType

log = logging.getLogger("docuflow")

REVIEW_THRESHOLD = 0.7
NEEDS_REVIEW_FOLDER = "Needs-review"

TYPE_CODE = {
    DocType.INVOICE: "INV",
    DocType.QUOTE: "QUO",
    DocType.CONTRACT: "CTR",
    DocType.PURCHASE_ORDER: "PO",
    DocType.SUPPLIER_CERTIFICATE: "CERT",
    DocType.OTHER: "DOC",
}
TYPE_FOLDER = {
    DocType.INVOICE: "Invoice",
    DocType.QUOTE: "Quote",
    DocType.CONTRACT: "Contract",
    DocType.PURCHASE_ORDER: "Purchase-Order",
    DocType.SUPPLIER_CERTIFICATE: "Supplier-Certificate",
    DocType.OTHER: "Other",
}


@dataclass
class Result:
    source: str
    status: str  # "ok", "flagged" or "needs_review"
    doc_type: DocType | None = None
    confidence: float | None = None
    data: BaseModel | None = None
    flags: list[str] = field(default_factory=list)  # business-rule findings
    reason: str | None = None  # why the document needs review


def run_checks(doc_type: DocType, data) -> list[str]:
    if doc_type is DocType.INVOICE:
        return check_invoice(data)
    if doc_type is DocType.SUPPLIER_CERTIFICATE:
        return check_certificate(data)
    return []


def process(path: str | Path) -> Result:
    """Read one PDF: load -> classify -> extract -> check. No network beyond the LLM."""
    doc = load_pdf(path)
    source = doc.metadata["source"]

    if doc.metadata["needs_ocr"]:
        return Result(source, "needs_review", reason="No extractable text; needs OCR.")

    cls = classify(doc)
    if cls.confidence < REVIEW_THRESHOLD:
        return Result(
            source, "needs_review", cls.doc_type, cls.confidence,
            reason=f"Low classification confidence: {cls.reason}",
        )

    try:
        data = extract(doc, cls.doc_type)
    except INVALID_OUTPUT as exc:
        # extract() already retried once. The schema stays strict; a human looks at it.
        return Result(
            source, "needs_review", cls.doc_type, cls.confidence,
            reason=f"Extraction failed validation twice: {exc}",
        )
    flags = run_checks(cls.doc_type, data) if data is not None else []
    return Result(source, "flagged" if flags else "ok", cls.doc_type, cls.confidence, data, flags)


# --- naming and register rows -------------------------------------------------

def _slug(text: str | None) -> str:
    ascii_text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", ascii_text).strip("-")


def _safe_name(name: str) -> str:
    """An attachment name is untrusted input: keep only a plain file name."""
    base = Path(name.replace("\\", "/")).name
    base = re.sub(r"[^\w.\- ]", "_", base)[:100]
    return base if base.lower().endswith(".pdf") else "document.pdf"


def _first(data, *names):
    for n in names:
        value = getattr(data, n, None)
        if value is not None:
            return value
    return None


def summarise(data) -> dict:
    """The register fields shared by all document types; missing ones are None."""
    return dict(
        counterparty=_first(data, "supplier_name", "counterparty", "company_name"),
        doc_number=_first(data, "invoice_number", "quote_number", "po_number"),
        issue_date=_first(data, "issue_date", "order_date", "start_date"),
        due_date=_first(data, "due_date"),
        total_incl_tax=_first(data, "total_incl_tax"),
        currency=_first(data, "currency"),
    )


def build_file_name(doc_type: DocType, info: dict, fallback_date: date) -> str:
    """2026-10-14_INV_Acme-SAS_F2026-0412.pdf; parts that are unknown are left out."""
    parts = (
        (info["issue_date"] or fallback_date).isoformat(),
        TYPE_CODE[doc_type],
        _slug(info["counterparty"]),
        _slug(info["doc_number"]),
    )
    return "_".join(p for p in parts if p) + ".pdf"


def _cell(value):
    """A sheet cell. Text is parsed by Sheets (USER_ENTERED), so defuse formulas."""
    if value is None:
        return ""
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


@dataclass
class Origin:
    """Where a PDF came from; everything the register records about the email."""
    message_id: str
    thread_id: str
    sender: str
    received: datetime


def register_row(*, origin: Origin, digest: str, file_name, doc_type, info, status, flags,
                 drive_link) -> list:
    row = {
        "received_at": origin.received.strftime("%Y-%m-%d %H:%M"),
        "file_name": file_name,
        "doc_type": doc_type.value if doc_type else "",
        **info,
        "status": status,
        "flags": flags,
        "sender": origin.sender,
        "drive_link": drive_link,
        "gmail_thread_id": origin.thread_id,
        "gmail_message_id": origin.message_id,
        "content_sha256": digest,
    }
    return [_cell(row.get(col)) for col in sheets.HEADER]


# --- one document, one message, the batch ---------------------------------------

def ingest_pdf(drive_svc, sheets_svc, name, data: bytes, digest: str, origin: Origin) -> str:
    """File one PDF in Drive and log it in the register. Returns its status; raises on failure."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / _safe_name(name)
        path.write_bytes(data)
        result = process(path)

    received = origin.received
    info = summarise(result.data)
    if result.status == "needs_review":
        folders = (NEEDS_REVIEW_FOLDER, str(received.year))
        file_name = _safe_name(name)
        flags = result.reason
    else:
        doc_date = info["issue_date"] or received.date()
        folders = (TYPE_FOLDER[result.doc_type], str(doc_date.year))
        file_name = build_file_name(result.doc_type, info, received.date())
        flags = ", ".join(result.flags)

    folder_id = drive.ensure_path(drive_svc, *folders, parent_id=settings.drive_root_folder_id)
    link = drive.upload_pdf(drive_svc, data, file_name, folder_id)["webViewLink"]
    sheets.append_row(sheets_svc, settings.register_sheet_id, register_row(
        origin=origin, digest=digest, file_name=file_name, doc_type=result.doc_type,
        info=info, status=result.status, flags=flags, drive_link=link,
    ))
    log.info("%s -> %s/%s [%s] %s", name, "/".join(folders), file_name, result.status, flags)
    return result.status


def log_failure(sheets_svc, name, digest: str, exc, origin: Origin) -> bool:
    """Register a document that crashed the pipeline as needs_review. True if logged."""
    error = f"{type(exc).__name__}: {exc}"[:200].replace("\n", " ")
    try:
        sheets.append_row(sheets_svc, settings.register_sheet_id, register_row(
            origin=origin, digest=digest, file_name=_safe_name(name), doc_type=None,
            info=summarise(None), status="needs_review", flags=f"error: {error}", drive_link="",
        ))
        return True
    except Exception:
        log.exception("could not log failure for %s", name)
        return False


def handle_message(gmail_svc, drive_svc, sheets_svc, msg_id: str, seen: set[str], stats: Counter) -> None:
    """File every new PDF of one message. `seen` holds the SHA-256 of every PDF already in the register."""
    files, from_header, thread_id = gmail.pdf_attachments(gmail_svc, msg_id)
    if not files:
        log.warning("message %s has no PDF attachment", msg_id)
        return

    origin = None  # built lazily: needs one more Gmail call, only worth it for a new PDF
    for name, data in files:
        digest = hashlib.sha256(data).hexdigest()
        if digest in seen:
            log.info("%s is already in the register; skipping", name)
            stats["duplicates_skipped"] += 1
            continue
        origin = origin or Origin(
            msg_id, thread_id, parseaddr(from_header)[1] or from_header,
            gmail.received_at(gmail_svc, msg_id),
        )
        try:
            status = ingest_pdf(drive_svc, sheets_svc, name, data, digest, origin)
            stats["needs_review" if status == "needs_review" else "filed"] += 1
        except Exception as exc:  # one bad PDF must not stop the batch
            log.exception("failed on %s", name)
            if not log_failure(sheets_svc, name, digest, exc, origin):
                stats["unlogged_errors"] += 1  # no register row, so the next run retries it
                continue
            stats["needs_review"] += 1
        seen.add(digest)


def run(gmail_svc=None, drive_svc=None, sheets_svc=None) -> dict:
    """Process every message under the To-process label. Returns a summary of what happened."""
    gmail_svc, drive_svc, sheets_svc = (
        gmail_svc or auth.gmail(), drive_svc or auth.drive(), sheets_svc or auth.sheets())
    msg_ids = gmail.list_labelled(gmail_svc, settings.gmail_label)
    log.info("%d message(s) under %s", len(msg_ids), settings.gmail_label)

    # Gmail access is read-only, so the register is the only record of what was filed.
    seen = {r["content_sha256"] for r in sheets.read_rows(sheets_svc, settings.register_sheet_id)
            if r.get("content_sha256")}
    stats = Counter(messages=len(msg_ids), filed=0, needs_review=0,
                    duplicates_skipped=0, unlogged_errors=0)
    for msg_id in msg_ids:
        try:
            handle_message(gmail_svc, drive_svc, sheets_svc, msg_id, seen, stats)
        except Exception:
            log.exception("message %s failed", msg_id)
            stats["message_errors"] += 1
    log.info("summary: %s", dict(stats))
    return dict(stats)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    missing = [k for k in ("drive_root_folder_id", "register_sheet_id") if not getattr(settings, k)]
    if missing:
        raise SystemExit(f"Set {', '.join(m.upper() for m in missing)} in .env (see scripts/setup_workspace.py).")
    run()


if __name__ == "__main__":
    main()
