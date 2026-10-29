import os
import re
import json
import requests
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

app = Flask(__name__)

# Zona Waktu Indonesia Barat (WIB)
WIB = timezone(timedelta(hours=7))

# ==============================================================================
# 1. LOAD ENVIRONMENT VARIABLES (.env)
# ==============================================================================
def load_env_file():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip("\"'")
                    if key and key not in os.environ:
                        os.environ[key] = value

load_env_file()

# Kredensial Google OAuth (Blogger API)
GCP_CLIENT_ID = os.getenv("GCP_CLIENT_ID", "")
GCP_CLIENT_SECRET = os.getenv("GCP_CLIENT_SECRET", "")
GCP_REFRESH_TOKEN = os.getenv("GCP_REFRESH_TOKEN", "")
BLOG_ID = os.getenv("BLOG_ID", "")

# Kredensial Shopify
SHOPIFY_STORE_NAME = os.getenv("SHOPIFY_STORE_NAME", "idwx")
SHOPIFY_CLIENT_ID = os.getenv("SHOPIFY_CLIENT_ID", "")
SHOPIFY_CLIENT_SECRET = os.getenv("SHOPIFY_CLIENT_SECRET", "")
API_VERSION = "2025-01"

# Webhooks Google Apps Script
# 1. Spreadsheet History Foto Studio (Pencatatan Jam Baru / Draft WA)
APPS_SCRIPT_HISTORY_URL = "https://script.google.com/macros/s/AKfycbxCEcepLLaNouGEmxMJPCFj3vTbWjH41_BFD7tFsYuEkL7h1tV_io3xZBPDSiRC_sgQ/exec"
# 2. Spreadsheet Consignment Listing Photo Studio (Reprice Tracking)
APPS_SCRIPT_CONSIGNMENT_URL = "https://script.google.com/macros/s/AKfycbw-PV4bR4PhgJyjPvY_dHnz54fhmzEvSOIJJCDyyWOASeaBMcdOkcMxpftXfTHcqPf2/exec"

# Green-API (WhatsApp Bot)
GREEN_API_ID_INSTANCE = os.getenv("GREEN_API_ID_INSTANCE", "")
GREEN_API_API_TOKEN = os.getenv("GREEN_API_API_TOKEN", "")
TARGET_GROUP_ID = os.getenv("TARGET_GROUP_ID", "")

# Cache Token Shopify
SHOPIFY_ACCESS_TOKEN = None

# ==============================================================================
# 2. HELPER FUNCTIONS: PARSING & FORMATTING
# ==============================================================================
def parse_price(price_str):
    """
    Mengubah format harga string menjadi float angka:
    Contoh: '92.000.000' -> 92000000.0, '92jt' -> 92000000.0, 'Rp 92.000.000' -> 92000000.0
    """
    clean_lower = price_str.lower().strip()
    if 'jt' in clean_lower:
        m = re.search(r'([\d,\.]+)\s*jt', clean_lower)
        if m:
            val_str = m.group(1).replace('.', '').replace(',', '.')
            try:
                return float(val_str) * 1_000_000
            except ValueError:
                pass

    numeric_str = re.sub(r'[^\d]', '', price_str)
    if numeric_str:
        return float(numeric_str)
    return 0.0

def format_rupiah(num):
    return f"Rp {int(num):,}".replace(",", ".")

def parse_reprice_chat(message_text):
    """
    Memvalidasi dan mengekstrak perintah chat:
    1. REPRICE / [KODE] / [HARGA]
    2. HARGA BARU / [KODE] / [HARGA]
    Mendukung SKU yang mengandung karakter garis miring (misal Patek Philippe: 5720232/4642909).
    """
    if not message_text or "/" not in message_text:
        return None

    # Cara 1: Coba split dengan pemisah ' / ' (garis miring berpagar spasi)
    spaced_parts = [p.strip() for p in re.split(r'\s+/\s+', message_text.strip()) if p.strip()]
    if len(spaced_parts) >= 3:
        cmd = spaced_parts[0].upper().strip()
        if cmd in ["REPRICE", "HARGA BARU", "HARGA_BARU"]:
            raw_price = spaced_parts[-1].strip()
            code = " / ".join(spaced_parts[1:-1]).strip()
            numeric_price = parse_price(raw_price)
            if numeric_price > 0:
                cmd_type = "REPRICE" if cmd == "REPRICE" else "HARGA_BARU"
                return {
                    "command_type": cmd_type,
                    "code": code,
                    "raw_price": raw_price,
                    "numeric_price": numeric_price,
                    "formatted_price": format_rupiah(numeric_price)
                }

    # Cara 2: Split standar dengan '/' jika user tidak memakai spasi di sekitar slash
    # Elemen pertama adalah command, elemen terakhir adalah harga, semua elemen di tengah adalah SKU
    parts = [p.strip() for p in message_text.split('/') if p.strip()]
    if len(parts) < 3:
        return None

    cmd = parts[0].upper().strip()
    if cmd not in ["REPRICE", "HARGA BARU", "HARGA_BARU"]:
        return None

    raw_price = parts[-1].strip()
    numeric_price = parse_price(raw_price)
    if numeric_price <= 0:
        return None

    code = "/".join(parts[1:-1]).strip()
    cmd_type = "REPRICE" if cmd == "REPRICE" else "HARGA_BARU"

    return {
        "command_type": cmd_type,
        "code": code,
        "raw_price": raw_price,
        "numeric_price": numeric_price,
        "formatted_price": format_rupiah(numeric_price)
    }

