"""Generate synthetic French business PDFs plus ground-truth labels.

Writes data/samples/*.pdf and data/samples/labels.json. The labels hold the true
document type, the values that are printed on each page and the planted defects,
so they serve as the evaluation set for the extraction pipeline.

Run from the project root:  uv run python scripts/make_samples.py
"""

import argparse
import json
import random
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from xml.sax.saxutils import escape

from faker import Faker
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parent.parent
TODAY = date.today()
VAT_RATE = Decimal("20")
CENT = Decimal("0.01")

# doc type -> (count, planted defects; the rest are clean). 8 defects out of 30.
SPEC = {
    "invoice": (
        12,
        ["missing_invoice_number"] * 2 + ["totals_mismatch"] * 2 + ["due_date_next_week"],
    ),
    "quote": (6, ["totals_mismatch"]),
    "contract": (4, []),
    "purchase_order": (4, []),
    "certificate": (4, ["expired_certificate"] * 2),
}

CATALOG = [
    ("Prestation de conseil (jour)", 450, 950),
    ("Licence logicielle annuelle", 800, 4500),
    ("Maintenance applicative (mois)", 300, 1800),
    ("Fourniture de matériel informatique", 90, 1500),
    ("Formation sur site (jour)", 700, 1600),
    ("Hébergement cloud (mois)", 120, 900),
    ("Audit de sécurité", 1500, 6000),
    ("Développement spécifique (jour)", 500, 850),
    ("Fournitures de bureau (lot)", 40, 400),
    ("Transport et livraison", 60, 350),
]

CERTIFICATES = [
    ("ISO 9001", "Certificat ISO 9001:2015 - Management de la qualité", "AFNOR Certification", 3),
    ("ISO 14001", "Certificat ISO 14001:2015 - Management environnemental", "Bureau Veritas Certification", 3),
    ("ISO 27001", "Certificat ISO/IEC 27001:2022 - Sécurité de l'information", "BSI Group France", 3),
    ("Attestation de vigilance", "Attestation de vigilance URSSAF", "URSSAF", 0.5),
]

CONTRACTS = [
    "Contrat de prestation de services informatiques",
    "Contrat de maintenance applicative",
    "Contrat de fourniture et de livraison",
    "Contrat de sous-traitance",
]

styles = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=styles["Title"], alignment=0, fontSize=22, spaceAfter=10)
H2 = ParagraphStyle("H2", parent=styles["Heading3"], spaceBefore=10, spaceAfter=4)
BODY = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=10, leading=14)
SMALL = ParagraphStyle("Small", parent=BODY, fontSize=8.5, leading=11, textColor=colors.grey)


def q(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def money(x: Decimal) -> str:
    return f"{x:,.2f}".replace(",", " ").replace(".", ",") + " €"


def fr_date(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def p(text: str, style=BODY) -> Paragraph:
    return Paragraph(text, style)


def party(fake: Faker) -> dict:
    return {
        "name": fake.company(),
        "address": fake.address().replace("\n", ", "),
        "siret": fake.siret().replace(" ", ""),
    }


def party_block(label: str, who: dict) -> Paragraph:
    return p(
        f"<b>{label}</b><br/>{escape(who['name'])}<br/>{escape(who['address'])}"
        f"<br/>SIRET : {who['siret']}"
    )


def make_items() -> list[dict]:
    items = []
    for desc, low, high in random.sample(CATALOG, random.randint(2, 5)):
        qty = random.randint(1, 10)
        unit = q(Decimal(random.randint(low * 100, high * 100)) / 100)
        items.append({"description": desc, "quantity": qty, "unit_price_ht": unit, "total_ht": q(unit * qty)})
    return items


def totals(items: list[dict], mismatch: bool = False) -> dict:
    ht = sum(i["total_ht"] for i in items)
    vat = q(ht * VAT_RATE / 100)
    ttc = ht + vat
    printed = ttc
    if mismatch:
        printed = ttc + random.choice([-1, 1]) * Decimal(random.randint(1500, 40000)) / 100
    out = {"total_ht": ht, "vat_rate": VAT_RATE, "total_vat": vat, "total_ttc": q(printed)}
    if mismatch:
        out["expected_total_ttc"] = ttc
    return out


def jsonable(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [jsonable(v) for v in value]
    return value


def commercial_doc(title, number_label, number, meta, left, right, items, tot, notes):
    """Story shared by invoices, quotes and purchase orders."""
    rows = []
    if number:
        rows.append([f"{number_label} :", number])
    rows += [[f"{label} :", value] for label, value in meta]
    meta_table = Table(rows, colWidths=[4.5 * cm, 6 * cm], hAlign="LEFT")
    meta_table.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 10), ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold")]))

    parties = Table([[left, right]], colWidths=[8.5 * cm, 8.5 * cm])
    parties.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

    lines = [["Désignation", "Qté", "PU HT", "Total HT"]]
    for i in items:
        lines.append([i["description"], str(i["quantity"]), money(i["unit_price_ht"]), money(i["total_ht"])])
    items_table = Table(lines, colWidths=[8 * cm, 1.8 * cm, 3.4 * cm, 3.8 * cm], repeatRows=1)
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8edf3")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
    ]))

    tot_table = Table(
        [
            ["Total HT", money(tot["total_ht"])],
            [f"TVA ({tot['vat_rate']} %)", money(tot["total_vat"])],
            ["Total TTC", money(tot["total_ttc"])],
        ],
        colWidths=[4 * cm, 3.8 * cm],
        hAlign="RIGHT",
    )
    tot_table.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
        ("LINEABOVE", (0, 2), (-1, 2), 0.8, colors.black),
    ]))

    story = [p(title, H1), meta_table, Spacer(1, 0.6 * cm), parties, Spacer(1, 0.8 * cm), items_table, Spacer(1, 0.4 * cm), tot_table, Spacer(1, 0.8 * cm)]
    story += [p(escape(n), SMALL) for n in notes]
    return story


