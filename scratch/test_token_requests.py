import os
import requests

env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
env = {}
with open(env_path, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip("\"'")

tok_res = requests.post(
    "https://oauth2.googleapis.com/token",
    data={
        "client_id": env["GCP_CLIENT_ID"],
        "client_secret": env["GCP_CLIENT_SECRET"],
        "refresh_token": env["GCP_REFRESH_TOKEN"],
        "grant_type": "refresh_token"
    },
    timeout=15
)
print("Token Status:", tok_res.status_code)
tok_data = tok_res.json()
access_token = tok_data.get("access_token")
print("Got access token:", bool(access_token))

if access_token:
    # List files in folder 1NO7JUz7kOzyjiKLqkZKJD18Tw0CSIB2K
    folder_id = "1NO7JUz7kOzyjiKLqkZKJD18Tw0CSIB2K"
    headers = {"Authorization": f"Bearer {access_token}"}
    drive_res = requests.get(
        "https://www.googleapis.com/drive/v3/files",
        headers=headers,
        params={
            "q": f"'{folder_id}' in parents and trashed = false",
            "fields": "files(id, name, mimeType, size)",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true"
        },
        timeout=15
    )
    print("Drive Status:", drive_res.status_code)
    files = drive_res.json().get("files", [])
    print(f"Total audio files in folder: {len(files)}")
    for f in files:
        print(f" - {f.get('name')} (ID: {f.get('id')}, Size: {f.get('size')} bytes)")
