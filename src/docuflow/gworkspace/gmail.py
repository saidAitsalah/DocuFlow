import base64
from datetime import datetime


def label_id(svc, name: str) -> str:
    labels = svc.users().labels().list(userId="me").execute()["labels"]
    return next(l["id"] for l in labels if l["name"] == name)


def list_labelled(svc, label: str) -> list[str]:
    res = svc.users().messages().list(userId="me", labelIds=[label_id(svc, label)]).execute()
    return [m["id"] for m in res.get("messages", [])]


def _parts(payload):
    yield payload
    for p in payload.get("parts", []):
        yield from _parts(p)


def pdf_attachments(svc, msg_id: str):
    msg = svc.users().messages().get(userId="me", id=msg_id).execute()
    files = []
    for part in _parts(msg["payload"]):
        if part.get("filename", "").lower().endswith(".pdf"):
            att = svc.users().messages().attachments().get(
                userId="me", messageId=msg_id, id=part["body"]["attachmentId"]).execute()
            files.append((part["filename"], base64.urlsafe_b64decode(att["data"])))
    headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
    return files, headers.get("From", ""), msg["threadId"]


def received_at(svc, msg_id: str) -> datetime:
    """When Gmail received the message, in local time."""
    msg = svc.users().messages().get(userId="me", id=msg_id, format="minimal").execute()
    return datetime.fromtimestamp(int(msg["internalDate"]) / 1000)