def line_fields(items):
    return [jsonable(i) for i in items]


def make_invoice(fake, defect):
    supplier, client = party(fake), party(fake)
    due = TODAY + timedelta(days=random.randint(3, 7) if defect == "due_date_next_week" else random.randint(10, 40))
    issue = due - timedelta(days=30)
    number = None if defect == "missing_invoice_number" else f"FAC-{issue.year}-{random.randint(1, 9999):04d}"
    items = make_items()
    tot = totals(items, mismatch=defect == "totals_mismatch")
    iban = fake.iban()
    story = commercial_doc(
        "FACTURE", "Facture n°", number,
        [("Date d'émission", fr_date(issue)), ("Date d'échéance", fr_date(due))],
        party_block("Émetteur", supplier), party_block("Client", client), items, tot,
        ["Conditions de paiement : 30 jours à compter de la date d'émission.", f"IBAN : {iban}"],
    )
    fields = {
        "invoice_number": number,
        "issue_date": issue.isoformat(),
        "due_date": due.isoformat(),
        "supplier_name": supplier["name"],
        "supplier_siret": supplier["siret"],
        "client_name": client["name"],
        "iban": iban,
        "line_items": line_fields(items),
        **jsonable(tot),
    }
    return story, fields


def make_quote(fake, defect):
    supplier, client = party(fake), party(fake)
    issue = TODAY - timedelta(days=random.randint(0, 30))
    valid_until = issue + timedelta(days=30)
    number = f"DEV-{issue.year}-{random.randint(1, 9999):04d}"
    items = make_items()
    tot = totals(items, mismatch=defect == "totals_mismatch")
    story = commercial_doc(
        "DEVIS", "Devis n°", number,
        [("Date d'émission", fr_date(issue)), ("Valable jusqu'au", fr_date(valid_until))],
        party_block("Émetteur", supplier), party_block("Client", client), items, tot,
        ["Devis valable 30 jours. Bon pour accord : date, signature et cachet du client."],
    )
    fields = {
        "quote_number": number,
        "issue_date": issue.isoformat(),
        "valid_until": valid_until.isoformat(),
        "supplier_name": supplier["name"],
        "supplier_siret": supplier["siret"],
        "client_name": client["name"],
        "line_items": line_fields(items),
        **jsonable(tot),
    }
    return story, fields


def make_purchase_order(fake, defect):
    buyer, supplier = party(fake), party(fake)
    order = TODAY - timedelta(days=random.randint(0, 20))
    delivery = order + timedelta(days=random.randint(7, 45))
    number = f"BC-{order.year}-{random.randint(1, 9999):04d}"
    delivery_address = fake.address().replace("\n", ", ")
    items = make_items()
    tot = totals(items)
    story = commercial_doc(
        "BON DE COMMANDE", "Commande n°", number,
        [("Date de commande", fr_date(order)), ("Livraison souhaitée", fr_date(delivery))],
        party_block("Acheteur", buyer), party_block("Fournisseur", supplier), items, tot,
        [f"Adresse de livraison : {delivery_address}"],
    )
    fields = {
        "po_number": number,
        "order_date": order.isoformat(),
        "delivery_date": delivery.isoformat(),
        "buyer_name": buyer["name"],
        "supplier_name": supplier["name"],
        "supplier_siret": supplier["siret"],
        "delivery_address": delivery_address,
        "line_items": line_fields(items),
        **jsonable(tot),
    }
    return story, fields


