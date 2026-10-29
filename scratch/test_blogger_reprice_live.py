import os
import re
import requests
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

def get_blogger_service():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GCP_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["GCP_CLIENT_ID"],
        client_secret=os.environ["GCP_CLIENT_SECRET"]
    )
    return build('blogger', 'v3', credentials=creds)

service = get_blogger_service()
blog_id = os.environ["BLOG_ID"]

# Cari post Y563525
res = service.posts().search(blogId=blog_id, q="Y563525").execute()
items = res.get("items", [])
print(f"Ditemukan {len(items)} post untuk Y563525")
if items:
    p = items[0]
    print("Title:", p.get("title"))
    print("Labels:", p.get("labels"))
    print("URL:", p.get("url"))
    # Check is_consign_ps
    labels = p.get("labels", [])
    is_consign_ps = any("CONSIGNMENT_PS" in l.upper() or "CONSINGMENT_PS" in l.upper() for l in labels)
    print("Is CONSIGNMENT_PS:", is_consign_ps)