def format_tanggal_indonesia():
    hari = ["Minggu", "Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu"]
    bulan = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni", 
             "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
    now = datetime.now(WIB)
    nama_hari = hari[int(now.strftime("%w"))]
    tgl = now.day
    nama_bulan = bulan[now.month]
    tahun = now.year
    return f"{nama_hari}, {tgl} {nama_bulan} {tahun}"

def is_valid_foto_studio_caption(caption, image_url):
    """
    Memvalidasi apakah pesan adalah input jam baru Foto Studio:
    1. WAJIB melampirkan foto/gambar (image_url harus ada).
    2. Menghapus URL/link sebelum memeriksa garis miring pemisah (agar URL tidak disangka format jam).
    3. Setelah URL dihapus, harus ada pemisah '/' dengan minimal 2 bagian (contoh: [Nama Jam] / [SN / Owner]).
    4. Nama produk (bagian pertama) tidak boleh berisikan kata-kata obrolan, meeting, briefing, pengumuman, dll.
    """
    if not image_url or not caption:
        return False

    # Hapus URL dari caption agar karakter '/' di http://, https://, link meet dll tidak dihitung
    clean_text = re.sub(r'https?://\S+', '', caption).strip()
    if not clean_text or "/" not in clean_text:
        return False

    # Filter kata-kata obrolan / meeting / pengumuman yang jelas bukan jam tangan
    ignored_keywords = [
        "meeting", "briefing", "google meet", "zoom", "teams", "selamat pagi", "selamat siang",
        "selamat sore", "selamat malam", "terima kasih", "thank you", "jadwal", "agenda",
        "video call", "joining info", "time zone", "reminder"
    ]
    lower_text = clean_text.lower()
    for kw in ignored_keywords:
        if kw in lower_text:
            return False

    # Split berdasarkan '/'
    parts = [p.strip() for p in clean_text.split('/') if p.strip()]
    if len(parts) < 2:
        return False

    # Bagian pertama adalah nama jam/model: tidak boleh terlalu panjang seperti paragraf (> 80 karakter)
    if len(parts[0]) > 80:
        return False

    return True

def ekstraksi_serial_number(caption):
    """
    Mengekstrak Serial Number jam tangan dari caption.
    Aturan:
    - Bersihkan link / URL terlebih dahulu
    - Abaikan kata keterangan umum (box, pinjem, pak, omni, dll)
    - Abaikan bulan / tahun
    - Serial number wajib memuat setidaknya satu digit/angka (anti nama orang/staf/domain)
    """
    clean_caption = re.sub(r'https?://\S+', '', caption).strip()
    parts = [p.strip() for p in clean_caption.split('/') if p.strip()]
    if not parts:
        return "INPUT-MANUAL"

    for part in parts:
        clean = part.strip()
        if re.search(r'\b(pinjem|box|pak|omni|pt|dial|satin|jubilee|besi|gold)\b', clean, re.IGNORECASE):
            continue
        if re.search(r'\b(jan|feb|mar|apr|may|mei|jun|jul|aug|agu|sep|oct|okt|nov|dec|des)\b|\b(19\d{2}|20\d{2})\b', clean, re.IGNORECASE):
            continue
        # Harus memuat angka (anti nama orang/staf) dan panjang 2-24 karakter
        if re.match(r'^[A-Z0-9\/-]{2,24}$', clean, re.IGNORECASE) and re.search(r'\d', clean):
            return clean.upper()

    if len(parts) >= 3:
        cand = parts[2].strip()
        if not re.search(r'\b(19\d{2}|20\d{2})\b', cand) and re.search(r'\d', cand):
            return cand.upper()

    return "INPUT-MANUAL"

