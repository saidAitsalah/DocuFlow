from collections import Counter
from datetime import date, datetime
from types import SimpleNamespace

import pytest

from docuflow import pipeline
from docuflow.schema import DocType, InvoiceData

RECEIVED = datetime(2026, 11, 3, 9, 14)


def make_invoice(**overrides) -> InvoiceData:
    fields = dict(supplier_name="Acme SAS", invoice_number="F2026-0412",
                  issue_date=date(2026, 10, 14), total_incl_tax=1440.0, currency="EUR")
    return InvoiceData(**{**fields, **overrides})


# --- naming -------------------------------------------------------------------

def test_file_name_matches_the_documented_example():
    info = pipeline.summarise(make_invoice())
    name = pipeline.build_file_name(DocType.INVOICE, info, RECEIVED.date())
    assert name == "2026-10-14_INV_Acme-SAS_F2026-0412.pdf"


def test_file_name_leaves_out_unknown_parts_and_falls_back_to_received_date():
    info = pipeline.summarise(make_invoice(invoice_number=None, issue_date=None, supplier_name="Société Générale"))
    name = pipeline.build_file_name(DocType.INVOICE, info, RECEIVED.date())
    assert name == "2026-11-03_INV_Societe-Generale.pdf"


@pytest.mark.parametrize("raw, expected", [
    ("..\\..\\evil.pdf", "evil.pdf"),
    ("../x/inv oice.pdf", "inv oice.pdf"),
    ("report.exe", "document.pdf"),
])
def test_attachment_names_are_reduced_to_a_plain_file_name(raw, expected):
    assert pipeline._safe_name(raw) == expected


def test_formulas_are_defused_before_reaching_the_sheet():
    assert pipeline._cell("=HYPERLINK(\"http://x\")") == "'=HYPERLINK(\"http://x\")"
    assert pipeline._cell(None) == ""
    assert pipeline._cell(date(2026, 10, 14)) == "2026-10-14"
    assert pipeline._cell(1440.0) == 1440.0




def test_register_row_follows_the_header_order():
    origin = pipeline.Origin("m1", "18c2f", "billing@acme.example", RECEIVED)
    row = pipeline.register_row(
        origin=origin, digest="abc123", file_name="f.pdf", doc_type=DocType.INVOICE,
        info=pipeline.summarise(make_invoice()), status="flagged", flags="missing_po_reference",
        drive_link="https://drive/x",
    )
    by_col = dict(zip(pipeline.sheets.HEADER, row))
    assert len(row) == len(pipeline.sheets.HEADER) == 16
    assert by_col["received_at"] == "2026-11-03 09:14"
    assert by_col["doc_type"] == "invoice"
    assert by_col["counterparty"] == "Acme SAS"
    assert by_col["total_incl_tax"] == 1440.0
    assert by_col["due_date"] == ""
    assert by_col["gmail_thread_id"] == "18c2f"
    assert by_col["gmail_message_id"] == "m1"
    assert by_col["content_sha256"] == "abc123"


# --- the batch ----------------------------------------------------------------

class FakeWorkspace:
    """Stands in for the gmail, drive and sheets modules; records what the pipeline does."""

    def __init__(self, messages, register=(), append_error=None):
        self.messages = messages  # msg_id -> (files, from_header, thread_id)
        self.register = [dict(r) for r in register]  # rows already in the sheet
        self.append_error = append_error
        self.uploads, self.rows = [], []

    @property
    def gmail(self):
        return SimpleNamespace(
            list_labelled=lambda svc, label: list(self.messages),
            pdf_attachments=lambda svc, mid: self.messages[mid],
            received_at=lambda svc, mid: RECEIVED,
        )

    @property
    def drive(self):
        return SimpleNamespace(
            ensure_path=lambda svc, *names, parent_id: "/".join((parent_id, *names)),
            upload_pdf=self._upload,
        )

    @property
    def sheets(self):
        return SimpleNamespace(
            HEADER=pipeline.sheets.HEADER,
            read_rows=lambda svc, sid: self.register,
            append_row=self._append,
        )

    def _upload(self, svc, data, name, folder):
        self.uploads.append((folder, name))
        return {"id": "1", "webViewLink": f"https://drive/{name}"}

    def _append(self, svc, sid, values):
        if self.append_error:
            raise self.append_error
        self.rows.append(dict(zip(pipeline.sheets.HEADER, values)))


