import os
import requests
from bs4 import BeautifulSoup
import re
import time
import sys
import base64
import json
import subprocess
import shutil
import random
from datetime import datetime, timezone, timedelta

# Definisikan Zona Waktu WIB (UTC+7)
WIB = timezone(timedelta(hours=7))
from urllib.parse import urlparse

# Library Google API dengan metode Refresh Token
import io
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload


def load_env_file(filepath=".env"):
    """Membaca file .env lokal jika ada dan memuatnya ke os.environ"""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filepath)
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v

load_env_file()


def get_required_env(name):
    value = os.getenv(name)
    if value is None or value == "":
        raise RuntimeError(f"Environment variable '{name}' is not set. Pastikan sudah didefinisikan di file .env atau environment sistem.")
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
SHOPIFY_STORE_NAME = os.getenv("SHOPIFY_STORE_NAME", "idwx")
API_VERSION = "2025-01"
SHOPIFY_CLIENT_ID = get_required_env("SHOPIFY_CLIENT_ID")
SHOPIFY_CLIENT_SECRET = get_required_env("SHOPIFY_CLIENT_SECRET")

# URL Webhook (Apps Script)
GOOGLE_WEB_APP_URL = "https://script.google.com/macros/s/AKfycbw-PV4bR4PhgJyjPvY_dHnz54fhmzEvSOIJJCDyyWOASeaBMcdOkcMxpftXfTHcqPf2/exec"
APPS_SCRIPT_HISTORY_PHOTO_STUDIO = "https://script.google.com/macros/s/AKfycbxCEcepLLaNouGEmxMJPCFj3vTbWjH41_BFD7tFsYuEkL7h1tV_io3xZBPDSiRC_sgQ/exec"
FEATURED_WEB_APP_URL = "https://script.google.com/macros/s/AKfycbymvWQh66pDkcSOe1fBC1rQ--VVsTKONFBM-o52qU-8sS0_aEV4JzxFBzEBx1dk-d6O_w/exec"
OWNER_APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbw-PV4bR4PhgJyjPvY_dHnz54fhmzEvSOIJJCDyyWOASeaBMcdOkcMxpftXfTHcqPf2/exec"

# Daftar Merek IDWX (gabungan dari semua script)
DAFTAR_MEREK_IDWX = {
    "ROLEX": "Rolex", "PATEK PHILIPPE": "Patek Philippe", "AUDEMARS PIGUET X SWATCH": "Swatch X Audemars Piguet" ,"AUDEMARS PIGUET": "Audemars Piguet","JAEGER LECOULTRE": "Jaeger-LeCoultre","JAEGER": "Jaeger-LeCoultre", "FRANCK MULLER": "Franck Muller", "BELL & ROSS": "Bell & Ross",
    "OMEGA": "Omega", "TUDOR": "Tudor", "SEIKO": "Seiko", "GRAND SEIKO": "Grand Seiko", "BAUME": "Baume & Mercier", "BAUME & MERCIER": "Baume & Mercier", "ROGER DUBUIS": "Roger Dubuis",
    "CARTIER": "Cartier", "PANERAI": "Panerai", "IWC": "IWC", "BREITLING": "Breitling", "OTSUKA LOTEC": "Otsuka Lotec",
    "TAG HEUER": "Tag Heuer", "JAEGER-LECOULTRE": "Jaeger-LeCoultre", "JLC": "Jaeger-LeCoultre",
    "HUBLOT": "Hublot", "RICHARD MILLE": "Richard Mille", "VACHERON CONSTANTIN": "Vacheron Constantin",
    "BLANCPAIN": "Blancpain", "CHOPARD": "Chopard", "ZENITH": "Zenith", "LONGINES": "Longines",
    "TISSOT": "Tissot", "F.P. JOURNE": "F.P. Journe", "BVLGARI": "Bvlgari", "A. LANGE": "A. Lange & Söhne"
}

# ==========================================
# 2. AUTENTIKASI OAUTH GOOGLE (BLOGGER, DRIVE, YOUTUBE)
# ==========================================

def get_google_credentials():
    return Credentials(
        token=None,
        refresh_token=GCP_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GCP_CLIENT_ID,
        client_secret=GCP_CLIENT_SECRET
    )

def get_blogger_service():
    print("Memulai autentikasi Google Blogger API dengan Refresh Token...")
    creds = get_google_credentials()
    blogger_service = build('blogger', 'v3', credentials=creds)
    print("✅ Autentikasi Google Blogger berhasil!")
    return blogger_service

def get_drive_service():
    creds = get_google_credentials()
    return build('drive', 'v3', credentials=creds)

def get_youtube_service():
    creds = get_google_credentials()
    return build('youtube', 'v3', credentials=creds)

# Konfigurasi Otomasi YouTube Shorts & Google Drive
YOUTUBE_SUBFOLDER_NAME = "youtube"
DRIVE_AUDIO_FOLDER_ID = os.getenv("DRIVE_AUDIO_FOLDER_ID", "1NO7JUz7kOzyjiKLqkZKJD18Tw0CSIB2K")
LOCAL_AUDIO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio_tracks")
YOUTUBE_DESCRIPTION_TEMPLATE = """🔹 IDWX - Your Trusted Luxury Timepiece Destination 🔹

🌐 Website:
🔗 https://idwx.co

📞 Contact:
📩 Email: idwxofficial@gmail.com
📱 WhatsApp: +62 819-0959-9009

#idwx #jamtanganmewah #luxurywatch #youtubeshorts"""

QUEUE_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pending_youtube_queue.json")

# ==========================================
# 3. FUNGSI API SHOPIFY & HELPER
# ==========================================
def ensure_shopify_token(force_refresh=False):
    global SHOPIFY_ACCESS_TOKEN, SHOPIFY_TOKEN_EXPIRY, HEADERS_SHOPIFY
    now = time.time()
    # Refresh jika token belum ada, diminta force_refresh, atau masa berlaku tersisa < 10 menit
    if force_refresh or not SHOPIFY_ACCESS_TOKEN or now >= (SHOPIFY_TOKEN_EXPIRY - 600):
        print("🔄 Meminta/memperbarui token akses API baru dari Shopify...")
        token_url = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/oauth/access_token"
        payload = {
            "grant_type": "client_credentials",
            "client_id": SHOPIFY_CLIENT_ID,
            "client_secret": SHOPIFY_CLIENT_SECRET
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        for attempt in range(3):
            try:
                response = requests.post(token_url, headers=headers, data=payload, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    SHOPIFY_ACCESS_TOKEN = data.get('access_token')
                    expires_in = int(data.get('expires_in', 86399))
                    SHOPIFY_TOKEN_EXPIRY = now + expires_in
                    HEADERS_SHOPIFY["X-Shopify-Access-Token"] = SHOPIFY_ACCESS_TOKEN
                    print(f"✅ Token Shopify berhasil diperbarui! (Masa berlaku ~{expires_in // 3600} jam)")
                    return SHOPIFY_ACCESS_TOKEN
                else:
                    print(f"⚠️ Gagal mendapatkan token Shopify (HTTP {response.status_code}): {response.text}")
            except Exception as e:
                print(f"⚠️ Error koneksi saat meminta token Shopify (percobaan {attempt+1}): {e}")
            time.sleep(2)
        print("❌ Gagal memperbarui token Shopify setelah 3 percobaan.")
        return SHOPIFY_ACCESS_TOKEN
    return SHOPIFY_ACCESS_TOKEN

# Inisialisasi token & header secara global
SHOPIFY_ACCESS_TOKEN = None
SHOPIFY_TOKEN_EXPIRY = 0
HEADERS_SHOPIFY = {
    "Content-Type": "application/json"
}
ensure_shopify_token(force_refresh=True)

GRAPHQL_URL = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{API_VERSION}/graphql.json"
SHOPIFY_UPLOAD_ENDPOINT = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{API_VERSION}/products.json"


def get_target_location(target_location_name):
    ensure_shopify_token()
    url = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{API_VERSION}/locations.json"
    try:
        res = requests.get(url, headers=HEADERS_SHOPIFY, timeout=30)
        if res.status_code == 200:
            for loc in res.json().get('locations', []):
                if loc.get('name') == target_location_name:
                    return loc['id']
    except Exception as e:
        print(f"⚠️ Error get_target_location({target_location_name}): {e}")
    return None

def get_category_id():
    ensure_shopify_token()
    query = '{ taxonomy { categories(search: "Watches", first: 1) { edges { node { id fullName } } } } }'
    try:
        res = requests.post(GRAPHQL_URL, headers=HEADERS_SHOPIFY, json={"query": query}, timeout=30)
        if res.status_code == 200:
            edges = res.json().get('data', {}).get('taxonomy', {}).get('categories', {}).get('edges', [])
            if edges: return edges[0]['node']['id']
    except Exception as e:
        print(f"⚠️ Error get_category_id: {e}")
    return None

def get_existing_data():
    ensure_shopify_token()
    print("Mendownload database SKU dan Handle dari Shopify (mohon tunggu)...")
    skus = set()
    handles = set()
    endpoint = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{API_VERSION}/products.json"
    params = {"limit": 250, "fields": "handle,variants"}
    total_fetched = 0
    while endpoint:
        try:
            response = requests.get(endpoint, headers=HEADERS_SHOPIFY, params=params, timeout=30)
        except requests.exceptions.Timeout:
            print("⚠️ Timeout saat menghubungi Shopify. Mencoba lagi...")
            continue
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Error koneksi: {e}")
            break

        if response.status_code != 200: break
        products = response.json().get('products', [])
        total_fetched += len(products)
        print(f"⏳ Telah memuat {total_fetched} produk...")

        for product in products:
            if product.get('handle'): handles.add(product.get('handle'))
            for variant in product.get('variants', []):
                if variant.get('sku'): skus.add(variant.get('sku'))

        link_header = response.headers.get('Link')
        endpoint = None
        params = None # Hapus params limit saat memanggil link pagination
        if link_header:
            for link in link_header.split(','):
                if 'rel="next"' in link:
                    endpoint = link[link.find("<")+1:link.find(">")]
                    break
    print(f"\n✅ Selesai! Database tersinkronisasi ({len(skus)} SKU unik).")
    return skus, handles

def extract_high_res_images(soup):
    raw_image_urls = []
    for img in soup.find_all('img'):
        if 'src' in img.attrs:
            raw_url = img['src']
            parent_a = img.find_parent('a')
            if parent_a and 'href' in parent_a.attrs:
                href = parent_a['href']
                # Tangkap jika href adalah file gambar, ATAU domain bawaan Blogger
                if re.search(r'\.(jpg|jpeg|png|webp)$', href, re.IGNORECASE) or 'googleusercontent.com' in href or 'bp.blogspot.com' in href:
                    raw_url = href

            # Konversi format ukuran lama (/s320/) dan format baru (=w640-h480) ke original size (/s0/ atau =s0)
            high_res_url = re.sub(r'=(s\d+|w\d+-h\d+[^/]*)$', '=s0', raw_url)
            high_res_url = re.sub(r'/(?:s\d+|w\d+-h\d+[^/]*)/([^/]+)$', r'/s0/\1', high_res_url)

            if high_res_url not in raw_image_urls:
                raw_image_urls.append(high_res_url)
    return raw_image_urls

def buat_handle_url(title, year, existing_handles):
    base_handle = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
    if year and not base_handle.endswith(str(year)):
        base_handle = f"{base_handle}-{year}"

    handle = base_handle
    counter = 1
    while handle in existing_handles:
        handle = f"{base_handle}-{counter}"
        counter += 1

    existing_handles.add(handle)
    return handle

# Headers & Session khusus untuk download gambar agar tidak diblokir/dibatasi CDN Google
IMAGE_SESSION = requests.Session()
IMAGE_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
})

