import os
import re
import json
import time
import base64
import html
from html.parser import HTMLParser
from collections import OrderedDict
import requests
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from bs4 import BeautifulSoup

app = Flask(__name__)

# Zona Waktu Indonesia Barat (WIB)
WIB = timezone(timedelta(hours=7))

# ==============================================================================
# DAFTAR MEREK JAM MEWAH & HELPER DETEKSI KONFLIK MEREK (SAFETY GUARD)
# ==============================================================================
LUXURY_WATCH_BRANDS = [
    ("ROLEX", ["ROLEX"]),
    ("PATEK PHILIPPE", ["PATEK PHILIPPE", "PATEK", "NAUTILUS", "AQUANAUT", "CALATRAVA"]),
    ("AUDEMARS PIGUET", ["AUDEMARS PIGUET", "AUDEMARS", "ROYAL OAK", "OFFSHORE"]),
    ("HUBLOT", ["HUBLOT", "BIG BANG", "CLASSIC FUSION", "KING POWER"]),
    ("FRANCK MULLER", ["FRANCK MULLER", "FRANCK", "MULLER", "CONQUISTADOR", "VANGUARD", "CASABLANCA", "CRAZY HOURS", "CURVEX"]),
    ("RICHARD MILLE", ["RICHARD MILLE", "MILLE"]),
    ("SWATCH X OMEGA", ["SWATCH X OMEGA", "OMEGA X SWATCH", "MOONSWATCH"]),
    ("OMEGA", ["OMEGA", "SPEEDMASTER", "SEAMASTER", "CONSTELLATION", "DE VILLE"]),
    ("TUDOR", ["TUDOR", "BLACK BAY", "PELAGOS"]),
    ("CARTIER", ["CARTIER", "SANTOS", "TANK", "BALLON BLEU", "PANTHERE", "PASHA"]),
    ("IWC", ["IWC", "SCHAFFHAUSEN", "PORTUGIESER", "PILOT", "PORTOFINO", "INGENIEUR", "BIG PILOT"]),
    ("PANERAI", ["PANERAI", "LUMINOR", "RADIOMIR", "SUBMERSIBLE"]),
    ("BREITLING", ["BREITLING", "NAVITIMER", "CHRONOMAT", "SUPEROCEAN", "AVENGER"]),
    ("TAG HEUER", ["TAG HEUER", "TAG", "CARRERA", "MONACO", "AQUARACER", "AUTAVIA"]),
    ("JAEGER-LECOULTRE", ["JAEGER-LECOULTRE", "JAEGER LECOULTRE", "JLC", "REVERSO", "POLARIS", "MASTER CONTROL"]),
    ("VACHERON CONSTANTIN", ["VACHERON CONSTANTIN", "VACHERON", "OVERSEAS", "HISTORIQUES"]),
    ("CHOPARD", ["CHOPARD", "MILLE MIGLIA", "HAPPY DIAMONDS", "ALPINE EAGLE"]),
    ("BULGARI", ["BULGARI", "BVLGARI", "OCTO", "OCTO FINISSIMO", "SERPENTI"]),
    ("ZENITH", ["ZENITH", "CHRONOMASTER", "DEFY", "EL PRIMERO"]),
    ("GIRARD-PERREGAUX", ["GIRARD-PERREGAUX", "GIRARD PERREGAUX", "GP", "LAUREATO"]),
    ("BLANCPAIN", ["BLANCPAIN", "FIFTY FATHOMS", "VILLERET"]),
    ("BELL & ROSS", ["BELL & ROSS", "BELL AND ROSS", "INSTRUMENTS"]),
    ("SEIKO", ["GRAND SEIKO", "SEIKO"])
]

class HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.result = []
    def handle_data(self, d):
        self.result.append(d)
    def handle_starttag(self, tag, attrs):
        if tag in ['br', 'p', 'div', 'tr', 'li', 'h1', 'h2', 'h3', 'h4']:
            self.result.append('\n')
    def handle_endtag(self, tag):
        if tag in ['p', 'div', 'tr', 'li']:
            self.result.append('\n')
    def get_text(self):
        return "".join(self.result)

def strip_html_to_text(html_content):
    """Mengubah format HTML menjadi plain text bersih baris per baris tanpa tag."""
    if not html_content:
        return ""
    try:
        parser = HTMLTextExtractor()
        parser.feed(html_content)
        raw_text = parser.get_text()
    except Exception:
        raw_text = re.sub(r'<[^>]+>', ' ', html_content)
    return html.unescape(raw_text)

def detect_watch_brand(title):
    """Mendeteksi merek jam tangan mewah berdasarkan teks judul."""
    if not title:
        return None
    upper_title = re.sub(r'\[.*?\]', '', title).upper()
    upper_title = re.sub(r'[^A-Z0-9\s]', ' ', upper_title)
    words = upper_title.split()

    for canonical_brand, keywords in LUXURY_WATCH_BRANDS:
        for kw in keywords:
            kw_words = kw.split()
            if len(kw_words) == 1:
                if kw in words:
                    return canonical_brand
            else:
                if kw in upper_title:
                    return canonical_brand
    return None

def is_brand_conflict(title_a, title_b):
    """
    Memeriksa apakah ada kontradiksi merek jam tangan yang berlainan antara dua judul.
    Contoh: Hublot vs Franck Muller -> Conflict! (True, 'HUBLOT', 'FRANCK MULLER')
    """
    if not title_a or not title_b:
        return False, None, None
    brand_a = detect_watch_brand(title_a)
    brand_b = detect_watch_brand(title_b)
    if brand_a and brand_b and brand_a != brand_b:
        return True, brand_a, brand_b
    return False, brand_a, brand_b

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
SHOPIFY_STORE_NAME = os.getenv("SHOPIFY_STORE_NAME", "your_shopify_store_name")
SHOPIFY_CLIENT_ID = os.getenv("SHOPIFY_CLIENT_ID", "")
SHOPIFY_CLIENT_SECRET = os.getenv("SHOPIFY_CLIENT_SECRET", "")
API_VERSION = "2025-01"

# Webhooks Google Apps Script (3 Spreadsheet Target)
# 1. Spreadsheet Consignment Listing (Tab 'PHOTO STUDIO' & 'PHOTO OWNER')
APPS_SCRIPT_CONSIGNMENT_URL = os.getenv("WEBHOOK_CONSIGNMENT_LISTING", os.getenv("APPS_SCRIPT_CONSIGNMENT_URL", ""))
# 2. Spreadsheet History Foto Studio (Pencatatan Jam Baru / Draft WA)
APPS_SCRIPT_HISTORY_URL = os.getenv("WEBHOOK_HISTORY_FOTO_STUDIO", os.getenv("APPS_SCRIPT_HISTORY_URL", ""))
# 3. Spreadsheet Slow Moving Items (Featured Items Reprice & Stock Tracking)
APPS_SCRIPT_SLOW_MOVING_URL = os.getenv("WEBHOOK_SLOW_MOVING_FEATURED", os.getenv("APPS_SCRIPT_SLOW_MOVING_URL", ""))

# Green-API (WhatsApp Bot)
GREEN_API_ID_INSTANCE = os.getenv("GREEN_API_ID_INSTANCE", "")
GREEN_API_API_TOKEN = os.getenv("GREEN_API_API_TOKEN", "")
TARGET_GROUP_ID = os.getenv("TARGET_GROUP_ID", "")

# Group/Chat ID yang dikecualikan dari fitur Identifikasi Jam Tangan Otomatis (Gemini Vision)
EXCLUDED_IDENTIFICATION_TARGETS = [
    t.strip().lower() for t in os.getenv("EXCLUDED_IDENTIFICATION_TARGETS", "62817626104-1627455181@g.us, 62817626104-1627455181").split(",") if t.strip()
]

# Gemini API Key & Vision Multimodal
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# Memory Penyimpanan Jam Teridentifikasi Sementara (In-Memory Session dengan TTL)
# Key: chat_id -> Value: dict {sku, title, formatted_price, numeric_price, sheet_info, timestamp}
ACTIVE_IDENTIFIED_WATCHES = OrderedDict()
MAX_ACTIVE_WATCHES = 100
IDENTIFIED_WATCH_TTL = 1800  # 30 menit

# Cache Token Shopify
SHOPIFY_ACCESS_TOKEN = None
SHOPIFY_TOKEN_EXPIRY = 0

# Cache Blogger Service & Deduplikasi Pesan WhatsApp
BLOGGER_SERVICE = None
PROCESSED_MESSAGE_IDS = OrderedDict()
MAX_PROCESSED_IDS = 300

# ==============================================================================
# 2. HELPER FUNCTIONS: PARSING & FORMATTING
# ==============================================================================
def parse_price(price_str):
    """
    Mengubah format harga string menjadi float angka:
    Contoh: '92.000.000' -> 92000000.0, '56.8 jt' -> 56800000.0, '56,8 jt' -> 56800000.0, 'Rp 92.000.000' -> 92000000.0
    """
    if not price_str:
        return 0.0
    clean_lower = price_str.lower().strip()

    # 1. Format miliar (m / milyar / miliar)
    m_miliar = re.search(r'([\d,\.]+)\s*(?:m|miliar|milyar)\b', clean_lower)
    if m_miliar:
        raw_val = m_miliar.group(1).strip()
        if '.' in raw_val and ',' in raw_val:
            val_str = raw_val.replace('.', '').replace(',', '.')
        elif ',' in raw_val:
            val_str = raw_val.replace(',', '.')
        elif '.' in raw_val:
            parts = raw_val.split('.')
            val_str = raw_val if len(parts) == 2 else raw_val.replace('.', '')
        else:
            val_str = raw_val
        try:
            return float(val_str) * 1_000_000_000
        except ValueError:
            pass

    # 2. Format juta (jt / juta)
    m_juta = re.search(r'([\d,\.]+)\s*(?:jt|juta)', clean_lower)
    if m_juta:
        raw_val = m_juta.group(1).strip()
        # Jika ada titik dan koma sekaligus (misal 1.250,5 jt), hapus titik pemisah ribuan dan ubah koma jadi desimal
        if '.' in raw_val and ',' in raw_val:
            val_str = raw_val.replace('.', '').replace(',', '.')
        elif ',' in raw_val:
            # Koma tunggal sebagai desimal (misal: 56,8 jt -> 56.8 jt)
            val_str = raw_val.replace(',', '.')
        elif '.' in raw_val:
            parts = raw_val.split('.')
            # Jika ada 1 titik desimal (misal 56.8 jt, 56.85 jt, 56.800 jt), jangan hapus titik
            if len(parts) == 2:
                val_str = raw_val
            else:
                # Lebih dari 1 titik pemisah ribuan (misal 56.000.000 jt)
                val_str = raw_val.replace('.', '')
        else:
            val_str = raw_val

        try:
            return float(val_str) * 1_000_000
        except ValueError:
            pass

    # 3. Format angka nominal biasa tanpa satuan (misal Rp 56.800.000, 56800000, 56.800.000)
    numeric_str = re.sub(r'[^\d]', '', price_str)
    if numeric_str:
        return float(numeric_str)
    return 0.0

def format_rupiah(num):
    return f"Rp {int(num):,}"

def parse_reprice_chat(message_text, fallback_sku=None):
    """
    Memvalidasi dan mengekstrak perintah chat:
    1. REPRICE / [KODE] / [HARGA]
    2. HARGA BARU / [KODE] / [HARGA]
    3. REPRICE [KODE] [HARGA]
    4. Format cepat dengan fallback_sku (misal: 'REPRICE 650JT' atau 'REPRICE Rp 650.000.000').
    Mendukung SKU yang mengandung karakter garis miring (misal Patek Philippe: 5720232/4642909).
    """
    if not message_text:
        return None

    # Cara 1: Coba split dengan pemisah ' / ' (garis miring berpagar spasi)
    if "/" in message_text:
        spaced_parts = [p.strip() for p in re.split(r'\s+/\s+', message_text.strip()) if p.strip()]
        if len(spaced_parts) >= 3:
            cmd = spaced_parts[0].upper().strip()
            if cmd in ["REPRICE", "HARGA BARU", "HARGA_BARU"]:
                raw_price = spaced_parts[-1].strip()
                code = clean_sku_string(" / ".join(spaced_parts[1:-1])).upper()
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
        if len(parts) >= 3:
            cmd = parts[0].upper().strip()
            if cmd in ["REPRICE", "HARGA BARU", "HARGA_BARU"]:
                raw_price = parts[-1].strip()
                numeric_price = parse_price(raw_price)
                if numeric_price > 0:
                    code = clean_sku_string("/".join(parts[1:-1])).upper()
                    cmd_type = "REPRICE" if cmd == "REPRICE" else "HARGA_BARU"
                    return {
                        "command_type": cmd_type,
                        "code": code,
                        "raw_price": raw_price,
                        "numeric_price": numeric_price,
                        "formatted_price": format_rupiah(numeric_price)
                    }

    # Cara 3: Dukung format tanpa garis miring: misal 'REPRICE abcd123 150JT' atau 'HARGA BARU abcd123 Rp 150.000.000'
    m_no_slash = re.match(r'^(REPRICE|HARGA\s+BARU)\s+([A-Za-z0-9\-\/]+)\s+(.+)$', message_text.strip(), re.IGNORECASE)
    if m_no_slash:
        cmd_raw = m_no_slash.group(1).upper()
        code_raw = m_no_slash.group(2).strip()
        price_raw = m_no_slash.group(3).strip()
        num_price = parse_price(price_raw)
        if num_price > 0:
            c_type = "REPRICE" if "REPRICE" in cmd_raw else "HARGA_BARU"
            return {
                "command_type": c_type,
                "code": clean_sku_string(code_raw).upper(),
                "raw_price": price_raw,
                "numeric_price": num_price,
                "formatted_price": format_rupiah(num_price)
            }

    # Cara 4: Format Cepat jika menggunakan fallback_sku (misal balasan chat: 'REPRICE 650JT' atau 'REPRICE / 650JT')
    if fallback_sku:
        m_fallback = re.match(r'^(REPRICE|HARGA\s+BARU|HARGA_BARU)(?:\s*/\s*|\s+)(.+)$', message_text.strip(), re.IGNORECASE)
        if m_fallback:
            cmd_raw = m_fallback.group(1).upper()
            price_raw = m_fallback.group(2).strip().lstrip('/:- \t')
            num_price = parse_price(price_raw)
            if num_price > 0:
                c_type = "REPRICE" if "REPRICE" in cmd_raw else "HARGA_BARU"
                return {
                    "command_type": c_type,
                    "code": clean_sku_string(fallback_sku).upper(),
                    "raw_price": price_raw,
                    "numeric_price": num_price,
                    "formatted_price": format_rupiah(num_price)
                }

    return None

def parse_takedown_chat(message_text, fallback_sku=None):
    """
    Memvalidasi dan mengekstrak perintah chat TAKEDOWN / SOLD / ON HOLD:
    Format yang didukung:
    1. TAKEDOWN / [KODE] (atau TAKE DOWN) -> status: Takedown
    2. SOLD / [KODE] (atau LAKU) -> status: Sold
    3. ON HOLD / [KODE] (atau HOLD) -> status: On Hold
    4. Format cepat: 'sold', 'laku', 'on hold', 'hold' dengan fallback_sku
    Mendukung SKU dengan karakter garis miring (misal 5720232/4642909).
    Bebas huruf besar/kecil (case-insensitive).
    """
    if not message_text:
        return None

    clean_text = message_text.strip()
    m = re.match(r'^(takedown|take\s*down|sold|laku|on\s*hold|on_hold|hold)\b\s*(.*)$', clean_text, re.IGNORECASE)
    if not m:
        return None

    raw_keyword = m.group(1).lower().replace(" ", "").replace("_", "")
    if raw_keyword in ["takedown"]:
        cmd_type = "TAKEDOWN"
        status_text = "Takedown"
    elif raw_keyword in ["sold", "laku"]:
        cmd_type = "SOLD"
        status_text = "Sold"
    elif raw_keyword in ["onhold", "hold"]:
        cmd_type = "ON_HOLD"
        status_text = "On Hold"
    else:
        cmd_type = "TAKEDOWN"
        status_text = "Takedown"

    rest = m.group(2).strip()
    if not rest:
        if fallback_sku:
            return {
                "command_type": cmd_type,
                "status_text": status_text,
                "code": clean_sku_string(fallback_sku).upper()
            }
        return None

    rest = rest.lstrip(':/- \t')

    if not rest:
        if fallback_sku:
            return {
                "command_type": cmd_type,
                "status_text": status_text,
                "code": clean_sku_string(fallback_sku).upper()
            }
        return None

    # Pisahkan jika ada pemisah ' / ' (misal: '5720232/4642909 / laku' atau '5720232 / 4642909')
    spaced_parts = [p.strip() for p in re.split(r'\s+/\s+', rest) if p.strip()]
    if len(spaced_parts) > 1:
        last_part = spaced_parts[-1].lower()
        if last_part in ["sold", "laku", "cancel", "batal", "booked", "retur", "hold"]:
            code = " / ".join(spaced_parts[:-1]).strip()
        else:
            # Jika user ketik serial ganda misal '5720232 / 4642909'
            code = "/".join(spaced_parts).strip()
    else:
        code = rest.strip()

    code = clean_sku_string(code).upper()
    if not code:
        if fallback_sku:
            code = clean_sku_string(fallback_sku).upper()
        else:
            return None

    return {
        "command_type": cmd_type,
        "status_text": status_text,
        "code": code
    }

def is_cancellation_chat(message_text):
    """
    Mengecek apakah pesan adalah perintah pembatalan / abaikan identifikasi jam tangan.
    Contoh: 'abaikan', 'batal', 'cancel', 'skip', 'batalkan'.
    """
    if not message_text:
        return False
    norm = message_text.strip().lower()
    return norm in ["abaikan", "batal", "batalkan", "cancel", "skip", "tidak", "batal.", "abaikan."]

def extract_sku_from_quoted_message(quoted_msg):
    """
    Mengekstrak Kode / SKU dari pesan yang di-reply / quote di WhatsApp.
    Contoh dalam quote: '🔢 *Kode / SKU:* 3012154' -> '3012154'
    """
    if not quoted_msg or not isinstance(quoted_msg, dict):
        return None
    raw_text = (
        quoted_msg.get("textMessage") 
        or quoted_msg.get("conversation") 
        or (quoted_msg.get("extendedTextMessageData", {}) or {}).get("text") 
        or ""
    )
    if not raw_text:
        return None
    m = re.search(r'(?:Kode\s*/\s*SKU|SKU|Kode)\s*:\*?\s*([A-Za-z0-9\-\/]+)', raw_text, re.IGNORECASE)
    if m:
        return clean_sku_string(m.group(1)).upper()
    return None

def is_chat_excluded_from_identification(chat_id):
    """
    Mengecek apakah chat_id berasal dari group/user yang dikecualikan dari fitur identifikasi jam tangan visual.
    Contoh: Group Foto Studio (62817626104-1627455181@g.us) yang sering kirim foto jam baru.
    """
    if not chat_id:
        return False
    clean_id = chat_id.strip().lower()
    base_id = clean_id.split("@")[0]
    for ex in EXCLUDED_IDENTIFICATION_TARGETS:
        ex_clean = ex.strip().lower()
        ex_base = ex_clean.split("@")[0]
        if clean_id == ex_clean or base_id == ex_base or ex_base in clean_id:
            return True
    return False

def normalize_watch_model_title(title):
    """
    Menormalkan judul model jam tangan untuk perbandingan kesamaan model (tie-breaker):
    - Menghapus tahun rilis dalam kurung seperti (2018), [2013], (2025), dsb.
    - Menghapus karakter non-alphanumeric selain spasi.
    - Mengubah ke huruf kapital dan memangkas spasi berlebih.
    Contoh: 'YACHT-MASTER II 44MM TWOTONE ROSEGOLD (2018)' -> 'YACHT MASTER II 44MM TWOTONE ROSEGOLD'
    """
    if not title:
        return ""
    clean = re.sub(r'[\(\[\{]\s*\d{4}\s*[\)\]\}]', '', title)
    clean = re.sub(r'[^A-Za-z0-9]+', ' ', clean).strip().upper()
    return clean

def is_known_action_command(text):
    """
    Mengecek apakah teks merupakan perintah aksi (sold, hold, reprice, takedown, repost, abaikan/batal).
    Jika True, pesan gambar tidak akan diarahkan ke identifikasi foto biasa melainkan ke handler aksi masing-masing.
    """
    if not text:
        return False
    t = text.strip()
    if is_cancellation_chat(t):
        return True
    if t.lower() in ["sold", "laku", "on hold", "onhold", "hold", "takedown"]:
        return True
    if re.match(r'^(REPRICE|HARGA\s+BARU|HARGA_BARU)(?:\s*/\s*|\s+)(.+)$', t, re.IGNORECASE):
        return True
    if parse_reprice_chat(t):
        return True
    if parse_takedown_chat(t):
        return True
    if parse_repost_chat(t):
        return True
    return False

def is_identification_request(text):
    """
    Mengecek apakah caption pesan memuat keyword 'identifikasi' atau 'identify'
    untuk memicu fitur Identifikasi Jam Tangan Visual IDWX multimodal Gemini Vision.
    Format yang didukung: 'identifikasi', 'identifikasi [keterangan]', 'tolong identifikasi', 'identify', dsb.
    """
    if not text:
        return False
    return bool(re.search(r'\b(identifikasi|identify)\b', text.strip(), re.IGNORECASE))