@pytest.fixture
def workspace(monkeypatch):
    def install(messages, **kw):
        ws = FakeWorkspace(messages, **kw)
        monkeypatch.setattr(pipeline, "gmail", ws.gmail)
        monkeypatch.setattr(pipeline, "drive", ws.drive)
        monkeypatch.setattr(pipeline, "sheets", ws.sheets)
        monkeypatch.setattr(pipeline, "settings", SimpleNamespace(
            drive_root_folder_id="ROOT", register_sheet_id="SHEET", gmail_label="To-process"))
        monkeypatch.setattr(pipeline, "process", fake_process)
        return ws
    return install


def fake_process(path):
    if "broken" in path.name:
        raise RuntimeError("model fell over")
    if "scan" in path.name:
        return pipeline.Result(path.name, "needs_review", reason="No extractable text; needs OCR.")
    return pipeline.Result(path.name, "flagged", DocType.INVOICE, 0.95, make_invoice(),
                           ["missing_po_reference"])


GOOD_NAME = "2026-10-14_INV_Acme-SAS_F2026-0412.pdf"


def test_one_bad_pdf_does_not_stop_the_batch(workspace):
    ws = workspace({
        "m1": ([("inv.pdf", b"good"), ("broken.pdf", b"bad")], "Acme <billing@acme.example>", "t1"),
        "m2": ([("scan.pdf", b"scanned")], "x@y.example", "t2"),
    })

    stats = pipeline.run(object(), object(), object())

    assert stats == dict(messages=2, filed=1, needs_review=2, duplicates_skipped=0, unlogged_errors=0)
    # good invoice filed under Type/Year with the clean name, link stored in the row
    assert ("ROOT/Invoice/2026", GOOD_NAME) in ws.uploads
    # scanned PDF is filed for review under its own (sanitised) name
    assert ("ROOT/Needs-review/2026", "scan.pdf") in ws.uploads
    # three register rows: flagged invoice, crashed PDF, scanned PDF
    by_file = {r["file_name"]: r for r in ws.rows}
    good = by_file[GOOD_NAME]
    assert good["status"] == "flagged"
    assert good["flags"] == "missing_po_reference"
    assert good["sender"] == "billing@acme.example"
    assert good["gmail_message_id"] == "m1"
    assert len(good["content_sha256"]) == 64
    assert by_file["broken.pdf"]["status"] == "needs_review"
    assert "model fell over" in by_file["broken.pdf"]["flags"]
    assert by_file["scan.pdf"]["status"] == "needs_review"


def test_second_run_files_nothing_new(workspace):
    messages = {"m1": ([("inv.pdf", b"good")], "x@y.example", "t1")}
    first = workspace(messages)
    pipeline.run(object(), object(), object())
    assert len(first.rows) == 1

    # same mailbox, but the register now holds what the first run wrote
    second = workspace(messages, register=first.rows)
    stats = pipeline.run(object(), object(), object())

    assert second.uploads == [] and second.rows == []
    assert stats["duplicates_skipped"] == 1 and stats["filed"] == 0


def test_identical_pdf_in_two_messages_is_filed_once(workspace):
    ws = workspace({
        "m1": ([("inv.pdf", b"same bytes")], "x@y.example", "t1"),
        "m2": ([("copy.pdf", b"same bytes")], "x@y.example", "t2"),
    })

    stats = pipeline.run(object(), object(), object())

    assert len(ws.rows) == 1
    assert stats["filed"] == 1 and stats["duplicates_skipped"] == 1


def test_pdf_without_a_register_row_is_retried_next_run(workspace):
    ws = workspace({"m1": ([("broken.pdf", b"bad")], "x@y.example", "t1")},
                   append_error=RuntimeError("sheets down"))

    stats = pipeline.run(object(), object(), object())

    assert stats["unlogged_errors"] == 1 and stats["needs_review"] == 0
    assert ws.rows == []  # nothing recorded, so its hash is not in the register and a rerun retries