def download_single_image(img_url, max_retries=3):
    """
    Mendownload konten gambar dari URL Blogger dengan retry berulang,
    headers browser, dan fallback multi-resolusi (/s0/, /s2000/, /s1600/, /w1600/).
    Mengembalikan bytes jika sukses, atau None jika seluruh resolusi gagal.
    """
    candidates = [img_url]
    if '/s0/' in img_url or '=s0' in img_url:
        candidates.append(img_url.replace('/s0/', '/s2000/').replace('=s0', '=s2000'))
        candidates.append(img_url.replace('/s0/', '/s1600/').replace('=s0', '=s1600'))
        candidates.append(img_url.replace('/s0/', '/w1600/').replace('=s0', '=w1600'))

    for candidate in candidates:
        for attempt in range(max_retries):
            try:
                res = IMAGE_SESSION.get(candidate, timeout=45)
                if res.status_code == 200 and len(res.content) > 0:
                    return res.content
                elif res.status_code in (429, 500, 502, 503, 504):
                    time.sleep(1.5 * (attempt + 1))
            except Exception:
                time.sleep(1.5 * (attempt + 1))
    return None

def prepare_image_payloads(raw_image_urls, clean_title):
    """
    Mempersiapkan array payload gambar untuk Shopify.
    - Mencoba download sebagai base64 'attachment' dengan nama file SEO-friendly.
    - JIKA download base64 gagal/timeout pada server setelah semua percobaan,
      SECARA OTOMATIS fallback ke URL 'src', sehingga Shopify yang akan
      mendownload gambar langsung dari CDN Google dan TIDAK ADA GAMBAR YANG HILANG!
    """
    image_payloads = []
    potongan_kata = clean_title.split()[:3]
    alt_text_rapi = " ".join(potongan_kata).title()
    nama_file_dasar = alt_text_rapi.replace(" ", "-")

    for i, img_url in enumerate(raw_image_urls):
        filename = f"{nama_file_dasar}-{i+1}.jpg"
        content_bytes = download_single_image(img_url)

        if content_bytes:
            img_base64 = base64.b64encode(content_bytes).decode('utf-8')
            image_payloads.append({
                "attachment": img_base64,
                "filename": filename,
                "alt": alt_text_rapi
            })
        else:
            print(f"   ⚠️ Gagal download lokal gambar {i+1} dari {img_url}. Menggunakan fallback link 'src' langsung ke Shopify.")
            image_payloads.append({
                "src": img_url,
                "alt": alt_text_rapi
            })

    return image_payloads, alt_text_rapi

# Variabel Global Database Shopify
LOCATION_ID_BLOK_M = get_target_location("DUALTIME - BLOK M PLAZA")
LOCATION_ID_OWNER = get_target_location("OWNER (S)")
CATEGORY_ID = get_category_id()
EXISTING_SKUS, EXISTING_HANDLES = get_existing_data()
LAST_SYNC_DATE = datetime.now(WIB).strftime("%Y-%m-%d")

def ensure_shopify_metadata(force_resync=False):
    global LOCATION_ID_BLOK_M, LOCATION_ID_OWNER, CATEGORY_ID, EXISTING_SKUS, EXISTING_HANDLES
    if not LOCATION_ID_BLOK_M:
        LOCATION_ID_BLOK_M = get_target_location("DUALTIME - BLOK M PLAZA")
    if not LOCATION_ID_OWNER:
        LOCATION_ID_OWNER = get_target_location("OWNER (S)")
    if not CATEGORY_ID:
        CATEGORY_ID = get_category_id()
    if force_resync:
        new_skus, new_handles = get_existing_data()
        if new_skus:
            EXISTING_SKUS = new_skus
        if new_handles:
            EXISTING_HANDLES = new_handles


def reconcile_shopify_product_images(product_id, raw_image_urls, clean_title, max_retries=3):
    """
    Idempotent image reconciliation:
    1. Mengambil daftar foto yang sudah tersimpan di produk Shopify.
    2. Jika jumlah foto sudah sama atau lebih, lewati (idempotent).
    3. Jika terdeteksi foto kurang (misal 6 dari 7), sistem mengidentifikasi foto
       mana yang belum masuk dan mengunggahnya secara terisolasi ke endpoint
       POST /admin/api/{version}/products/{id}/images.json.
    """
    ensure_shopify_token()
    if not raw_image_urls or not product_id:
        return

    potongan_kata = clean_title.split()[:3]
    alt_text_rapi = " ".join(potongan_kata).title()
    nama_file_dasar = alt_text_rapi.replace(" ", "-")

    url = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{API_VERSION}/products/{product_id}/images.json"
    existing_images = []
    try:
        res = requests.get(url, headers=HEADERS_SHOPIFY, timeout=30)
        if res.status_code == 200:
            existing_images = res.json().get('images', [])
        else:
            print(f"   ⚠️ Gagal memeriksa foto di Shopify (HTTP {res.status_code}).")
            return
    except Exception as e:
        print(f"   ⚠️ Error koneksi saat cek foto produk {product_id}: {e}")
        return

    total_expected = len(raw_image_urls)
    total_existing = len(existing_images)

    if total_existing >= total_expected:
        print(f"   ✅ Integritas foto terverifikasi lengkap: {total_existing}/{total_expected} foto ada di Shopify.")
        return

    print(f"   ⚠️ Terdeteksi foto kurang di Shopify ({total_existing}/{total_expected}). Memulai rekonsiliasi foto...")

    for i, raw_url in enumerate(raw_image_urls):
        pos = i + 1
        filename = f"{nama_file_dasar}-{pos}.jpg"
        raw_basename = os.path.basename(urlparse(raw_url).path)

        # Cek apakah foto ini sudah ada di Shopify
        already_exists = False
        for ex in existing_images:
            src = ex.get('src', '')
            if f"{nama_file_dasar}-{pos}" in src or (raw_basename and raw_basename in src):
                already_exists = True
                break

        if already_exists:
            continue

        print(f"   ⏳ Mengunggah foto posisi {pos} yang belum masuk ({filename})...")
        content_bytes = download_single_image(raw_url)
        uploaded = False

        # Jalur 1: Upload via Base64 attachment
        if content_bytes:
            img_b64 = base64.b64encode(content_bytes).decode('utf-8')
            img_payload = {
                "image": {
                    "attachment": img_b64,
                    "filename": filename,
                    "position": pos,
                    "alt": alt_text_rapi
                }
            }
            for attempt in range(max_retries):
                try:
                    r_img = requests.post(url, headers=HEADERS_SHOPIFY, json=img_payload, timeout=45)
                    if r_img.status_code in (200, 201):
                        print(f"   ✅ Foto posisi {pos} BERHASIL ditambahkan via Base64!")
                        uploaded = True
                        break
                    elif r_img.status_code == 401:
                        ensure_shopify_token(force_refresh=True)
                except Exception:
                    time.sleep(2)

        # Jalur 2: Fallback ke URL src direct jika Base64 gagal
        if not uploaded:
            print(f"   ⚠️ Mencoba upload foto posisi {pos} via direct URL...")
            img_payload_src = {
                "image": {
                    "src": raw_url,
                    "position": pos,
                    "alt": alt_text_rapi
                }
            }
            for attempt in range(max_retries):
                try:
                    r_src = requests.post(url, headers=HEADERS_SHOPIFY, json=img_payload_src, timeout=45)
                    if r_src.status_code in (200, 201):
                        print(f"   ✅ Foto posisi {pos} BERHASIL ditambahkan via direct URL!")
                        uploaded = True
                        break
                    elif r_src.status_code == 401:
                        ensure_shopify_token(force_refresh=True)
                except Exception:
                    time.sleep(2)

    # Verifikasi akhir setelah rekonsiliasi
    try:
        final_res = requests.get(url, headers=HEADERS_SHOPIFY, timeout=30)
        if final_res.status_code == 200:
            final_count = len(final_res.json().get('images', []))
            print(f"   📸 Rekonsiliasi selesai! Total foto sekarang di Shopify: {final_count}/{total_expected}")
    except Exception:
        pass