def format_watch_identification_message(title, sku, formatted_price, sheet_info, location=None, form_content="", owner=None, sales=None):
    """
    Memformat pesan identifikasi jam tangan IDWX dengan opsi Aksi Cepat (termasuk opsi 'batal').
    Mendukung status lokasi dinamis (misal: 'Ready di Toko' atau 'Ready in Bali').
    Menyertakan baris '*Owner:* [owner]' jika ada (tab ALL STOCK atau PHOTO STUDIO),
    serta baris '*Sales:* [sales]' jika ada (khusus tab PHOTO STUDIO),
    dan isi formulir konsinyasi (Kolom D) jika dari tab PHOTO STUDIO / PHOTO OWNER.
    """
    status_str = f"AKTIF ({location})" if location else "AKTIF (Ready di Toko)"
    msg = (
        f"⌚ *IDENTIFIKASI JAM TANGAN IDWX*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📌 *Merek & Seri:* {title}\n"
        f"🔢 *Kode / SKU:* {sku}\n"
        f"💰 *Harga Saat Ini:* {formatted_price}\n"
        f"📦 *Status:* {status_str}\n"
        f"📊 *Spreadsheet:* {sheet_info}\n"
    )
    if owner and str(owner).strip():
        msg += f"*Owner:* {str(owner).strip()}\n"
    if sales and str(sales).strip():
        msg += f"*Sales:* {str(sales).strip()}\n"

    if form_content and form_content.strip():
        msg += f"\n{form_content.strip()}\n"

    msg += (
        f"\n👉 *Aksi Cepat (Balas pesan ini):*\n"
        f"• Ketik *sold* untuk menandai laku\n"
        f"• Ketik *on hold* untuk simpan/hold\n"
        f"• Ketik *reprice [harga]* untuk ubah harga\n"
        f"• Ketik *batal* jika tidak ada tindakan"
    )
    return msg

def identify_watch_with_gemini(image_url=None, image_bytes=None, jpeg_thumbnail=None, chat_id=None, id_message=None):
    """
    Menganalisis foto jam tangan menggunakan Gemini Vision multimodal (gemini-3.1-flash-lite / gemini-3.5-flash).
    Mengekstrak merek, model/seri, tahun rilis, warna dial, nomor referensi, harga tertera, badge lokasi, full title text, query pencarian, serta photo_type (photo_owner vs photo_studio).
    Dilengkapi sistem unduh tangguh (User-Agent, fallback Green API downloadFile, dan fallback jpegThumbnail).
    """
    if not GEMINI_API_KEY:
        print("⚠️ GEMINI_API_KEY tidak terkonfigurasi di environment.")
        return None

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        # 1. Coba unduh gambar dari downloadUrl utama
        if not image_bytes and image_url:
            print(f"📥 Mengunduh gambar untuk analisis Gemini Vision dari: {image_url[:80]}...")
            try:
                img_res = requests.get(image_url, headers=headers, timeout=20)
                if img_res.status_code == 200 and len(img_res.content) > 100:
                    image_bytes = img_res.content
                else:
                    print(f"⚠️ Gagal unduh downloadUrl langsung: HTTP {img_res.status_code}")
            except Exception as dl_err:
                print(f"⚠️ Exception unduh downloadUrl langsung: {dl_err}")

        # 2. Fallback: Request link unduh segar via Green API downloadFile API jika tersedia
        if not image_bytes and GREEN_API_ID_INSTANCE and GREEN_API_API_TOKEN and chat_id and id_message:
            try:
                dl_api_url = f"https://api.green-api.com/waInstance{GREEN_API_ID_INSTANCE}/downloadFile/{GREEN_API_API_TOKEN}"
                dl_res = requests.post(dl_api_url, json={"chatId": chat_id, "idMessage": id_message}, timeout=15)
                if dl_res.status_code == 200:
                    fresh_url = dl_res.json().get("downloadUrl")
                    if fresh_url:
                        res_fresh = requests.get(fresh_url, headers=headers, timeout=20)
                        if res_fresh.status_code == 200 and len(res_fresh.content) > 100:
                            image_bytes = res_fresh.content
                            print("📥 Berhasil mengunduh gambar via Green API downloadFile endpoint.")
            except Exception as api_dl_err:
                print(f"⚠️ Fallback Green API downloadFile gagal: {api_dl_err}")

        # 3. Fallback: Gunakan jpegThumbnail dari payload jika download link gagal
        if not image_bytes and jpeg_thumbnail:
            try:
                decoded_thumb = base64.b64decode(jpeg_thumbnail)
                if decoded_thumb and len(decoded_thumb) > 50:
                    image_bytes = decoded_thumb
                    print("📸 Menggunakan fallback jpegThumbnail dari Green API webhook.")
            except Exception as th_err:
                print(f"⚠️ Gagal decode jpegThumbnail: {th_err}")

        if not image_bytes:
            print("⚠️ Data gambar kosong untuk analisis Gemini Vision.")
            return None

        b64_img = base64.b64encode(image_bytes).decode("utf-8")

        prompt = (
            "You are a luxury watch authentication and cataloging expert at IDWX.\n"
            "Analyze this luxury wristwatch image carefully.\n\n"
            "SPECIAL INSTRUCTION FOR SCREENSHOTS, PRODUCT CARDS, OR CATALOG LISTINGS:\n"
            "- If the image is a screenshot, product card, website flyer, or catalog listing containing text/specifications (e.g. brand, model name, dial, reference, year, price, or location badge like 'Ready In Bali' or 'Consignment'), READ and EXTRACT that visible text directly to ensure exact identification!\n\n"
            "Identify:\n"
            "1. brand: Brand name (e.g. Rolex, Hublot, Patek Philippe, Audemars Piguet, Omega, Tudor, Cartier, etc.)\n"
            "2. model: Model / Series / Collection (e.g. Datejust 41, Big Bang Unico 42mm, Air King, Yacht-Master II 44mm, Historiques American 1921, Submariner Date, etc.)\n"
            "3. year: Release / catalog year as a 4-digit string if visible in text or recognized (e.g. '2022', '2018', '2025', '2026', or empty string if uncertain)\n"
            "4. dial_color: Dial color / key dial features (e.g. 'Wimbledon', 'Slate Grey', 'Black', 'Blue', 'Skeleton', 'Silver', 'Salmon', etc.)\n"
            "5. reference: Reference or case number if visible or recognized (e.g. '126333', '116681', '126900', '441.NM.1170.RX', or empty string if uncertain)\n"
            "6. extracted_price: Numeric price in Rupiah (integer) if visible in image (e.g. 249000000, 258000000, 135000000, 359000000, or null if no price text)\n"
            "7. location_badge: Location / tag badge if visible on card (e.g. 'Ready In Bali', 'Consignment', or empty string)\n"
            "8. full_title_text: Full product title text as written on the card/screenshot if visible (e.g. 'DATEJUST 41MM TWOTONE YELLOWGOLD WIMBLEDON DIAL (2022)', 'BIG BANG UNICO 42MM TITANIUM CERAMIC (2026)', 'YACHT-MASTER II 44MM TWOTONE ROSEGOLD (2018)', 'AIR KING (2025)')\n"
            "9. search_query: Search keywords optimized for searching Shopify inventory (e.g. 'Datejust 41 Wimbledon', 'Big Bang Unico 42mm Titanium Ceramic', 'Air King')\n"
            "10. photo_type: Determine whether this image is 'photo_owner' or 'photo_studio':\n"
            "   - 'photo_owner': Casual photo taken by owner (e.g. on pillow/cushion, bed, sofa, car interior, desk, or wrist).\n"
            "   - 'photo_studio': Professional photo with plain lightbox/studio background or on a watch stand.\n\n"
            "Respond STRICTLY in JSON format with keys:\n"
            "brand, model, year, dial_color, reference, extracted_price, location_badge, full_title_text, search_query, photo_type"
        )

        models_to_try = ["gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3.6-flash"]
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/jpeg", "data": b64_img}}
                ]
            }],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.1
            }
        }

        for model_name in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
            try:
                res = requests.post(url, json=payload, timeout=25)
                if res.status_code == 200:
                    res_json = res.json()
                    candidates = res_json.get("candidates", [])
                    if candidates:
                        raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        if raw_text:
                            parsed = None
                            json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
                            if json_match:
                                try:
                                    parsed = json.loads(json_match.group(0))
                                except Exception:
                                    pass
                            if not parsed:
                                clean_json_str = re.sub(r'^```json\s*', '', raw_text.strip(), flags=re.IGNORECASE)
                                clean_json_str = re.sub(r'```$', '', clean_json_str.strip())
                                parsed = json.loads(clean_json_str)

                            parsed["_image_bytes"] = image_bytes
                            print(f"🤖 Gemini Vision ({model_name}) berhasil mengidentifikasi: {parsed.get('brand')} - {parsed.get('model')} (Tahun: {parsed.get('year')}, Harga: {parsed.get('extracted_price')}, Tipe Foto: {parsed.get('photo_type')})")
                            return parsed
                else:
                    print(f"⚠️ Gemini Vision ({model_name}) HTTP {res.status_code}: {res.text[:120]}")
            except Exception as m_err:
                print(f"⚠️ Exception memanggil Gemini ({model_name}): {m_err}")

    except Exception as e:
        print(f"❌ Error identify_watch_with_gemini: {e}")

    return None

def verify_watch_visually_with_gemini(inquiry_image_bytes, candidate_a, candidate_b):
    """
    Multimodal visual verification tie-breaker when multiple top candidates match the same model/title.
    Sends inquiry image + candidate A image + candidate B image to Gemini Vision to pick the best match.
    Returns 'A', 'B', or None.
    """
    if not GEMINI_API_KEY or not inquiry_image_bytes:
        return None

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        url_a = candidate_a.get("image_url")
        url_b = candidate_b.get("image_url")
        if not url_a or not url_b:
            return None

        # Download featured image for candidate A & B (timeout 10s each with browser headers)
        try:
            res_a = requests.get(url_a, headers=headers, timeout=10)
            res_b = requests.get(url_b, headers=headers, timeout=10)
            if res_a.status_code != 200 or res_b.status_code != 200:
                print("⚠️ Gagal mengunduh gambar kandidat untuk verifikasi visual.")
                return None
        except Exception as dl_err:
            print(f"⚠️ Exception unduh gambar kandidat: {dl_err}")
            return None

        b64_inquiry = base64.b64encode(inquiry_image_bytes).decode("utf-8")
        b64_a = base64.b64encode(res_a.content).decode("utf-8")
        b64_b = base64.b64encode(res_b.content).decode("utf-8")

        prompt = (
            "You are an expert luxury watch catalog matching assistant at IDWX.\n"
            "You are given 3 images:\n"
            "1. INQUIRY IMAGE: The watch photo sent by the user.\n"
            "2. CANDIDATE A: Catalog photo for candidate A.\n"
            "3. CANDIDATE B: Catalog photo for candidate B.\n\n"
            "Compare the INQUIRY IMAGE closely with CANDIDATE A and CANDIDATE B.\n"
            "Pay close attention to:\n"
            "- Photo setting/background (e.g. pillow/cushion color/texture, bedsheet, studio lightbox plain background, lighting reflection).\n"
            "- Exact dial features, numerals, hands position, bezel, bracelet/strap.\n"
            "Determine which candidate (A or B) is the EXACT same catalog item or photo listing as the INQUIRY IMAGE.\n\n"
            "Respond strictly in JSON format with keys:\n"
            "\"winner\": \"A\" or \"B\",\n"
            "\"confidence\": \"high\" or \"medium\" or \"low\",\n"
            "\"reason\": \"brief explanation of visual similarities\"\n"
        )

        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"text": "INQUIRY IMAGE:"},
                    {"inline_data": {"mime_type": "image/jpeg", "data": b64_inquiry}},
                    {"text": "CANDIDATE A:"},
                    {"inline_data": {"mime_type": "image/jpeg", "data": b64_a}},
                    {"text": "CANDIDATE B:"},
                    {"inline_data": {"mime_type": "image/jpeg", "data": b64_b}}
                ]
            }],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.1
            }
        }

        models_to_try = ["gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3.6-flash"]
        for model_name in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
            try:
                res = requests.post(url, json=payload, timeout=20)
                if res.status_code == 200:
                    res_json = res.json()
                    candidates = res_json.get("candidates", [])
                    if candidates:
                        raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        parsed = None
                        json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
                        if json_match:
                            try:
                                parsed = json.loads(json_match.group(0))
                            except Exception:
                                pass
                        if not parsed:
                            clean_json_str = re.sub(r'^```json\s*', '', raw_text.strip(), flags=re.IGNORECASE)
                            clean_json_str = re.sub(r'```$', '', clean_json_str.strip())
                            parsed = json.loads(clean_json_str)

                        winner = parsed.get("winner", "").strip().upper()
                        print(f"👁️ Visual Verification ({model_name}): Pemenang '{winner}' (Confidence: {parsed.get('confidence')}, Alasan: {parsed.get('reason')})")
                        if winner in ["A", "B"]:
                            return winner
                else:
                    print(f"⚠️ Visual verification ({model_name}) HTTP {res.status_code}: {res.text[:120]}")
            except Exception as m_err:
                print(f"⚠️ Exception visual verification ({model_name}): {m_err}")

    except Exception as e:
        print(f"⚠️ Error verify_watch_visually_with_gemini: {e}")

    return None

def find_active_watch_in_shopify(gemini_info, user_caption=""):
    """
    Mencari produk jam tangan AKTIF di Shopify yang paling sesuai dengan hasil analisis Gemini Vision.
    Mendukung pembedaan Photo Owner vs Photo Studio, Recency, Filter/Tag Lokasi (Ready in Bali / Consignment),
    Kecocokan Tahun Rilis, Kecocokan Harga Tertera, dan Verifikasi Visual Multimodal (Tie-Breaker).
    Mengembalikan dict dengan product_node, variant_node, sku, title, numeric_price, formatted_price, location.
    """
    token = get_shopify_token()
    if not token or not gemini_info:
        return None

    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
    graphql_url = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{API_VERSION}/graphql.json"

    brand = (gemini_info.get("brand") or "").strip()
    model = (gemini_info.get("model") or "").strip()
    ref = (gemini_info.get("reference") or "").strip()
    dial = (gemini_info.get("dial_color") or "").strip()
    year = (gemini_info.get("year") or "").strip()
    extracted_price = gemini_info.get("extracted_price")
    location_badge = (gemini_info.get("location_badge") or "").strip()
    full_title_text = (gemini_info.get("full_title_text") or "").strip()
    photo_type = (gemini_info.get("photo_type") or "").strip().lower()
    inquiry_image_bytes = gemini_info.pop("_image_bytes", None)
    query_str = (gemini_info.get("search_query") or f"{brand} {model}").strip()

    # Deteksi indikasi Ready in Bali dari caption teks user maupun badge/text pada gambar
    is_caption_bali = "bali" in (user_caption or "").lower()
    is_image_bali = "bali" in location_badge.lower() or "bali" in full_title_text.lower()
    is_bali_requested = is_caption_bali or is_image_bali

    model_words = [w for w in re.split(r'[^A-Za-z0-9]+', model) if len(w) >= 3 and w.lower() not in ["watch", "automatic", "chronograph", "dial", "edition", "series"]]
    brand_words = [w for w in re.split(r'[^A-Za-z0-9]+', brand) if len(w) >= 3]

    candidate_search_queries = []

    # 1. Prioritas Tertinggi: Jika terdeteksi full_title_text dari screenshot/product card
    if full_title_text:
        clean_full = re.sub(r'[\(\)\[\]\{\}]', ' ', full_title_text).strip()
        candidate_search_queries.append(f"status:active {clean_full}")
        if is_bali_requested:
            candidate_search_queries.append(f"status:active {clean_full} bali")

    # 2. Query search_query langsung yang spesifik (misal: "Hublot Big Bang Unico 42mm Titanium Ceramic 2026")
    if query_str:
        clean_qs = re.sub(r'[\(\)\[\]\{\}]', ' ', query_str).strip()
        candidate_search_queries.append(f"status:active {clean_qs}")
        if is_bali_requested:
            candidate_search_queries.append(f"status:active {clean_qs} bali")

    # 3. Query spesifik dengan referensi jika ada
    if ref:
        candidate_search_queries.append(f"status:active {ref}")

    # 4. Query model + year jika ada
    if model_words and year and year.isdigit():
        candidate_search_queries.append(f"status:active {' '.join(model_words[:3])} {year}")

    # 5. Query model unik (misal: "Big Bang Unico 42mm", "Yacht-Master II 44mm", "Historiques American 1921")
    if len(model_words) >= 2:
        candidate_search_queries.append(f"status:active {' '.join(model_words[:3])}")
    if model_words:
        candidate_search_queries.append(f"status:active {model_words[-1]}")
        if len(model_words) > 1:
            candidate_search_queries.append(f"status:active {model_words[0]}")

    # 6. Query brand + model
    if brand_words and model_words:
        candidate_search_queries.append(f"status:active {brand_words[0]} {model_words[0]}")

    seen_product_ids = set()
    scored_candidates = []

    search_gql = """
    query searchProducts($query: String!) {
      products(first: 20, query: $query) {
        edges {
          node {
            id
            title
            tags
            descriptionHtml
            status
            createdAt
            featuredImage {
              url
            }
            variants(first: 10) {
              edges {
                node {
                  id
                  sku
                  price
                  inventoryQuantity
                }
              }
            }
          }
        }
      }
    }
    """

    for q in candidate_search_queries:
        if len(scored_candidates) >= 15:
            break
        try:
            res = requests.post(graphql_url, headers=headers, json={"query": search_gql, "variables": {"query": q}}, timeout=15)
            if res.status_code == 200:
                data = res.json().get("data", {}).get("products", {}).get("edges", [])
                for edge in data:
                    p_node = edge.get("node", {})
                    p_id = p_node.get("id")
                    if p_id in seen_product_ids:
                        continue
                    seen_product_ids.add(p_id)

                    title_upper = (p_node.get("title") or "").upper()
                    status_upper = (p_node.get("status") or "").upper()
                    raw_tags = p_node.get("tags") or []
                    if isinstance(raw_tags, str):
                        raw_tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
                    tags_list = [str(t).strip() for t in raw_tags if str(t).strip()]

                    # Cek apakah produk memiliki label / tag Ready in Bali
                    is_candidate_bali = any("bali" in t.lower() for t in tags_list) or "bali" in title_upper.lower()
                    product_location = "Ready in Bali" if is_candidate_bali else "Ready di Toko"

                    score = 0
                    if status_upper == "ACTIVE":
                        score += 5000
                    elif status_upper == "DRAFT":
                        score -= 2000

                    # 1. Matching Full Title Text (sangat tinggi jika cocok dengan screenshot/card)
                    if full_title_text:
                        norm_full = re.sub(r'[^A-Z0-9]+', ' ', full_title_text.upper()).strip()
                        norm_cand = re.sub(r'[^A-Z0-9]+', ' ', title_upper).strip()
                        if norm_full and norm_cand:
                            if norm_full == norm_cand:
                                score += 40000
                            elif norm_full in norm_cand or norm_cand in norm_full:
                                score += 20000

                    # 2. Matching Year (misal 2018 vs 2013, 2022, 2025, 2026)
                    if year and len(year) == 4 and year.isdigit():
                        if f"({year})" in title_upper or f" {year} " in f" {title_upper} ":
                            score += 25000
                        else:
                            # Penalti tajam jika judul kandidat memiliki tahun berbeda yang kontradiktif
                            cand_years = re.findall(r'\b(19\d\d|20\d\d)\b', title_upper)
                            if cand_years and any(cy != year for cy in cand_years):
                                score -= 35000

                    # 3. Matching Brand Words & Model Words
                    for bw in brand_words:
                        if bw.upper() in title_upper:
                            score += 2000

                    for mw in model_words:
                        if mw.upper() in title_upper:
                            score += 3000

                    # 4. Matching Dial Color / Dial Features
                    if dial:
                        if dial.upper() in title_upper:
                            score += 5000
                        else:
                            dial_words = [dw for dw in re.split(r'[^A-Za-z0-9]+', dial) if len(dw) >= 3 and dw.lower() not in ["dial", "color", "colour", "with", "and"]]
                            for dw in dial_words:
                                if dw.upper() in title_upper:
                                    score += 2500

                    # 5. Matching Reference Number
                    if ref and ref.upper() in title_upper:
                        score += 5000

                    # 6. Matching Search Query keywords (e.g. 42mm, Titanium, Ceramic)
                    query_words = [qw for qw in re.split(r'[^A-Za-z0-9]+', query_str) if len(qw) >= 3 and qw.lower() not in ["watch", "automatic", "chronograph", "edition", "series", "rolex", "hublot", "patek"]]
                    for qw in query_words:
                        if qw.upper() in title_upper:
                            score += 1500

                    # 7. Penyesuaian Lokasi Bali
                    if is_bali_requested:
                        if is_candidate_bali:
                            score += 30000  # Prioritas sangat tinggi jika Bali terdeteksi dan produk bertag Bali
                        else:
                            score -= 15000  # Penalti untuk produk non-bali jika user/gambar spesifik menyebut bali
                    elif is_candidate_bali and not is_image_bali and not is_caption_bali:
                        # Jika tidak ada indikasi Bali sama sekali, jangan beri prioritas berlebih pada Bali
                        pass

                    v_edges = p_node.get("variants", {}).get("edges", [])
                    chosen_variant = None
                    for v_edge in v_edges:
                        vn = v_edge.get("node", {})
                        if vn.get("sku"):
                            chosen_variant = vn
                            if (vn.get("inventoryQuantity") or 0) > 0:
                                score += 1000
                            break
                    if not chosen_variant and v_edges:
                        chosen_variant = v_edges[0].get("node", {})

                    if chosen_variant and chosen_variant.get("sku"):
                        chosen_sku = (chosen_variant.get("sku") or "").strip()
                        is_cpo_sku = chosen_sku.upper().startswith("CPO")
                        cand_price = float(chosen_variant.get("price") or 0.0)

                        # 8. Matching Harga yang Tertera di Gambar (extracted_price)
                        if extracted_price and isinstance(extracted_price, (int, float)) and extracted_price > 0:
                            if cand_price > 0:
                                price_diff_ratio = abs(cand_price - extracted_price) / extracted_price
                                if price_diff_ratio <= 0.02:  # Cocok persis (selisih <= 2%)
                                    score += 35000
                                elif price_diff_ratio <= 0.05:  # Selisih sangat tipis (<= 5%)
                                    score += 15000
                                elif price_diff_ratio > 0.15:  # Beda harga signifikan (> 15%)
                                    score -= 20000

                        # 9. Penyesuaian skor berdasarkan photo_type vs tipe SKU (CPO vs Reguler Studio)
                        if photo_type == "photo_owner":
                            if is_cpo_sku:
                                score += 15000  # Memprioritaskan konsinyasi Photo Owner
                            else:
                                score -= 5000   # Penalti untuk stok studio jika foto dari owner
                        elif photo_type == "photo_studio":
                            if not is_cpo_sku:
                                score += 2000   # Sedikit prioritas untuk stok studio reguler

                        # 10. Bonus tanggal listing terbaru (Recency)
                        created_at_str = p_node.get("createdAt")
                        if created_at_str:
                            try:
                                c_dt = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                                age_days = (datetime.now(timezone.utc) - c_dt).days
                                if age_days <= 30:
                                    score += 3000
                                elif age_days <= 90:
                                    score += 1500
                                elif age_days <= 180:
                                    score += 500
                            except Exception:
                                pass

                        feat_img = p_node.get("featuredImage") or {}
                        cand_img_url = feat_img.get("url")

                        scored_candidates.append({
                            "score": score,
                            "product_node": p_node,
                            "variant_node": chosen_variant,
                            "sku": chosen_sku,
                            "title": p_node.get("title", "").strip(),
                            "price": cand_price,
                            "image_url": cand_img_url,
                            "created_at": created_at_str,
                            "location": product_location,
                            "tags": tags_list
                        })
        except Exception as e:
            print(f"⚠️ Error search Shopify GraphQL with query '{q}': {e}")

    if not scored_candidates:
        return None

    scored_candidates.sort(key=lambda x: x["score"], reverse=True)

    # Verifikasi Visual Multimodal (Tie-Breaker) HANYA jika kandidat teratas bersaing ketat dan tidak ada pemenang pasti berdasarkan tahun atau harga
    if len(scored_candidates) >= 2 and inquiry_image_bytes:
        top1 = scored_candidates[0]
        top2 = scored_candidates[1]

        # Cek apakah sudah ada pemenang pasti berdasarkan tahun tertera atau harga tertera
        has_clear_year_winner = (
            year and year.isdigit() and
            (f"({year})" in top1["title"] or year in top1["title"]) and
            not (f"({year})" in top2["title"] or year in top2["title"])
        )
        has_clear_price_winner = (
            extracted_price and
            abs(top1["price"] - extracted_price) / extracted_price <= 0.05 and
            abs(top2["price"] - extracted_price) / extracted_price > 0.10
        )

        if not has_clear_year_winner and not has_clear_price_winner:
            norm1 = normalize_watch_model_title(top1["title"])
            norm2 = normalize_watch_model_title(top2["title"])

            is_same_model = bool(norm1 and norm2 and norm1 == norm2)
            is_close_score = abs(top1["score"] - top2["score"]) < 8000

            if (is_same_model or is_close_score) and top1.get("image_url") and top2.get("image_url"):
                print(f"🔍 Top 2 kandidat bersaing ketat: '{top1['title']}' ({top1['sku']}) skor {top1['score']} vs '{top2['title']}' ({top2['sku']}) skor {top2['score']}. Menjalankan verifikasi visual multimodal...")
                winner = verify_watch_visually_with_gemini(inquiry_image_bytes, top1, top2)
                if winner == "B":
                    print(f"🔄 Visual verification memilih Kandidat B ('{top2['title']}' SKU: {top2['sku']}) mengalahkan Kandidat A ('{top1['title']}' SKU: {top1['sku']})")
                    top2["score"] += 30000
                    scored_candidates.sort(key=lambda x: x["score"], reverse=True)
                elif winner == "A":
                    print(f"✅ Visual verification mengonfirmasi Kandidat A ('{top1['title']}' SKU: {top1['sku']})")
                    top1["score"] += 30000

    best = scored_candidates[0]
    print(f"🏆 Produk Shopify terbaik terpilih: '{best['title']}' (SKU: {best['sku']}) dengan skor: {best['score']}")

    return {
        "product_node": best["product_node"],
        "variant_node": best["variant_node"],
        "sku": best["sku"],
        "title": best["title"],
        "numeric_price": best["price"],
        "formatted_price": format_rupiah(best["price"]),
        "location": best.get("location", "Ready di Toko")
    }