def kirim_balasan_wa(chat_id, pesan_text):
    if not GREEN_API_ID_INSTANCE or not GREEN_API_API_TOKEN or "xxxx" in GREEN_API_ID_INSTANCE:
        return
    try:
        url = f"https://api.green-api.com/waInstance{GREEN_API_ID_INSTANCE}/sendMessage/{GREEN_API_API_TOKEN}"
        payload = {"chatId": chat_id, "message": pesan_text}
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"⚠️ Gagal kirim balasan WA: {e}")

# ==============================================================================
# 3. BLOGGER SERVICE & REPRICE LOGIC
# ==============================================================================
def get_blogger_service():
    if not GCP_REFRESH_TOKEN or not GCP_CLIENT_ID or not GCP_CLIENT_SECRET:
        return None
    creds = Credentials(
        token=None,
        refresh_token=GCP_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GCP_CLIENT_ID,
        client_secret=GCP_CLIENT_SECRET
    )
    return build('blogger', 'v3', credentials=creds)

def clean_sku_string(sku_str):
    """
    Membersihkan string SKU dari input WhatsApp:
    - Membuang teks di dalam kurung: misal '1Y53F376 (Omniluxe)' -> '1Y53F376'
    - Menghapus spasi dan tanda baca berlebih di ujung
    """
    if not sku_str:
        return ""
    cleaned = re.sub(r'\(.*?\)', '', str(sku_str))
    return cleaned.strip(" \t\n\r.,-")

def extract_sku_from_blogger_post(post):
    """Mengekstrak base SKU dan nama owner dari isi postingan Blogspot jika ada."""
    if not post:
        return None, None
    content = post.get("content", "")
    sku_match = re.search(r'Code:\s*([\w\-\/]+)', content, re.IGNORECASE)
    sku = sku_match.group(1).strip() if sku_match else None
    owner_match = re.search(r'Code:\s*[\w\-\/]+\s*\((.*?)\)', content, re.IGNORECASE)
    owner = owner_match.group(1).strip() if owner_match else None
    return sku, owner

def find_blogger_post_by_code(service, code):
    if not service or not BLOG_ID or not code:
        return None
    clean_code = clean_sku_string(code)
    base_code = re.sub(r'-\d+$', '', clean_code)

    search_candidates = [clean_code]
    if base_code and base_code != clean_code:
        search_candidates.append(base_code)
    if "/" in clean_code:
        for sp in clean_code.split('/'):
            sp_clean = sp.strip()
            if sp_clean and sp_clean not in search_candidates:
                search_candidates.append(sp_clean)
    if code.strip() not in search_candidates:
        search_candidates.append(code.strip())

    for cand in search_candidates:
        try:
            res = service.posts().search(blogId=BLOG_ID, q=cand).execute()
            items = res.get("items", [])
            for item in items:
                content = item.get("content", "")
                title = item.get("title", "")
                if cand.upper() in content.upper() or cand.upper() in title.upper():
                    return item
            if items:
                return items[0]
        except Exception as e:
            print(f"⚠️ Error search Blogger post ({cand}): {e}")
    return None

def format_published_date(published_str):
    """Mengubah format ISO published date Blogger menjadi string '24 Aug 2026'."""
    if not published_str:
        return ""
    months_en = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    try:
        clean_str = published_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_str)
        if dt.tzinfo:
            dt = dt.astimezone(WIB)
        return f"{dt.day} {months_en[dt.month]} {dt.year}"
    except Exception:
        m = re.match(r'^(\d{4})-(\d{2})-(\d{2})', published_str)
        if m:
            yr, mo, da = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return f"{da} {months_en[mo]} {yr}"
        return ""

