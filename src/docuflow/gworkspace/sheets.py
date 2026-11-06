TAB = "Register"
HEADER = [
    "received_at", "file_name", "doc_type", "counterparty", "doc_number",
    "issue_date", "due_date", "total_incl_tax", "currency", "status",
    "flags", "sender", "drive_link", "gmail_thread_id", "gmail_message_id", "content_sha256",
]


def append_row(svc, sheet_id: str, values: list):
    """Append one row after the last row of the Register tab."""
    return svc.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"{TAB}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [values]},
    ).execute()


def read_rows(svc, sheet_id: str) -> list[dict]:
    """Rows of the Register tab as dicts keyed by the header row."""
    res = svc.spreadsheets().values().get(spreadsheetId=sheet_id, range=TAB).execute()
    header, *rows = res.get("values", [[]])
    # The API drops trailing empty cells, so pad short rows to the header width.
    return [dict(zip(header, row + [""] * (len(header) - len(row)))) for row in rows]
