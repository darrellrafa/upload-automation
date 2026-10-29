import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Load .env
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip().strip("\"'")

creds = Credentials(
    token=None,
    refresh_token=os.environ["GCP_REFRESH_TOKEN"],
    token_uri="https://oauth2.googleapis.com/token",
    client_id=os.environ["GCP_CLIENT_ID"],
    client_secret=os.environ["GCP_CLIENT_SECRET"]
)
drive_service = build('drive', 'v3', credentials=creds)

folder_id = "1NO7JUz7kOzyjiKLqkZKJD18Tw0CSIB2K"
query = f"'{folder_id}' in parents and trashed = false"
results = drive_service.files().list(
    q=query,
    fields="files(id, name, mimeType, size)",
    supportsAllDrives=True,
    includeItemsFromAllDrives=True
).execute()

files = results.get('files', [])
print(f"Total files in folder {folder_id}: {len(files)}")
for f in files:
    print(f" - {f.get('name')} (ID: {f.get('id')}, Size: {f.get('size')} bytes, Mime: {f.get('mimeType')})")