def update_blogger_reprice(service, post, command_type, formatted_price):
    try:
        post_id = post["id"]
        current_html = post.get("content", "")
        current_labels = post.get("labels", [])

        # Ambil tanggal terakhir postingan sebelum update dilakukan
        original_published_str = post.get("published", "")
        formatted_prev_date = format_published_date(original_published_str)

        # Cek apakah postingan SUDAH memiliki tag/label REPRICE atau REPOST
        has_reprice_or_repost = any(l.strip().upper() in ["REPRICE", "REPOST"] for l in current_labels)

        # 1. Update Labels: Hapus NEW ARRIVAL, Tambahkan REPRICE
        new_labels = [l for l in current_labels if l.strip().upper() != "NEW ARRIVAL"]
        if not any(l.strip().upper() == "REPRICE" for l in new_labels):
            new_labels.append("REPRICE")

        is_consign_ps = any("CONSIGNMENT_PS" in l.upper() or "CONSINGMENT_PS" in l.upper() for l in current_labels)

        # 2. Update HTML Konten (Harga)
        price_pattern = r'(Price\s*:\s*)(.*?)(?=<br|</p|</div>|\n|$)'
        reprice_pattern = r'(?:<br\s*/?>|\n)?\s*Reprice\s*:\s*<b>.*?</b>'

        updated_html = current_html

        if command_type == "REPRICE":
            m = re.search(price_pattern, updated_html, re.IGNORECASE)
            old_price_text = ""
            if m:
                raw_val = m.group(2)
                if "<strike>" not in raw_val.lower() and "<s>" not in raw_val.lower():
                    old_price_text = raw_val.strip()
                else:
                    strike_m = re.search(r'<(?:strike|s)>(.*?)</(?:strike|s)>', raw_val, re.IGNORECASE)
                    if strike_m:
                        old_price_text = strike_m.group(1).strip()

            updated_html = re.sub(reprice_pattern, '', updated_html, flags=re.IGNORECASE)

            if m:
                if old_price_text:
                    replacement = f"Price: <strike>{old_price_text}</strike><br/>Reprice: <b>{formatted_price}</b>"
                else:
                    replacement = f"Price: <strike>{formatted_price}</strike><br/>Reprice: <b>{formatted_price}</b>"
                updated_html = re.sub(price_pattern, replacement, updated_html, count=1, flags=re.IGNORECASE)
            else:
                updated_html += f"<br/>Price: <strike>{formatted_price}</strike><br/>Reprice: <b>{formatted_price}</b>"

        else: # HARGA_BARU
            updated_html = re.sub(reprice_pattern, '', updated_html, flags=re.IGNORECASE)
            replacement = f"Price: {formatted_price}"
            if re.search(price_pattern, updated_html, re.IGNORECASE):
                updated_html = re.sub(price_pattern, replacement, updated_html, count=1, flags=re.IGNORECASE)
            else:
                updated_html += f"<br/>Price: {formatted_price}"

        # 2b. Update / Tambahkan 'Last Post: [tanggal sebelum update]' jika sudah REPRICE atau REPOST
        if (has_reprice_or_repost or re.search(r'Last\s*Post\s*:', updated_html, re.IGNORECASE)) and formatted_prev_date:
            last_post_regex = r'((?:<b>)?Last\s*Post\s*:\s*(?:</b>)?\s*)([^\n<]+)'
            if re.search(last_post_regex, updated_html, re.IGNORECASE):
                updated_html = re.sub(last_post_regex, fr'\g<1>{formatted_prev_date}', updated_html, count=1, flags=re.IGNORECASE)
                print(f"   📅 Mengubah 'Last Post' menjadi tanggal sebelum update: {formatted_prev_date}")
            else:
                # Sisipkan tepat setelah baris Code:
                if re.search(r'((?:<b>)?Code\s*:\s*(?:</b>)?\s*[^\n<]+)', updated_html, re.IGNORECASE):
                    updated_html = re.sub(
                        r'((?:<b>)?Code\s*:\s*(?:</b>)?\s*[^\n<]+)',
                        fr'\g<1><br/>Last Post: {formatted_prev_date}',
                        updated_html,
                        count=1,
                        flags=re.IGNORECASE
                    )
                elif re.search(r'((?:<b>)?Assets\s*:\s*)', updated_html, re.IGNORECASE):
                    updated_html = re.sub(
                        r'((?:<b>)?Assets\s*:\s*)',
                        fr'Last Post: {formatted_prev_date}<br/>\g<1>',
                        updated_html,
                        count=1,
                        flags=re.IGNORECASE
                    )
                else:
                    updated_html += f"<br/>Last Post: {formatted_prev_date}"
                print(f"   📅 Menambahkan 'Last Post: {formatted_prev_date}' ke postingan.")

        # 3. Patch ke Blogger API (Setel Tanggal Dipublikasikan ke 'Otomatis' / Waktu Sekarang)
        now_wib = datetime.now(WIB)
        published_timestamp = now_wib.strftime("%Y-%m-%dT%H:%M:%S+07:00")

        patch_body = {
            "content": updated_html,
            "labels": new_labels,
            "published": published_timestamp
        }
        res = service.posts().patch(blogId=BLOG_ID, postId=post_id, body=patch_body).execute()
        return {
            "status": "success",
            "post_title": res.get("title", ""),
            "is_consign_ps": is_consign_ps,
            "labels": res.get("labels", []),
            "published": res.get("published", "")
        }
    except Exception as e:
        print(f"⚠️ Error update Blogger post: {e}")
        return {"status": "error", "message": str(e), "is_consign_ps": False}

