from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from docuflow.classifier import classify
from docuflow.extract import INVALID_OUTPUT, extract
from docuflow.loaders import load_pdf
from docuflow.schema import DocType

REVIEW_THRESHOLD = 0.7


@dataclass
class Result:
    source: str
    status: str  # "ok" or "needs_review"
    doc_type: DocType | None = None
    confidence: float | None = None
    data: BaseModel | None = None
    reason: str | None = None  # why the document needs review


def process(path: str | Path) -> Result:
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
    return Result(source, "ok", cls.doc_type, cls.confidence, data)
