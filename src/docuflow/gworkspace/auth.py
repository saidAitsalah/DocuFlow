from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.file",
]
CLIENT = Path("secrets/credentials.json")
TOKEN = Path("secrets/token.json")


def get_creds() -> Credentials:
    creds = Credentials.from_authorized_user_file(TOKEN, SCOPES) if TOKEN.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds = InstalledAppFlow.from_client_secrets_file(CLIENT, SCOPES).run_local_server(port=0)
        TOKEN.write_text(creds.to_json())
    return creds


def gmail():  return build("gmail", "v1", credentials=get_creds())
def drive():  return build("drive", "v3", credentials=get_creds())
def sheets(): return build("sheets", "v4", credentials=get_creds())