def resolve_watch_spreadsheet_location(sku, blogger_post=None, return_form=False):
    """
    Menentukan lokasi spreadsheet (Nama Tab & Nomor Baris), isi formulir konsinyasi (Kolom D),
    Owner (Kolom E tab PHOTO STUDIO atau tab ALL STOCK), dan Sales (Kolom F tab PHOTO STUDIO) untuk jam tangan yang diidentifikasi.
    Format yang dihasilkan: "ALL STOCK (Baris 313)" atau "PHOTO STUDIO (Baris 142)"
    Jika return_form=True, mengembalikan tuple (sheet_info, form_content, owner, sales).
    """
    is_consign_ps = False
    is_consign_po = False
    is_featured = False

    if blogger_post:
        labels = blogger_post.get("labels", [])
        is_consign_ps = any("CONSIGNMENT_PS" in l.upper() or "CONSINGMENT_PS" in l.upper() for l in labels)
        is_consign_po = any("CONSIGNMENT_PO" in l.upper() or "CONSINGMENT_PO" in l.upper() for l in labels) or sku.upper().startswith("CPO")
        is_featured = any("FEATURED" in l.upper() for l in labels)

    canonical_sku = clean_sku_string(sku).upper()
    sheet_info = "ALL STOCK"
    form_content = ""
    owner = ""
    sales = ""

    # 1. Jika terindikasi Consignment PO atau berawalan CPO
    if is_consign_po or sku.upper().startswith("CPO"):
        try:
            res = requests.post(APPS_SCRIPT_CONSIGNMENT_URL, json={"action": "query_sku", "sheet_name": "PHOTO OWNER", "sku": canonical_sku}, timeout=15)
            if res.status_code == 200:
                data = res.json()
                if data.get("status") == "success" and data.get("row"):
                    sheet_info = f"{data.get('tab_name', 'PHOTO OWNER')} (Baris {data.get('row')})"
                    form_content = (data.get("form") or "").strip()
                    return (sheet_info, form_content, "", "") if return_form else sheet_info
        except Exception as e:
            print(f"⚠️ Error query consignment PO sheet: {e}")
        sheet_info = "PHOTO OWNER"
        return (sheet_info, form_content, "", "") if return_form else sheet_info

    # 2. Jika terindikasi Consignment PS
    if is_consign_ps:
        try:
            res = requests.post(APPS_SCRIPT_CONSIGNMENT_URL, json={"action": "query_sku", "sheet_name": "PHOTO STUDIO", "sku": canonical_sku}, timeout=15)
            if res.status_code == 200:
                data = res.json()
                if data.get("status") == "success" and data.get("row"):
                    sheet_info = f"{data.get('tab_name', 'PHOTO STUDIO')} (Baris {data.get('row')})"
                    form_content = (data.get("form") or "").strip()
                    owner = (data.get("owner") or "").strip()
                    sales = (data.get("sales") or "").strip()
                    if not owner and form_content:
                        m_owner = re.search(r'(?:^|\n)\s*Nama\s*:\s*([^\n\r]+)', form_content, re.IGNORECASE)
                        if m_owner:
                            owner = m_owner.group(1).strip()
                    if not sales and form_content:
                        m_sales = re.search(r'(?:^|\n)\s*Order\s+received\s+by\s*:\s*([^\n\r]+)', form_content, re.IGNORECASE)
                        if m_sales:
                            sales = m_sales.group(1).strip()
                    return (sheet_info, form_content, owner, sales) if return_form else sheet_info
        except Exception as e:
            print(f"⚠️ Error query consignment PS sheet: {e}")
        sheet_info = "PHOTO STUDIO"
        return (sheet_info, form_content, owner, sales) if return_form else sheet_info

    # 3. Default atau FEATURED: Cek Spreadsheet Slow Moving (Tab ALL STOCK)
    try:
        res = requests.post(APPS_SCRIPT_SLOW_MOVING_URL, json={"action": "query_sku", "sku": canonical_sku, "canonical_sku": canonical_sku}, timeout=15)
        if res.status_code == 200:
            data = res.json()
            if data.get("status") == "success" and data.get("row"):
                sheet_info = f"{data.get('tab_name', 'ALL STOCK')} (Baris {data.get('row')})"
                owner = (data.get("owner") or "").strip()
                return (sheet_info, form_content, owner, "") if return_form else sheet_info
    except Exception as e:
        print(f"⚠️ Error query slow moving sheet: {e}")

    # Fallback cek Consignment PHOTO STUDIO jika di Slow Moving tidak terdata
    try:
        res_alt = requests.post(APPS_SCRIPT_CONSIGNMENT_URL, json={"action": "query_sku", "sheet_name": "PHOTO STUDIO", "sku": canonical_sku}, timeout=15)
        if res_alt.status_code == 200:
            data_alt = res_alt.json()
            if data_alt.get("status") == "success" and data_alt.get("row"):
                sheet_info = f"{data_alt.get('tab_name', 'PHOTO STUDIO')} (Baris {data_alt.get('row')})"
                form_content = (data_alt.get("form") or "").strip()
                owner = (data_alt.get("owner") or "").strip()
                sales = (data_alt.get("sales") or "").strip()
                if not owner and form_content:
                    m_owner = re.search(r'(?:^|\n)\s*Nama\s*:\s*([^\n\r]+)', form_content, re.IGNORECASE)
                    if m_owner:
                        owner = m_owner.group(1).strip()
                if not sales and form_content:
                    m_sales = re.search(r'(?:^|\n)\s*Order\s+received\s+by\s*:\s*([^\n\r]+)', form_content, re.IGNORECASE)
                    if m_sales:
                        sales = m_sales.group(1).strip()
                return (sheet_info, form_content, owner, sales) if return_form else sheet_info
    except Exception:
        pass

    # Fallback cek Consignment PHOTO OWNER jika masih belum ketemu
    try:
        res_alt_po = requests.post(APPS_SCRIPT_CONSIGNMENT_URL, json={"action": "query_sku", "sheet_name": "PHOTO OWNER", "sku": canonical_sku}, timeout=15)
        if res_alt_po.status_code == 200:
            data_alt_po = res_alt_po.json()
            if data_alt_po.get("status") == "success" and data_alt_po.get("row"):
                sheet_info = f"{data_alt_po.get('tab_name', 'PHOTO OWNER')} (Baris {data_alt_po.get('row')})"
                form_content = (data_alt_po.get("form") or "").strip()
                return (sheet_info, form_content, "", "") if return_form else sheet_info
    except Exception:
        pass

    return (sheet_info, form_content, owner, sales) if return_form else sheet_info

def parse_repost_chat(message_text):
    """
    Memvalidasi dan mengekstrak perintah chat REPOST:
    Format yang didukung:
    1. REPOST / [KODE]
    2. REPOST [KODE]
    Mendukung SKU dengan karakter garis miring (misal 5720232/4642909).
    Bebas huruf besar/kecil (case-insensitive).
    """
    if not message_text:
        return None

    clean_text = message_text.strip()
    m = re.match(r'^(repost|re-post|re\s+post)\b\s*(.*)$', clean_text, re.IGNORECASE)
    if not m:
        return None

    rest = m.group(2).strip()
    if not rest:
        return None

    rest = rest.lstrip(':/- \t')

    if not rest:
        return None

    spaced_parts = [p.strip() for p in re.split(r'\s+/\s+', rest) if p.strip()]
    if len(spaced_parts) > 1:
        code = "/".join(spaced_parts).strip()
    else:
        code = rest.strip()

    code = clean_sku_string(code).upper()
    if not code:
        return None

    return {
        "command_type": "REPOST",
        "code": code
    }

def parse_download_foto_chat(message_text):
    """
    Memvalidasi dan mengekstrak perintah chat DOWNLOAD FOTO:
    Format trigger yang didukung:
    1. FOTO [SKU] (contoh: 'foto 2034349', 'FOTO CPO-240626-02')
    2. FOTO / [SKU] atau FOTO: [SKU]
    3. DOWNLOAD FOTO [SKU]
    Mendukung SKU dengan karakter garis miring (misal 5720232/4642909) atau strip.
    Bebas huruf besar/kecil (case-insensitive).
    """
    if not message_text:
        return None

    clean_text = message_text.strip()
    m = re.match(r'^(?:download\s+)?foto\b\s*[:/]?\s*(.*)$', clean_text, re.IGNORECASE)
    if not m:
        return None

    rest = m.group(1).strip()
    if not rest:
        return {
            "command_type": "DOWNLOAD_FOTO_EMPTY",
            "code": ""
        }

    if rest.startswith('/'):
        rest = rest.lstrip('/ \t')

    if not rest:
        return {
            "command_type": "DOWNLOAD_FOTO_EMPTY",
            "code": ""
        }

    spaced_parts = [p.strip() for p in re.split(r'\s+/\s+', rest) if p.strip()]
    if len(spaced_parts) > 1:
        code = "/".join(spaced_parts).strip()
    else:
        code = rest.strip()

    code = clean_sku_string(code).upper()
    if not code:
        return None

    return {
        "command_type": "DOWNLOAD_FOTO",
        "code": code
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
        "video call", "joining info", "reminder"
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

def normalize_blogger_image_url(url):
    """
    Memastikan URL gambar Blogger memiliki parameter resolusi tinggi (/s1600/ atau =s0)
    sehingga tidak menghasilkan HTTP 400 Bad Request saat di-download oleh Green API.
    """
    if not url:
        return None
    url = url.strip()
    if url.startswith("//"):
        url = "https:" + url
    if 'blogger.googleusercontent.com/img/b/' in url:
        if re.search(r'/(?:s\d+|w\d+-h\d+[^/]*)/([^/]+)$', url):
            url = re.sub(r'/(?:s\d+|w\d+-h\d+[^/]*)/([^/]+)$', r'/s1600/\1', url)
        elif not re.search(r'/s1600/([^/]+)$', url):
            url = re.sub(r'/([^/]+)$', r'/s1600/\1', url)
    elif 'googleusercontent.com' in url or 'bp.blogspot.com' in url:
        if re.search(r'/(?:s\d+|w\d+-h\d+[^/]*)/([^/]+)$', url):
            url = re.sub(r'/(?:s\d+|w\d+-h\d+[^/]*)/([^/]+)$', r'/s1600/\1', url)
        elif re.search(r'=(s\d+|w\d+-h\d+[^/]*)$', url):
            url = re.sub(r'=(s\d+|w\d+-h\d+[^/]*)$', '=s0', url)
    return url

def is_image_url_accessible(url, timeout=5):
    """
    Memeriksa apakah URL gambar mengembalikan HTTP 200 OK sehingga aman dikirim via Green API.
    """
    if not url:
        return False
    # Fast path: URL dari CDN Google / Blogspot / Shopify dijamin valid dan dapat diakses langsung
    if "googleusercontent.com" in url or "bp.blogspot.com" in url or "cdn.shopify.com" in url:
        return True
    try:
        r = requests.head(url, timeout=timeout, allow_redirects=True)
        if r.status_code == 200:
            return True
        if r.status_code in [400, 404]:
            return False
        # Server yang menolak HEAD dicoba via GET stream
        r_get = requests.get(url, stream=True, timeout=timeout, allow_redirects=True)
        return r_get.status_code == 200
    except Exception as e:
        print(f"⚠️ Cek akses gambar ({url[:60]}...): {e}")
        return False

def extract_first_image_from_post(post):
    """
    Memastikan mengambil gambar PERTAMA dari postingan di Blogspot
    berdasarkan urutan dokumen HTML (tampilan paling atas artikel).
    """
    if not post:
        return None

    # 1. Prioritaskan parsing konten HTML agar 100% sesuai urutan gambar paling atas
    content = post.get("content", "")
    if content:
        try:
            soup = BeautifulSoup(content, 'html.parser')
            first_img = soup.find('img')
            if first_img and 'src' in first_img.attrs:
                raw_url = first_img['src'].strip()
                # Cek jika img dibungkus oleh tag <a> (biasanya link resolusi tinggi bawaan Blogger)
                parent_a = first_img.find_parent('a')
                if parent_a and 'href' in parent_a.attrs:
                    href = parent_a['href'].strip()
                    if re.search(r'\.(jpg|jpeg|png|webp)($|\?)', href, re.IGNORECASE) or 'googleusercontent.com' in href or 'bp.blogspot.com' in href:
                        raw_url = href

                return normalize_blogger_image_url(raw_url)
        except Exception as e:
            print(f"⚠️ Error parsing HTML untuk gambar pertama: {e}")

        # Fallback regex untuk tag <img> pertama dalam HTML jika parser ada kendala
        img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content, re.IGNORECASE)
        if img_match:
            return normalize_blogger_image_url(img_match.group(1).strip())

    # 2. Fallback terakhir: Cek field images bawaan Blogger API jika konten HTML tidak memuat tag <img>
    images = post.get("images", [])
    if images and isinstance(images, list) and len(images) > 0:
        first_img = images[0]
        url = first_img.get("url") if isinstance(first_img, dict) else first_img
        if url:
            return normalize_blogger_image_url(url)

    return None

def extract_all_images_from_post(post):
    """
    Mengekstrak seluruh URL gambar beresolusi tinggi dari postingan Blogspot
    berdasarkan urutan tampilan di artikel HTML, dinormalisasi ke ukuran original/high-res (/s1600/ atau =s0).
    """
    if not post:
        return []

    image_urls = []
    content = post.get("content", "")

    if content:
        try:
            soup = BeautifulSoup(content, 'html.parser')
            for img in soup.find_all('img'):
                if 'src' in img.attrs:
                    raw_url = img['src'].strip()
                    parent_a = img.find_parent('a')
                    if parent_a and 'href' in parent_a.attrs:
                        href = parent_a['href'].strip()
                        if re.search(r'\.(jpg|jpeg|png|webp)($|\?)', href, re.IGNORECASE) or 'googleusercontent.com' in href or 'bp.blogspot.com' in href:
                            raw_url = href

                    norm_url = normalize_blogger_image_url(raw_url)
                    if norm_url and norm_url not in image_urls:
                        image_urls.append(norm_url)
        except Exception as e:
            print(f"⚠️ Error parsing HTML untuk semua gambar: {e}")

    # Fallback jika dari HTML tidak ditemukan atau untuk melengkapi: cek field images Blogger API
    api_images = post.get("images", [])
    if isinstance(api_images, list):
        for img_obj in api_images:
            url = img_obj.get("url") if isinstance(img_obj, dict) else img_obj
            if url:
                norm_url = normalize_blogger_image_url(str(url).strip())
                if norm_url and norm_url not in image_urls:
                    image_urls.append(norm_url)

    return image_urls

def extract_shopify_image_url(product_node):
    """
    Mengekstrak URL gambar utama dari node produk Shopify.
    Mendukung featuredImage dan images edges.
    """
    if not product_node or not isinstance(product_node, dict):
        return None
    # 1. featuredImage
    feat = product_node.get("featuredImage")
    if feat and isinstance(feat, dict) and feat.get("url"):
        return feat["url"].strip()
    # 2. images edges
    images_edges = product_node.get("images", {}).get("edges", [])
    if images_edges and len(images_edges) > 0:
        first_img = images_edges[0].get("node", {}).get("url")
        if first_img:
            return first_img.strip()
    return None

def get_shopify_image_by_sku(sku, blogger_post=None):
    """
    Mencari produk di Shopify dan mengambil URL fotonya.
    """
    if not sku:
        return None
    try:
        matched_product, _, _ = find_shopify_product_and_variant(sku, blogger_post=blogger_post)
        if matched_product:
            url = extract_shopify_image_url(matched_product)
            if url:
                print(f"🛍️ Ditemukan foto jam tangan dari Shopify: {url}")
                return url
    except Exception as e:
        print(f"⚠️ Error ambil foto dari Shopify untuk SKU '{sku}': {e}")
    return None

def get_watch_photo_url(post=None, sku=None, shopify_product=None, fallback_url=None):
    """
    Mendapatkan URL foto jam tangan dengan strategi prioritas:
    1. Foto pertama Blogspot (dinormalisasi resolusi tinggi & diverifikasi HTTP 200)
    2. Jika Blogspot tidak ada / gagal diakses -> Ambil foto dari Shopify
    3. Jika masih belum ada -> Cek fallback_url (misal URL foto dari Google Sheets)
    """
    # 1. Prioritas Utama: Blogspot
    if post:
        blog_img = extract_first_image_from_post(post)
        if blog_img:
            norm_blog_img = normalize_blogger_image_url(blog_img)
            if is_image_url_accessible(norm_blog_img):
                print(f"📸 Foto jam tangan valid dari Blogspot: {norm_blog_img}")
                return norm_blog_img
            else:
                print(f"⚠️ Foto Blogspot ({norm_blog_img}) mengembalikan error HTTP. Fallback mengambil foto dari Shopify...")
        else:
            print(f"ℹ️ Postingan Blogspot tidak memuat gambar. Mengambil foto dari Shopify...")

    # 2. Prioritas Kedua: Shopify
    shopify_img = None
    if shopify_product:
        shopify_img = extract_shopify_image_url(shopify_product)

    if not shopify_img and sku:
        print(f"🔍 Mencari foto jam tangan di Shopify untuk SKU: '{sku}'...")
        shopify_img = get_shopify_image_by_sku(sku, blogger_post=post)

    if shopify_img and is_image_url_accessible(shopify_img):
        print(f"📸 Foto jam tangan berhasil diambil dari Shopify: {shopify_img}")
        return shopify_img

    # 3. Fallback: URL cadangan (misal dari Spreadsheet)
    if fallback_url:
        norm_fb = normalize_blogger_image_url(fallback_url)
        if is_image_url_accessible(norm_fb):
            print(f"📸 Foto jam tangan diambil dari fallback Spreadsheet: {norm_fb}")
            return norm_fb

    print(f"⚠️ Tidak dapat menemukan foto jam tangan yang valid dari Blogspot maupun Shopify untuk SKU '{sku}'.")
    return None

