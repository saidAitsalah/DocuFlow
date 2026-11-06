import io

from googleapiclient.http import MediaIoBaseUpload

FOLDER_MIME = "application/vnd.google-apps.folder"


def _q(value: str) -> str:
    """Escape a value for use inside single quotes in a Drive query."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def ensure_folder(svc, name: str, parent_id: str) -> str:
    """Return the id of folder `name` under `parent_id`, creating it if absent."""
    q = (f"name='{_q(name)}' and '{_q(parent_id)}' in parents "
         f"and mimeType='{FOLDER_MIME}' and trashed=false")
    found = svc.files().list(q=q, fields="files(id)", pageSize=1).execute().get("files", [])
    if found:
        return found[0]["id"]
    body = {"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id]}
    return svc.files().create(body=body, fields="id").execute()["id"]


def ensure_path(svc, *names: str, parent_id: str = "root") -> str:
    """ensure_path(svc, "DocuFlow", "Invoice", "2026") -> id of DocuFlow/Invoice/2026."""
    for name in names:
        parent_id = ensure_folder(svc, name, parent_id)
    return parent_id


def upload_pdf(svc, data: bytes, name: str, parent_id: str) -> dict:
    """Upload PDF bytes; returns {"id": ..., "webViewLink": ...}."""
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype="application/pdf")
    return svc.files().create(
        body={"name": name, "parents": [parent_id]},
        media_body=media,
        fields="id, webViewLink",
    ).execute()
