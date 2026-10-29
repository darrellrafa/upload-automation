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
    timeout=10
)
access_token = tok_res.json().get("access_token")
print("Token OK:", bool(access_token))

folder_id = "1NO7JUz7kOzyjiKLqkZKJD18Tw0CSIB2K"
headers = {"Authorization": f"Bearer {access_token}"}
r = requests.get(
    f"https://www.googleapis.com/drive/v3/files?q='{folder_id}'+in+parents+and+trashed=false&fields=files(id,name,size,mimeType)",
    headers=headers,
    timeout=10
)
print("Drive Response Status:", r.status_code)
files = r.json().get("files", [])
print(f"Total files: {len(files)}")
for f in files:
    print(f" - {f.get('name')} (ID: {f.get('id')}, Size: {f.get('size')})")
