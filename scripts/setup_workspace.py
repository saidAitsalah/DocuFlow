"""One-off Google Workspace setup: the DocuFlow root folder and the Register sheet.

Creates the folder (reused if it already exists) and a spreadsheet with a
Register tab and the header row, then prints both ids for your .env.

Run from the project root (it reads secrets/credentials.json and opens a
browser for consent on first use):  uv run python scripts/setup_workspace.py
"""

from docuflow.config import settings
from docuflow.gworkspace import auth
from docuflow.gworkspace.drive import ensure_folder
from docuflow.gworkspace.sheets import HEADER, TAB

ROOT_FOLDER = "DocuFlow"
SHEET_TITLE = "DocuFlow Register"


def create_register(sheets_svc) -> str:
    sheet_id = sheets_svc.spreadsheets().create(
        body={
            "properties": {"title": SHEET_TITLE},
            "sheets": [{"properties": {"title": TAB, "gridProperties": {"frozenRowCount": 1}}}],
        },
        fields="spreadsheetId",
    ).execute()["spreadsheetId"]
    sheets_svc.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"{TAB}!A1",
        valueInputOption="RAW",
        body={"values": [HEADER]},
    ).execute()
    return sheet_id


def main() -> None:
    folder_id = ensure_folder(auth.drive(), ROOT_FOLDER, "root")

    if settings.register_sheet_id:
        sheet_id = settings.register_sheet_id
        print("REGISTER_SHEET_ID is already set; not creating another sheet.")
    else:
        sheet_id = create_register(auth.sheets())

    print("\nPut these in .env:")
    print(f"DRIVE_ROOT_FOLDER_ID={folder_id}")
    print(f"REGISTER_SHEET_ID={sheet_id}")


if __name__ == "__main__":
    main()