def kirim_balasan_wa(chat_id, pesan_text, image_url=None, sku=None, blogger_post=None, shopify_product=None, fallback_url=None):
    if not GREEN_API_ID_INSTANCE or not GREEN_API_API_TOKEN or "xxxx" in GREEN_API_ID_INSTANCE:
        return
    try:
        # Tentukan URL foto yang valid
        final_image_url = None
        if image_url:
            norm_url = normalize_blogger_image_url(image_url)
            if is_image_url_accessible(norm_url):
                final_image_url = norm_url
            else:
                print(f"⚠️ URL gambar ({norm_url}) tidak dapat diakses. Mencari alternatif foto...")

        # Jika belum dapat foto yang valid, cari otomatis via get_watch_photo_url
        if not final_image_url and (sku or blogger_post or shopify_product or fallback_url):
            final_image_url = get_watch_photo_url(
                post=blogger_post,
                sku=sku,
                shopify_product=shopify_product,
                fallback_url=fallback_url
            )

        sent_image = False
        if final_image_url:
            # Batasi caption maksimal 1024 karakter sesuai limit Green API sendFileByUrl
            caption_wa = pesan_text if len(pesan_text) <= 1024 else pesan_text[:1020] + "..."
            url_file = f"https://api.green-api.com/waInstance{GREEN_API_ID_INSTANCE}/sendFileByUrl/{GREEN_API_API_TOKEN}"
            payload_file = {
                "chatId": chat_id,
                "urlFile": final_image_url,
                "fileName": "watch.jpg",
                "caption": caption_wa
            }
            res = requests.post(url_file, json=payload_file, timeout=20)
            id_message = None
            if res.status_code == 200:
                try:
                    id_message = res.json().get("idMessage")
                except Exception:
                    id_message = None
                print(f"📷 Green API menerima sendFileByUrl (idMessage: {id_message}, URL: {final_image_url})")

                # Verifikasi status pengiriman jika ada idMessage
                is_failed = False
                if id_message:
                    time.sleep(1.5)
                    try:
                        url_msg = f"https://api.green-api.com/waInstance{GREEN_API_ID_INSTANCE}/getMessage/{GREEN_API_API_TOKEN}"
                        check_res = requests.post(url_msg, json={"chatId": chat_id, "idMessage": id_message}, timeout=5)
                        if check_res.status_code == 200:
                            msg_info = check_res.json()
                            status_msg = msg_info.get("statusMessage")
                            if status_msg == "failed":
                                is_failed = True
                                print(f"⚠️ Green API sendFileByUrl gagal terkirim (statusMessage: failed, idMessage: {id_message})")
                    except Exception as e_ch:
                        print(f"ℹ️ Verifikasi Green API getMessage: {e_ch}")

                if not is_failed:
                    sent_image = True
                    print(f"📷 Berhasil mengirim feedback WA beserta foto jam tangan ke {chat_id}")
                    # Jika ada teks panjang yang terpotong karena batas caption 1024 karakter, kirim sambungannya
                    if len(pesan_text) > 1024:
                        sisa_pesan = "..." + pesan_text[1020:]
                        url_txt = f"https://api.green-api.com/waInstance{GREEN_API_ID_INSTANCE}/sendMessage/{GREEN_API_API_TOKEN}"
                        requests.post(url_txt, json={"chatId": chat_id, "message": sisa_pesan}, timeout=10)
            else:
                print(f"⚠️ Green API sendFileByUrl gagal (Status {res.status_code}): {res.text}.")

            # Coba cadangan foto dari Shopify jika percobaan pertama gagal
            if not sent_image:
                shopify_backup = None
                if sku:
                    shopify_backup = get_shopify_image_by_sku(sku, blogger_post=blogger_post)
                if shopify_backup and shopify_backup != final_image_url and is_image_url_accessible(shopify_backup):
                    print(f"🔄 Mencoba mengirim ulang feedback dengan foto cadangan dari Shopify: {shopify_backup}")
                    payload_file["urlFile"] = shopify_backup
                    res_backup = requests.post(url_file, json=payload_file, timeout=20)
                    if res_backup.status_code == 200:
                        print(f"📷 Berhasil mengirim feedback WA beserta foto cadangan Shopify ke {chat_id}")
                        sent_image = True
                        if len(pesan_text) > 1024:
                            sisa_pesan = "..." + pesan_text[1020:]
                            url_txt = f"https://api.green-api.com/waInstance{GREEN_API_ID_INSTANCE}/sendMessage/{GREEN_API_API_TOKEN}"
                            requests.post(url_txt, json={"chatId": chat_id, "message": sisa_pesan}, timeout=10)
                    else:
                        print(f"⚠️ Kirim foto cadangan Shopify juga gagal: {res_backup.text}")

        # Fallback ke pesan teks biasa HANYA jika semua percobaan pengiriman gambar gagal
        if not sent_image:
            print(f"⚠️ Mengirim feedback dalam format teks biasa...")
            url = f"https://api.green-api.com/waInstance{GREEN_API_ID_INSTANCE}/sendMessage/{GREEN_API_API_TOKEN}"
            payload = {"chatId": chat_id, "message": pesan_text}
            res_txt = requests.post(url, json=payload, timeout=10)
            if res_txt.status_code == 200:
                print(f"💬 Berhasil mengirim feedback pesan teks ke {chat_id}")
            else:
                print(f"⚠️ Gagal kirim pesan teks ke Green API (Status {res_txt.status_code}): {res_txt.text}")
    except Exception as e:
        print(f"⚠️ Gagal kirim balasan WA: {e}")

def kirim_semua_foto_wa(chat_id, image_urls, sku, post_title=""):
    """
    Mengirim seluruh foto produk ke chat WhatsApp via Green API sendFileByUrl.
    """
    if not GREEN_API_ID_INSTANCE or not GREEN_API_API_TOKEN or "xxxx" in GREEN_API_ID_INSTANCE:
        return 0

    if not image_urls:
        return 0

    url_file = f"https://api.green-api.com/waInstance{GREEN_API_ID_INSTANCE}/sendFileByUrl/{GREEN_API_API_TOKEN}"
    success_count = 0
    total = len(image_urls)
    clean_sku = clean_sku_string(sku)

    # 1. Kirim pesan pengantar terlebih dahulu
    pesan_header = (
        f"📸 *FOTO PRODUK BLOGSPOT*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔢 *Kode / SKU:* {clean_sku}\n"
        f"⌚ *Judul:* {post_title or '-'}\n"
        f"🖼️ *Jumlah Foto:* {total} lembar\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"_Mengirim {total} foto ke WhatsApp..._"
    )
    url_txt = f"https://api.green-api.com/waInstance{GREEN_API_ID_INSTANCE}/sendMessage/{GREEN_API_API_TOKEN}"
    try:
        requests.post(url_txt, json={"chatId": chat_id, "message": pesan_header}, timeout=10)
    except Exception as e:
        print(f"⚠️ Gagal kirim pesan pengantar foto: {e}")

    # 2. Kirim setiap foto ke WhatsApp
    for idx, img_url in enumerate(image_urls, 1):
        try:
            caption_img = f"📸 *{clean_sku}* ({idx}/{total})\n{post_title}" if idx == 1 else f"📸 *{clean_sku}* ({idx}/{total})"
            payload_file = {
                "chatId": chat_id,
                "urlFile": img_url,
                "fileName": f"{clean_sku}_{idx}.jpg",
                "caption": caption_img[:1024]
            }
            res = requests.post(url_file, json=payload_file, timeout=25)
            if res.status_code == 200:
                success_count += 1
                print(f"   📷 WA Foto [{idx}/{total}] terkirim ke {chat_id}")
            else:
                print(f"   ⚠️ WA Foto [{idx}/{total}] gagal (Status {res.status_code}): {res.text}")
            time.sleep(0.5)
        except Exception as e:
            print(f"   ⚠️ Error kirim foto [{idx}/{total}] ke WA: {e}")

    return success_count

def extract_takedown_description_from_post(post):
    """
    Mengekstrak teks deskripsi spesifikasi jam tangan dari postingan Blogspot
    (Judul, Ref, Size, Box & Paper, Condition, Price, Code, Last Post).
    Mengabaikan data internal seperti Assets GDrive, Order Received, Form, dan Notes.
    """
    if not post:
        return ""

    content = post.get("content", "")
    if not content:
        return post.get("title", "")

    soup = BeautifulSoup(content, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for tag in soup.find_all(["div", "p", "li", "ul", "h1", "h2", "h3", "h4", "hr", "table", "tr"]):
        tag.insert_before("\n")
        tag.insert_after("\n")

    raw_lines = [re.sub(r'[\xa0\s]+', ' ', line.strip()).strip() for line in soup.get_text().split("\n") if line.strip()]

    stop_patterns = [
        r'^assets?\b',
        r'^order\s+received\b',
        r'^form\b',
        r'^notes?\b',
        r'^nama\s*:',
        r'^no\s*hp\s*:',
        r'^instagram\s*:',
        r'^[=\-_]{3,}$',
        r'^https?://'
    ]

    desc_lines = []
    for line in raw_lines:
        clean_line = line.strip()
        if not clean_line:
            continue
        # Berhenti jika mencapai data internal/link Drive/form
        if any(re.search(pat, clean_line, re.IGNORECASE) for pat in stop_patterns):
            break
        desc_lines.append(clean_line)

    if not desc_lines:
        return post.get("title", "")

    return "\n".join(desc_lines)

def extract_description_from_shopify_html(desc_html, title=""):
    """
    Mengekstrak teks deskripsi spesifikasi jam tangan dari descriptionHtml Shopify
    ketika postingan Blogspot sudah tidak tersedia (misal sudah di Trash sejak On Hold).
    """
    if not desc_html:
        return title or ""

    clean_html = re.sub(r'<!--.*?-->', '', desc_html, flags=re.DOTALL)
    soup = BeautifulSoup(clean_html, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for tag in soup.find_all(["div", "p", "li", "ul", "h1", "h2", "h3", "h4", "hr", "table", "tr"]):
        tag.insert_before("\n")
        tag.insert_after("\n")

    raw_lines = [re.sub(r'[\xa0\s]+', ' ', line.strip()).strip() for line in soup.get_text().split("\n") if line.strip()]

    stop_patterns = [
        r'^assets?\b',
        r'^order\s+received\b',
        r'^form\b',
        r'^notes?\b',
        r'^nama\s*:',
        r'^no\s*hp\s*:',
        r'^instagram\s*:',
        r'^[=\-_]{3,}$',
        r'^https?://'
    ]

    desc_lines = []
    for line in raw_lines:
        clean_line = line.strip()
        if not clean_line:
            continue
        if any(re.search(pat, clean_line, re.IGNORECASE) for pat in stop_patterns):
            break
        desc_lines.append(clean_line)

    if not desc_lines:
        return title or ""

    return "\n".join(desc_lines)

# ==============================================================================
# 3. BLOGGER SERVICE & REPRICE LOGIC
# ==============================================================================
def get_blogger_service():
    global BLOGGER_SERVICE
    if BLOGGER_SERVICE:
        return BLOGGER_SERVICE
    if not GCP_REFRESH_TOKEN or not GCP_CLIENT_ID or not GCP_CLIENT_SECRET:
        return None
    try:
        creds = Credentials(
            token=None,
            refresh_token=GCP_REFRESH_TOKEN,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=GCP_CLIENT_ID,
            client_secret=GCP_CLIENT_SECRET
        )
        BLOGGER_SERVICE = build('blogger', 'v3', credentials=creds, cache_discovery=False)
        return BLOGGER_SERVICE
    except Exception as e:
        print(f"⚠️ Error inisialisasi Blogger service: {e}")
        return None

def clean_sku_string(sku_str):
    """
    Membersihkan string SKU dari input WhatsApp:
    - Membuang teks di dalam kurung: misal '1Y53F376 (Omniluxe)' -> '1Y53F376'
    - Menghapus spasi dan tanda baca berlebih di ujung
    """
    if not sku_str:
        return ""
    cleaned = re.sub(r'\(.*?\)', '', str(sku_str))
    cleaned = cleaned.replace('\n', ' ').replace('\r', ' ')
    return cleaned.strip(" \t\n\r.,-:")

def extract_post_sku_details(post):
    """
    Mengekstrak rincian kode/SKU dan nomor referensi dari postingan Blogspot.
    Mengembalikan dict:
    - shopify_sku: dari 'SKU Shopify: ...'
    - base_sku: dari 'Code: ...'
    - owner: dari 'Code: ... (owner)'
    - resolved_sku: shopify_sku if shopify_sku else base_sku
    - ref_number: dari 'Ref. ...' (untuk safety guard anti-collision)
    - title: judul postingan
    - content: isi HTML postingan
    """
    if not post:
        return {"shopify_sku": None, "base_sku": None, "owner": None, "resolved_sku": None, "ref_number": None, "title": "", "content": ""}
    content = post.get("content", "")
    title = post.get("title", "")

    shopify_sku = None
    base_sku = None
    owner = None
    ref_number = None

    # 1. Regex langsung pada HTML
    m_shop = re.search(r'SKU\s*Shopify\s*:\s*(?:<[^>]+>|\s|&nbsp;)*([\w\-\/\.]+)', content, re.IGNORECASE)
    if m_shop:
        shopify_sku = m_shop.group(1).strip()

    m_code = re.search(r'(?:\b|>)Code\s*:\s*(?:<[^>]+>|\s|&nbsp;)*([\w\-\/\.]+)', content, re.IGNORECASE)
    if m_code:
        base_sku = m_code.group(1).strip()

    m_owner = re.search(r'(?:\b|>)Code\s*:\s*(?:<[^>]+>|\s|&nbsp;)*[\w\-\/\.]+(?:<[^>]+>|\s|&nbsp;)*\((.*?)\)', content, re.IGNORECASE)
    if m_owner:
        owner = m_owner.group(1).strip()

    m_ref = re.search(r'(?:\b|>)Ref\.?\s*:\s*(?:<[^>]+>|\s|&nbsp;)*([\w\-\/\.]+)', content, re.IGNORECASE)
    if not m_ref:
        m_ref = re.search(r'(?:\b|>)Ref\b\s*(?:<[^>]+>|\s|&nbsp;)*\.?\s*([\w\-\/\.]+)', content, re.IGNORECASE)
    if m_ref:
        ref_number = m_ref.group(1).strip()

    # 2. Fallback via strip_html_to_text
    if not shopify_sku or not base_sku or not ref_number:
        try:
            text = strip_html_to_text(content)
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            for line in lines:
                if not shopify_sku:
                    sm = re.search(r'^SKU\s*Shopify\s*:\s*([\w\-\/\.]+)', line, re.IGNORECASE)
                    if sm:
                        shopify_sku = sm.group(1).strip()
                if not base_sku:
                    cm = re.search(r'^Code\s*:\s*([\w\-\/\.]+)', line, re.IGNORECASE)
                    if cm:
                        base_sku = cm.group(1).strip()
                        om = re.search(r'\((.*?)\)', line)
                        if om and not owner:
                            owner = om.group(1).strip()
                if not ref_number:
                    rm = re.search(r'^Ref\.?\s*:\s*([\w\-\/\.]+)', line, re.IGNORECASE)
                    if not rm:
                        rm = re.search(r'^Ref\b\s*\.?\s*([\w\-\/\.]+)', line, re.IGNORECASE)
                    if rm:
                        ref_number = rm.group(1).strip()
        except Exception:
            pass

    resolved_sku = shopify_sku if shopify_sku else base_sku
    return {
        "shopify_sku": shopify_sku,
        "base_sku": base_sku,
        "owner": owner,
        "resolved_sku": resolved_sku,
        "ref_number": ref_number,
        "title": title,
        "content": content
    }

def extract_sku_from_blogger_post(post):
    """
    Mengekstrak SKU dan nama owner dari isi postingan Blogspot jika ada.
    Jika postingan memiliki catatan 'SKU Shopify: [sku]', SKU tersebut diutamakan sebagai canonical SKU.
    """
    if not post:
        return None, None
    details = extract_post_sku_details(post)
    return details.get("resolved_sku"), details.get("owner")

def check_blogger_post_sku_match(post_details, target_sku):
    """
    Memeriksa apakah postingan Blogger BENAR-BENAR memiliki Code atau SKU Shopify yang cocok dengan target_sku.
    Mengembalikan (is_match: bool, score: int, matched_via: str).
    JIKA target_sku hanya cocok sebagai nomor referensi jam tangan (misal '703' di 'Ref. 703.OM...'):
    MUTLAK DITOLAK demi mencegah false takedown!
    """
    if not post_details or not target_sku:
        return False, 0, ""

    clean_target = clean_sku_string(target_sku).upper()
    base_target = re.sub(r'-\d+$', '', clean_target).upper()

    shopify_sku = (post_details.get("shopify_sku") or "").strip().upper()
    base_sku = (post_details.get("base_sku") or "").strip().upper()
    resolved_sku = (post_details.get("resolved_sku") or "").strip().upper()
    ref_number = (post_details.get("ref_number") or "").strip().upper()

    # Kumpulkan semua kandidat SKU resmi dari postingan
    post_skus = []
    if shopify_sku:
        post_skus.append((shopify_sku, "shopify_sku", 100))
    if base_sku and base_sku != shopify_sku:
        post_skus.append((base_sku, "base_sku", 90))
    if resolved_sku and resolved_sku not in [shopify_sku, base_sku]:
        post_skus.append((resolved_sku, "resolved_sku", 85))

    best_match = False
    best_score = 0
    best_via = ""

    for p_sku, sku_type, base_weight in post_skus:
        p_base = re.sub(r'-\d+$', '', p_sku)

        # 1. Exact Match pada Code / SKU Shopify
        if p_sku == clean_target:
            score = base_weight + 50
            if score > best_score:
                best_match, best_score, best_via = True, score, f"exact_{sku_type}"

        # 2. Base SKU Match (misal target 703 vs post 703-1 atau target 703-1 vs post 703)
        elif p_base == base_target and base_target:
            score = base_weight + 30
            if score > best_score:
                best_match, best_score, best_via = True, score, f"base_counter_{sku_type}"

        # 3. Slash Part Match (misal serial movement/case)
        elif "/" in p_sku or "/" in clean_target:
            p_parts = [p.strip() for p in p_sku.split('/') if p.strip()]
            t_parts = [p.strip() for p in clean_target.split('/') if p.strip()]
            if any(tp in p_parts for tp in t_parts) or any(pp in t_parts for pp in p_parts):
                score = base_weight + 20
                if score > best_score:
                    best_match, best_score, best_via = True, score, f"slash_part_{sku_type}"

        # 4. Normalized Alphanumeric Match
        elif re.sub(r'[^A-Z0-9]', '', p_sku) == re.sub(r'[^A-Z0-9]', '', clean_target) and len(clean_target) >= 3:
            score = base_weight + 10
            if score > best_score:
                best_match, best_score, best_via = True, score, f"normalized_{sku_type}"

    # REJECTION GUARD: Jika target_sku tidak cocok dengan SKU apa pun di atas,
    # tapi ada substring match di ref_number (seperti '703' di '703.OM.6912.HR.FMC12'):
    # Ini 100% false positive! MUTLAK DITOLAK!
    if not best_match and ref_number and clean_target in ref_number:
        return False, 0, f"rejected_ref_number_collision({ref_number})"

    return best_match, best_score, best_via

def find_blogger_post_by_code(service, code, include_drafts=True, expected_title=None):
    """
    Mencari postingan Blogspot berdasarkan SKU / Code dengan Multi-Candidate Filtering ketat:
    1. Hanya menerima postingan yang Code atau SKU Shopify-nya benar-benar cocok.
    2. Menolak kecocokan palsu dari Ref. Number, teks tahun, ukuran diameter, atau harga.
    3. Memprioritaskan postingan yang merek/judulnya konsisten dengan expected_title (Shopify).
    4. Menolak postingan yang benturan merek keras (misal Blogspot HUBLOT vs Shopify FRANCK MULLER).
    5. Mengembalikan None jika tidak ada kandidat yang valid (tidak pernah return sembarang item).
    """
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

    matched_candidates = []
    seen_post_ids = set()

    # 1. Cari di postingan yang LIVE / Terbit
    for cand in search_candidates:
        search_queries = [cand]
        if len(cand) <= 6:
            search_queries.append(f'"{cand}"')
            search_queries.append(f'Code: {cand}')

        for q_str in search_queries:
            try:
                res = service.posts().search(blogId=BLOG_ID, q=q_str).execute()
                items = res.get("items", [])
                for item in items:
                    p_id = item.get("id")
                    if p_id in seen_post_ids:
                        continue

                    details = extract_post_sku_details(item)
                    is_match, score, matched_via = check_blogger_post_sku_match(details, clean_code)
                    if not is_match:
                        continue

                    # Evaluasi brand conflict jika expected_title diberikan
                    item_title = item.get("title", "")
                    if expected_title:
                        conflict, b1, b2 = is_brand_conflict(item_title, expected_title)
                        if conflict:
                            print(f"⚠️ Melewati postingan '{item_title}' karena benturan merek ({b1} vs {b2}) dengan '{expected_title}'")
                            continue

                        # Bonus kesesuaian kata judul
                        clean_item_t = re.sub(r'\[.*?\]', '', item_title).upper()
                        clean_exp_t = re.sub(r'\[.*?\]', '', expected_title).upper()
                        exp_words = [w for w in re.split(r'[^A-Z0-9]+', clean_exp_t) if len(w) >= 3]
                        if exp_words:
                            matched_words = [w for w in exp_words if w in clean_item_t]
                            score += int((len(matched_words) / len(exp_words)) * 50)

                    # Prioritas status LIVE
                    if str(item.get("status", "LIVE")).upper() == "LIVE":
                        score += 30

                    seen_post_ids.add(p_id)
                    matched_candidates.append({
                        "item": item,
                        "score": score,
                        "matched_via": matched_via,
                        "details": details
                    })
            except Exception as e:
                print(f"⚠️ Error search Blogger post ({q_str}): {e}")

        if matched_candidates:
            break

    if matched_candidates:
        matched_candidates.sort(key=lambda x: x["score"], reverse=True)
        best = matched_candidates[0]
        print(f"✅ Ditemukan postingan Blogspot untuk SKU '{code}': '{best['item'].get('title')}' (Skor: {best['score']}, Via: {best['matched_via']})")
        return best["item"]

    # 2. Fallback: Cari di postingan DRAFT
    if include_drafts:
        try:
            draft_res = service.posts().list(blogId=BLOG_ID, status=['DRAFT'], maxResults=50).execute()
            draft_items = draft_res.get("items", [])
            draft_candidates = []
            for item in draft_items:
                p_id = item.get("id")
                if p_id in seen_post_ids:
                    continue

                details = extract_post_sku_details(item)
                is_match, score, matched_via = check_blogger_post_sku_match(details, clean_code)
                if not is_match:
                    continue

                item_title = item.get("title", "")
                if expected_title:
                    conflict, b1, b2 = is_brand_conflict(item_title, expected_title)
                    if conflict:
                        continue

                draft_candidates.append({
                    "item": item,
                    "score": score,
                    "matched_via": matched_via,
                    "details": details
                })

            if draft_candidates:
                draft_candidates.sort(key=lambda x: x["score"], reverse=True)
                best_draft = draft_candidates[0]
                print(f"ℹ️ Ditemukan postingan Blogspot DRAFT untuk SKU '{code}': '{best_draft['item'].get('title')}'")
                return best_draft["item"]
        except Exception as e:
            print(f"⚠️ Error list Blogger drafts: {e}")

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

        # 1. Update Labels: Hapus NEW ARRIVAL dan REPOST, Tambahkan REPRICE
        new_labels = [l for l in current_labels if l.strip().upper() not in ["NEW ARRIVAL", "REPOST"]]
        if not any(l.strip().upper() == "REPRICE" for l in new_labels):
            new_labels.append("REPRICE")

        is_consign_ps = any("CONSIGNMENT_PS" in l.upper() or "CONSINGMENT_PS" in l.upper() for l in current_labels)
        is_consign_po = any("CONSIGNMENT_PO" in l.upper() or "CONSINGMENT_PO" in l.upper() for l in current_labels)
        is_featured = any("FEATURED" in l.upper() for l in current_labels)

        # 2. Update HTML Konten (Harga)
        updated_html = current_html

        # a. Pulihkan Retail Price jika sebelumnya pernah salah dicoret / disisipkan Reprice
        updated_html = re.sub(
            r'(\bRetail\s*(?:<[^>]+>)*\s*Price\s*(?:<[^>]+>)*\s*:[^\n<]*?)\s*(?:<br\s*/?>|\n)?\s*(?:<span[^>]*>)?\s*Reprice\s*:\s*.*?(?=(?:</span>\s*)?</div>|</p|<br\s*/?>|\n|$)',
            r'\1',
            updated_html,
            flags=re.IGNORECASE
        )
        updated_html = re.sub(
            r'(\bRetail\s*(?:<(?:b\b|strong\b|span\b)[^>]*>)?\s*Price\s*(?:</(?:b\b|strong\b|span\b)>)?\s*:\s*)<(?:strike|s)>(.*?)</(?:strike|s)>',
            r'\1\2',
            updated_html,
            flags=re.IGNORECASE
        )

        # b. Bersihkan Reprice sebelumnya jika berada di container div / separator tersendiri
        updated_html = re.sub(
            r'<div[^>]*class=["\']separator["\'][^>]*>\s*(?:<strike>)?\s*(?:<span[^>]*>)?\s*Reprice\s*:.*?</div>',
            '',
            updated_html,
            flags=re.IGNORECASE | re.DOTALL
        )
        updated_html = re.sub(
            r'<div[^>]*>\s*(?:<strike>)?\s*(?:<span[^>]*>)?\s*Reprice\s*:.*?</div>',
            '',
            updated_html,
            flags=re.IGNORECASE | re.DOTALL
        )
        # Bersihkan Reprice inline jika masih ada di luar blok Price
        updated_html = re.sub(
            r'(?:<br\s*/?>|\n)\s*(?:<span[^>]*>)?\s*Reprice\s*:\s*.*?(?=(?:</span>\s*)?</div>|</p|<br\s*/?>|<span><!--more-->|<!--more-->|\n|$)',
            '',
            updated_html,
            flags=re.IGNORECASE
        )
        # Bersihkan sisa tag strike kosong atau more yang terpotong dari reprice lama
        updated_html = re.sub(r'<strike>\s*(?:<br\s*/?>)?\s*</strike>', '', updated_html, flags=re.IGNORECASE)
        updated_html = re.sub(r'<span[^>]*>\s*<strike>\s*<span><!--more--></span>\s*</strike>\s*</span>', '', updated_html, flags=re.IGNORECASE)

        # c. Cari blok 'Price:' yang BENAR (Bukan Retail Price, dan bukan Reprice)
        # Mengabaikan Retail Price dan hanya fokus pada teks Price jual utama
        price_pattern = re.compile(
            r'(?P<full_match>(?:<(?:b\b|strong\b|span\b)[^>]*>\s*)*\bPrice\b\s*(?:</(?:b\b|strong\b|span\b)>\s*)*:\s*(?P<val>.*?))(?=(?:<span>\s*)?<!--more-->|<!--more-->|(?:</span>\s*)?</div>|</p|<br\s*/?>|\n|$)',
            re.IGNORECASE
        )

        matched_span = None
        old_price_text = ""

        for m in price_pattern.finditer(updated_html):
            start = m.start()
            preceding = updated_html[:start]
            last_boundary = max(
                preceding.rfind('\n'),
                preceding.rfind('<div'),
                preceding.rfind('<p'),
                preceding.rfind('<br'),
                preceding.rfind('<li>'),
                preceding.rfind('<tr>'),
                0
            )
            line_context = preceding[last_boundary:start]
            # Abaikan jika ada tulisan 'retail' pada baris / container sebelum Price
            if re.search(r'\bretail\b', line_context, re.IGNORECASE):
                continue

            matched_span = m.span('full_match')
            raw_val = m.group('val')

            strike_m = re.search(r'<(?:strike|s)>(.*?)</(?:strike|s)>', raw_val, re.IGNORECASE)
            target_val = strike_m.group(1) if strike_m else raw_val
            clean_text = re.sub(r'<[^>]+>', '', target_val)
            clean_text = clean_text.replace('&nbsp;', ' ').strip()
            curr_m = re.search(r'(?:Rp\.?|IDR)?\s*[\d\.,]+', clean_text, re.IGNORECASE)
            if curr_m:
                raw_old = curr_m.group(0).strip()
                old_num = parse_price(raw_old)
                if old_num > 0:
                    old_price_text = format_rupiah(old_num)
                else:
                    old_price_text = raw_old
                    if not old_price_text.upper().startswith("RP") and not old_price_text.upper().startswith("IDR"):
                        old_price_text = "Rp " + old_price_text
            else:
                old_num = parse_price(clean_text) if clean_text else 0
                if old_num > 0:
                    old_price_text = format_rupiah(old_num)
                else:
                    old_price_text = clean_text or formatted_price
            break

        if not old_price_text:
            old_price_text = formatted_price

        # Pastikan formatted_price menggunakan pemisah ribuan koma secara konsisten (misal: Rp 120,000,000)
        num_check = parse_price(formatted_price)
        if num_check > 0:
            formatted_price = format_rupiah(num_check)

        # d. Terapkan penggantian seluruh blok harga (Price yang sah)
        if command_type == "REPRICE":
            replacement = f"Price: <strike>{old_price_text}</strike><br/>Reprice: <b>{formatted_price}</b>"
        else: # HARGA_BARU
            replacement = f"Price: {formatted_price}"

        if matched_span:
            start_idx, end_idx = matched_span
            updated_html = updated_html[:start_idx] + replacement + updated_html[end_idx:]
        else:
            if command_type == "REPRICE":
                updated_html += f"<br/>Price: <strike>{formatted_price}</strike><br/>Reprice: <b>{formatted_price}</b>"
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
            "publish_date": formatted_prev_date,
            "is_consign_ps": is_consign_ps,
            "is_consign_po": is_consign_po,
            "is_featured": is_featured,
            "labels": res.get("labels", []),
            "published": res.get("published", "")
        }
    except Exception as e:
        print(f"⚠️ Error update Blogger post: {e}")
        return {"status": "error", "message": str(e), "is_consign_ps": False, "is_consign_po": False, "is_featured": False}

def delete_blogger_post(service, post):
    """
    Menghapus postingan di Blogspot berdasarkan objek post dan memindahkannya ke Sampah (Trash).
    """
    if not service or not BLOG_ID or not post:
        return {"status": "skipped", "message": "Blogger service atau data postingan tidak tersedia"}

    post_id = post.get("id")
    post_title = post.get("title", "")
    publish_date = format_published_date(post.get("published", ""))
    post_status = post.get("status", "LIVE")

    # Jika postingan sudah berstatus DRAFT (sudah pernah dipindahkan ke sampah sebelumnya)
    if str(post_status).upper() == "DRAFT":
        print(f"ℹ️ Postingan Blogspot '{post_title}' sudah berada di Sampah / Trash (Status DRAFT).")
        return {
            "status": "success",
            "post_title": post_title,
            "publish_date": publish_date,
            "post_id": post_id,
            "in_trash": True,
            "already_in_trash": True
        }

    try:
        # Gunakan useTrash=True agar postingan dipindahkan ke folder Sampah (Trash), bukan dihapus permanen
        service.posts().delete(blogId=BLOG_ID, postId=post_id, useTrash=True).execute()
        print(f"🗑️ Berhasil memindahkan postingan Blogspot ke Trash: '{post_title}' (ID: {post_id}, Publish Date: {publish_date})")
        return {
            "status": "success",
            "post_title": post_title,
            "publish_date": publish_date,
            "post_id": post_id,
            "in_trash": True
        }
    except Exception as e:
        print(f"⚠️ Error memindahkan postingan Blogger ke Trash: {e}")
        return {"status": "error", "message": str(e), "post_title": post_title, "publish_date": publish_date}

def update_blogger_repost(service, post):
    """
    Melakukan update postingan di Blogspot untuk perintah REPOST:
    1. Update Labels: Hapus NEW ARRIVAL, Tambahkan REPOST.
    2. Update HTML: Catat / perbarui 'Last Post: [tanggal sebelum update]'.
       (Harga TIDAK diubah).
    3. Patch ke Blogger API: Setel tanggal dipublikasikan ke waktu sekarang.
    """
    try:
        post_id = post["id"]
        current_html = post.get("content", "")
        current_labels = post.get("labels", [])

        # Ambil tanggal terakhir postingan sebelum update dilakukan
        original_published_str = post.get("published", "")
        formatted_prev_date = format_published_date(original_published_str)

        # 1. Update Labels: Hapus NEW ARRIVAL dan REPRICE, Tambahkan REPOST
        new_labels = [l for l in current_labels if l.strip().upper() not in ["NEW ARRIVAL", "REPRICE", "REPOST"]]
        new_labels.append("REPOST")

        is_consign_ps = any("CONSIGNMENT_PS" in l.upper() or "CONSINGMENT_PS" in l.upper() for l in current_labels)
        is_consign_po = any("CONSIGNMENT_PO" in l.upper() or "CONSINGMENT_PO" in l.upper() for l in current_labels)

        # 2. Update HTML Konten: Update atau Tambahkan 'Last Post: [tanggal sebelumnya]'
        updated_html = current_html
        if formatted_prev_date:
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
            "publish_date": formatted_prev_date,
            "new_publish_date": format_published_date(published_timestamp),
            "is_consign_ps": is_consign_ps,
            "is_consign_po": is_consign_po,
            "labels": res.get("labels", []),
            "published": res.get("published", "")
        }
    except Exception as e:
        print(f"⚠️ Error update Blogger repost: {e}")
        return {"status": "error", "message": str(e), "is_consign_ps": False, "is_consign_po": False}