# ==============================================================================
# 4. SHOPIFY GRAPHQL REPRICE LOGIC
# ==============================================================================
def get_shopify_token():
    global SHOPIFY_ACCESS_TOKEN
    if SHOPIFY_ACCESS_TOKEN:
        return SHOPIFY_ACCESS_TOKEN
    try:
        tok_res = requests.post(
            f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/oauth/access_token",
            data={
                "grant_type": "client_credentials",
                "client_id": SHOPIFY_CLIENT_ID,
                "client_secret": SHOPIFY_CLIENT_SECRET
            },
            timeout=30
        )
        if tok_res.status_code == 200:
            SHOPIFY_ACCESS_TOKEN = tok_res.json().get("access_token")
            return SHOPIFY_ACCESS_TOKEN
    except Exception as e:
        print(f"⚠️ Error get Shopify token: {e}")
    return None

def update_shopify_reprice(sku, command_type, numeric_price, blogger_post=None):
    token = get_shopify_token()
    if not token:
        return {"status": "error", "message": "Gagal mendapatkan access token Shopify"}

    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
    graphql_url = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{API_VERSION}/graphql.json"

    # 1. Bangun daftar kandidat query SKU untuk pencarian bertingkat (Waterfall Search)
    clean_input_sku = clean_sku_string(sku)
    base_input_sku = re.sub(r'-\d+$', '', clean_input_sku)
    canonical_sku, _ = extract_sku_from_blogger_post(blogger_post) if blogger_post else (None, None)

    search_queries = []
    if clean_input_sku:
        search_queries.append(f"sku:{clean_input_sku}")
        search_queries.append(f"sku:{clean_input_sku}*") # Wildcard (cocokkan varian bertanda -1, -2)
    if base_input_sku and base_input_sku != clean_input_sku:
        search_queries.append(f"sku:{base_input_sku}")
        search_queries.append(f"sku:{base_input_sku}*")
    if "/" in clean_input_sku:
        slash_parts = [p.strip() for p in clean_input_sku.split('/') if p.strip()]
        for sp in slash_parts:
            if f"sku:{sp}" not in search_queries:
                search_queries.append(f"sku:{sp}")
                search_queries.append(f"sku:{sp}*")
    if canonical_sku:
        clean_canonical = clean_sku_string(canonical_sku)
        if f"sku:{clean_canonical}" not in search_queries:
            search_queries.append(f"sku:{clean_canonical}")
            search_queries.append(f"sku:{clean_canonical}*")
    if clean_input_sku and clean_input_sku not in search_queries:
        search_queries.append(clean_input_sku)

    product_query = """
    query getProducts($query: String!) {
      products(first: 5, query: $query) {
        edges {
          node {
            id
            title
            variants(first: 10) {
              edges {
                node {
                  id
                  sku
                  price
                  compareAtPrice
                }
              }
            }
          }
        }
      }
    }
    """

    matched_product = None
    matched_variant = None
    matched_method = None

    # Coba pencarian bertingkat berdasarkan variasi SKU
    for q in search_queries:
        try:
            res = requests.post(graphql_url, headers=headers, json={"query": product_query, "variables": {"query": q}}, timeout=20)
            data = res.json()
            edges = data.get("data", {}).get("products", {}).get("edges", [])
            if not edges:
                continue

            # Cari varian yang paling cocok di antara hasil
            for p_edge in edges:
                p_node = p_edge["node"]
                for v_edge in p_node["variants"]["edges"]:
                    vn = v_edge["node"]
                    v_sku = vn.get("sku", "").strip().upper()
                    # Level A: Exact match
                    if v_sku == clean_input_sku.upper():
                        matched_product = p_node
                        matched_variant = vn
                        matched_method = "exact_sku"
                        break
                    # Level B: Canonical SKU match (dari Blogspot)
                    if canonical_sku and v_sku == canonical_sku.strip().upper():
                        matched_product = p_node
                        matched_variant = vn
                        matched_method = "canonical_sku"
                        break
                    # Level C: Base SKU match (buang counter -1, -2)
                    v_base = re.sub(r'-\d+$', '', v_sku)
                    if v_base and v_base == base_input_sku.upper():
                        matched_product = p_node
                        matched_variant = vn
                        matched_method = "base_sku"
                        break
                    # Level D: Normalized match (hapus simbol strip & spasi)
                    if re.sub(r'[^A-Z0-9]', '', v_sku) == re.sub(r'[^A-Z0-9]', '', clean_input_sku.upper()):
                        matched_product = p_node
                        matched_variant = vn
                        matched_method = "normalized_sku"
                        break
                    # Level E: Match slash parts (misal serial ganda movement/case)
                    if "/" in clean_input_sku or "/" in v_sku:
                        input_parts = [p.strip().upper() for p in clean_input_sku.split('/') if p.strip()]
                        v_parts = [p.strip().upper() for p in v_sku.split('/') if p.strip()]
                        if any(ip in v_parts or ip == v_sku for ip in input_parts) or any(vp in input_parts or vp == clean_input_sku.upper() for vp in v_parts):
                            matched_product = p_node
                            matched_variant = vn
                            matched_method = "slash_part_sku"
                            break

                if matched_variant:
                    break

            # Jika belum terpilih varian spesifik tapi ada produk dari query SKU, gunakan varian produk pertama
            if not matched_variant and edges:
                matched_product = edges[0]["node"]
                matched_variant = matched_product["variants"]["edges"][0]["node"]
                matched_method = "wildcard_fallback"

            if matched_variant:
                break
        except Exception as e:
            print(f"⚠️ Error search Shopify with query '{q}': {e}")

    # Level 4 Fallback: Cross-Reference Judul dari Blogspot jika via SKU masih belum ketemu
    if not matched_variant and blogger_post:
        post_title = blogger_post.get("title", "")
        clean_title = re.sub(r'\[.*?\]', '', post_title).strip()
        search_title = re.sub(r'\s*\(\d{4}\)', '', clean_title).strip()
        if search_title:
            print(f"🔄 SKU '{sku}' tidak ditemukan langsung di Shopify. Mencoba Cross-Reference Judul Blogspot: '{search_title}'...")
            try:
                t_query = f"title:\"{search_title}\""
                res = requests.post(graphql_url, headers=headers, json={"query": product_query, "variables": {"query": t_query}}, timeout=20)
                data = res.json()
                edges = data.get("data", {}).get("products", {}).get("edges", [])
                if edges:
                    matched_product = edges[0]["node"]
                    matched_variant = matched_product["variants"]["edges"][0]["node"]
                    matched_method = "blogger_title_crossref"
                    print(f"🎯 Berhasil menemukan produk via Judul Blogspot: '{matched_product['title']}' (SKU: {matched_variant.get('sku')})")
            except Exception as e:
                print(f"⚠️ Error search Shopify via title: {e}")

    if not matched_variant or not matched_product:
        return {"status": "not_found", "message": f"Produk dengan SKU '{sku}' tidak ditemukan di Shopify (sudah dicoba variasi SKU & cross-reference)."}

    variant_id = matched_variant["id"]
    current_price = float(matched_variant.get("price") or 0)
    current_compare = matched_variant.get("compareAtPrice")
    actual_sku = matched_variant.get("sku", "")

    # 2. Tentukan price & compareAtPrice
    if command_type == "REPRICE":
        if current_compare is None or float(current_compare) == 0:
            compare_at_val = f"{current_price:.2f}"
        else:
            compare_at_val = current_compare
        price_val = f"{float(numeric_price):.2f}"
    else: # HARGA_BARU
        compare_at_val = None
        price_val = f"{float(numeric_price):.2f}"


    # 3. Update harga varian ke Shopify via Admin REST API (Akurat, Langsung, dan Bebas Masalah Versi GraphQL)
    numeric_variant_id = variant_id.split('/')[-1]
    rest_variant_url = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{API_VERSION}/variants/{numeric_variant_id}.json"

    variant_payload = {
        "variant": {
            "id": int(numeric_variant_id),
            "price": price_val,
            "compare_at_price": compare_at_val
        }
    }
    try:
        put_res = requests.put(rest_variant_url, headers=headers, json=variant_payload, timeout=30)
        if put_res.status_code == 200:
            res_variant = put_res.json().get("variant", {})
            updated_price = float(res_variant.get("price") or price_val)
            updated_compare = res_variant.get("compare_at_price")
            print(f"✅ Berhasil update harga Shopify: {matched_product['title']} (SKU: {actual_sku}, Price: {updated_price}, Compare: {updated_compare}, Method: {matched_method})")
            return {
                "status": "success",
                "product_title": matched_product["title"],
                "matched_sku": actual_sku,
                "method": matched_method,
                "new_price": updated_price,
                "compare_at_price": updated_compare
            }
        else:
            print(f"⚠️ Gagal update harga Shopify (HTTP {put_res.status_code}): {put_res.text}")
            return {"status": "error", "message": f"Shopify HTTP {put_res.status_code}: {put_res.text}"}
    except Exception as e:
        print(f"⚠️ Error update Shopify price: {e}")
        return {"status": "error", "message": str(e)}