# ==========================================
# 5. FUNGSI PROSES UNTUK NOTSYNC
# ==========================================
def process_notsync(blogger_service, urls):
    if not urls:
        return []

    success_urls = []
    print(f"\nMemulai proses pemindahan data untuk {len(urls)} item (Format NotSync)...")
    for idx, url in enumerate(urls, 1):
        print(f"\n[{idx}/{len(urls)}] Memproses: {url}")
        try:
            parsed_url = urlparse(url)
            post_path = parsed_url.path

            request = blogger_service.posts().getByPath(blogId=BLOG_ID, path=post_path)
            response = request.execute()

            raw_title = response.get('title', '')
            raw_html = response.get('content', '')

            # --- EKSTRAKSI JUDUL ---
            clean_title = re.sub(r'^\[?FOR\s+SALE\]?\s*', '', raw_title, flags=re.IGNORECASE).strip()
            clean_title = re.sub(r'\(\d{4}\)', '', clean_title).strip()
            if not clean_title: continue

            soup = BeautifulSoup(raw_html, 'html.parser')

            # --- EKSTRAKSI GAMBAR ---
            raw_image_urls = extract_high_res_images(soup)

            image_urls, alt_text_rapi = prepare_image_payloads(raw_image_urls, clean_title)

            # --- EKSTRAKSI TEKS ---
            for br in soup.find_all("br"): br.replace_with("\n")
            for tag in soup.find_all(['div', 'p', 'li', 'ul', 'h1', 'h2', 'h3']):
                tag.insert_before("\n")
                tag.insert_after("\n")

            clean_lines = [re.sub(r'\s+', ' ', line.strip()) for line in soup.get_text().split('\n') if re.sub(r'\s+', ' ', line.strip())]
            body_text = "\n".join(clean_lines)
            lines = clean_lines

            # --- EKSTRAKSI SKU ---
            sku = ""
            sku_match = re.search(r'Code:\s*([\w\-\/]+)', body_text, re.IGNORECASE)
            if sku_match:
                base_sku = sku_match.group(1)
                sku = base_sku
                counter = 1
                while sku in EXISTING_SKUS:
                    sku = f"{base_sku}-{counter}"
                    counter += 1
                EXISTING_SKUS.add(sku)

            # --- EKSTRAKSI HARGA & TAHUN ---
            price = "0"
            price_match = re.search(r'Price\s*:\s*([^\n]+)', body_text, re.IGNORECASE)
            if price_match: price = re.sub(r'[^\d]', '', price_match.group(1)) or "0"

            year = ""
            year_match = re.search(r'(?:Year|Tahun)\s*:\s*(\d{4})', body_text, re.IGNORECASE)
            if year_match:
                year = year_match.group(1)
            else:
                year_match_title = re.search(r'\b(19\d{2}|20\d{2})\b', raw_title)
                if year_match_title:
                    year = year_match_title.group(1)

            # --- MENYUSUN TAGS & DESKRIPSI ---
            tags_list = ['NotSync']
            desc_lines = []
            for line in lines:
                if re.search(r'^(Price|Code|Last Post|Order Received|Form|Notes):', line, re.IGNORECASE): break
                desc_lines.append(line)
            if desc_lines: desc_lines[0] = f"<strong>{desc_lines[0]}</strong>"
            if len(desc_lines) > 1:
                final_description_html = f"<p>{desc_lines[0]}</p><p>" + "<br>".join(desc_lines[1:]) + "</p>"
            else:
                final_description_html = f"<p>{desc_lines[0] if desc_lines else ''}</p>"

            # --- DETEKSI MEREK, PAGE TITLE, URL HANDLE & DISPLAY TITLE ---
            vendor = "Unknown"
            matched_keyword = ""
            for keyword in sorted(DAFTAR_MEREK_IDWX.keys(), key=len, reverse=True):
                if keyword in clean_title.upper():
                    vendor = DAFTAR_MEREK_IDWX[keyword]
                    matched_keyword = keyword
                    break

            if vendor == "Unknown":
                vendor = clean_title.split()[0].title()
                matched_keyword = vendor

            seo_page_title = f"{clean_title} ({year})" if year else clean_title
            display_title = re.sub(rf"(?i)^({re.escape(matched_keyword)}|{re.escape(vendor)})\s*", "", clean_title).strip()


            custom_handle = buat_handle_url(clean_title, year, EXISTING_HANDLES)

            print(f"   ✅ Data siap: {vendor} | SKU: {sku} | Harga: Rp {price} | Handle: {custom_handle}")

            # --- UPLOAD KE SHOPIFY ---
            variant_payload = {
                "price": price, "sku": sku, "requires_shipping": True, "grams": 3000,
                "weight_unit": "kg", "inventory_management": "shopify", "inventory_policy": "deny", "fulfillment_service": "manual"
            }

            product_payload = {
                "product": {
                    "title": display_title, "body_html": final_description_html, "vendor": vendor,
                    "tags": ", ".join(tags_list), "handle": custom_handle, "status": "active",
                    "published": True, "published_scope": "global", "variants": [variant_payload],
                    "images": image_urls,
                    "metafields": [{"namespace": "global", "key": "title_tag", "value": seo_page_title[:70], "type": "single_line_text_field"}]
                }
            }

            shopify_res = requests.post(SHOPIFY_UPLOAD_ENDPOINT, headers=HEADERS_SHOPIFY, json=product_payload, timeout=60)

            # Jika 401 Unauthorized, refresh token dan coba lagi sekali
            if shopify_res.status_code == 401:
                print("   ⚠️ Token Shopify expired (401). Meminta token baru dan mengulang upload...")
                ensure_shopify_token(force_refresh=True)
                shopify_res = requests.post(SHOPIFY_UPLOAD_ENDPOINT, headers=HEADERS_SHOPIFY, json=product_payload, timeout=60)

            if shopify_res.status_code == 201:
                prod_data = shopify_res.json()['product']
                new_id = prod_data['id']
                graphql_product_id = f"gid://shopify/Product/{new_id}"
                print(f"   🎉 Sukses diunggah! Product ID: {new_id}")

                # Verifikasi & rekonsiliasi foto seketika agar 100% lengkap
                reconcile_shopify_product_images(new_id, raw_image_urls, clean_title)

                if CATEGORY_ID:
                    mutation = "mutation productUpdate($input: ProductInput!) { productUpdate(input: $input) { userErrors { message } } }"
                    requests.post(GRAPHQL_URL, headers=HEADERS_SHOPIFY, json={"query": mutation, "variables": {"input": {"id": graphql_product_id, "category": CATEGORY_ID}}}, timeout=30)

                res_pubs = requests.post(GRAPHQL_URL, headers=HEADERS_SHOPIFY, json={"query": "{ publications(first: 20) { edges { node { id name } } } }"}, timeout=30)
                if res_pubs.status_code == 200:
                    pub_inputs = [{"publicationId": edge['node']['id']} for edge in res_pubs.json().get('data', {}).get('publications', {}).get('edges', [])]
                    if pub_inputs:
                        mutation_pub = "mutation publishablePublish($id: ID!, $input: [PublicationInput!]!) { publishablePublish(id: $id, input: $input) { userErrors { message } } }"
                        requests.post(GRAPHQL_URL, headers=HEADERS_SHOPIFY, json={"query": mutation_pub, "variables": {"id": graphql_product_id, "input": pub_inputs}}, timeout=30)

                if LOCATION_ID_BLOK_M:
                    inv_url = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{API_VERSION}/inventory_levels/set.json"
                    requests.post(inv_url, headers=HEADERS_SHOPIFY, json={"location_id": LOCATION_ID_BLOK_M, "inventory_item_id": prod_data['variants'][0]['inventory_item_id'], "available": 1}, timeout=30)

                success_urls.append(url)
            else:
                print(f"   ❌ Gagal mengunggah. Error: {shopify_res.text}")

        except Exception as e:
            print(f"   ❌ Error saat memproses {url}: {e}")

        time.sleep(1)

    print("✅ SEMUA PROSES (NOTSYNC) SELESAI!")
    return success_urls