def download_all_images_from_blogspot(sku, output_dir=None, post=None):
    """
    Mendownload semua gambar produk dari postingan Blogspot berdasarkan SKU/Kode produk.
    Menyimpan file ke output_dir (default: 'downloaded_images/<clean_sku>').
    Mengembalikan dict berisi status, daftar path file lokal, dan daftar URL gambar.
    """
    if not sku:
        return {"status": "error", "message": "SKU tidak boleh kosong", "sku": "", "image_urls": [], "downloaded_files": []}

    service = get_blogger_service()
    if not post and service:
        post = find_blogger_post_by_code(service, sku)

    if not post:
        return {
            "status": "not_found",
            "sku": sku,
            "message": f"Postingan dengan kode {sku} tidak ditemukan di Blogspot.",
            "image_urls": [],
            "downloaded_files": []
        }

    image_urls = extract_all_images_from_post(post)
    post_title = post.get("title", "")
    publish_date = format_published_date(post.get("published", ""))

    if not image_urls:
        return {
            "status": "no_images",
            "sku": sku,
            "post_title": post_title,
            "publish_date": publish_date,
            "message": f"Tidak ditemukan gambar pada postingan '{post_title}'.",
            "image_urls": [],
            "downloaded_files": []
        }

    clean_sku = re.sub(r'[^\w\-]', '_', clean_sku_string(sku))
    if not output_dir:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        output_dir = os.path.join(base_dir, "downloaded_images", clean_sku)

    os.makedirs(output_dir, exist_ok=True)

    downloaded_files = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
    }

    print(f"📥 Memulai download {len(image_urls)} gambar untuk SKU '{sku}' ke folder: {output_dir}")

    for idx, url in enumerate(image_urls, 1):
        filename = f"{clean_sku}_{idx}.jpg"
        filepath = os.path.join(output_dir, filename)

        # Kandidat resolusi URL untuk keandalan download
        candidates = [url]
        if '/s1600/' in url:
            candidates.append(url.replace('/s1600/', '/s0/'))
        elif '/s0/' in url:
            candidates.append(url.replace('/s0/', '/s1600/'))

        download_success = False
        for cand_url in candidates:
            try:
                res = requests.get(cand_url, headers=headers, timeout=30)
                if res.status_code == 200 and len(res.content) > 0:
                    with open(filepath, 'wb') as f:
                        f.write(res.content)
                    downloaded_files.append(filepath)
                    download_success = True
                    print(f"   ✅ [{idx}/{len(image_urls)}] Tersimpan: {filename} ({len(res.content)} bytes)")
                    break
            except Exception as e:
                print(f"   ⚠️ Gagal download {cand_url}: {e}")

        if not download_success:
            print(f"   ❌ Gagal mendownload gambar {idx} dari semua kandidat URL.")

    return {
        "status": "success",
        "sku": sku,
        "post_title": post_title,
        "publish_date": publish_date,
        "total_images": len(image_urls),
        "total_downloaded": len(downloaded_files),
        "image_urls": image_urls,
        "downloaded_files": downloaded_files,
        "output_dir": output_dir,
        "post": post
    }

# ==============================================================================
# 4. SHOPIFY GRAPHQL REPRICE LOGIC
# ==============================================================================
def get_shopify_token(force_refresh=False):
    global SHOPIFY_ACCESS_TOKEN, SHOPIFY_TOKEN_EXPIRY
    now = time.time()
    if not force_refresh and SHOPIFY_ACCESS_TOKEN and now < (SHOPIFY_TOKEN_EXPIRY - 600):
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
            data = tok_res.json()
            SHOPIFY_ACCESS_TOKEN = data.get("access_token")
            expires_in = int(data.get("expires_in", 86399))
            SHOPIFY_TOKEN_EXPIRY = now + expires_in
            print(f"🔄 Berhasil memperbarui access token Shopify baru (berlaku {expires_in} detik).")
            return SHOPIFY_ACCESS_TOKEN
        else:
            print(f"⚠️ Gagal request token Shopify: HTTP {tok_res.status_code} - {tok_res.text}")
    except Exception as e:
        print(f"⚠️ Error get Shopify token: {e}")
    return None

def score_shopify_candidate(p_node, vn, clean_input_sku, base_input_sku, canonical_sku, blogger_post=None):
    """
    Menghitung skor kecocokan kandidat produk Shopify.
    Prioritas Utama:
    1. Produk ACTIVE di etalase live (skor +10000) dibanding produk DRAFT/arsip lama.
    2. Stok > 0 (skor +3000).
    3. Kecocokan Base SKU dan varian counter (-1, -2, dll).
    4. Tanggal pembuatan produk (produk tahun 2026 lebih relevan dibanding 2025).
    5. Kesamaan tanggal publish Blogspot dengan tanggal dibuat di Shopify (+4000).
    6. Kesamaan judul jam tangan antara Blogspot dan Shopify.
    """
    score = 0
    v_sku = (vn.get("sku") or "").strip().upper()
    v_base = re.sub(r'-\d+$', '', v_sku)
    input_upper = clean_input_sku.upper()
    base_upper = base_input_sku.upper()
    status = (p_node.get("status") or "").strip().upper()
    stock = vn.get("inventoryQuantity") or 0
    created_at = p_node.get("createdAt") or ""
    title = (p_node.get("title") or "").strip().upper()

    # 1. STATUS BONUS (Active vs Draft vs Archived)
    # Operasi (SOLD / ON HOLD / TAKEDOWN / REPRICE) memprioritaskan produk ACTIVE yang sedang live di web
    if status == "ACTIVE":
        score += 10000
    elif status == "DRAFT":
        score += 0
    elif status == "ARCHIVED":
        score -= 2000

    # 2. STOK INVENTARIS
    if stock > 0:
        score += 3000
        score += min(stock, 5) * 50

    # 3. KECOCOKAN BASE SKU
    if v_base == base_upper:
        score += 3000
    elif canonical_sku and v_base == re.sub(r'-\d+$', '', clean_sku_string(canonical_sku)).upper():
        score += 2500

    # 4. KECOCOKAN EKSPLISIT INPUT USER
    counter_match = re.search(r'-(\d+)$', v_sku)
    input_has_counter = bool(re.search(r'-(\d+)$', input_upper))

    if v_sku == input_upper:
        if input_has_counter:
            # Jika user secara eksplisit mengetikkan counter persis (misal 136V34W8-1)
            # Berikan bobot mutlak (+50000) agar langsung terpilih dan tidak terdistraksi varian lain
            score += 50000
        else:
            # User ketik base SKU polos: hanya beri bonus kecil (+100) sebagai baseline
            # agar varian counter baru (-1, -2, dll) dapat mengungguli produk lama polos
            score += 100

    # 5. COUNTER SUFFIX BONUS (-1, -2, -3...)
    if counter_match:
        counter_val = int(counter_match.group(1))
        # Jika user hanya ketik base SKU polos (misal 136V34W8):
        # Varian dengan counter (-1, -2, -3...) menandakan iterasi/generasi produk yang LEBIH BARU
        # Berikan prioritas sangat tinggi (+8000 + counter_val * 1000) agar selalu mengalahkan produk lama tanpa strip
        if not input_has_counter:
            score += 8000 + (counter_val * 1000)
        else:
            # Jika user ketik SKU counter tertentu tapi bukan yang ini
            score += counter_val * 200

    # 6. RECENCY BONUS (Berdasarkan createdAt produk di Shopify)
    # Bobot diperbesar (x10) agar produk tahun terbaru (misal 2026 vs 2025/2024) unggul signifikan
    if created_at and len(created_at) >= 10:
        try:
            year_val = int(created_at[:4])
            month_val = int(created_at[5:7])
            day_val = int(created_at[8:10])
            days_num = year_val * 365 + month_val * 30 + day_val
            score += days_num * 10
        except Exception:
            pass

    # 7. KORELASI DENGAN POSTINGAN BLOGGER
    if blogger_post:
        # A. Tanggal dibuat di Shopify sama persis dengan tanggal terbit Blogspot
        blog_pub = blogger_post.get("published", "")
        if blog_pub and created_at and blog_pub[:10] == created_at[:10]:
            score += 4000

        # B. Kemiripan Judul
        blog_title = (blogger_post.get("title") or "").upper()
        clean_blog_title = re.sub(r'\[.*?\]', '', blog_title)
        clean_blog_title = re.sub(r'\s*\(\d{4}\)', '', clean_blog_title).strip()
        words = [w for w in re.split(r'[^A-Z0-9]+', clean_blog_title) if len(w) >= 3]
        if words:
            matching_words = [w for w in words if w in title]
            if matching_words:
                score += int((len(matching_words) / len(words)) * 2000)

    return score


