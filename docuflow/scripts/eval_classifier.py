"""Evaluate the document classifier on data/samples against labels.json.

Prints accuracy, a confusion table (true type x predicted type) and how many
documents land in needs_review (confidence < REVIEW_THRESHOLD).

Run from the project root:  uv run python scripts/eval_classifier.py
"""

import json
from collections import Counter
from pathlib import Path

from docuflow.classifier import classify
from docuflow.loaders import load_pdf

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "data" / "samples"
REVIEW_THRESHOLD = 0.7

LABEL_TO_DOCTYPE = {"certificate": "supplier_certificate"}


def main() -> None:
    labels = json.loads((SAMPLES / "labels.json").read_text(encoding="utf-8"))
    truth = {
        d["file"]: LABEL_TO_DOCTYPE.get(d["doc_type"], d["doc_type"])
        for d in labels["documents"]
    }

    rows = []  # (file, true, predicted, confidence)
    for path in sorted(SAMPLES.glob("*.pdf")):
        if path.name not in truth:
            print(f"skip {path.name}: not in labels.json")
            continue
        try:
            result = classify(load_pdf(path))
            pred, conf = result.doc_type.value, result.confidence
        except Exception as exc:  
            print(f"error {path.name}: {exc}")
            pred, conf = "error", 0.0
        rows.append((path.name, truth[path.name], pred, conf))

    if not rows:
        print("No documents evaluated.")
        return

    correct = sum(t == p for _, t, p, _ in rows)
    print(f"Accuracy: {correct}/{len(rows)} = {correct / len(rows):.1%}\n")

    types = sorted({t for _, t, _, _ in rows} | {p for _, _, p, _ in rows})
    counts = Counter((t, p) for _, t, p, _ in rows)
    width = max(len(x) for x in types)
    abbrev = [x[:6] for x in types]
    print("Confusion (rows = true, columns = predicted)")
    print(" " * width + " | " + " ".join(f"{a:>6}" for a in abbrev))
    for t in types:
        cells = " ".join(f"{counts[(t, p)] or '.':>6}" for p in types)
        print(f"{t:<{width}} | {cells}")

    wrong = [(f, t, p, c) for f, t, p, c in rows if t != p]
    if wrong:
        print("\nMisclassified:")
        for f, t, p, c in wrong:
            print(f"  {f}: true={t} predicted={p} confidence={c:.2f}")


    review = [r for r in rows if r[3] < REVIEW_THRESHOLD]
    accepted = [r for r in rows if r[3] >= REVIEW_THRESHOLD]
    caught = sum(t != p for _, t, p, _ in review)
    missed = sum(t != p for _, t, p, _ in accepted)
    print(f"\nStatus (threshold {REVIEW_THRESHOLD}):")
    print(f"  needs_review: {len(review)}  (wrong: {caught})")
    print(f"  accepted:     {len(accepted)}  (wrong: {missed})")
    if accepted:
        print(f"  accuracy on accepted: {(len(accepted) - missed) / len(accepted):.1%}")
    if wrong:
        print(f"  errors caught by threshold: {caught}/{len(wrong)}")


if __name__ == "__main__":
    main()