# ==========================================
# FUNGSI PROSES UNTUK TWP
# ==========================================
def process_twp(blogger_service, urls):
    if not urls:
        return []

    success_urls = []
    print(f"\nMemulai proses pemindahan data untuk {len(urls)} item (Format TWP)...")
    for idx, url in enumerate(urls, 1):
        print(f"\n[{idx}/{len(urls)}] Memproses: {url}")
        try:
            parsed_url = urlparse(url)
            post_path = parsed_url.path

            request = blogger_service.posts().getByPath(blogId=BLOG_ID, path=post_path)
            response = request.execute()

            raw_title = response.get('title', '')
            raw_html = response.get('content', '')

            # --- EKSTRAKSI JUDUL ---
            clean_title = re.sub(r'^\[?FOR\s+SALE\]?\s*', '', raw_title, flags=re.IGNORECASE).strip()
            clean_title = re.sub(r'\(\d{4}\)', '', clean_title).strip()
            if not clean_title: continue

            soup = BeautifulSoup(raw_html, 'html.parser')

            # --- EKSTRAKSI GAMBAR ---
            raw_image_urls = extract_high_res_images(soup)

            image_urls, alt_text_rapi = prepare_image_payloads(raw_image_urls, clean_title)

            # --- EKSTRAKSI TEKS ---
            for br in soup.find_all("br"): br.replace_with("\n")
            for tag in soup.find_all(['div', 'p', 'li', 'ul', 'h1', 'h2', 'h3']):
                tag.insert_before("\n")
                tag.insert_after("\n")

            clean_lines = [re.sub(r'\s+', ' ', line.strip()) for line in soup.get_text().split('\n') if re.sub(r'\s+', ' ', line.strip())]
            body_text = "\n".join(clean_lines)
            lines = clean_lines

            # --- EKSTRAKSI SKU ---
            sku = ""
            sku_match = re.search(r'Code:\s*([\w\-\/]+)', body_text, re.IGNORECASE)
            if sku_match:
                base_sku = sku_match.group(1)
                sku = base_sku
                counter = 1
                while sku in EXISTING_SKUS:
                    sku = f"{base_sku}-{counter}"
                    counter += 1
                EXISTING_SKUS.add(sku)

            # --- EKSTRAKSI HARGA & TAHUN ---
            price = "0"
            price_match = re.search(r'Price\s*:\s*([^\n]+)', body_text, re.IGNORECASE)
            if price_match: price = re.sub(r'[^\d]', '', price_match.group(1)) or "0"

            year = ""
            year_match = re.search(r'(?:Year|Tahun)\s*:\s*(\d{4})', body_text, re.IGNORECASE)
            if year_match:
                year = year_match.group(1)
            else:
                year_match_title = re.search(r'\b(19\d{2}|20\d{2})\b', raw_title)
                if year_match_title:
                    year = year_match_title.group(1)

            # --- MENYUSUN TAGS & DESKRIPSI ---
            tags_list = ['SG']
            desc_lines = []
            for line in lines:
                if re.search(r'^(Price|Code|Last Post|Order Received|Form|Notes):', line, re.IGNORECASE): break
                desc_lines.append(line)
            if desc_lines: desc_lines[0] = f"<strong>{desc_lines[0]}</strong>"
            if len(desc_lines) > 1:
                final_description_html = f"<p>{desc_lines[0]}</p><p>" + "<br>".join(desc_lines[1:]) + "</p>"
            else:
                final_description_html = f"<p>{desc_lines[0] if desc_lines else ''}</p>"

            # --- DETEKSI MEREK, PAGE TITLE, URL HANDLE & DISPLAY TITLE ---
            vendor = "Unknown"
            matched_keyword = ""
            for keyword in sorted(DAFTAR_MEREK_IDWX.keys(), key=len, reverse=True):
                if keyword in clean_title.upper():
                    vendor = DAFTAR_MEREK_IDWX[keyword]
                    matched_keyword = keyword
                    break

            if vendor == "Unknown":
                vendor = clean_title.split()[0].title()
                matched_keyword = vendor

            seo_page_title = f"{clean_title} ({year})" if year else clean_title
            display_title = re.sub(rf"(?i)^({re.escape(matched_keyword)}|{re.escape(vendor)})\s*", "", clean_title).strip()


            custom_handle = buat_handle_url(clean_title, year, EXISTING_HANDLES)

            print(f"   ✅ Data siap: {vendor} | SKU: {sku} | Harga: Rp {price} | Handle: {custom_handle}")

            # --- UPLOAD KE SHOPIFY ---
            variant_payload = {
                "price": price, "sku": sku, "requires_shipping": True, "grams": 3000,
                "weight_unit": "kg", "inventory_management": "shopify", "inventory_policy": "deny", "fulfillment_service": "manual"
            }

            product_payload = {
                "product": {
                    "title": display_title, "body_html": final_description_html, "vendor": vendor,
                    "tags": ", ".join(tags_list), "handle": custom_handle, "status": "active",
                    "published": True, "published_scope": "global", "variants": [variant_payload],
                    "images": image_urls,
                    "metafields": [{"namespace": "global", "key": "title_tag", "value": seo_page_title[:70], "type": "single_line_text_field"}]
                }
            }

            shopify_res = requests.post(SHOPIFY_UPLOAD_ENDPOINT, headers=HEADERS_SHOPIFY, json=product_payload, timeout=60)

            # Jika 401 Unauthorized, refresh token dan coba lagi sekali
            if shopify_res.status_code == 401:
                print("   ⚠️ Token Shopify expired (401). Meminta token baru dan mengulang upload...")
                ensure_shopify_token(force_refresh=True)
                shopify_res = requests.post(SHOPIFY_UPLOAD_ENDPOINT, headers=HEADERS_SHOPIFY, json=product_payload, timeout=60)

            if shopify_res.status_code == 201:
                prod_data = shopify_res.json()['product']
                new_id = prod_data['id']
                graphql_product_id = f"gid://shopify/Product/{new_id}"
                print(f"   🎉 Sukses diunggah! Product ID: {new_id}")

                # Verifikasi & rekonsiliasi foto seketika agar 100% lengkap
                reconcile_shopify_product_images(new_id, raw_image_urls, clean_title)

                if CATEGORY_ID:
                    mutation = "mutation productUpdate($input: ProductInput!) { productUpdate(input: $input) { userErrors { message } } }"
                    requests.post(GRAPHQL_URL, headers=HEADERS_SHOPIFY, json={"query": mutation, "variables": {"input": {"id": graphql_product_id, "category": CATEGORY_ID}}}, timeout=30)

                res_pubs = requests.post(GRAPHQL_URL, headers=HEADERS_SHOPIFY, json={"query": "{ publications(first: 20) { edges { node { id name } } } }"}, timeout=30)
                if res_pubs.status_code == 200:
                    pub_inputs = [{"publicationId": edge['node']['id']} for edge in res_pubs.json().get('data', {}).get('publications', {}).get('edges', [])]
                    if pub_inputs:
                        mutation_pub = "mutation publishablePublish($id: ID!, $input: [PublicationInput!]!) { publishablePublish(id: $id, input: $input) { userErrors { message } } }"
                        requests.post(GRAPHQL_URL, headers=HEADERS_SHOPIFY, json={"query": mutation_pub, "variables": {"id": graphql_product_id, "input": pub_inputs}}, timeout=30)

                if LOCATION_ID_BLOK_M:
                    inv_url = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{API_VERSION}/inventory_levels/set.json"
                    requests.post(inv_url, headers=HEADERS_SHOPIFY, json={"location_id": LOCATION_ID_BLOK_M, "inventory_item_id": prod_data['variants'][0]['inventory_item_id'], "available": 1}, timeout=30)

                success_urls.append(url)
            else:
                print(f"   ❌ Gagal mengunggah. Error: {shopify_res.text}")

        except Exception as e:
            print(f"   ❌ Error saat memproses {url}: {e}")

        time.sleep(1)

    print("✅ SEMUA PROSES (TWP) SELESAI!")
    return success_urls