def make_contract(fake, defect):
    a, b = party(fake), party(fake)
    title = random.choice(CONTRACTS)
    signed = TODAY - timedelta(days=random.randint(10, 400))
    start = signed + timedelta(days=random.randint(1, 30))
    years = random.choice([1, 2, 3])
    end = start.replace(year=start.year + years) - timedelta(days=1)
    amount = q(Decimal(random.randint(60, 900)) * 100)
    notice = random.choice([1, 2, 3])
    pay_days = random.choice([30, 45, 60])
    city = fake.city()
    number = f"CTR-{signed.year}-{random.randint(1, 999):03d}"
    story = [
        p(escape(title).upper(), H1),
        p(f"Référence : {number}"),
        p(f"Conclu à {escape(city)}, le {fr_date(signed)}"),
        Spacer(1, 0.4 * cm),
        p("ENTRE LES SOUSSIGNÉS", H2),
        p(f"{escape(a['name'])}, {escape(a['address'])}, SIRET {a['siret']}, ci-après « le Prestataire »."),
        p(f"ET {escape(b['name'])}, {escape(b['address'])}, SIRET {b['siret']}, ci-après « le Client »."),
        p("Article 1 - Objet", H2),
        p(f"Le présent contrat a pour objet de définir les conditions dans lesquelles le Prestataire fournit ses services au Client ({escape(title.lower())})."),
        p("Article 2 - Durée", H2),
        p(f"Le contrat prend effet le {fr_date(start)} pour une durée de {years} an(s), soit jusqu'au {fr_date(end)}. Chaque partie peut le résilier moyennant un préavis de {notice} mois."),
        p("Article 3 - Prix et paiement", H2),
        p(f"Le prix annuel est de {money(amount)} HT. Les factures sont payables à {pay_days} jours."),
        p("Article 4 - Confidentialité", H2),
        p("Chaque partie s'engage à garder confidentielles les informations échangées pendant l'exécution du contrat."),
        p("Article 5 - Litiges", H2),
        p(f"Le présent contrat est soumis au droit français. Tout litige relève des tribunaux compétents de {escape(city)}."),
        Spacer(1, 1 * cm),
        p("Signatures : le Prestataire ______________________   le Client ______________________", SMALL),
    ]
    fields = {
        "contract_number": number,
        "title": title,
        "signed_date": signed.isoformat(),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "party_a_name": a["name"],
        "party_b_name": b["name"],
        "annual_amount_ht": float(amount),
        "payment_terms_days": pay_days,
        "notice_months": notice,
        "jurisdiction_city": city,
    }
    return story, fields


def make_certificate(fake, defect):
    supplier = party(fake)
    short, title, issuer, years = random.choice(CERTIFICATES)
    validity = timedelta(days=int(365 * years))
    if defect == "expired_certificate":
        expiry = TODAY - timedelta(days=random.randint(10, 300))
    else:
        expiry = TODAY + timedelta(days=random.randint(60, 700))
    issue = expiry - validity
    number = f"{short.split()[-1]}-{random.randint(100000, 999999)}"
    story = [
        p(escape(title), H1),
        Spacer(1, 0.4 * cm),
        p(f"<b>{issuer}</b> atteste que l'entreprise :"),
        Spacer(1, 0.2 * cm),
        p(f"<b>{escape(supplier['name'])}</b><br/>{escape(supplier['address'])}<br/>SIRET : {supplier['siret']}"),
        Spacer(1, 0.4 * cm),
        p(f"satisfait aux exigences de la référence « {escape(short)} » pour ses activités de fourniture de biens et de services."),
        Spacer(1, 0.6 * cm),
        p(f"Certificat n° : {number}"),
        p(f"Date de délivrance : {fr_date(issue)}"),
        p(f"Valable jusqu'au : {fr_date(expiry)}"),
        Spacer(1, 1 * cm),
        p(f"Délivré par {issuer}", SMALL),
    ]
    fields = {
        "supplier_name": supplier["name"],
        "supplier_siret": supplier["siret"],
        "certificate_type": short,
        "certificate_number": number,
        "issuer": issuer,
        "issue_date": issue.isoformat(),
        "expiry_date": expiry.isoformat(),
    }
    return story, fields


BUILDERS = {
    "invoice": make_invoice,
    "quote": make_quote,
    "contract": make_contract,
    "purchase_order": make_purchase_order,
    "certificate": make_certificate,
}


def write_pdf(path: Path, story) -> None:
    SimpleDocTemplate(
        str(path), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm
    ).build(story)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "samples")
    args = parser.parse_args()

    random.seed(args.seed)
    Faker.seed(args.seed)
    fake = Faker("fr_FR")
    args.out.mkdir(parents=True, exist_ok=True)

    labels = []
    for doc_type, (count, planted) in SPEC.items():
        defects = planted + [None] * (count - len(planted))
        random.shuffle(defects)
        for n, defect in enumerate(defects, start=1):
            story, fields = BUILDERS[doc_type](fake, defect)
            name = f"{doc_type}_{n:02d}.pdf"
            write_pdf(args.out / name, story)
            labels.append({"file": name, "doc_type": doc_type, "defects": [defect] if defect else [], "fields": fields})

    payload = {"generated_on": TODAY.isoformat(), "seed": args.seed, "documents": labels}
    (args.out / "labels.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    flawed = sum(1 for d in labels if d["defects"])
    print(f"Wrote {len(labels)} PDFs ({flawed} with a planted defect) and labels.json to {args.out}")


if __name__ == "__main__":
    main()
