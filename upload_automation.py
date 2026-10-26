import os
import requests
from bs4 import BeautifulSoup
import re
import time
import sys
import base64
import json
from datetime import datetime, timezone, timedelta

# Definisikan Zona Waktu WIB (UTC+7)
WIB = timezone(timedelta(hours=7))
from urllib.parse import urlparse

# Library Google API dengan metode Refresh Token
import io
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload


def get_required_env(name):
    value = os.getenv(name)
    if value is None or value == "":
        raise RuntimeError(f"Environment variable '{name}' is not set.")
    return value


# ==========================================
# 1. KONFIGURASI KREDENSIAL GOOGLE & SHOPIFY
# ==========================================
# Kredensial Google OAuth (Blogger API)
GCP_CLIENT_ID = get_required_env("GCP_CLIENT_ID")
GCP_CLIENT_SECRET = get_required_env("GCP_CLIENT_SECRET")
GCP_REFRESH_TOKEN = get_required_env("GCP_REFRESH_TOKEN")
BLOG_ID = get_required_env("BLOG_ID")

# Kredensial Shopify
SHOPIFY_STORE_NAME = os.getenv("SHOPIFY_STORE_NAME", "your_shopify_store_name")
API_VERSION = "2025-01"
SHOPIFY_CLIENT_ID = get_required_env("SHOPIFY_CLIENT_ID")
SHOPIFY_CLIENT_SECRET = get_required_env("SHOPIFY_CLIENT_SECRET")

# URL Webhook (Apps Script)
GOOGLE_WEB_APP_URL = "https://script.google.com/macros/s/your_apps_script_url/exec"
APPS_SCRIPT_HISTORY_PHOTO_STUDIO = "https://script.google.com/macros/s/your_apps_script_url/exec"
FEATURED_WEB_APP_URL = "https://script.google.com/macros/s/your_apps_script_url/exec"
OWNER_APPS_SCRIPT_URL = "https://script.google.com/macros/s/your_apps_script_url/exec"