def find_shopify_product_and_variant(sku, blogger_post=None):
    """
    Mencari Product dan Variant di Shopify menggunakan strategi Multi-Candidate Ranking:
    1. Query GraphQL mencari SKU persis dan Wildcard (sku:SKU*) untuk mencakup counter (-1, -2, dll).
    2. Mengumpulkan seluruh kandidat yang cocok dengan Base SKU.
    3. Memberi ranking cerdas via score_shopify_candidate:
       - Memprioritaskan produk ACTIVE ketimbang produk DRAFT lama (seperti produk 2025).
       - Memprioritaskan produk yang memiliki stok > 0.
       - Memprioritaskan produk yang dibuat pada tanggal yang sama dengan artikel Blogspot.
       - Memprioritaskan varian counter terbaru (-1, -2).
    4. Fallback ke Cross-Reference Judul Blogspot jika SKU tidak ditemukan sama sekali.
    """
    token = get_shopify_token()
    if not token:
        return None, None, None

    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
    graphql_url = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{API_VERSION}/graphql.json"

    clean_input_sku = clean_sku_string(sku)
    base_input_sku = re.sub(r'-\d+$', '', clean_input_sku)
    canonical_sku, _ = extract_sku_from_blogger_post(blogger_post) if blogger_post else (None, None)

    search_queries = []
    # 1. Wildcard query pada base SKU: otomatis menjaring SKU polos maupun varian bertanda -1, -2
    if base_input_sku:
        search_queries.append(f"sku:{base_input_sku}*")
        if "/" in base_input_sku or " " in base_input_sku or "-" in base_input_sku:
            search_queries.append(f"sku:'{base_input_sku}*'")

    # 2. Query persis input SKU
    if clean_input_sku:
        if f"sku:{clean_input_sku}" not in search_queries:
            search_queries.append(f"sku:{clean_input_sku}")
        if "/" in clean_input_sku or " " in clean_input_sku or "-" in clean_input_sku:
            search_queries.append(f"sku:'{clean_input_sku}'")

    # 3. Canonical SKU dari Blogspot
    if canonical_sku:
        clean_canonical = clean_sku_string(canonical_sku)
        base_canonical = re.sub(r'-\d+$', '', clean_canonical)
        if f"sku:{base_canonical}*" not in search_queries:
            search_queries.append(f"sku:{base_canonical}*")
        if f"sku:{clean_canonical}" not in search_queries:
            search_queries.append(f"sku:{clean_canonical}")

    # 4. Serial ganda dengan garis miring (movement/case)
    if "/" in clean_input_sku:
        slash_parts = [p.strip() for p in clean_input_sku.split('/') if p.strip()]
        for sp in slash_parts:
            sp_base = re.sub(r'-\d+$', '', sp)
            if f"sku:{sp_base}*" not in search_queries:
                search_queries.append(f"sku:{sp_base}*")
            if f"sku:{sp}" not in search_queries:
                search_queries.append(f"sku:{sp}")

    product_query_with_sort = """
    query getProducts($query: String!) {
      products(first: 25, query: $query, sortKey: CREATED_AT, reverse: true) {
        edges {
          node {
            id
            title
            descriptionHtml
            status
            createdAt
            updatedAt
            featuredImage {
              url
            }
            images(first: 2) {
              edges {
                node {
                  url
                }
              }
            }
            variants(first: 20) {
              edges {
                node {
                  id
                  sku
                  price
                  compareAtPrice
                  inventoryItem {
                    id
                  }
                  inventoryQuantity
                }
              }
            }
          }
        }
      }
    }
    """

    product_query_simple = """
    query getProducts($query: String!) {
      products(first: 25, query: $query) {
        edges {
          node {
            id
            title
            descriptionHtml
            status
            createdAt
            updatedAt
            featuredImage {
              url
            }
            images(first: 2) {
              edges {
                node {
                  url
                }
              }
            }
            variants(first: 20) {
              edges {
                node {
                  id
                  sku
                  price
                  compareAtPrice
                  inventoryItem {
                    id
                  }
                  inventoryQuantity
                }
              }
            }
          }
        }
      }
    }
    """

    candidates = []
    seen_variant_ids = set()

    for q in search_queries:
        try:
            res = requests.post(graphql_url, headers=headers, json={"query": product_query_with_sort, "variables": {"query": q}}, timeout=20)
            if res.status_code == 401:
                print("🔄 Token Shopify expired (401). Memperbarui token...")
                token = get_shopify_token(force_refresh=True)
                if token:
                    headers["X-Shopify-Access-Token"] = token
                    res = requests.post(graphql_url, headers=headers, json={"query": product_query_with_sort, "variables": {"query": q}}, timeout=20)

            data = res.json() if res.status_code == 200 else {}
            # Fallback jika query dengan sortKey tidak didukung
            if "errors" in data or res.status_code != 200:
                res = requests.post(graphql_url, headers=headers, json={"query": product_query_simple, "variables": {"query": q}}, timeout=20)
                data = res.json() if res.status_code == 200 else {}

            edges = data.get("data", {}).get("products", {}).get("edges", [])
            for p_edge in edges:
                p_node = p_edge["node"]
                for v_edge in p_node.get("variants", {}).get("edges", []):
                    vn = v_edge["node"]
                    v_id = vn.get("id")
                    if v_id in seen_variant_ids:
                        continue

                    v_sku = (vn.get("sku") or "").strip().upper()
                    v_base = re.sub(r'-\d+$', '', v_sku)

                    is_match = False
                    method = "wildcard"
                    if v_sku == clean_input_sku.upper():
                        is_match = True
                        method = "exact_sku"
                    elif v_base == base_input_sku.upper():
                        is_match = True
                        method = "base_sku_with_counter"
                    elif canonical_sku and v_sku == clean_sku_string(canonical_sku).upper():
                        is_match = True
                        method = "canonical_sku"
                    elif canonical_sku and v_base == re.sub(r'-\d+$', '', clean_sku_string(canonical_sku)).upper():
                        is_match = True
                        method = "canonical_base_sku"
                    elif re.sub(r'[^A-Z0-9]', '', v_sku) == re.sub(r'[^A-Z0-9]', '', clean_input_sku.upper()):
                        is_match = True
                        method = "normalized_sku"
                    elif "/" in clean_input_sku or "/" in v_sku:
                        input_parts = [p.strip().upper() for p in clean_input_sku.split('/') if p.strip()]
                        v_parts = [p.strip().upper() for p in v_sku.split('/') if p.strip()]
                        if any(ip in v_parts or ip == v_sku for ip in input_parts) or any(vp in input_parts or vp == clean_input_sku.upper() for vp in v_parts):
                            is_match = True
                            method = "slash_part_sku"

                    if is_match:
                        seen_variant_ids.add(v_id)
                        cand_score = score_shopify_candidate(p_node, vn, clean_input_sku, base_input_sku, canonical_sku, blogger_post)
                        candidates.append({
                            "score": cand_score,
                            "product": p_node,
                            "variant": vn,
                            "method": method
                        })
        except Exception as e:
            print(f"⚠️ Error search Shopify with query '{q}': {e}")

        # Jika query wildcard/exact ini sudah menemukan kandidat, hentikan iterasi query berikutnya
        if candidates:
            break

    # Level Fallback: Cross-Reference Judul dari Blogspot jika via SKU masih belum ketemu sama sekali
    if not candidates and blogger_post:
        post_title = blogger_post.get("title", "")
        clean_title = re.sub(r'\[.*?\]', '', post_title).strip()
        search_title = re.sub(r'\s*\(\d{4}\)', '', clean_title).strip()
        if search_title:
            print(f"🔄 SKU '{sku}' tidak ditemukan via pencarian SKU Shopify. Mencoba Cross-Reference Judul Blogspot: '{search_title}'...")
            try:
                t_query = f"title:\"{search_title}\""
                res = requests.post(graphql_url, headers=headers, json={"query": product_query_with_sort, "variables": {"query": t_query}}, timeout=20)
                if res.status_code == 401:
                    token = get_shopify_token(force_refresh=True)
                    if token:
                        headers["X-Shopify-Access-Token"] = token
                        res = requests.post(graphql_url, headers=headers, json={"query": product_query_with_sort, "variables": {"query": t_query}}, timeout=20)

                data = res.json() if res.status_code == 200 else {}
                if "errors" in data or res.status_code != 200:
                    res = requests.post(graphql_url, headers=headers, json={"query": product_query_simple, "variables": {"query": t_query}}, timeout=20)
                    data = res.json() if res.status_code == 200 else {}

                edges = data.get("data", {}).get("products", {}).get("edges", [])
                for p_edge in edges:
                    p_node = p_edge["node"]
                    for v_edge in p_node.get("variants", {}).get("edges", []):
                        vn = v_edge["node"]
                        cand_score = score_shopify_candidate(p_node, vn, clean_input_sku, base_input_sku, canonical_sku, blogger_post)
                        candidates.append({
                            "score": cand_score,
                            "product": p_node,
                            "variant": vn,
                            "method": "blogger_title_crossref"
                        })
            except Exception as e:
                print(f"⚠️ Error search Shopify via title: {e}")

    # Pilih kandidat dengan skor tertinggi
    matched_product = None
    matched_variant = None
    matched_method = None

    if candidates:
        candidates.sort(key=lambda x: x["score"], reverse=True)
        best = candidates[0]
        matched_product = best["product"]
        matched_variant = best["variant"]
        matched_method = best["method"]
        print(f"🎯 Terpilih produk Shopify terbaik: '{matched_product.get('title')}' (SKU: {matched_variant.get('sku')}, Status: {matched_product.get('status')}, Stock: {matched_variant.get('inventoryQuantity')}, Created: {matched_product.get('createdAt')}) - Metode: {matched_method} (Score: {best['score']})")
        if len(candidates) > 1:
            other_summaries = [f"SKU: {c['variant'].get('sku')}, Status: {c['product'].get('status')}, Stock: {c['variant'].get('inventoryQuantity')}, Score: {c['score']}" for c in candidates[1:]]
            print(f"ℹ️ Kandidat lain yang diabaikan: {other_summaries}")

    return matched_product, matched_variant, matched_method

def update_shopify_reprice(sku, command_type, numeric_price, blogger_post=None):
    token = get_shopify_token()
    if not token:
        return {"status": "error", "message": "Gagal mendapatkan access token Shopify"}

    matched_product, matched_variant, matched_method = find_shopify_product_and_variant(sku, blogger_post=blogger_post)
    if not matched_variant or not matched_product:
        return {"status": "not_found", "message": f"Produk dengan SKU '{sku}' tidak ditemukan di Shopify (sudah dicoba variasi SKU & cross-reference)."}

    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
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
                "compare_at_price": updated_compare,
                "photo_url": extract_shopify_image_url(matched_product),
                "product_node": matched_product
            }
        else:
            print(f"⚠️ Gagal update harga Shopify (HTTP {put_res.status_code}): {put_res.text}")
            return {"status": "error", "message": f"Shopify HTTP {put_res.status_code}: {put_res.text}"}
    except Exception as e:
        print(f"⚠️ Error update Shopify price: {e}")
        return {"status": "error", "message": str(e)}