# ==========================================
# 6. FUNGSI PROSES UNTUK PHOTO STUDIO
# ==========================================
def process_photo_studio(blogger_service, urls):
    if not urls:
        return []

    success_urls = []
    print(f"\nMemulai proses pemindahan data untuk {len(urls)} item (Format Photo Studio)...")
    for idx, url in enumerate(urls, 1):
        print(f"\n[{idx}/{len(urls)}] Memproses: {url}")
        try:
            parsed_url = urlparse(url)
            post_path = parsed_url.path

            request = blogger_service.posts().getByPath(blogId=BLOG_ID, path=post_path)
            response = request.execute()

            raw_title = response.get('title', '')
            raw_html = response.get('content', '')
            labels = response.get('labels', [])

            is_consignment = any('CONSIGNMENT' in label.upper() for label in labels)
            is_featured = any('FEATURED' in label.upper() for label in labels)

            year = ""
            year_match = re.search(r'\((\d{4})\)', raw_title)
            if year_match: year = year_match.group(1)

            clean_title = re.sub(r'^\[?FOR\s+SALE\]?\s*', '', raw_title, flags=re.IGNORECASE).strip()
            clean_title = re.sub(r'\(\d{4}\)', '', clean_title).strip()
            if not clean_title: continue

            vendor = "Unknown"
            for keyword in sorted(DAFTAR_MEREK_IDWX.keys(), key=len, reverse=True):
                if keyword in clean_title.upper(): vendor = DAFTAR_MEREK_IDWX[keyword]; break
            if vendor == "Unknown": vendor = clean_title.split()[0].title()

            seo_page_title = f"{clean_title} ({year})" if year else clean_title
            display_title_no_year = re.sub(rf"^{re.escape(vendor)}\s+", "", clean_title, flags=re.IGNORECASE).strip()
            short_display_title = f"{display_title_no_year} ({year})" if year else display_title_no_year

            soup = BeautifulSoup(raw_html, 'html.parser')

            raw_image_urls = extract_high_res_images(soup)
            image_urls, alt_text_rapi = prepare_image_payloads(raw_image_urls, clean_title)
            first_image_url = raw_image_urls[0] if raw_image_urls else ""

            for br in soup.find_all("br"): br.replace_with("\n")
            for tag in soup.find_all(['div', 'p', 'li', 'ul', 'h1', 'h2', 'h3']): tag.insert_before("\n"); tag.insert_after("\n")
            raw_text = soup.get_text()
            clean_lines = [re.sub(r'\s+', ' ', line.strip()) for line in raw_text.split('\n') if re.sub(r'\s+', ' ', line.strip())]
            body_text, lines = "\n".join(clean_lines), clean_lines

            sku, base_sku, owner, reference = "", "", "", ""
            sku_match = re.search(r'Code:\s*([\w\-\/]+)', body_text, re.IGNORECASE)
            if sku_match:
                base_sku = sku_match.group(1)
                sku = base_sku
                if sku in EXISTING_SKUS:
                    counter = 1
                    while f"{base_sku}-{counter}" in EXISTING_SKUS: counter += 1
                    sku = f"{base_sku}-{counter}"
                EXISTING_SKUS.add(sku)
                owner_match = re.search(r'Code:\s*[\w\-\/]+\s*\((.*?)\)', body_text, re.IGNORECASE)
                if owner_match: owner = owner_match.group(1).strip()


            custom_handle = buat_handle_url(clean_title, year, EXISTING_HANDLES)

            ref_match = re.search(r'Ref\.\s*([^\n]+)', body_text, re.IGNORECASE)
            if ref_match: reference = ref_match.group(1).strip()

            price = "0"
            price_match = re.search(r'Price\s*:\s*(?:Rp\.?\s*)?([\d\.,]+)', body_text, flags=re.IGNORECASE)
            if price_match:
                angka_saja = re.sub(r'[^\d]', '', price_match.group(1))
                if angka_saja: price = angka_saja

            gender_tag = "Men" if re.search(r'(\d{2,3})(?:\.\d+)?\s*mm', body_text, re.IGNORECASE) and float(re.search(r'(\d{2,3})(?:\.\d+)?\s*mm', body_text, re.IGNORECASE).group(1)) >= 36 else "Ladies" if re.search(r'(\d{2,3})(?:\.\d+)?\s*mm', body_text, re.IGNORECASE) else ""

            condition = ""
            for line in lines:
                cond_match = re.search(r'^(.+?)\s+Condition\b', line, re.IGNORECASE)
                if cond_match and len(cond_match.group(1)) <= 30: condition = cond_match.group(1).strip(); break

            tags_list = []
            is_consign_item = (not is_featured)

            if is_consign_item: tags_list.extend(['__label2:Consignment', 'TitipIDWX'])
            if gender_tag: tags_list.append(gender_tag)

            desc_lines = []
            for line in lines:
                if re.search(r'^Price\s*:|^Code\s*:|^Last Post\s*:|^Order Received\s*:|^Form\s*:|^Notes\s*:', line, re.IGNORECASE): break
                desc_lines.append(line)
            if desc_lines: desc_lines[0] = f"<strong>{desc_lines[0]}</strong>"

            youtube_embed_placeholder = '\n<!-- \n<div style="position: relative; padding-bottom: 56.25%; height: 0; overflow: hidden; max-width: 100%;">\n<iframe src="https://www.youtube.com/embed/xxxx" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;" frameborder="0" allowfullscreen></iframe>\n</div>\n-->'
            if len(desc_lines) > 1:
                final_description_html = f"<p>{desc_lines[0]}</p><p>" + "<br>".join(desc_lines[1:]) + "</p>" + youtube_embed_placeholder
            else:
                final_description_html = f"<p>{desc_lines[0] if desc_lines else ''}</p>" + youtube_embed_placeholder

            print(f"   ✅ Data siap: {vendor} | SKU: {sku} | Harga: Rp {price} | Handle: {custom_handle}")

            variant_payload = {"price": price, "sku": sku, "requires_shipping": True, "grams": 3000, "weight_unit": "kg", "inventory_management": "shopify", "inventory_policy": "deny", "fulfillment_service": "manual"}
            options_payload = []
            opt_idx = 1
            if year:
                options_payload.append({"name": "Year", "values": [year]})
                variant_payload[f"option{opt_idx}"] = year
                opt_idx += 1
            if condition:
                options_payload.append({"name": "Condition", "values": [condition]})
                variant_payload[f"option{opt_idx}"] = condition
                opt_idx += 1

            product_payload = {
                "product": {
                    "title": short_display_title, "handle": custom_handle, "body_html": final_description_html,
                    "vendor": vendor, "product_type": "Watches", "tags": ", ".join(tags_list),
                    "status": "active", "published": True, "published_scope": "global",
                    "variants": [variant_payload], "images": image_urls, "metafields_global_title_tag": seo_page_title
                }
            }
            if options_payload: product_payload["product"]["options"] = options_payload

            print(f"   ⏳ Mengunggah produk utama...")
            shopify_res = requests.post(SHOPIFY_UPLOAD_ENDPOINT, headers=HEADERS_SHOPIFY, json=product_payload, timeout=60)

            # Jika 401 Unauthorized, refresh token dan coba lagi sekali
            if shopify_res.status_code == 401:
                print("   ⚠️ Token Shopify expired (401). Meminta token baru dan mengulang upload...")
                ensure_shopify_token(force_refresh=True)
                shopify_res = requests.post(SHOPIFY_UPLOAD_ENDPOINT, headers=HEADERS_SHOPIFY, json=product_payload, timeout=60)

            if shopify_res.status_code == 201:
                prod_data = shopify_res.json()['product']
                new_id = prod_data['id']
                graphql_product_id = f"gid://shopify/Product/{new_id}"
                print(f"   🎉 Sukses diunggah! Product ID: {new_id}")

                # Verifikasi & rekonsiliasi foto seketika agar 100% lengkap
                reconcile_shopify_product_images(new_id, raw_image_urls, clean_title)

                if CATEGORY_ID:
                    requests.post(GRAPHQL_URL, headers=HEADERS_SHOPIFY, json={"query": "mutation productUpdate($input: ProductInput!) { productUpdate(input: $input) { userErrors { message } } }", "variables": {"input": {"id": graphql_product_id, "category": CATEGORY_ID}}}, timeout=30)

                res_pubs = requests.post(GRAPHQL_URL, headers=HEADERS_SHOPIFY, json={"query": "{ publications(first: 20) { edges { node { id name } } } }"}, timeout=30)
                if res_pubs.status_code == 200:
                    pub_inputs = [{"publicationId": edge['node']['id']} for edge in res_pubs.json().get('data', {}).get('publications', {}).get('edges', [])]
                    if pub_inputs: requests.post(GRAPHQL_URL, headers=HEADERS_SHOPIFY, json={"query": "mutation publishablePublish($id: ID!, $input: [PublicationInput!]!) { publishablePublish(id: $id, input: $input) { userErrors { message } } }", "variables": {"id": graphql_product_id, "input": pub_inputs}}, timeout=30)

                if LOCATION_ID_BLOK_M:
                    requests.post(f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{API_VERSION}/inventory_levels/set.json", headers=HEADERS_SHOPIFY, json={"location_id": LOCATION_ID_BLOK_M, "inventory_item_id": prod_data['variants'][0]['inventory_item_id'], "available": 1}, timeout=30)

                # POST KE GOOGLE SHEETS VIA WEBHOOK
                now = datetime.now(WIB)
                sku_pencarian = base_sku if base_sku else sku

                # 1. Kirim ke Spreadsheet Slow Moving (Khusus Featured)
                if is_featured:
                    print(f"   ⭐ Item FEATURED. Mengirim data ke Spreadsheet Slow Moving...")
                    try:
                        tanggal_hari_ini = now.strftime("%d/%m/%Y")
                        payload_featured = {
                            "date": tanggal_hari_ini, "owner": owner.upper() if owner else "", "brand": vendor.upper(),
                            "description": display_title_no_year.upper(), "year": year, "condition": condition.upper(),
                            "price": price, "reference": reference, "serial_number": sku_pencarian, "link": url
                        }
                        res_feat = requests.post(FEATURED_WEB_APP_URL, json=payload_featured, timeout=30)
                        try:
                            res_feat_data = res_feat.json()
                            if res_feat.status_code == 200 and res_feat_data.get("status") == "success": print(f"   📊 Berhasil! {res_feat_data.get('message')}")
                            else: print(f"   ⚠️ Gagal update Sheets Featured: {res_feat_data.get('message')}")
                        except: pass
                    except Exception as e: print(f"   ⚠️ Error Webhook Featured Sheets: {e}")

                # 2. Kirim ke Webhook LAMA Google Sheets Photo Studio (Khusus Consignment)
                if is_consign_item:
                    print(f"   📝 Item Consign. Update SKU Asli '{sku_pencarian}' di Webhook LAMA Photo Studio...")
                    try:
                        tanggal_hari_ini = now.strftime(f"%A, {now.day} %B %Y")
                        payload_sheets_lama = {
                            "sheet_name": "PHOTO STUDIO",
                            "sku": sku_pencarian,
                            "tanggal": tanggal_hari_ini,
                            "photo_url": first_image_url,
                            "status": "Publish"
                        }
                        requests.post(GOOGLE_WEB_APP_URL, json=payload_sheets_lama, timeout=30)
                        print(f"   ✅ Apps Script LAMA (Photo Studio) terkirim untuk SKU {sku_pencarian}!")
                    except Exception as e:
                        print(f"   ⚠️ Error Webhook LAMA Sheets: {e}")

                # 3. Kirim ke Webhook BARU (Spreadsheet History Foto Studio) - Update Status ke 'Publish'
                print(f"   📋 Mengubah Status di Spreadsheet History Foto Studio untuk Serial Number '{sku_pencarian}'...")
                try:
                    payload_history_studio = {
                        "sheet_name": "PHOTO STUDIO",
                        "sku": sku_pencarian,
                        "status": "Publish"
                    }
                    res_studio = requests.post(APPS_SCRIPT_HISTORY_PHOTO_STUDIO, json=payload_history_studio, timeout=30)
                    if res_studio.status_code == 200:
                        try:
                            res_studio_data = res_studio.json()
                            if res_studio_data.get("status") == "success":
                                print(f"   ✅ Apps Script (History Foto Studio): {res_studio_data.get('message')}")
                            else:
                                print(f"   ⚠️ Apps Script (History Foto Studio) Info: {res_studio_data.get('message')}")
                        except Exception:
                            print(f"   ✅ Apps Script (History Foto Studio) terkirim! (Balasan: {res_studio.text.strip()[:60]})")
                    else:
                        print(f"   ⚠️ Gagal menghubungi Apps Script History Foto Studio. Status: {res_studio.status_code}")
                except Exception as e:
                    print(f"   ⚠️ Error Webhook History Foto Studio: {e}")

                # 4. Cek Link Google Drive Assets & Masukkan ke Antrean YouTube Video
                try:
                    gdrive_folder_id = extract_gdrive_folder_id(raw_html)
                    if gdrive_folder_id:
                        yt_title = format_youtube_title(raw_title, vendor)
                        print(f"   🎬 Link GDrive Assets terdeteksi ({gdrive_folder_id}). Menambahkan ke antrean YouTube...")
                        add_to_youtube_queue({
                            "shopify_product_id": new_id,
                            "shopify_handle": custom_handle,
                            "blogger_title": raw_title,
                            "yt_title": yt_title,
                            "vendor": vendor,
                            "gdrive_folder_id": gdrive_folder_id,
                            "post_url": url,
                            "status": "pending",
                            "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                            "check_count": 0
                        })
                except Exception as e:
                    print(f"   ⚠️ Error saat menambahkan ke antrean YouTube: {e}")

                success_urls.append(url)
            else:
                print(f"   ❌ Gagal mengunggah. Error: {shopify_res.text}")

        except Exception as e:
            print(f"   ❌ Error saat memproses {url}: {e}")

        time.sleep(1)

    print("✅ SEMUA PROSES (PHOTO STUDIO) SELESAI!")
    return success_urls


# ==========================================
# 7. FUNGSI PROSES UNTUK PHOTO OWNER
# ==========================================
def process_photo_owner(blogger_service, urls):
    if not urls:
        return []

    success_urls = []
    print(f"\nMemulai proses pemindahan data untuk {len(urls)} item (Format Photo Owner)...")
    for idx, url in enumerate(urls, 1):
        print(f"\n[{idx}/{len(urls)}] Memproses: {url}")
        try:
            parsed_url = urlparse(url)
            post_path = parsed_url.path

            request = blogger_service.posts().getByPath(blogId=BLOG_ID, path=post_path)
            response = request.execute()

            raw_title = response.get('title', '')
            clean_title = re.sub(r'^\[?FOR\s+SALE\]?\s*', '', raw_title, flags=re.IGNORECASE).strip()
            clean_title = re.sub(r'\(\d{4}\)', '', clean_title).strip()
            if not clean_title: continue

            raw_html = response.get('content', '')
            soup = BeautifulSoup(raw_html, 'html.parser')

            for br in soup.find_all("br"): br.replace_with("\n")
            for tag in soup.find_all(['div', 'p', 'li', 'ul', 'h1', 'h2', 'h3']):
                tag.insert_before("\n")
                tag.insert_after("\n")

            raw_text = soup.get_text()
            clean_lines = [re.sub(r'\s+', ' ', line.strip()) for line in raw_text.split('\n') if re.sub(r'\s+', ' ', line.strip())]
            body_text = "\n".join(clean_lines)
            lines = clean_lines

            year = ""
            year_match_desc = re.search(r'(?:Year|Tahun|Dated)\s*:\s*(\d{4})', body_text, re.IGNORECASE)
            if year_match_desc:
                year = year_match_desc.group(1)
            else:
                year_match_title = re.search(r'\b(19\d{2}|20\d{2})\b', raw_title)
                if year_match_title:
                    year = year_match_title.group(1)

            vendor = "Unknown"
            for keyword in sorted(DAFTAR_MEREK_IDWX.keys(), key=len, reverse=True):
                if keyword in clean_title.upper():
                    vendor = DAFTAR_MEREK_IDWX[keyword]
                    break
            if vendor == "Unknown": vendor = clean_title.split()[0].title()

            seo_page_title = f"{clean_title} ({year})" if year else clean_title
            short_display_title = re.sub(rf"^{vendor}\s+", "", clean_title, flags=re.IGNORECASE).strip()
            if year: short_display_title = f"{short_display_title} ({year})"

            raw_image_urls = extract_high_res_images(soup)

            image_urls, alt_text_rapi = prepare_image_payloads(raw_image_urls, clean_title)

            sku, base_sku = "", ""
            sku_match = re.search(r'Code:\s*([\w\-\/]+)', body_text, re.IGNORECASE)
            if sku_match:
                base_sku = sku_match.group(1)
                sku = base_sku


            custom_handle = buat_handle_url(clean_title, year, EXISTING_HANDLES)

            if base_sku:
                if sku in EXISTING_SKUS:
                    counter = 1
                    while f"{base_sku}-{counter}" in EXISTING_SKUS: counter += 1
                    sku = f"{base_sku}-{counter}"
                EXISTING_SKUS.add(sku)

            price = "0"
            price_match = re.search(r'Price\s*:\s*([^\n]+)', body_text, re.IGNORECASE)
            if price_match:
                angka_saja = re.sub(r'[^\d]', '', price_match.group(1))
                if angka_saja: price = angka_saja

            tags_list = ['TitipOwner']
            desc_lines = []
            for line in lines:
                if re.search(r'^(Price|Code|Last Post|Order Received|Form|Notes):', line, re.IGNORECASE): break
                desc_lines.append(line)

            if desc_lines: desc_lines[0] = f"<strong>{desc_lines[0]}</strong>"
            if len(desc_lines) > 1:
                final_description_html = f"<p>{desc_lines[0]}</p><p>" + "<br>".join(desc_lines[1:]) + "</p>"
            else:
                final_description_html = f"<p>{desc_lines[0] if desc_lines else ''}</p>"

            print(f"   ✅ Data siap: {vendor} | Handle: {custom_handle} | SKU: {sku} | Harga: Rp {price}")

            variant_payload = {
                "price": price, "sku": sku, "requires_shipping": True, "grams": 3000,
                "weight_unit": "kg", "inventory_management": "shopify", "inventory_policy": "deny", "fulfillment_service": "manual"
            }

            product_payload = {
                "product": {
                    "title": short_display_title, "handle": custom_handle, "body_html": final_description_html,
                    "vendor": vendor, "tags": ", ".join(tags_list), "status": "active", "published": True, "published_scope": "global",
                    "template_suffix": "consign", "variants": [variant_payload], "images": image_urls,
                    "metafields": [{"namespace": "global", "key": "title_tag", "value": seo_page_title, "type": "single_line_text_field"}]
                }
            }

            print(f"   ⏳ Mengunggah produk utama...")
            shopify_res = requests.post(SHOPIFY_UPLOAD_ENDPOINT, headers=HEADERS_SHOPIFY, json=product_payload, timeout=60)

            # Jika 401 Unauthorized, refresh token dan coba lagi sekali
            if shopify_res.status_code == 401:
                print("   ⚠️ Token Shopify expired (401). Meminta token baru dan mengulang upload...")
                ensure_shopify_token(force_refresh=True)
                shopify_res = requests.post(SHOPIFY_UPLOAD_ENDPOINT, headers=HEADERS_SHOPIFY, json=product_payload, timeout=60)

            if shopify_res.status_code == 201:
                prod_data = shopify_res.json()['product']
                new_id = prod_data['id']
                graphql_product_id = f"gid://shopify/Product/{new_id}"
                print(f"   🎉 Sukses diunggah! Product ID: {new_id}")

                # Verifikasi & rekonsiliasi foto seketika agar 100% lengkap
                reconcile_shopify_product_images(new_id, raw_image_urls, clean_title)

                if CATEGORY_ID:
                    mutation = "mutation productUpdate($input: ProductInput!) { productUpdate(input: $input) { userErrors { message } } }"
                    variables = {"input": {"id": graphql_product_id, "category": CATEGORY_ID}}
                    requests.post(GRAPHQL_URL, headers=HEADERS_SHOPIFY, json={"query": mutation, "variables": variables}, timeout=30)
                    print(f"   🏷️  Kategori diatur ke 'Watches'.")

                query_pubs = "{ publications(first: 20) { edges { node { id name } } } }"
                res_pubs = requests.post(GRAPHQL_URL, headers=HEADERS_SHOPIFY, json={"query": query_pubs}, timeout=30)
                if res_pubs.status_code == 200:
                    edges = res_pubs.json().get('data', {}).get('publications', {}).get('edges', [])
                    pub_inputs = [{"publicationId": edge['node']['id']} for edge in edges]

                    if pub_inputs:
                        mutation_pub = "mutation publishablePublish($id: ID!, $input: [PublicationInput!]!) { publishablePublish(id: $id, input: $input) { userErrors { message } } }"
                        vars_pub = {"id": graphql_product_id, "input": pub_inputs}
                        requests.post(GRAPHQL_URL, headers=HEADERS_SHOPIFY, json={"query": mutation_pub, "variables": vars_pub}, timeout=30)
                        print(f"   📢 Berhasil dipublikasikan ke {len(pub_inputs)} Sales Channels.")

                if LOCATION_ID_OWNER:
                    inventory_item_id = prod_data['variants'][0]['inventory_item_id']
                    inv_url = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{API_VERSION}/inventory_levels/set.json"
                    inv_payload = {"location_id": LOCATION_ID_OWNER, "inventory_item_id": inventory_item_id, "available": 1}
                    requests.post(inv_url, headers=HEADERS_SHOPIFY, json=inv_payload, timeout=30)
                    print(f"   📦 Stok disetel ke 1 untuk OWNER (S).")

                print(f"   🔍 Mengirim perintah ke Spreadsheet untuk mencentang SKU '{sku}'...")
                try:
                    sku_pencarian = base_sku if 'base_sku' in locals() and base_sku else sku
                    payload_ke_gsheets = {"action": "check_web_owner", "sku": sku_pencarian}
                    app_res = requests.post(OWNER_APPS_SCRIPT_URL, json=payload_ke_gsheets, timeout=30)

                    if app_res.status_code == 200:
                        try:
                            res_data = app_res.json()
                            if res_data.get("status") == "success":
                                print(f"   ✅ Apps Script: Kolom WEB berhasil dicentang!")
                            else:
                                print(f"   ⚠️ Apps Script Info: {res_data.get('message')}")
                        except json.JSONDecodeError:
                            print(f"   ⚠️ Gagal parsing JSON dari Apps Script: {app_res.text}")
                    else:
                        print(f"   ❌ Gagal menghubungi Apps Script. Status: {app_res.status_code}")
                except Exception as e:
                    print(f"   ❌ Error saat memanggil Apps Script: {e}")

                success_urls.append(url)
            else:
                print(f"   ❌ Gagal mengunggah ke Shopify. Error: {shopify_res.text}")

        except Exception as e:
            print(f"   ❌ Error saat memproses {url}: {e}")

        time.sleep(1)

    print("✅ SEMUA PROSES (PHOTO OWNER) SELESAI!")
    return success_urls


# ==========================================
# 8. LOGIKA OTOMASI CONTINUOUS (MONITORING 5 MENIT)
# ==========================================
def load_processed_urls(filepath="processed_urls.json"):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()

def save_processed_urls(urls, filepath="processed_urls.json"):
    with open(filepath, "w") as f:
        json.dump(list(urls), f)

def load_processed_skus(filepath="processed_skus.json"):
    today_str = datetime.now(WIB).strftime("%Y-%m-%d")
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
                # Jika format baru dan tanggalnya adalah hari ini
                if isinstance(data, dict) and data.get("date") == today_str:
                    return set(data.get("skus", []))
                # Jika beda hari atau format list lama, otomatis reset
        except Exception:
            pass
    return set()

def save_processed_skus(skus, filepath="processed_skus.json"):
    today_str = datetime.now(WIB).strftime("%Y-%m-%d")
    with open(filepath, "w") as f:
        json.dump({"date": today_str, "skus": list(skus)}, f)

PROCESSED_SKUS = load_processed_skus()

def get_todays_archive_url():
    # Tetap dipertahankan kalau-kalau dibutuhkan untuk logging lama
    now = datetime.now(WIB)
    date_str = now.strftime("%Y_%m_%d")
    return f"https://www.dualtime.id/{date_str}_archive.html"

def extract_post_links_via_api(blogger_service):
    try:
        # Menggunakan API yang terautentikasi untuk mengambil 20 post terbaru
        request = blogger_service.posts().list(blogId=BLOG_ID, maxResults=20, status='LIVE')
        response = request.execute()

        post_links = set()
        items = response.get('items', [])

        # Ambil tanggal hari ini dan kemarin WIB untuk antisipasi postingan larut malam di sekitar pergantian hari
        now_wib = datetime.now(WIB)
        today_str = now_wib.strftime("%Y-%m-%d")
        yesterday_str = (now_wib - timedelta(days=1)).strftime("%Y-%m-%d")
        valid_dates = {today_str, yesterday_str}

        for post in items:
            published_date = post.get('published', '')
            # Pastikan field 'url' ada dan tanggal publikasi berada di rentang valid
            if 'url' in post and published_date[:10] in valid_dates:
                post_links.add(post['url'])

        return list(post_links)
    except Exception as e:
        print(f"⚠️ Error saat mengambil daftar post via API: {e}")
        return []

def classify_and_process_url(blogger_service, url):
    try:
        parsed_url = urlparse(url)
        post_path = parsed_url.path
        request = blogger_service.posts().getByPath(blogId=BLOG_ID, path=post_path)
        response = request.execute()

        labels = response.get('labels', [])

        # Pengecekan Wajib Label NEW ARRIVAL
        is_new_arrival = any('NEW ARRIVAL' in label.upper() for label in labels)
        if not is_new_arrival:
            print(f"⏭️ {url} dilewati karena TIDAK memiliki tag/label 'NEW ARRIVAL'.")
            return True

        raw_html = response.get('content', '')

        # Ekstrak SKU terlebih dahulu untuk pengecekan duplikat
        soup = BeautifulSoup(raw_html, 'html.parser')

        for br in soup.find_all("br"): br.replace_with("\n")
        for tag in soup.find_all(['div', 'p', 'li', 'ul', 'h1', 'h2', 'h3']):
            tag.insert_before("\n")
            tag.insert_after("\n")

        clean_lines = [re.sub(r'\s+', ' ', line.strip()) for line in soup.get_text().split('\n') if re.sub(r'\s+', ' ', line.strip())]
        body_text = "\n".join(clean_lines)

        sku = ""
        sku_match = re.search(r'Code:\s*([\w\-\/]+)', body_text, re.IGNORECASE)
        if sku_match:
            sku = sku_match.group(1).upper()

        if sku and sku in PROCESSED_SKUS:
            print(f"⏭️ {url} dilewati karena SKU '{sku}' sudah terupload di sesi ini.")
            return True # Dianggap sukses agar link masuk processed_urls

        is_ps = any('CONSIGNMENT_PS' in label.upper() or 'CONSINGMENT_PS' in label.upper() for label in labels)
        is_featured = any('FEATURED' in label.upper() for label in labels)
        is_notsync = any('NOTSYNC' in label.upper() for label in labels)
        is_po = any('CONSIGNMENT_PO' in label.upper() or 'CONSINGMENT_PO' in label.upper() for label in labels)
        is_twp = any('TWP' in label.upper() for label in labels)

        success_urls = []
        if is_ps:
            print(f"📌 {url} diklasifikasikan sebagai: PHOTO STUDIO (berdasarkan label CONSIGNMENT_PS)")
            success_urls = process_photo_studio(blogger_service, [url])
        elif is_featured:
            print(f"📌 {url} diklasifikasikan sebagai: PHOTO STUDIO (berdasarkan label FEATURED)")
            success_urls = process_photo_studio(blogger_service, [url])
        elif is_notsync:
            print(f"📌 {url} diklasifikasikan sebagai: NOTSYNC (berdasarkan label NOTSYNC)")
            success_urls = process_notsync(blogger_service, [url])
        elif is_po:
            print(f"📌 {url} diklasifikasikan sebagai: PHOTO OWNER (berdasarkan label CONSIGNMENT_PO)")
            success_urls = process_photo_owner(blogger_service, [url])
        elif is_twp:
            print(f"📌 {url} diklasifikasikan sebagai: TWP (The Watch Project - berdasarkan label TWP)")
            success_urls = process_twp(blogger_service, [url])
        else:
            if sku.startswith("CPO"):
                print(f"📌 {url} diklasifikasikan sebagai: PHOTO OWNER (berdasarkan awalan SKU {sku})")
                success_urls = process_photo_owner(blogger_service, [url])
            else:
                print(f"⚠️ {url} tidak memiliki label format khusus (SKU '{sku}'). Akan diproses default sebagai PHOTO STUDIO.")
                success_urls = process_photo_studio(blogger_service, [url])

        if url in (success_urls or []):
            if sku:
                PROCESSED_SKUS.add(sku)
                save_processed_skus(PROCESSED_SKUS)
            return True
        else:
            print(f"❌ Upload produk gagal untuk {url}. Tidak akan dicatat sebagai processed agar bisa dicoba kembali.")
            return False

    except Exception as e:
        print(f"❌ Gagal mengklasifikasikan atau memproses {url}: {e}")
        return False

# ==========================================
# 9. OTOMASI YOUTUBE SHORTS & GOOGLE DRIVE QUEUE
# ==========================================

def format_youtube_title(raw_title, vendor="Unknown"):
    """
    Format judul YouTube:
    1. Hapus awalan [FOR SALE]
    2. Hapus nama brand/vendor di awal judul
    3. Batasi panjang total maks 100 karakter (tanpa tagar #shorts)
    """
    clean = re.sub(r'^\[?FOR\s+SALE\]?\s*', '', raw_title, flags=re.IGNORECASE).strip()

    if vendor and vendor != "Unknown":
        clean = re.sub(rf"^{re.escape(vendor)}\s+", "", clean, flags=re.IGNORECASE).strip()
    else:
        for keyword in sorted(DAFTAR_MEREK_IDWX.keys(), key=len, reverse=True):
            if clean.upper().startswith(keyword):
                clean = clean[len(keyword):].strip()
                break

    if len(clean) > 100:
        clean = clean[:97].strip() + "..."
    return clean

def extract_gdrive_folder_id(html_content):
    """Mengekstrak ID folder Google Drive dari link Assets di isi postingan."""
    match = re.search(r'drive\.google\.com/drive/(?:u/\d+/)?folders/([a-zA-Z0-9_-]+)', html_content)
    return match.group(1) if match else None

def check_drive_for_youtube_video(drive_service, parent_folder_id, subfolder_name=YOUTUBE_SUBFOLDER_NAME):
    """
    Mencari sub-folder bernama subfolder_name (case-insensitive) di dalam parent_folder_id,
    lalu mencari file video (.mp4, .mov, dll) di dalam subfolder tersebut.
    """
    try:
        query_folder = f"'{parent_folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        res_folder = drive_service.files().list(q=query_folder, fields="files(id, name)").execute()
        subfolders = res_folder.get('files', [])

        target_folder_id = None
        for sf in subfolders:
            if sf.get('name', '').strip().lower() == subfolder_name.lower():
                target_folder_id = sf.get('id')
                break

        if not target_folder_id:
            return None # Subfolder belum dibuat oleh videographer

        query_video = f"'{target_folder_id}' in parents and trashed = false"
        res_video = drive_service.files().list(q=query_video, fields="files(id, name, mimeType, size)").execute()
        files = res_video.get('files', [])

        for f in files:
            mime = f.get('mimeType', '').lower()
            name = f.get('name', '').lower()
            if 'video' in mime or name.endswith(('.mp4', '.mov', '.avi', '.m4v', '.webm')):
                return {
                    "file_id": f.get('id'),
                    "file_name": f.get('name'),
                    "mime_type": f.get('mimeType'),
                    "size": f.get('size'),
                    "folder_id": target_folder_id
                }
        return None # Subfolder ada tapi file video belum dimasukkan
    except Exception as e:
        print(f"   ⚠️ Error cek Google Drive ({parent_folder_id}): {e}")
        return None

def download_drive_file(drive_service, file_id, dest_path):
    """Download file dari Google Drive ke disk lokal secara bertahap."""
    request = drive_service.files().get_media(fileId=file_id)
    with io.FileIO(dest_path, 'wb') as fh:
        downloader = MediaIoBaseDownload(fh, request, chunksize=10*1024*1024)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                print(f"      ⬇️ Progress download video: {int(status.progress() * 100)}%")
    return True

def get_ffmpeg_path():
    """Mencari path binary ffmpeg yang valid dan dapat dieksekusi di OS saat ini (Mac/Linux)."""
    # 1. Cek system PATH terlebih dahulu (di Linux / PythonAnywhere biasanya /usr/bin/ffmpeg)
    sys_bin = shutil.which("ffmpeg")
    if sys_bin:
        try:
            subprocess.run([sys_bin, "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return sys_bin
        except Exception:
            pass

    # 2. Cek binary lokal bin/ffmpeg (misal di Mac lokal)
    local_bin = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin", "ffmpeg")
    if os.path.exists(local_bin) and os.access(local_bin, os.X_OK):
        try:
            subprocess.run([local_bin, "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return local_bin
        except Exception:
            pass

    # 3. Cek library imageio_ffmpeg jika tersedia
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass

    return None

def sync_audio_tracks_from_drive(drive_service):
    """Mengunduh file audio (.mp3) dari Google Drive folder jika lokal kosong."""
    os.makedirs(LOCAL_AUDIO_DIR, exist_ok=True)
    existing = [f for f in os.listdir(LOCAL_AUDIO_DIR) if f.lower().endswith(('.mp3', '.m4a', '.wav'))]
    if existing:
        return existing
    print(f"   🎵 Folder audio lokal kosong. Mengunduh daftar BGM dari Google Drive...")
    try:
        query = f"'{DRIVE_AUDIO_FOLDER_ID}' in parents and trashed = false"
        res = drive_service.files().list(q=query, fields="files(id, name, mimeType)").execute()
        files = res.get('files', [])
        for f in files:
            name = f.get('name')
            if name and name.lower().endswith(('.mp3', '.m4a', '.wav')):
                dest = os.path.join(LOCAL_AUDIO_DIR, name)
                print(f"      ⬇️ Mengunduh BGM: {name}...")
                download_drive_file(drive_service, f.get('id'), dest)
        return [f for f in os.listdir(LOCAL_AUDIO_DIR) if f.lower().endswith(('.mp3', '.m4a', '.wav'))]
    except Exception as e:
        print(f"   ⚠️ Gagal sinkronisasi audio dari Google Drive: {e}")
        return []

def get_random_audio_track(drive_service=None):
    """Memilih satu lagu BGM secara acak dari library audio lokal."""
    os.makedirs(LOCAL_AUDIO_DIR, exist_ok=True)
    audio_files = [
        os.path.join(LOCAL_AUDIO_DIR, f)
        for f in os.listdir(LOCAL_AUDIO_DIR)
        if f.lower().endswith(('.mp3', '.m4a', '.wav'))
    ]
    if not audio_files and drive_service:
        sync_audio_tracks_from_drive(drive_service)
        audio_files = [
            os.path.join(LOCAL_AUDIO_DIR, f)
            for f in os.listdir(LOCAL_AUDIO_DIR)
            if f.lower().endswith(('.mp3', '.m4a', '.wav'))
        ]
    if audio_files:
        return random.choice(audio_files)
    return None

def merge_audio_with_video(video_path, audio_path, output_path):
    """
    Menggabungkan video dengan audio BGM menggunakan ffmpeg.
    - Video di-copy tanpa encode ulang (-c:v copy) sehingga sangat cepat dan kualitas 100% terjaga.
    - Audio di-encode ke AAC kualitas tinggi (-c:a aac -b:a 192k).
    - Audio dipotong otomatis sesuai durasi video (-shortest).
    """
    ffmpeg_bin = get_ffmpeg_path()
    if not ffmpeg_bin:
        print("   ⚠️ Binary FFmpeg tidak ditemukan. Melewati penggabungan audio.")
        return False

    cmd = [
        ffmpeg_bin,
        "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-shortest",
        output_path
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except subprocess.CalledProcessError as e:
        print(f"   ⚠️ FFmpeg error: {e.stderr.decode('utf-8', errors='ignore')[:300]}")
        return False
    except Exception as e:
        print(f"   ⚠️ Gagal menggabungkan audio: {e}")
        return False

def upload_video_to_youtube(youtube_service, file_path, title, description=YOUTUBE_DESCRIPTION_TEMPLATE):
    """Unggah file video lokal ke YouTube sebagai Shorts Unlisted."""
    body = {
        'snippet': {
            'title': title,
            'description': description,
            'tags': ['idwx', 'jamtanganmewah', 'luxurywatch', 'shorts', 'youtubeshorts'],
            'categoryId': '26' # Howto & Style
        },
        'status': {
            'privacyStatus': 'unlisted',
            'selfDeclaredMadeForKids': False
        }
    }

    media = MediaFileUpload(file_path, chunksize=10*1024*1024, resumable=True)
    request = youtube_service.videos().insert(
        part=','.join(body.keys()),
        body=body,
        media_body=media
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"      ⬆️ Progress upload YouTube: {int(status.progress() * 100)}%")

    video_id = response.get('id')
    return video_id

def inject_youtube_embed_to_shopify(product_id, video_id):
    """
    Update body_html produk Shopify: mengganti placeholder video xxxx
    dengan embed player iframe YouTube Shorts aktif yang responsif.
    """
    ensure_shopify_token()
    get_url = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{API_VERSION}/products/{product_id}.json"
    res_get = requests.get(get_url, headers=HEADERS_SHOPIFY, timeout=30)
    if res_get.status_code != 200:
        print(f"   ⚠️ Gagal mengambil produk Shopify ID {product_id} (Status: {res_get.status_code})")
        return False

    current_body = res_get.json().get('product', {}).get('body_html', '') or ''

    youtube_iframe_html = f'''<div style="position: relative; padding-bottom: 56.25%; height: 0; overflow: hidden; max-width: 100%;">
<iframe src="https://www.youtube.com/embed/{video_id}?feature=share" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;" frameborder="0" allowfullscreen></iframe>
</div>'''

    placeholder_pattern = r'<!--\s*<div[^>]*>.*?https://www.youtube.com/embed/xxxx.*?</div>\s*-->'
    if re.search(placeholder_pattern, current_body, re.DOTALL):
        updated_body = re.sub(placeholder_pattern, youtube_iframe_html, current_body, flags=re.DOTALL)
    else:
        if f"youtube.com/embed/{video_id}" in current_body:
            print(f"   ℹ️ Video YouTube {video_id} sudah terpasang di Shopify ID {product_id}.")
            return True
        updated_body = current_body.strip() + "\n" + youtube_iframe_html

    update_payload = {
        "product": {
            "id": product_id,
            "body_html": updated_body
        }
    }
    put_url = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{API_VERSION}/products/{product_id}.json"
    res_put = requests.put(put_url, headers=HEADERS_SHOPIFY, json=update_payload, timeout=30)
    if res_put.status_code == 200:
        print(f"   🎉 Berhasil memasang embed YouTube ({video_id}) ke produk Shopify ID {product_id}!")
        return True
    else:
        print(f"   ⚠️ Gagal update embed YouTube di Shopify: {res_put.status_code} - {res_put.text}")
        return False

def load_youtube_queue():
    if not os.path.exists(QUEUE_FILE_PATH):
        return []
    try:
        with open(QUEUE_FILE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []

def save_youtube_queue(queue):
    try:
        with open(QUEUE_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(queue, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"   ⚠️ Gagal menyimpan {QUEUE_FILE_PATH}: {e}")

def add_to_youtube_queue(item_data):
    queue = load_youtube_queue()
    for q in queue:
        if q.get('shopify_product_id') == item_data.get('shopify_product_id'):
            return
        if q.get('post_url') and q.get('post_url') == item_data.get('post_url'):
            return
    queue.append(item_data)
    save_youtube_queue(queue)
    print(f"   📥 Ditambahkan ke antrean YouTube: '{item_data.get('yt_title')}' (Status: Menunggu video di Drive)")

def process_pending_youtube_queue():
    queue = load_youtube_queue()
    pending_items = [item for item in queue if item.get('status') == 'pending']

    if not pending_items:
        return

    print(f"\n🎬 Memeriksa {len(pending_items)} item di antrean video YouTube...")
    drive_service = None
    youtube_service = None

    temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_videos")
    os.makedirs(temp_dir, exist_ok=True)

    for item in pending_items:
        gdrive_folder_id = item.get('gdrive_folder_id')
        prod_id = item.get('shopify_product_id')
        yt_title = item.get('yt_title')

        if not gdrive_folder_id or not prod_id:
            item['status'] = 'invalid'
            continue

        print(f"   🔍 Cek folder Drive ({gdrive_folder_id}) untuk: {yt_title}")

        if drive_service is None:
            drive_service = get_drive_service()

        video_info = check_drive_for_youtube_video(drive_service, gdrive_folder_id)
        if not video_info:
            item['check_count'] = item.get('check_count', 0) + 1
            item['last_checked'] = datetime.now(WIB).strftime("%Y-%m-%d %H:%M:%S")
            print(f"      ⏳ Video di sub-folder '{YOUTUBE_SUBFOLDER_NAME}' belum tersedia. (Pengecekan ke-{item['check_count']})")
            continue

        file_id = video_info['file_id']
        file_name = video_info['file_name']
        print(f"      🎥 Video DITEMUKAN: {file_name} (ID: {file_id})")

        temp_file_path = os.path.join(temp_dir, f"{prod_id}_{file_name}")
        merged_file_path = os.path.join(temp_dir, f"{prod_id}_with_audio_{file_name}")
        upload_target_path = temp_file_path
        audio_name_used = None

        try:
            print(f"      ⬇️ Mendownload video dari Google Drive...")
            download_drive_file(drive_service, file_id, temp_file_path)

            # Pilih lagu BGM acak dan gabungkan ke video
            audio_track = get_random_audio_track(drive_service)
            if audio_track:
                audio_name_used = os.path.basename(audio_track)
                print(f"      🎵 Memilih BGM acak: '{audio_name_used}'")
                print(f"      🎬 Menggabungkan BGM ke video...")
                if merge_audio_with_video(temp_file_path, audio_track, merged_file_path):
                    print(f"      ✅ Audio berhasil digabungkan!")
                    upload_target_path = merged_file_path
                else:
                    print(f"      ⚠️ Gagal menggabungkan audio, mengunggah video asli...")
            else:
                print(f"      ℹ️ Tidak ada lagu BGM yang tersedia. Mengunggah video asli...")

            if youtube_service is None:
                youtube_service = get_youtube_service()

            print(f"      ⬆️ Mengunggah ke YouTube Shorts (Unlisted): '{yt_title}'...")
            video_id = upload_video_to_youtube(youtube_service, upload_target_path, yt_title)
            print(f"      🎉 Video berhasil terunggah ke YouTube! Video ID: {video_id}")

            print(f"      🔗 Memasang embed video ke Shopify Product ID {prod_id}...")
            inject_youtube_embed_to_shopify(prod_id, video_id)

            item['status'] = 'completed'
            item['youtube_video_id'] = video_id
            item['youtube_url'] = f"https://youtu.be/{video_id}"
            if audio_name_used:
                item['bgm_track'] = audio_name_used
            item['completed_at'] = datetime.now(WIB).strftime("%Y-%m-%d %H:%M:%S")
            save_youtube_queue(queue)
            print(f"      ✅ Selesai! Antrean untuk '{yt_title}' ditandai COMPLETED.")

        except Exception as e:
            print(f"      ❌ Error saat memproses video {file_name}: {e}")
            item['last_error'] = str(e)
        finally:
            for p in [temp_file_path, merged_file_path]:
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass

    save_youtube_queue(queue)

# ==========================================
# 10. PROGRAM UTAMA
# ==========================================
if __name__ == "__main__":
    print("="*50)
    print("🚀 MEMULAI OTOMASI UPLOAD IDWX (MODE CONTINUOUS)")
    print("="*50)

    blogger_service = get_blogger_service()
    print("\nMemasuki mode monitoring otomatis setiap 5 menit...")

    while True:
        try:
            # Re-inisialisasi koneksi Blogger setiap putaran agar tidak terjadi Broken Pipe
            blogger_service = get_blogger_service()

            # Pastikan token Shopify masih aktif (refresh otomatis sebelum 24 jam)
            ensure_shopify_token()

            # Pengecekan pergantian hari untuk resync data Shopify (SKU & Handle)
            current_date_str = datetime.now(WIB).strftime("%Y-%m-%d")
            if current_date_str != LAST_SYNC_DATE:
                print(f"\n🔄 Pergantian hari terdeteksi ({LAST_SYNC_DATE} -> {current_date_str}). Menyelaraskan ulang data Shopify...")
                ensure_shopify_metadata(force_resync=True)
                LAST_SYNC_DATE = current_date_str

            processed_urls = load_processed_urls()
            PROCESSED_SKUS = load_processed_skus()

            archive_url = get_todays_archive_url()
            print(f"\n[{datetime.now(WIB).strftime('%H:%M:%S')}] Mengecek: {archive_url} (Via API)")

            new_links = extract_post_links_via_api(blogger_service)

            links_to_process = [link for link in new_links if link not in processed_urls]

            if not links_to_process:
                print("Tidak ada postingan baru untuk diproses.")
            else:
                print(f"Menemukan {len(links_to_process)} postingan baru! Mulai memproses...")
                for link in links_to_process:
                    success = classify_and_process_url(blogger_service, link)
                    if success:
                        processed_urls.add(link)
                        save_processed_urls(processed_urls)

            # Cek dan proses antrean video YouTube yang tertunda
            try:
                process_pending_youtube_queue()
            except Exception as e:
                print(f"⚠️ Error saat memproses antrean YouTube: {e}")

            print("Menunggu 5 menit sebelum pengecekan berikutnya...")
            time.sleep(300)

        except KeyboardInterrupt:
            print("\nProgram dihentikan oleh user.")
            break
        except Exception as e:
            print(f"⚠️ Terjadi kesalahan pada loop utama: {e}")
            time.sleep(60)