# ==============================================================================
# 5. GOOGLE SPREADSHEET REPRICE LOGIC (PHOTO STUDIO - CONSIGNMENT PS)
# ==============================================================================
def update_consignment_ps_sheet(sku, command_type, formatted_price, numeric_price):
    """
    Mengirim perintah update ke Google Apps Script Spreadsheet Consignment Listing Photo Studio.
    Kriteria:
    - Tab: PHOTO STUDIO
    - Kolom A (Status) harus Available / Reprice
    - Kolom C (Serial Number) = SKU
    - Kolom M (2ND), N (3RD), O (4TH) dicek berurutan mana yang belum dicentang
    - Kolom G (Notes) ditambahkan: REPRICE [harga] [DD/MM/YY]
    """
    now_wib = datetime.now(WIB)
    date_str = now_wib.strftime("%d/%m/%y") # Format DD/MM/YY (contoh: 27/10/26)

    notes_text = f"REPRICE {formatted_price} ({date_str})" if command_type == "REPRICE" else f"HARGA BARU {formatted_price} ({date_str})"

    payload = {
        "action": "reprice_photo_studio",
        "sheet_name": "PHOTO STUDIO",
        "sku": sku,
        "command_type": command_type,
        "formatted_price": formatted_price,
        "numeric_price": numeric_price,
        "date_str": date_str,
        "notes_text": notes_text
    }

    try:
        res = requests.post(APPS_SCRIPT_CONSIGNMENT_URL, json=payload, timeout=25)
        if res.status_code == 200:
            return res.json()
        else:
            return {"status": "error", "message": f"HTTP status {res.status_code}"}
    except Exception as e:
        print(f"⚠️ Error Webhook Sheets Consignment: {e}")
        return {"status": "error", "message": str(e)}