def update_shopify_takedown(sku, blogger_post=None):
    """
    Mengubah status produk di Shopify menjadi DRAFT dan mengosongkan stoknya (Stock = 0).
    """
    token = get_shopify_token()
    if not token:
        return {"status": "error", "message": "Gagal mendapatkan access token Shopify"}

    matched_product, matched_variant, matched_method = find_shopify_product_and_variant(sku, blogger_post=blogger_post)
    if not matched_variant or not matched_product:
        return {"status": "not_found", "message": f"Produk dengan SKU '{sku}' tidak ditemukan di Shopify."}

    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
    product_id = matched_product["id"]
    numeric_product_id = product_id.split('/')[-1]
    variant_id = matched_variant["id"]
    numeric_variant_id = variant_id.split('/')[-1]
    product_title = matched_product.get("title", "")
    actual_sku = matched_variant.get("sku", "")

    # 1. Ubah status produk menjadi 'draft' via REST API
    prod_url = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{API_VERSION}/products/{numeric_product_id}.json"
    prod_payload = {
        "product": {
            "id": int(numeric_product_id),
            "status": "draft"
        }
    }
    status_updated = False
    try:
        put_res = requests.put(prod_url, headers=headers, json=prod_payload, timeout=25)
        if put_res.status_code == 200:
            status_updated = True
            print(f"✅ Berhasil ubah status Shopify menjadi DRAFT: {product_title} (ID: {numeric_product_id})")
        else:
            print(f"⚠️ Gagal update status produk Shopify: HTTP {put_res.status_code} - {put_res.text}")
    except Exception as e:
        print(f"⚠️ Error ubah status draft Shopify: {e}")

    # 2. Ambil inventory_item_id dan set stok menjadi 0 di semua lokasi
    stock_zeroed = False
    locations_updated = []
    try:
        inv_item_id = None
        # Optimasi: Ambil inventory_item_id langsung dari query GraphQL sebelumnya jika tersedia
        raw_inv_id = matched_variant.get("inventoryItem", {}).get("id")
        if raw_inv_id:
            inv_item_id = raw_inv_id.split('/')[-1]

        if not inv_item_id:
            var_url = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{API_VERSION}/variants/{numeric_variant_id}.json"
            v_res = requests.get(var_url, headers=headers, timeout=15)
            if v_res.status_code == 200:
                v_data = v_res.json().get("variant", {})
                inv_item_id = v_data.get("inventory_item_id")

        if inv_item_id:
            levels_url = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{API_VERSION}/inventory_levels.json?inventory_item_ids={inv_item_id}"
            l_res = requests.get(levels_url, headers=headers, timeout=20)
            levels = l_res.json().get("inventory_levels", []) if l_res.status_code == 200 else []

            set_inv_url = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{API_VERSION}/inventory_levels/set.json"

            if levels:
                for lvl in levels:
                    loc_id = lvl.get("location_id")
                    s_res = requests.post(set_inv_url, headers=headers, json={
                        "location_id": loc_id,
                        "inventory_item_id": inv_item_id,
                        "available": 0
                    }, timeout=20)
                    if s_res.status_code == 200:
                        locations_updated.append(loc_id)
                        stock_zeroed = True
            else:
                loc_res = requests.get(f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{API_VERSION}/locations.json", headers=headers, timeout=20)
                locs = loc_res.json().get("locations", []) if loc_res.status_code == 200 else []
                if locs:
                    s_res = requests.post(set_inv_url, headers=headers, json={
                        "location_id": locs[0]["id"],
                        "inventory_item_id": inv_item_id,
                        "available": 0
                    }, timeout=20)
                    if s_res.status_code == 200:
                        locations_updated.append(locs[0]["id"])
                        stock_zeroed = True

            print(f"📦 Stok varian {actual_sku} berhasil di-set 0 di {len(locations_updated)} lokasi.")
    except Exception as e:
        print(f"⚠️ Error ubah stok Shopify ke 0: {e}")

    if status_updated or stock_zeroed:
        return {
            "status": "success",
            "product_title": product_title,
            "matched_sku": actual_sku,
            "status_draft": status_updated,
            "stock_zero": stock_zeroed,
            "method": matched_method,
            "photo_url": extract_shopify_image_url(matched_product),
            "product_node": matched_product
        }
    else:
        return {"status": "error", "message": f"Gagal mengubah status dan stok produk '{product_title}'."}

# ==============================================================================
# 5. GOOGLE SPREADSHEET REPRICE LOGIC (CONSIGNMENT PS & CONSIGNMENT PO)
# ==============================================================================
def update_consignment_sheet(sku, command_type, formatted_price="", numeric_price=0, sheet_name="PHOTO STUDIO"):
    """
    Mengirim perintah update ke Google Apps Script Spreadsheet Consignment Listing.
    Mendukung:
    - Tab 'PHOTO STUDIO' (Label: CONSIGNMENT_PS)
    - Tab 'PHOTO OWNER'  (Label: CONSIGNMENT_PO)
    Kriteria:
    - Tab: Sesuai parameter sheet_name ('PHOTO STUDIO' / 'PHOTO OWNER')
    - Kolom A (Status) harus Available / Reprice
    - Kolom C (Serial Number) = SKU
    - Kolom M (2ND), N (3RD), O (4TH) dicek berurutan mana yang belum dicentang
    - Kolom G (Notes) ditambahkan: REPRICE [harga] [DD/MM/YY] atau REPOST [DD/MM/YY]
    """
    now_wib = datetime.now(WIB)
    date_str = now_wib.strftime("%d/%m/%y") # Format DD/MM/YY (contoh: 27/10/26)

    if command_type == "REPOST":
        notes_text = f"REPOST ({date_str})"
        action_name = "repost_consignment"
    elif command_type == "REPRICE":
        notes_text = f"REPRICE {formatted_price} ({date_str})"
        action_name = "reprice_photo_owner" if sheet_name == "PHOTO OWNER" else "reprice_photo_studio"
    else:
        notes_text = f"HARGA BARU {formatted_price} ({date_str})"
        action_name = "reprice_photo_owner" if sheet_name == "PHOTO OWNER" else "reprice_photo_studio"

    payload = {
        "action": action_name,
        "sheet_name": sheet_name,
        "sku": sku,
        "command_type": command_type,
        "status_text": "Reprice/post",
        "formatted_price": formatted_price,
        "numeric_price": numeric_price,
        "date_str": date_str,
        "notes_text": notes_text
    }

    for attempt in range(2):
        try:
            res = requests.post(APPS_SCRIPT_CONSIGNMENT_URL, json=payload, timeout=60)
            if res.status_code == 200:
                return res.json()
            else:
                return {"status": "error", "message": f"HTTP status {res.status_code}"}
        except requests.exceptions.Timeout:
            if attempt == 0:
                print(f"⚠️ Percobaan 1 Timeout Webhook Sheets Consignment ({sheet_name}) setelah 60s. Mengulang...")
                time.sleep(1)
                continue
            print(f"⚠️ Error Timeout Webhook Sheets Consignment ({sheet_name}) setelah 2x percobaan.")
            return {"status": "error", "message": "Google Sheets timeout (>60s). Sedang diproses di background."}
        except Exception as e:
            print(f"⚠️ Error Webhook Sheets Consignment ({sheet_name}): {e}")
            return {"status": "error", "message": f"Koneksi Google Sheets gagal: {e}"}

def update_consignment_ps_sheet(sku, command_type, formatted_price, numeric_price):
    return update_consignment_sheet(sku, command_type, formatted_price, numeric_price, sheet_name="PHOTO STUDIO")

def update_consignment_po_sheet(sku, command_type, formatted_price, numeric_price):
    return update_consignment_sheet(sku, command_type, formatted_price, numeric_price, sheet_name="PHOTO OWNER")

def update_consignment_repost_sheet(sku, sheet_name="PHOTO STUDIO"):
    return update_consignment_sheet(sku, "REPOST", "", 0, sheet_name=sheet_name)

def update_consignment_status_sheet(sku, status_text, sheet_name="PHOTO STUDIO"):
    """
    Mengirim perintah update status (Sold, On Hold, Takedown, Reprice/post) ke Google Apps Script
    Spreadsheet Consignment Listing (Tab PHOTO STUDIO / PHOTO OWNER).
    Kriteria:
    - Kolom A (Status) diubah menjadi status_text ('Sold', 'On Hold', 'Takedown', 'Reprice/post').
    - Kolom Tracking Post (L, M, N, O): Kolom yang belum dicentang dihapus centangnya.
    """
    # Normalisasi nilai status_text agar persis sesuai Data Validation Google Sheets
    clean_status = (status_text or "").strip()
    norm_key = clean_status.lower().replace(" ", "").replace("_", "").replace("/", "")
    if norm_key in ["takedown", "take"]:
        clean_status = "Takedown"
    elif norm_key in ["sold"]:
        clean_status = "Sold"
    elif norm_key in ["onhold", "hold"]:
        clean_status = "On Hold"
    elif norm_key in ["reprice", "repost", "repricepost"]:
        clean_status = "Reprice/post"

    now_wib = datetime.now(WIB)
    date_str = now_wib.strftime("%d/%m/%y")
    notes_text = f"{clean_status.upper()} ({date_str})"

    payload = {
        "action": "update_consignment_status",
        "sheet_name": sheet_name,
        "sku": sku,
        "status_text": clean_status,
        "date_str": date_str,
        "notes_text": notes_text
    }

    for attempt in range(2):
        try:
            res = requests.post(APPS_SCRIPT_CONSIGNMENT_URL, json=payload, timeout=60)
            if res.status_code == 200:
                return res.json()
            else:
                return {"status": "error", "message": f"HTTP status {res.status_code}"}
        except requests.exceptions.Timeout:
            if attempt == 0:
                print(f"⚠️ Percobaan 1 Timeout Webhook Sheets Consignment Status ({sheet_name}) setelah 60s. Mengulang...")
                time.sleep(1)
                continue
            print(f"⚠️ Error Timeout Webhook Sheets Consignment Status ({sheet_name}) setelah 2x percobaan.")
            return {"status": "error", "message": "Google Sheets timeout (>60s). Sedang diproses di background."}
        except Exception as e:
            print(f"⚠️ Error Webhook Sheets Consignment Status ({sheet_name}): {e}")
            return {"status": "error", "message": f"Koneksi Google Sheets gagal: {e}"}

def update_slow_moving_sheet(sku, command_type, formatted_price, numeric_price, canonical_sku=None):
    """
    Mengirim perintah update harga ke Google Apps Script Spreadsheet 'Stock List Slow Moving Items'.
    Kriteria:
    - Hanya jika produk memiliki label FEATURED di Blogspot.
    - Mencari di tab 'ALL STOCK'.
    - Mencocokkan SKU / Serial Number di Kolom L (SERIAL NUMBER).
    - Memperbarui Harga langsung di Kolom J (PRICE) dengan harga baru (numerik format #,##0).
    - Memperbarui Status di Kolom C (STATUS) menjadi 'REPRICE'.
    (Catatan: Spreadsheet Slow Moving tidak memiliki kolom NOTES; harga langsung ditimpa di Kolom J).
    """
    payload = {
        "action": "reprice_slow_moving",
        "sku": sku,
        "canonical_sku": canonical_sku,
        "command_type": command_type,
        "formatted_price": formatted_price,
        "numeric_price": numeric_price
    }
    for attempt in range(2):
        try:
            res = requests.post(APPS_SCRIPT_SLOW_MOVING_URL, json=payload, timeout=60)
            if res.status_code == 200:
                return res.json()
            elif attempt == 0:
                time.sleep(2)
            else:
                return {"status": "error", "message": f"HTTP status {res.status_code}"}
        except requests.exceptions.Timeout:
            if attempt == 0:
                time.sleep(2)
            else:
                return {"status": "error", "message": "Google Sheets Slow Moving timeout (>60s). Sedang diproses di background."}
        except Exception as e:
            if attempt == 0:
                time.sleep(2)
            else:
                print(f"⚠️ Error Webhook Sheets Slow Moving: {e}")
                return {"status": "error", "message": f"Koneksi Google Sheets gagal: {e}"}

def update_slow_moving_status_sheet(sku, status_text, canonical_sku=None):
    """
    Mengirim perintah update status (SOLD, ON HOLD, TAKEDOWN) ke Google Apps Script
    Spreadsheet 'Stock List Slow Moving Items' (Tab 'ALL STOCK').
    Kriteria:
    - Hanya jika produk memiliki label FEATURED di Blogspot (atau fallback pencarian).
    - Mengubah kolom STATUS menjadi status_text (misal 'SOLD', 'ON HOLD', 'TAKEDOWN').
    """
    clean_status = (status_text or "").strip().upper()
    if clean_status in ["HOLD", "ON HOLD", "ONHOLD"]:
        clean_status = "ON HOLD"
    elif clean_status in ["TAKE", "TAKEDOWN"]:
        clean_status = "TAKEDOWN"
    elif clean_status in ["SOLD"]:
        clean_status = "SOLD"

    payload = {
        "action": "update_status_slow_moving",
        "sku": sku,
        "canonical_sku": canonical_sku,
        "status_text": clean_status
    }
    for attempt in range(2):
        try:
            res = requests.post(APPS_SCRIPT_SLOW_MOVING_URL, json=payload, timeout=60)
            if res.status_code == 200:
                return res.json()
            elif attempt == 0:
                time.sleep(2)
            else:
                return {"status": "error", "message": f"HTTP status {res.status_code}"}
        except requests.exceptions.Timeout:
            if attempt == 0:
                time.sleep(2)
            else:
                return {"status": "error", "message": "Google Sheets Slow Moving timeout (>60s). Sedang diproses di background."}
        except Exception as e:
            if attempt == 0:
                time.sleep(2)
            else:
                print(f"⚠️ Error Webhook Sheets Slow Moving Status: {e}")
                return {"status": "error", "message": f"Koneksi Google Sheets gagal: {e}"}

# ==============================================================================
# 6. ROUTE ENDPOINTS
# ==============================================================================
@app.route('/', methods=['GET'])
def home():
    return "✅ WhatsApp Webhook & Reprice Bot IDWX is RUNNING!", 200

@app.route('/wa-webhook', methods=['POST'])
def wa_webhook():
    chat_id = ""
    sender_name = "Staff"
    caption = ""
    try:
        payload = request.get_json(force=True) or {}

        # 1. Filter Instan: Hanya proses event pesan masuk (incomingMessageReceived)
        # Mengabaikan event statusMessage, outgoingAPIMessageReceived, stateInstanceChanged dll dalam < 1ms
        type_webhook = payload.get("typeWebhook", "")
        if type_webhook and type_webhook != "incomingMessageReceived":
            return jsonify({"status": "ignored", "reason": f"Non-incoming webhook type: {type_webhook}"}), 200

        # 2. Deduplikasi Pesan (Mencegah retry / double processing yang membebani antrian worker)
        id_message = payload.get("idMessage", "")
        if id_message:
            if id_message in PROCESSED_MESSAGE_IDS:
                print(f"⏭️ Diabaikan: Pesan ID '{id_message}' sudah pernah diproses sebelumnya (Deduplikasi).")
                return jsonify({"status": "ignored", "reason": "Duplicate message ID"}), 200
            PROCESSED_MESSAGE_IDS[id_message] = time.time()
            if len(PROCESSED_MESSAGE_IDS) > MAX_PROCESSED_IDS:
                PROCESSED_MESSAGE_IDS.popitem(last=False)

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

        image_url = ""
        jpeg_thumbnail_b64 = None
        quoted_sku = None

        if type_msg == "imageMessage":
            file_data = message_data.get("fileMessageData", {})
            caption = file_data.get("caption", "").strip()
            image_url = file_data.get("downloadUrl", "").strip()
            jpeg_thumbnail_b64 = file_data.get("jpegThumbnail", "").strip()
        elif type_msg == "documentMessage":
            file_data = message_data.get("fileMessageData", {})
            mime_type = file_data.get("mimeType", "").lower()
            file_name = file_data.get("fileName", "").lower()
            if mime_type.startswith("image/") or file_name.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                type_msg = "imageMessage"
                caption = file_data.get("caption", "").strip()
                image_url = file_data.get("downloadUrl", "").strip()
                jpeg_thumbnail_b64 = file_data.get("jpegThumbnail", "").strip()
        elif type_msg == "textMessage":
            caption = message_data.get("textMessageData", {}).get("textMessage", "").strip()
        elif type_msg == "extendedTextMessage":
            ext_data = message_data.get("extendedTextMessageData", {})
            caption = ext_data.get("text", "").strip()
            quoted_msg = ext_data.get("quotedMessage", {})
            quoted_sku = extract_sku_from_quoted_message(quoted_msg)
        else:
            return jsonify({"status": "ignored", "reason": "Unsupported message type"}), 200

        # ======================================================================
        # JALUR 0: IDENTIFIKASI JAM TANGAN DARI FOTO (MULTIMODAL GEMINI VISION)
        # ======================================================================
        # Khusus memanggil fitur IDENTIFIKASI JAM TANGAN IDWX jika user melampirkan foto
        # dan menyertakan kata kunci 'identifikasi' (atau 'identify') pada caption.
        is_identifikasi_cmd = is_identification_request(caption)

        if type_msg == "imageMessage" and is_identifikasi_cmd:
            # Pengecekan grup/chat yang dikecualikan dari identifikasi visual (misal Group Foto Studio)
            if is_chat_excluded_from_identification(chat_id):
                print(f"⏭️ Diabaikan: Chat {chat_id} dikecualikan dari fitur identifikasi jam tangan visual.")
                return jsonify({"status": "ignored", "reason": "Excluded chat/group for watch identification"}), 200

            if not image_url and not jpeg_thumbnail_b64:
                return jsonify({"status": "ignored", "reason": "Empty image URL and thumbnail"}), 200

            caption_log = f" (caption: '{caption}')" if caption else ""
            print(f"📸 Menerima foto jam tangan dengan kata kunci identifikasi{caption_log} dari: {sender_name}. Menjalankan Gemini Vision...")
            gemini_info = identify_watch_with_gemini(
                image_url=image_url,
                jpeg_thumbnail=jpeg_thumbnail_b64,
                chat_id=chat_id,
                id_message=id_message
            )
            if not gemini_info:
                pesan_err = (
                    "⚠️ *IDENTIFIKASI GAGAL*\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "Maaf, sistem tidak dapat mengidentifikasi jam tangan dari foto yang dikirimkan. Pastikan foto jam terlihat jelas pada bagian dial / merek."
                )
                kirim_balasan_wa(chat_id, pesan_err)
                return jsonify({"status": "failed", "reason": "Gemini vision failed"}), 200

            # Cari produk AKTIF yang cocok di Shopify, dengan konteks caption user jika ada
            shopify_match = find_active_watch_in_shopify(gemini_info, user_caption=caption)
            clean_gemini_info = {k: v for k, v in gemini_info.items() if not isinstance(v, (bytes, bytearray))}
            if not shopify_match:
                pesan_err = (
                    f"⚠️ *PRODUK TIDAK DITEMUKAN DI SHOPIFY*\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"Merek/Model terdeteksi: *{gemini_info.get('brand', '')} {gemini_info.get('model', '')}*\n"
                    f"Namun tidak ditemukan produk aktif yang cocok di etalase toko Shopify."
                )
                kirim_balasan_wa(chat_id, pesan_err)
                return jsonify({"status": "not_found", "gemini_info": clean_gemini_info}), 200

            matched_sku = shopify_match["sku"]
            matched_title = shopify_match["title"]
            formatted_price = shopify_match["formatted_price"]
            numeric_price = shopify_match["numeric_price"]
            matched_location = shopify_match.get("location", "Ready di Toko")

            # Cek Blogspot jika ada untuk label
            service = get_blogger_service()
            post = find_blogger_post_by_code(service, matched_sku) if service else None

            # Tentukan lokasi spreadsheet (Tab & Nomor Baris), form konsinyasi, dan owner/sales jika ada
            sheet_res = resolve_watch_spreadsheet_location(matched_sku, blogger_post=post, return_form=True)
            if isinstance(sheet_res, (tuple, list)):
                if len(sheet_res) >= 4:
                    sheet_info, form_content, owner, sales = sheet_res[0], sheet_res[1], sheet_res[2], sheet_res[3]
                elif len(sheet_res) == 3:
                    sheet_info, form_content, owner = sheet_res[0], sheet_res[1], sheet_res[2]
                    sales = ""
                elif len(sheet_res) == 2:
                    sheet_info, form_content = sheet_res[0], sheet_res[1]
                    owner = ""
                    sales = ""
                else:
                    sheet_info = sheet_res[0]
                    form_content = ""
                    owner = ""
                    sales = ""
            else:
                sheet_info = str(sheet_res)
                form_content = ""
                owner = ""
                sales = ""

            # Simpan ke sesi jam tangan aktif per chat_id
            ACTIVE_IDENTIFIED_WATCHES[chat_id] = {
                "sku": matched_sku,
                "title": matched_title,
                "formatted_price": formatted_price,
                "numeric_price": numeric_price,
                "sheet_info": sheet_info,
                "form_content": form_content,
                "owner": owner,
                "sales": sales,
                "location": matched_location,
                "timestamp": time.time()
            }
            if len(ACTIVE_IDENTIFIED_WATCHES) > MAX_ACTIVE_WATCHES:
                ACTIVE_IDENTIFIED_WATCHES.popitem(last=False)

            # Kirim pesan identifikasi lengkap dengan opsi Aksi Cepat (termasuk status lokasi dinamis, form konsinyasi, atau owner/sales)
            pesan_id = format_watch_identification_message(
                matched_title,
                matched_sku,
                formatted_price,
                sheet_info,
                location=matched_location,
                form_content=form_content,
                owner=owner,
                sales=sales
            )
            kirim_balasan_wa(chat_id, pesan_id)

            return jsonify({
                "status": "success",
                "action": "identify_watch",
                "gemini": clean_gemini_info,
                "shopify": shopify_match,
                "sheet_info": sheet_info,
                "form_content": form_content,
                "owner": owner,
                "sales": sales
            }), 200

        if not caption:
            return jsonify({"status": "ignored", "reason": "Empty message"}), 200

        # ======================================================================
        # JALUR PEMBATALAN / ABAIKAN IDENTIFIKASI
        # ======================================================================
        if is_cancellation_chat(caption):
            last_watch = ACTIVE_IDENTIFIED_WATCHES.pop(chat_id, None)
            if last_watch:
                pesan_batal = (
                    "❌ *Identifikasi jam tangan dibatalkan.*\n"
                    f"Tidak ada perubahan yang dilakukan untuk *{last_watch.get('title', 'produk')}* (`{last_watch.get('sku', '')}`)."
                )
            else:
                pesan_batal = "ℹ️ *Tidak ada sesi identifikasi jam tangan yang aktif.*"
            kirim_balasan_wa(chat_id, pesan_batal)
            return jsonify({"status": "cancelled", "watch": last_watch}), 200

        # Resolusi fallback SKU dari quoted message atau sesi identifikasi aktif
        fallback_sku = quoted_sku
        if not fallback_sku and chat_id in ACTIVE_IDENTIFIED_WATCHES:
            session = ACTIVE_IDENTIFIED_WATCHES.get(chat_id)
            if session and (time.time() - session.get("timestamp", 0)) <= IDENTIFIED_WATCH_TTL:
                fallback_sku = session.get("sku")

        # Jika user mengirim foto dengan caption aksi langsung tanpa mengetik SKU (misal: foto + "sold", foto + "reprice 650jt"):
        if type_msg == "imageMessage" and image_url and not fallback_sku and not is_chat_excluded_from_identification(chat_id):
            is_action_caption = (
                caption.lower().strip() in ["sold", "laku", "on hold", "onhold", "hold", "takedown"]
                or re.match(r'^(REPRICE|HARGA\s+BARU|HARGA_BARU)(?:\s*/\s*|\s+)(.+)$', caption.strip(), re.IGNORECASE)
            )
            if is_action_caption:
                print(f"📸 Menerima foto dengan caption aksi '{caption}' dari: {sender_name}. Menjalankan identifikasi Gemini Vision...")
                g_info = identify_watch_with_gemini(
                    image_url=image_url,
                    jpeg_thumbnail=jpeg_thumbnail_b64,
                    chat_id=chat_id,
                    id_message=id_message
                )
                if g_info:
                    s_match = find_active_watch_in_shopify(g_info, user_caption=caption)
                    if s_match and s_match.get("sku"):
                        fallback_sku = s_match["sku"]
                        print(f"✅ SKU otomatis teridentifikasi dari foto untuk aksi langsung: {fallback_sku}")

        # ======================================================================
        # JALUR A: PERINTAH REPRICE / HARGA BARU
        # ======================================================================
        reprice_cmd = parse_reprice_chat(caption, fallback_sku=fallback_sku)
        if reprice_cmd:
            ACTIVE_IDENTIFIED_WATCHES.pop(chat_id, None)
            sku = reprice_cmd["code"]
            cmd_type = reprice_cmd["command_type"]
            formatted_price = reprice_cmd["formatted_price"]
            numeric_price = reprice_cmd["numeric_price"]

            print(f"⚡ Menerima Perintah {cmd_type} untuk SKU: '{sku}' dengan harga: {formatted_price}")

            # 1. Update Shopify (Multi-Level Smart Matching)
            shopify_res = update_shopify_reprice(sku, cmd_type, numeric_price, blogger_post=None)
            shopify_product_title = shopify_res.get("product_title", "")

            # 2. Update Blogspot dengan Filter SKU Ketat & Validasi Merek
            blogger_res = {"status": "skipped", "message": "Blogger service not configured"}
            is_consign_ps = False
            is_consign_po = False
            is_featured = False
            service = get_blogger_service()
            post = None
            if service:
                post = find_blogger_post_by_code(service, sku, expected_title=shopify_product_title)
                if post:
                    post_title = post.get("title", "")
                    # Safety Guard: Benturan Merek
                    if shopify_product_title:
                        conflict, b_blog, b_shop = is_brand_conflict(post_title, shopify_product_title)
                        if conflict:
                            print(f"🚨 ALERT: Benturan merek terdeteksi! Blogspot '{b_blog}' vs Shopify '{b_shop}'. Membatalkan reprice Blogspot demi keamanan.")
                            blogger_res = {
                                "status": "mismatch_aborted",
                                "post_title": post_title,
                                "brand_blog": b_blog,
                                "brand_shop": b_shop,
                                "message": f"Dibatalkan otomatis demi keamanan: Merek Blogspot ({b_blog}) berbeda dengan Shopify ({b_shop})"
                            }
                        else:
                            blogger_res = update_blogger_reprice(service, post, cmd_type, formatted_price)
                    else:
                        blogger_res = update_blogger_reprice(service, post, cmd_type, formatted_price)

                    post_labels = post.get("labels", [])
                    is_consign_ps = any("CONSIGNMENT_PS" in l.upper() or "CONSINGMENT_PS" in l.upper() for l in post_labels)
                    is_consign_po = any("CONSIGNMENT_PO" in l.upper() or "CONSINGMENT_PO" in l.upper() for l in post_labels) or sku.upper().startswith("CPO")
                    is_featured = any("FEATURED" in l.upper() for l in post_labels)
                else:
                    blogger_res = {"status": "not_found", "message": f"Postingan dengan kode {sku} tidak ditemukan di Blogspot."}

            # 3. Update Google Spreadsheet
            canonical_sku = shopify_res.get("matched_sku") or (extract_sku_from_blogger_post(post)[0] if post else None) or clean_sku_string(sku)
            
            # 3a. Update Spreadsheet Consignment PS (HANYA jika CONSIGNMENT_PS)
            sheet_consign_ps_res = {"status": "skipped", "message": "Bukan tag CONSIGNMENT_PS"}
            if is_consign_ps:
                print(f"📌 Produk '{canonical_sku}' memiliki label CONSIGNMENT_PS. Memperbarui Google Spreadsheet Consignment (Tab PHOTO STUDIO)...")
                sheet_consign_ps_res = update_consignment_ps_sheet(canonical_sku, cmd_type, formatted_price, numeric_price)
            else:
                print(f"ℹ️ Produk '{sku}' BUKAN CONSIGNMENT_PS.")

            # 3b. Update Spreadsheet Consignment PO (HANYA jika CONSIGNMENT_PO)
            sheet_consign_po_res = {"status": "skipped", "message": "Bukan tag CONSIGNMENT_PO"}
            if is_consign_po:
                print(f"📌 Produk '{canonical_sku}' memiliki label CONSIGNMENT_PO. Memperbarui Google Spreadsheet Consignment (Tab PHOTO OWNER)...")
                sheet_consign_po_res = update_consignment_po_sheet(canonical_sku, cmd_type, formatted_price, numeric_price)
            else:
                print(f"ℹ️ Produk '{sku}' BUKAN CONSIGNMENT_PO.")

            # 3c. Update Spreadsheet Slow Moving (HANYA jika FEATURED)
            sheet_slow_moving_res = {"status": "skipped", "message": "Bukan tag FEATURED"}
            if is_featured:
                print(f"⭐ Produk '{canonical_sku}' memiliki label FEATURED. Memperbarui Google Spreadsheet Slow Moving (Tab ALL STOCK)...")
                sheet_slow_moving_res = update_slow_moving_sheet(sku, cmd_type, formatted_price, numeric_price, canonical_sku=canonical_sku)
            else:
                print(f"ℹ️ Produk '{sku}' BUKAN FEATURED.")

            # 4. Kirim Balasan Laporan Lengkap ke WhatsApp
            status_blog_icon = "✅" if blogger_res.get("status") == "success" else "⚠️"
            status_shop_icon = "✅" if shopify_res.get("status") == "success" else "⚠️"

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
            )
            if blogger_res.get("publish_date"):
                pesan_konfirmasi += f"   • Publish Date: {blogger_res.get('publish_date')}\n"

            pesan_konfirmasi += f"{status_shop_icon} *Shopify:* {shopify_res.get('product_title', shopify_res.get('message', 'Sukses'))}\n"

            # Bagian Status Spreadsheet
            if is_consign_ps:
                status_consign_icon = "✅" if sheet_consign_ps_res.get("status") == "success" else "⚠️"
                pesan_konfirmasi += f"{status_consign_icon} *Spreadsheet (Consignment PS):* "
                if sheet_consign_ps_res.get("status") == "success":
                    tracking_info = f", {sheet_consign_ps_res.get('tracking_checked')}" if sheet_consign_ps_res.get('tracking_checked') else ""
                    pesan_konfirmasi += f"Status diubah ke *Reprice/post* (Baris {sheet_consign_ps_res.get('row', '-')}, Tab PHOTO STUDIO{tracking_info})\n"
                else:
                    pesan_konfirmasi += f"{sheet_consign_ps_res.get('message', 'Gagal')}\n"

            if is_consign_po:
                status_consign_po_icon = "✅" if sheet_consign_po_res.get("status") == "success" else "⚠️"
                pesan_konfirmasi += f"{status_consign_po_icon} *Spreadsheet (Consignment PO):* "
                if sheet_consign_po_res.get("status") == "success":
                    tracking_info = f", {sheet_consign_po_res.get('tracking_checked')}" if sheet_consign_po_res.get('tracking_checked') else ""
                    pesan_konfirmasi += f"Status diubah ke *Reprice/post* (Baris {sheet_consign_po_res.get('row', '-')}, Tab PHOTO OWNER{tracking_info})\n"
                else:
                    pesan_konfirmasi += f"{sheet_consign_po_res.get('message', 'Gagal')}\n"

            if is_featured:
                status_slow_icon = "✅" if sheet_slow_moving_res.get("status") == "success" else "⚠️"
                pesan_konfirmasi += f"{status_slow_icon} *Spreadsheet (Slow Moving):* "
                if sheet_slow_moving_res.get("status") == "success":
                    pesan_konfirmasi += f"Status diubah ke *REPRICE* (Baris {sheet_slow_moving_res.get('row', '-')}, Tab {sheet_slow_moving_res.get('tab_name', 'ALL STOCK')})\n"
                else:
                    pesan_konfirmasi += f"{sheet_slow_moving_res.get('message', 'Gagal')}\n"

            if not is_consign_ps and not is_consign_po and not is_featured:
                pesan_konfirmasi += "⏭️ *Spreadsheet:* Dilewati (Bukan tag CONSIGNMENT_PS / CONSIGNMENT_PO / FEATURED)\n"

            kirim_balasan_wa(chat_id, pesan_konfirmasi.strip())

            return jsonify({
                "status": "success",
                "command": cmd_type,
                "sku": sku,
                "blogger": blogger_res,
                "shopify": shopify_res,
                "spreadsheet_consignment_ps": sheet_consign_ps_res,
                "spreadsheet_consignment_po": sheet_consign_po_res,
                "spreadsheet_slow_moving": sheet_slow_moving_res
            }), 200


        # ======================================================================
        # JALUR B: PERINTAH TAKEDOWN / SOLD / ON HOLD
        # ======================================================================
        takedown_cmd = parse_takedown_chat(caption, fallback_sku=fallback_sku)
        if takedown_cmd:
            ACTIVE_IDENTIFIED_WATCHES.pop(chat_id, None)
            sku = takedown_cmd["code"]
            cmd_type = takedown_cmd["command_type"]
            status_text = takedown_cmd["status_text"]
            cmd_title = cmd_type.replace("_", " ")
            print(f"🗑️ Menerima Perintah {cmd_type} (Status: {status_text}) untuk SKU: '{sku}' dari: {sender_name}")

            # 1. Update Shopify: Status DRAFT & Stock 0
            shopify_res = update_shopify_takedown(sku)
            shopify_product_title = shopify_res.get("product_title", "")

            # 2. Cari & Proses Postingan di Blogspot
            service = get_blogger_service()
            post = None
            blogger_res = {"status": "skipped", "message": "Blogger service tidak aktif"}
            photo_url = None
            post_description = ""
            is_consign_ps = False
            is_consign_po = False
            is_featured = False

            if service:
                # Cari postingan dengan filter SKU ketat & verifikasi expected_title
                post = find_blogger_post_by_code(service, sku, expected_title=shopify_product_title)
                if post:
                    post_title = post.get("title", "")
                    photo_url = extract_first_image_from_post(post)
                    post_description = extract_takedown_description_from_post(post)
                    post_labels = post.get("labels", [])
                    is_consign_ps = any("CONSIGNMENT_PS" in l.upper() or "CONSINGMENT_PS" in l.upper() for l in post_labels)
                    is_consign_po = any("CONSIGNMENT_PO" in l.upper() or "CONSINGMENT_PO" in l.upper() for l in post_labels) or sku.upper().startswith("CPO")
                    is_featured = any("FEATURED" in l.upper() for l in post_labels)

                    # Safety Guard: Periksa benturan merek antara Blogspot dan Shopify
                    if shopify_product_title:
                        conflict, b_blog, b_shop = is_brand_conflict(post_title, shopify_product_title)
                        if conflict:
                            print(f"🚨 ALERT: Benturan merek terdeteksi! Blogspot '{b_blog}' vs Shopify '{b_shop}'. Membatalkan takedown Blogspot demi keamanan.")
                            blogger_res = {
                                "status": "mismatch_aborted",
                                "post_title": post_title,
                                "brand_blog": b_blog,
                                "brand_shop": b_shop,
                                "message": f"Dibatalkan otomatis demi keamanan: Merek Blogspot ({b_blog}) berbeda dengan Shopify ({b_shop})"
                            }
                        else:
                            blogger_res = delete_blogger_post(service, post)
                    else:
                        blogger_res = delete_blogger_post(service, post)
                else:
                    blogger_res = {"status": "not_found", "message": f"Postingan dengan kode {sku} tidak ditemukan di Blogspot."}

            # 3. Update Google Spreadsheet
            canonical_sku = (extract_sku_from_blogger_post(post)[0] if post else None) or shopify_res.get("matched_sku") or clean_sku_string(sku)
            sheet_consign_ps_res = {"status": "skipped", "message": "Bukan tag CONSIGNMENT_PS"}
            sheet_consign_po_res = {"status": "skipped", "message": "Bukan tag CONSIGNMENT_PO"}
            sheet_slow_moving_res = {"status": "skipped", "message": "Bukan tag FEATURED"}

            if post and blogger_res.get("status") == "success":
                # Jika postingan Blogspot ada dan berhasil dipindahkan ke Sampah
                if is_consign_ps:
                    print(f"📌 Produk '{canonical_sku}' memiliki label CONSIGNMENT_PS. Memperbarui Google Spreadsheet Consignment (Tab PHOTO STUDIO) status ke '{status_text}'...")
                    sheet_consign_ps_res = update_consignment_status_sheet(canonical_sku, status_text, sheet_name="PHOTO STUDIO")
                elif is_consign_po:
                    print(f"📌 Produk '{canonical_sku}' memiliki label CONSIGNMENT_PO. Memperbarui Google Spreadsheet Consignment (Tab PHOTO OWNER) status ke '{status_text}'...")
                    sheet_consign_po_res = update_consignment_status_sheet(canonical_sku, status_text, sheet_name="PHOTO OWNER")
                else:
                    print(f"ℹ️ Produk '{sku}' BUKAN CONSIGNMENT_PS atau CONSIGNMENT_PO.")

                if is_featured:
                    print(f"⭐ Produk '{canonical_sku}' memiliki label FEATURED. Memperbarui Google Spreadsheet Slow Moving (Tab ALL STOCK) status ke '{status_text}'...")
                    sheet_slow_moving_res = update_slow_moving_status_sheet(sku, status_text, canonical_sku=canonical_sku)
            else:
                # KONDISI KHUSUS: Postingan Blogspot tidak ditemukan atau dibatalkan karena benturan merek
                # Tetap periksa dan update Google Spreadsheet yang relevan
                print(f"ℹ️ Memeriksa Google Spreadsheet untuk SKU '{sku}' (canonical: '{canonical_sku}')...")
                target_sheet = "PHOTO OWNER" if sku.upper().startswith("CPO") else "PHOTO STUDIO"
                sheet_res = update_consignment_status_sheet(canonical_sku, status_text, sheet_name=target_sheet)

                if sheet_res.get("status") == "success":
                    if target_sheet == "PHOTO OWNER":
                        is_consign_po = True
                        sheet_consign_po_res = sheet_res
                    else:
                        is_consign_ps = True
                        sheet_consign_ps_res = sheet_res
                else:
                    alt_sheet = "PHOTO STUDIO" if target_sheet == "PHOTO OWNER" else "PHOTO OWNER"
                    alt_res = update_consignment_status_sheet(canonical_sku, status_text, sheet_name=alt_sheet)
                    if alt_res.get("status") == "success":
                        if alt_sheet == "PHOTO OWNER":
                            is_consign_po = True
                            sheet_consign_po_res = alt_res
                        else:
                            is_consign_ps = True
                            sheet_consign_ps_res = alt_res
                    else:
                        # Jika tidak ditemukan di Consignment, cek Spreadsheet Slow Moving (ALL STOCK)
                        print(f"🔍 SKU '{sku}' tidak ditemukan di Consignment. Memeriksa Spreadsheet Slow Moving (Tab ALL STOCK)...")
                        sheet_slow_res = update_slow_moving_status_sheet(sku, status_text, canonical_sku=canonical_sku)
                        if sheet_slow_res.get("status") == "success":
                            is_featured = True
                            sheet_slow_moving_res = sheet_slow_res
                            print(f"✅ Ditemukan dan berhasil diupdate di Spreadsheet Slow Moving (Baris {sheet_slow_res.get('row', '-')}, Tab {sheet_slow_res.get('tab_name', '-')})")
                        else:
                            print(f"ℹ️ SKU '{sku}' juga tidak ditemukan di Slow Moving: {sheet_slow_res.get('message', '')}")

            # 4. Format Laporan Konfirmasi WhatsApp
            status_shop_icon = "✅" if shopify_res.get("status") == "success" else "⚠️"
            status_blog_icon = "✅" if blogger_res.get("status") == "success" else ("⚠️" if blogger_res.get("status") == "mismatch_aborted" else "ℹ️")

            sku_display = sku
            if shopify_res.get("matched_sku") and shopify_res.get("matched_sku").upper() != clean_sku_string(sku).upper():
                sku_display += f" _(Shopify: {shopify_res.get('matched_sku')})_"

            cmd_icon = "🏷️" if cmd_type == "SOLD" else ("⏸️" if cmd_type == "ON_HOLD" else "🗑️")
            pesan_konfirmasi = (
                f"{cmd_icon} *LAPORAN {cmd_title} IDWX*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🔢 *Kode / SKU:* {sku_display}\n"
                f"👤 *Diupdate oleh:* {sender_name}\n\n"
                f"{status_shop_icon} *Shopify:* {shopify_res.get('product_title', shopify_res.get('message', 'Sukses'))}\n"
            )
            if shopify_res.get("status") == "success":
                pesan_konfirmasi += "   • Status: *DRAFT*\n   • Stock: *0*\n"

            if blogger_res.get("status") == "mismatch_aborted":
                pesan_konfirmasi += (
                    f"⚠️ *Blogspot: DIBATALKAN (Mencegah Salah Takedown!)*\n"
                    f"   • Judul Blogspot: {blogger_res.get('post_title', '-')}\n"
                    f"   • Peringatan: Merek Blogspot *({blogger_res.get('brand_blog')})* berbeda dengan Shopify *({blogger_res.get('brand_shop')})*.\n"
                    f"   • Postingan Blogspot *TIDAK* dihapus demi keamanan.\n"
                )
            elif blogger_res.get("already_in_trash"):
                pesan_konfirmasi += f"✅ *Blogspot:* Sudah di Sampah (Trash) sebelumnya\n   • Judul: {blogger_res.get('post_title', shopify_product_title or '-')}\n"
            elif blogger_res.get("status") == "success":
                pesan_konfirmasi += f"✅ *Blogspot:* Dipindahkan ke Sampah (Trash)\n   • Judul: {blogger_res.get('post_title', '-')}\n"
                if blogger_res.get("publish_date"):
                    pesan_konfirmasi += f"   • Publish Date: {blogger_res.get('publish_date')}\n"
            else:
                if shopify_product_title:
                    pesan_konfirmasi += f"✅ *Blogspot:* Sudah di Sampah (Trash) sebelumnya\n   • Judul: {shopify_product_title}\n"
                else:
                    pesan_konfirmasi += f"ℹ️ *Blogspot:* {blogger_res.get('message', 'Postingan tidak ditemukan / sudah tidak aktif')}\n"

            # Status Spreadsheet Consignment & Slow Moving
            if is_consign_ps:
                status_consign_icon = "✅" if sheet_consign_ps_res.get("status") == "success" else "⚠️"
                pesan_konfirmasi += f"{status_consign_icon} *Spreadsheet (Consignment PS):* "
                if sheet_consign_ps_res.get("status") == "success":
                    pesan_konfirmasi += f"Status diubah ke *{status_text}* (Baris {sheet_consign_ps_res.get('row', '-')}, Tab PHOTO STUDIO)\n"
                else:
                    pesan_konfirmasi += f"{sheet_consign_ps_res.get('message', 'Gagal')}\n"
            elif is_consign_po:
                status_consign_po_icon = "✅" if sheet_consign_po_res.get("status") == "success" else "⚠️"
                pesan_konfirmasi += f"{status_consign_po_icon} *Spreadsheet (Consignment PO):* "
                if sheet_consign_po_res.get("status") == "success":
                    pesan_konfirmasi += f"Status diubah ke *{status_text}* (Baris {sheet_consign_po_res.get('row', '-')}, Tab PHOTO OWNER)\n"
                else:
                    pesan_konfirmasi += f"{sheet_consign_po_res.get('message', 'Gagal')}\n"

            if is_featured:
                status_slow_icon = "✅" if sheet_slow_moving_res.get("status") == "success" else "⚠️"
                pesan_konfirmasi += f"{status_slow_icon} *Spreadsheet (Slow Moving):* "
                if sheet_slow_moving_res.get("status") == "success":
                    pesan_konfirmasi += f"Status diubah ke *{status_text}* (Baris {sheet_slow_moving_res.get('row', '-')}, Tab {sheet_slow_moving_res.get('tab_name', 'ALL STOCK')})\n"
                else:
                    pesan_konfirmasi += f"{sheet_slow_moving_res.get('message', 'Gagal')}\n"

            if not is_consign_ps and not is_consign_po and not is_featured:
                pesan_konfirmasi += "⏭️ *Spreadsheet:* Dilewati (SKU tidak ditemukan di Consignment maupun Slow Moving)\n"

            # Resolusi deskripsi lengkap spesifikasi jam tangan (Blogspot / fallback Shopify)
            if not post_description and shopify_res.get("product_node"):
                shopify_desc_html = shopify_res["product_node"].get("descriptionHtml", "")
                post_description = extract_description_from_shopify_html(shopify_desc_html, title=shopify_product_title)

            if post_description:
                pesan_konfirmasi += f"\n━━━━━━━━━━━━━━━━━━\n{post_description}\n"

            # 5. Resolusi foto produk (Prioritas Blogspot jika sukses -> Fallback Shopify -> Fallback Spreadsheet)
            fallback_sheet_photo = sheet_consign_ps_res.get("photo_url") or sheet_consign_po_res.get("photo_url")
            photo_url = get_watch_photo_url(
                post=post if blogger_res.get("status") == "success" else None,
                sku=sku,
                shopify_product=shopify_res.get("product_node"),
                fallback_url=fallback_sheet_photo
            )

            kirim_balasan_wa(
                chat_id,
                pesan_konfirmasi.strip(),
                image_url=photo_url,
                sku=sku,
                blogger_post=post if blogger_res.get("status") == "success" else None,
                shopify_product=shopify_res.get("product_node"),
                fallback_url=fallback_sheet_photo
            )

            return jsonify({
                "status": "success",
                "command": cmd_type,
                "status_text": status_text,
                "sku": sku,
                "photo_url": photo_url,
                "description": post_description,
                "shopify": shopify_res,
                "blogger": blogger_res,
                "spreadsheet_consignment_ps": sheet_consign_ps_res,
                "spreadsheet_consignment_po": sheet_consign_po_res,
                "spreadsheet_slow_moving": sheet_slow_moving_res
            }), 200

        # ======================================================================
        # JALUR C: PERINTAH REPOST
        # ======================================================================
        repost_cmd = parse_repost_chat(caption)
        if repost_cmd:
            sku = repost_cmd["code"]
            print(f"🔁 Menerima Perintah REPOST untuk SKU: '{sku}' dari: {sender_name}")

            service = get_blogger_service()
            post = None
            blogger_res = {"status": "skipped", "message": "Blogger service not configured"}
            is_consign_ps = False
            is_consign_po = False
            is_featured = False

            if service:
                post = find_blogger_post_by_code(service, sku)
                if post:
                    blogger_res = update_blogger_repost(service, post)
                    post_labels = post.get("labels", [])
                    is_consign_ps = any("CONSIGNMENT_PS" in l.upper() or "CONSINGMENT_PS" in l.upper() for l in post_labels)
                    is_consign_po = any("CONSIGNMENT_PO" in l.upper() or "CONSINGMENT_PO" in l.upper() for l in post_labels) or sku.upper().startswith("CPO")
                    is_featured = any("FEATURED" in l.upper() for l in post_labels)
                else:
                    blogger_res = {"status": "not_found", "message": f"Postingan dengan kode {sku} tidak ditemukan di Blogspot."}

            canonical_sku = (extract_sku_from_blogger_post(post)[0] if post else None) or clean_sku_string(sku)

            # Update Spreadsheet Consignment PS (HANYA jika CONSIGNMENT_PS)
            sheet_consign_ps_res = {"status": "skipped", "message": "Bukan tag CONSIGNMENT_PS"}
            if is_consign_ps and blogger_res.get("status") == "success":
                print(f"📌 Produk '{canonical_sku}' memiliki label CONSIGNMENT_PS. Memperbarui Google Spreadsheet Consignment (Tab PHOTO STUDIO)...")
                sheet_consign_ps_res = update_consignment_repost_sheet(canonical_sku, sheet_name="PHOTO STUDIO")
            else:
                print(f"ℹ️ Produk '{sku}' BUKAN CONSIGNMENT_PS atau Blogspot gagal.")

            # Update Spreadsheet Consignment PO (HANYA jika CONSIGNMENT_PO)
            sheet_consign_po_res = {"status": "skipped", "message": "Bukan tag CONSIGNMENT_PO"}
            if is_consign_po and blogger_res.get("status") == "success":
                print(f"📌 Produk '{canonical_sku}' memiliki label CONSIGNMENT_PO. Memperbarui Google Spreadsheet Consignment (Tab PHOTO OWNER)...")
                sheet_consign_po_res = update_consignment_repost_sheet(canonical_sku, sheet_name="PHOTO OWNER")
            else:
                print(f"ℹ️ Produk '{sku}' BUKAN CONSIGNMENT_PO atau Blogspot gagal.")

            # Inisialisasi status spreadsheet Slow Moving (Dilewati untuk REPOST)
            sheet_slow_moving_res = {"status": "skipped", "message": "Dilewati (Tidak ada perubahan spreadsheet Slow Moving untuk REPOST)"}

            # Kirim Balasan Laporan Lengkap ke WhatsApp
            status_blog_icon = "✅" if blogger_res.get("status") == "success" else "⚠️"

            pesan_konfirmasi = (
                f"🔁 *LAPORAN REPOST IDWX*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🔢 *Kode / SKU:* {sku}\n"
                f"👤 *Diupdate oleh:* {sender_name}\n\n"
                f"{status_blog_icon} *Blogspot:* {blogger_res.get('post_title', blogger_res.get('message', 'Sukses'))}\n"
            )
            if blogger_res.get("publish_date"):
                pesan_konfirmasi += f"   • Last Post: {blogger_res.get('publish_date')}\n"

            pesan_konfirmasi += "⏭️ *Shopify:* Dilewati (Tidak ada perubahan untuk REPOST)\n"

            if is_consign_ps:
                status_consign_icon = "✅" if sheet_consign_ps_res.get("status") == "success" else "⚠️"
                pesan_konfirmasi += f"{status_consign_icon} *Spreadsheet (Consignment PS):* "
                if sheet_consign_ps_res.get("status") == "success":
                    tracking_info = f", {sheet_consign_ps_res.get('tracking_checked')}" if sheet_consign_ps_res.get('tracking_checked') else ""
                    pesan_konfirmasi += f"Status diubah ke *Reprice/post* (Baris {sheet_consign_ps_res.get('row', '-')}, Tab PHOTO STUDIO{tracking_info})\n"
                else:
                    pesan_konfirmasi += f"{sheet_consign_ps_res.get('message', 'Gagal')}\n"

            if is_consign_po:
                status_consign_po_icon = "✅" if sheet_consign_po_res.get("status") == "success" else "⚠️"
                pesan_konfirmasi += f"{status_consign_po_icon} *Spreadsheet (Consignment PO):* "
                if sheet_consign_po_res.get("status") == "success":
                    tracking_info = f", {sheet_consign_po_res.get('tracking_checked')}" if sheet_consign_po_res.get('tracking_checked') else ""
                    pesan_konfirmasi += f"Status diubah ke *Reprice/post* (Baris {sheet_consign_po_res.get('row', '-')}, Tab PHOTO OWNER{tracking_info})\n"
                else:
                    pesan_konfirmasi += f"{sheet_consign_po_res.get('message', 'Gagal')}\n"

            if is_featured:
                pesan_konfirmasi += "⏭️ *Spreadsheet (Slow Moving):* Dilewati (Tidak ada perubahan status untuk REPOST)\n"
            elif not is_consign_ps and not is_consign_po:
                pesan_konfirmasi += "⏭️ *Spreadsheet:* Dilewati (Bukan tag CONSIGNMENT_PS / CONSIGNMENT_PO)\n"

            kirim_balasan_wa(chat_id, pesan_konfirmasi.strip())

            return jsonify({
                "status": "success",
                "command": "REPOST",
                "sku": sku,
                "blogger": blogger_res,
                "spreadsheet_consignment_ps": sheet_consign_ps_res,
                "spreadsheet_consignment_po": sheet_consign_po_res,
                "spreadsheet_slow_moving": sheet_slow_moving_res
            }), 200

        # ======================================================================
        # JALUR BARU: PERINTAH DOWNLOAD FOTO BLOGSPOT (TRIGGER: FOTO + SKU)
        # ======================================================================
        foto_cmd = parse_download_foto_chat(caption) if not image_url else None
        if foto_cmd:
            if foto_cmd.get("command_type") == "DOWNLOAD_FOTO_EMPTY":
                pesan_bantuan = (
                    "ℹ️ *FORMAT DOWNLOAD FOTO:*\n"
                    "Ketik *FOTO [SKU]* untuk mendownload dan menerima seluruh foto produk dari Blogspot.\n\n"
                    "Contoh:\n"
                    "• *FOTO 2034349*\n"
                    "• *FOTO CPO-240626-02*"
                )
                kirim_balasan_wa(chat_id, pesan_bantuan)
                return jsonify({"status": "ignored", "reason": "Missing SKU in FOTO command"}), 200

            sku = foto_cmd["code"]
            print(f"📸 Menerima Perintah FOTO untuk SKU: '{sku}' dari: {sender_name}")

            # Eksekusi fungsi download semua image produk dari Blogspot
            result = download_all_images_from_blogspot(sku)

            if result.get("status") == "not_found":
                pesan_err = (
                    f"⚠️ *FOTO PRODUK TIDAK DITEMUKAN*\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🔢 *Kode / SKU:* {sku}\n"
                    f"👤 *Diminta oleh:* {sender_name}\n\n"
                    f"❌ Postingan dengan kode *{sku}* tidak ditemukan di Blogspot."
                )
                kirim_balasan_wa(chat_id, pesan_err.strip())
                return jsonify(result), 200

            elif result.get("status") == "no_images":
                pesan_err = (
                    f"⚠️ *FOTO PRODUK KOSONG*\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🔢 *Kode / SKU:* {sku}\n"
                    f"⌚ *Judul:* {result.get('post_title', '-')}\n"
                    f"👤 *Diminta oleh:* {sender_name}\n\n"
                    f"❌ Tidak ditemukan foto pada postingan ini di Blogspot."
                )
                kirim_balasan_wa(chat_id, pesan_err.strip())
                return jsonify(result), 200

            # Kirim semua foto ke WhatsApp
            image_urls = result.get("image_urls", [])
            post_title = result.get("post_title", "")
            kirim_semua_foto_wa(chat_id, image_urls, sku, post_title=post_title)

            return jsonify({
                "status": "success",
                "command": "DOWNLOAD_FOTO",
                "sku": sku,
                "post_title": post_title,
                "total_images": len(image_urls),
                "total_downloaded": result.get("total_downloaded", 0),
                "output_dir": result.get("output_dir", "")
            }), 200

        # ======================================================================
        # JALUR D: INPUT DRAFT JAM BARU (FOTO STUDIO WA)
        # ======================================================================
        # Validasi ketat: Wajib melampirkan foto & format caption jam tangan valid
        if not is_valid_foto_studio_caption(caption, image_url):
            print(f"⏭️ Diabaikan: Pesan bukan perintah REPRICE/TAKEDOWN/REPOST dan bukan format foto studio jam baru yang valid.")
            return jsonify({"status": "ignored", "reason": "Not recognized as reprice/takedown/repost or valid photo studio submission"}), 200

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

        res_sheets = requests.post(APPS_SCRIPT_HISTORY_URL, json=payload_sheets, timeout=45)
        res_data = res_sheets.json() if res_sheets.status_code == 200 else {}

        # Mode Hening (Silent Mode): Tidak mengirim balasan WA ke grup untuk input jam baru
        print(f"✅ Data jam baru ({serial_number}) berhasil masuk ke History Foto Studio (Silent Mode)")
        return jsonify({"status": "success", "sheets_response": res_data}), 200

    except Exception as e:
        print(f"❌ Error Webhook: {e}")
        try:
            if chat_id and caption:
                pesan_err = (
                    f"⚠️ *GAGAL MEMPROSES PERINTAH IDWX*\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"👤 *Pengirim:* {sender_name}\n"
                    f"📝 *Perintah:* `{caption[:80]}`\n\n"
                    f"❌ *Kendala:* Terjadi error saat memproses (`{str(e)}`). Silakan coba kirim ulang dalam beberapa saat."
                )
                kirim_balasan_wa(chat_id, pesan_err.strip())
        except Exception as send_err:
            print(f"⚠️ Gagal mengirim notifikasi error ke WA: {send_err}")
        return jsonify({"status": "error", "message": str(e)}), 200

@app.route("/api/download_photos", methods=["GET", "POST"])
def api_download_photos():
    """
    Endpoint API manual untuk mendownload semua foto produk dari Blogspot berdasarkan SKU.
    Contoh: /api/download_photos?sku=2034349
    """
    sku = request.args.get("sku") or (request.get_json(silent=True) or {}).get("sku")
    if not sku:
        return jsonify({"status": "error", "message": "Parameter 'sku' wajib disertakan"}), 400
    res = download_all_images_from_blogspot(sku)
    return jsonify(res), (200 if res.get("status") == "success" else 404)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1].lower() in ("foto", "download", "--download"):
        if len(sys.argv) > 2:
            target_sku = sys.argv[2]
            res = download_all_images_from_blogspot(target_sku)
            print("Hasil:", res)
        else:
            print("Penggunaan CLI: python3 flask_app.py foto <SKU>")
    else:
        app.run(host="0.0.0.0", port=5000, debug=True)
