"""Field-level accuracy of invoice extraction against data/samples/labels.json.

For every invoice, runs extract() and compares each field with the label.
Per field it prints how often the value matches, plus the three ways to be
wrong: a different value, a missed value (None where the label has one) and an
invented value (a value where the label is None).

Run from the project root:  uv run python scripts/eval_extraction.py
"""

import json
from datetime import date
from pathlib import Path

from docuflow.extract import INVALID_OUTPUT, extract
from docuflow.loaders import load_pdf
from docuflow.schema import DocType

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "data" / "samples"
AMOUNT_TOLERANCE = 0.01

# schema field -> labels.json key. Label keys with no schema field (client_name,iban, vat_rate) and schema fields with no label (purchase_order_ref) are not scored.
FIELD_MAP = {
    "invoice_number": "invoice_number",
    "issue_date": "issue_date",
    "due_date": "due_date",
    "supplier_name": "supplier_name",
    "supplier_siret": "supplier_siret",
    "total_excl_tax": "total_ht",
    "vat_amount": "total_vat",
    "total_incl_tax": "total_ttc",
}
DATE_FIELDS = {"issue_date", "due_date"}
AMOUNT_FIELDS = {"total_excl_tax", "vat_amount", "total_incl_tax"}


def same(field: str, got, want) -> bool:
    """Both values are present; do they match?"""
    if field in DATE_FIELDS:
        return got == date.fromisoformat(want)
    if field in AMOUNT_FIELDS:
        return abs(got - want) <= AMOUNT_TOLERANCE
    if field == "supplier_siret":
        return "".join(ch for ch in str(got) if ch.isdigit()) == "".join(
            ch for ch in str(want) if ch.isdigit()
        )
    return str(got).strip().casefold() == str(want).strip().casefold()


def main() -> None:
    labels = json.loads((SAMPLES / "labels.json").read_text(encoding="utf-8"))
    invoices = [d for d in labels["documents"] if d["doc_type"] == "invoice"]

    # field -> counters; "line_items" is scored on item count only.
    fields = list(FIELD_MAP) + ["line_items"]
    stats = {f: dict(correct=0, wrong=0, missed=0, invented=0) for f in fields}
    mismatches = []  # (file, field, expected, got)
    failed = []  # files where extraction failed validation twice

    for entry in invoices:
        name = entry["file"]
        try:
            data = extract(load_pdf(SAMPLES / name), DocType.INVOICE)
        except INVALID_OUTPUT as exc:
            failed.append(name)
            print(f"validation failed {name}: {exc}")
            continue

        for field in FIELD_MAP:
            got, want = getattr(data, field), entry["fields"].get(FIELD_MAP[field])
            if got is None and want is None:
                outcome = "correct"
            elif got is None:
                outcome = "missed"
            elif want is None:
                outcome = "invented"
            else:
                outcome = "correct" if same(field, got, want) else "wrong"
            stats[field][outcome] += 1
            if outcome != "correct":
                mismatches.append((name, field, want, got))

        n_got, n_want = len(data.line_items), len(entry["fields"]["line_items"])
        stats["line_items"]["correct" if n_got == n_want else "wrong"] += 1
        if n_got != n_want:
            mismatches.append((name, "line_items (count)", n_want, n_got))

    scored = len(invoices) - len(failed)
    if not scored:
        print("No invoice was extracted.")
        return

    print(f"\nInvoices: {len(invoices)}  extracted: {scored}  failed validation: {len(failed)}")
    print("(failed documents are left out of the per-field numbers)\n")
    width = max(len(f) for f in fields)
    print(f"{'field':<{width}} | correct |   acc | wrong | missed | invented")
    for f in fields:
        s = stats[f]
        print(
            f"{f:<{width}} | {s['correct']:>2}/{scored:<4} | {s['correct'] / scored:>4.0%} "
            f"| {s['wrong']:>5} | {s['missed']:>6} | {s['invented']:>8}"
        )

    if mismatches:
        print("\nMismatches (expected -> got):")
        for name, field, want, got in mismatches:
            print(f"  {name} {field}: {want!r} -> {got!r}")


if __name__ == "__main__":
    main()