# ==============================================================================
# 6. ROUTE ENDPOINTS
# ==============================================================================
@app.route('/', methods=['GET'])
def home():
    return "✅ WhatsApp Webhook & Reprice Bot IDWX is RUNNING!", 200

@app.route('/wa-webhook', methods=['POST'])
def wa_webhook():
    try:
        payload = request.get_json(force=True) or {}

        sender_data = payload.get("senderData", {})
        chat_id = sender_data.get("chatId", "")
        sender_name = sender_data.get("senderName") or sender_data.get("senderContactName") or "Staff"

        print(f"📡 Event Chat ID: {chat_id} dari: {sender_name}")
        allowed_targets = [g.strip().lower() for g in TARGET_GROUP_ID.split(",") if g.strip()]
        if allowed_targets and chat_id.strip().lower() not in allowed_targets:
            print(f"⏭️ Diabaikan: Chat berasal dari {chat_id}, bukan target terdaftar ({allowed_targets}).")
            return jsonify({"status": "ignored", "reason": "Not target group/chat"}), 200

        message_data = payload.get("messageData", {})
        type_msg = message_data.get("typeMessage", "")

        caption = ""
        image_url = ""

        if type_msg == "imageMessage":
            file_data = message_data.get("fileMessageData", {})
            caption = file_data.get("caption", "").strip()
            image_url = file_data.get("downloadUrl", "").strip()
        elif type_msg == "textMessage":
            caption = message_data.get("textMessageData", {}).get("textMessage", "").strip()
        elif type_msg == "extendedTextMessage":
            caption = message_data.get("extendedTextMessageData", {}).get("text", "").strip()
        else:
            return jsonify({"status": "ignored", "reason": "Unsupported message type"}), 200

        if not caption:
            return jsonify({"status": "ignored", "reason": "Empty message"}), 200

        # ======================================================================
        # JALUR A: PERINTAH REPRICE / HARGA BARU
        # ======================================================================
        reprice_cmd = parse_reprice_chat(caption)
        if reprice_cmd:
            sku = reprice_cmd["code"]
            cmd_type = reprice_cmd["command_type"]
            formatted_price = reprice_cmd["formatted_price"]
            numeric_price = reprice_cmd["numeric_price"]

            print(f"⚡ Menerima Perintah {cmd_type} untuk SKU: '{sku}' dengan harga: {formatted_price}")

            # 1. Update Blogspot
            blogger_res = {"status": "skipped", "message": "Blogger service not configured"}
            is_consign_ps = False
            service = get_blogger_service()
            post = None
            if service:
                post = find_blogger_post_by_code(service, sku)
                if post:
                    blogger_res = update_blogger_reprice(service, post, cmd_type, formatted_price)
                    is_consign_ps = blogger_res.get("is_consign_ps", False)
                else:
                    blogger_res = {"status": "not_found", "message": f"Postingan dengan kode {sku} tidak ditemukan di Blogspot."}

            # 2. Update Shopify (dengan Multi-Level Smart Matching & Fallback Post Blogspot)
            shopify_res = update_shopify_reprice(sku, cmd_type, numeric_price, blogger_post=post)

            # 3. Update Google Spreadsheet Consignment (HANYA jika CONSIGNMENT_PS)
            sheet_res = {"status": "skipped", "message": "Bukan CONSIGNMENT_PS (diabaikan)"}
            if is_consign_ps:
                # Gunakan SKU kanonik dari Shopify atau Blogspot jika ada
                canonical_sku = shopify_res.get("matched_sku") or (extract_sku_from_blogger_post(post)[0] if post else None) or clean_sku_string(sku)
                print(f"📌 Produk '{canonical_sku}' memiliki label CONSIGNMENT_PS. Memperbarui Google Spreadsheet Consignment...")
                sheet_res = update_consignment_ps_sheet(canonical_sku, cmd_type, formatted_price, numeric_price)
            else:
                print(f"ℹ️ Produk '{sku}' BUKAN CONSIGNMENT_PS. Google Spreadsheet dilewati sesuai aturan.")

            # 4. Kirim Balasan Laporan Lengkap ke WhatsApp
            status_blog_icon = "✅" if blogger_res.get("status") == "success" else "⚠️"
            status_shop_icon = "✅" if shopify_res.get("status") == "success" else "⚠️"
            status_sheet_icon = "✅" if sheet_res.get("status") == "success" else ("⏭️" if sheet_res.get("status") == "skipped" else "⚠️")

            sku_display = sku
            if shopify_res.get("matched_sku") and shopify_res.get("matched_sku").upper() != clean_sku_string(sku).upper():
                sku_display += f" _(Shopify: {shopify_res.get('matched_sku')})_"

            pesan_konfirmasi = (
                f"🏷️ *LAPORAN {cmd_type} IDWX*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🔢 *Kode / SKU:* {sku_display}\n"
                f"💰 *Harga Baru:* {formatted_price}\n"
                f"👤 *Diupdate oleh:* {sender_name}\n\n"
                f"{status_blog_icon} *Blogspot:* {blogger_res.get('post_title', blogger_res.get('message', 'Sukses'))}\n"
                f"{status_shop_icon} *Shopify:* {shopify_res.get('product_title', shopify_res.get('message', 'Sukses'))}\n"
                f"{status_sheet_icon} *Spreadsheet (Consignment):* "
            )
            if sheet_res.get("status") == "success":
                pesan_konfirmasi += f"Tercatat di baris {sheet_res.get('row', '-')} ({sheet_res.get('tracking_checked', '')})"
            elif sheet_res.get("status") == "skipped":
                pesan_konfirmasi += "Dilewati (Bukan tag CONSIGNMENT_PS)"
            else:
                pesan_konfirmasi += f"{sheet_res.get('message', 'Gagal')}"

            kirim_balasan_wa(chat_id, pesan_konfirmasi)

            return jsonify({
                "status": "success",
                "command": cmd_type,
                "sku": sku,
                "blogger": blogger_res,
                "shopify": shopify_res,
                "spreadsheet": sheet_res
            }), 200

        # ======================================================================
        # JALUR B: INPUT DRAFT JAM BARU (FOTO STUDIO WA)
        # ======================================================================
        # Validasi ketat: Wajib melampirkan foto & format caption jam tangan valid
        if not is_valid_foto_studio_caption(caption, image_url):
            print(f"⏭️ Diabaikan: Pesan bukan perintah REPRICE dan bukan format foto studio jam baru yang valid.")
            return jsonify({"status": "ignored", "reason": "Not recognized as reprice or valid photo studio submission"}), 200

        serial_number = ekstraksi_serial_number(caption)
        tanggal_hari_ini = format_tanggal_indonesia()
        catatan_notes = f"Diinput oleh: {sender_name}"

        payload_sheets = {
            "action": "insert_draft",
            "tanggal": tanggal_hari_ini,
            "image_url": image_url,
            "name_in_creative": caption,
            "serial_number": serial_number,
            "status": "On Draft",
            "notes": catatan_notes
        }

        res_sheets = requests.post(APPS_SCRIPT_HISTORY_URL, json=payload_sheets, timeout=20)
        res_data = res_sheets.json() if res_sheets.status_code == 200 else {}

        # Mode Hening (Silent Mode): Tidak mengirim balasan WA ke grup untuk input jam baru
        print(f"✅ Data jam baru ({serial_number}) berhasil masuk ke History Foto Studio (Silent Mode)")
        return jsonify({"status": "success", "sheets_response": res_data}), 200

    except Exception as e:
        print(f"❌ Error Webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
