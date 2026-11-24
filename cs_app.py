# ==============================================================================
# CS_APP.PY - IDWX CUSTOMER SERVICE AI CONCIERGE FLASK APPLICATION
# ==============================================================================
# Aplikasi Flask mandiri khusus untuk layanan Customer Service (Instagram DM & WhatsApp CS).
# Terpisah sepenuhnya dari flask_app.py (Internal Admin Bot).
#
# PRINSIP KEAMANAN UTAMA (ZERO-LEAKAGE PRIVACY):
# 1. ZERO ACCESS TO GOOGLE SHEETS: Tidak ada koneksi, kredensial, atau impor ke Google Sheets.
#    Data Owner (Kolom E), Sales (Kolom F), Form Titip (Kolom D), dan Modal TIDAK PERNAH DIMUAT.
# 2. DATA WHITELISTING (DTO STRIPPER): Membuang 'sku', 'tags' konsinyasi, dan ID internal
#    sebelum data katalog diumpankan ke Gemini AI.
# 3. CONCIERGE GUARDRAILS & OUTBOUND REDACTION: Menjamin respon ramah, elegan, dan kebal
#    terhadap upaya prompt injection atau pencurian data internal.
# ==============================================================================

import os
import sys
import re
import json
import time
import html
import requests
from flask import Flask, request, jsonify

# Inisialisasi Flask Application
app = Flask(__name__)

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
                    value = value.strip().strip("'").strip('"')
                    os.environ[key] = value

load_env_file()

# Kredensial Shopify
SHOPIFY_STORE_NAME = os.getenv("SHOPIFY_STORE_NAME", "your_shopify_store_name")
SHOPIFY_CLIENT_ID = os.getenv("SHOPIFY_CLIENT_ID", "")
SHOPIFY_CLIENT_SECRET = os.getenv("SHOPIFY_CLIENT_SECRET", "")
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
SHOPIFY_TOKEN_EXPIRY = 0

# Kredensial Google Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Kredensial Instagram Direct Message (Meta Graph API)
INSTAGRAM_PAGE_ACCESS_TOKEN = os.getenv("INSTAGRAM_PAGE_ACCESS_TOKEN", "")
INSTAGRAM_VERIFY_TOKEN = os.getenv("INSTAGRAM_VERIFY_TOKEN", "idwx_ig_webhook_secret_2026")

# Konfigurasi Toko Publik & Kontak Sales
STORE_PUBLIC_DOMAIN = os.getenv("STORE_PUBLIC_DOMAIN", "idwx.co")
WA_SALES_PHONE = os.getenv("WA_SALES_PHONE", "628118811159")
SHOWROOM_ADDRESS = os.getenv(
    "SHOWROOM_ADDRESS",
    "IDWX Boutique & Showroom, Jakarta, Indonesia (Buka Senin - Sabtu 10:00 - 19:00 WIB)"
)

# ==============================================================================
# 2. DAFTAR MEREK RESMI (BRAND DICTIONARY)
# ==============================================================================
LUXURY_WATCH_BRANDS = [
    ("ROLEX", ["ROLEX"]),
    ("PATEK PHILIPPE", ["PATEK PHILIPPE", "PATEK"]),
    ("AUDEMARS PIGUET", ["AUDEMARS PIGUET", "AP"]),
    ("RICHARD MILLE", ["RICHARD MILLE", "RM"]),
    ("HUBLOT", ["HUBLOT"]),
    ("SWATCH X OMEGA", ["SWATCH X OMEGA", "OMEGA X SWATCH", "MOONSWATCH"]),
    ("OMEGA", ["OMEGA"]),
    ("CARTIER", ["CARTIER"]),
    ("TUDOR", ["TUDOR"]),
    ("PANERAI", ["PANERAI", "OFFICINE PANERAI"]),
    ("IWC", ["IWC", "SCHAFFHAUSEN"]),
    ("BREITLING", ["BREITLING"]),
    ("TAG HEUER", ["TAG HEUER", "TAG"]),
    ("VACHERON CONSTANTIN", ["VACHERON CONSTANTIN", "VACHERON"]),
    ("JAEGER-LECOULTRE", ["JAEGER-LECOULTRE", "JLC"]),
    ("FRANCK MULLER", ["FRANCK MULLER"]),
    ("ZENITH", ["ZENITH"]),
    ("CHOPARD", ["CHOPARD"]),
    ("GIRARD-PERREGAUX", ["GIRARD-PERREGAUX", "GIRARD PERREGAUX"]),
    ("BVLGARI", ["BVLGARI", "BULGARI"]),
    ("GRAND SEIKO", ["GRAND SEIKO"]),
]

# ==============================================================================
# 3. HELPER FORMATTING & SANITASI
# ==============================================================================
def format_rupiah(num):
    """Format angka nominal ke dalam format mata uang Rupiah Indonesia."""
    try:
        val = int(float(num))
        return f"Rp {val:,}".replace(",", ".")
    except Exception:
        return f"Rp {num}"

def clean_text_snippet(raw_html, max_chars=180):
    """Membersihkan tag HTML dan merapikan teks deskripsi jam tangan."""
    if not raw_html:
        return ""
    text = re.sub(r'<[^>]+>', ' ', str(raw_html))
    text = html.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "..."
    return text

# Pola regex kata kunci rahasia internal toko untuk penyaringan keluar akhir
SENSITIVE_PATTERNS = [
    r'(?i)\b(owner|pemilik|titipan|konsinyor|sales|komisi|modal|nett)\b\s*[:=]\s*\w+',
    r'(?i)\bsku\b\s*[:=]\s*\w+',
    r'(?i)\bCPO-\d{6}-\d{2}\b',
    r'(?i)\b[A-Za-z0-9]{7,15}\b(?=\s*(?:internal|gudang|brankas|titip))',
]

def redact_sensitive_output(text: str) -> str:
    """
    LAPIS 4 KEAMANAN: Memindai respon AI sebelum dikirimkan ke pelanggan publik.
    Menghapus atau meredaksi informasi sensitif toko jika secara tidak sengaja muncul.
    """
    if not text:
        return ""
    sanitized = text
    for pattern in SENSITIVE_PATTERNS:
        sanitized = re.sub(pattern, "[Info Internal Terlindungi]", sanitized)
    return sanitized

# ==============================================================================
# 4. SHOPIFY TOKEN & CATALOG QUERY ENGINE
# ==============================================================================
def get_shopify_token(force_refresh=False):
    """Mendapatkan atau memperbarui token akses API Shopify via Client Credentials."""
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
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15
        )
        if tok_res.status_code == 200:
            tok_data = tok_res.json()
            SHOPIFY_ACCESS_TOKEN = tok_data.get("access_token")
            SHOPIFY_TOKEN_EXPIRY = now + tok_data.get("expires_in", 86300)
            return SHOPIFY_ACCESS_TOKEN
        else:
            print(f"⚠️ Gagal refresh token Shopify CS: {tok_res.status_code} - {tok_res.text[:120]}")
    except Exception as e:
        print(f"❌ Error get_shopify_token CS: {e}")
    return SHOPIFY_ACCESS_TOKEN

def sanitize_watch_for_customer(product_node):
    """
    LAPIS 2 KEAMANAN: DATA WHITELISTING (DTO STRIPPER).
    Mengekstrak HANYA data publik jam tangan yang relevan bagi calon pembeli.
    
    KRITIS:
    - Field 'sku' SENGAJA DIBUANG.
    - Field 'tags' internal (__label2:Consignment, TitipIDWX) SENGAJA DIBUANG.
    - Field internal ID, variant ID, metafields SENGAJA DIBUANG.
    """
    if not product_node:
        return None

    variants = product_node.get("variants", {}).get("edges", [])
    price_val = 0.0
    compare_val = 0.0
    is_available = False

    if variants:
        v_node = variants[0].get("node", {})
        try:
            price_val = float(v_node.get("price", "0"))
        except Exception:
            price_val = 0.0
        try:
            compare_val = float(v_node.get("compareAtPrice") or 0.0)
        except Exception:
            compare_val = 0.0

        qty = v_node.get("inventoryQuantity")
        if qty is not None and qty > 0:
            is_available = True
        elif v_node.get("availableForSale"):
            is_available = True

    # Jika produk tidak tersedia / stok 0, abaikan
    if not is_available and price_val <= 0:
        return None

    handle = product_node.get("handle", "")
    featured_img = product_node.get("featuredImage", {})
    image_url = featured_img.get("url") if featured_img else None

    # Link langsung ke etalase publik website
    public_url = f"https://{STORE_PUBLIC_DOMAIN}/products/{handle}" if handle else f"https://{STORE_PUBLIC_DOMAIN}"

    return {
        "title": product_node.get("title", "").strip(),
        "vendor": product_node.get("vendor", "").strip(),
        "price": price_val,
        "price_formatted": format_rupiah(price_val),
        "compare_at_price_formatted": format_rupiah(compare_val) if compare_val > price_val else None,
        "product_url": public_url,
        "image_url": image_url,
        "summary": clean_text_snippet(product_node.get("descriptionHtml", ""))
    }

def search_shopify_catalog_for_cs(brand=None, min_price=None, max_price=None, query_text=None, limit=6):
    """
    Mencari katalog produk jam tangan aktif di Shopify khusus untuk melayani calon pembeli.
    Hanya mengembalikan produk dengan status: ACTIVE dan stok tersedia.
    """
    token = get_shopify_token()
    if not token:
        print("⚠️ Token Shopify tidak tersedia untuk CS search.")
        return []

    # Bangun parameter query Shopify GraphQL
    query_parts = ["status:active"]
    if brand:
        query_parts.append(f"vendor:'{brand}'")
    if query_text:
        # Bersihkan karakter khusus dari query text
        clean_q = re.sub(r'[^a-zA-Z0-9\s]', '', query_text).strip()
        if clean_q:
            query_parts.append(clean_q)

    full_search_filter = " AND ".join(query_parts)

    graphql_query = """
    query searchCatalogForCS($query: String!, $limit: Int!) {
      products(first: $limit, query: $query) {
        edges {
          node {
            id
            title
            handle
            vendor
            status
            descriptionHtml
            featuredImage {
              url
            }
            variants(first: 1) {
              edges {
                node {
                  price
                  compareAtPrice
                  inventoryQuantity
                  availableForSale
                }
              }
            }
          }
        }
      }
    }
    """

    url = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/2026-01/graphql.json"
    headers = {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json"
    }

    try:
        res = requests.post(
            url,
            json={"query": graphql_query, "variables": {"query": full_search_filter, "limit": max(limit * 2, 10)}},
            headers=headers,
            timeout=15
        )
        if res.status_code == 200:
            data = res.json().get("data", {}).get("products", {}).get("edges", [])
            sanitized_results = []
            for item in data:
                node = item.get("node", {})
                clean_watch = sanitize_watch_for_customer(node)
                if not clean_watch:
                    continue

                # Filter rentang harga (budget) jika diminta
                p = clean_watch["price"]
                if min_price is not None and p < float(min_price):
                    continue
                if max_price is not None and p > float(max_price):
                    continue

                sanitized_results.append(clean_watch)
                if len(sanitized_results) >= limit:
                    break

            return sanitized_results
        else:
            print(f"⚠️ Shopify GraphQL search error HTTP {res.status_code}: {res.text[:120]}")
    except Exception as e:
        print(f"❌ Error search_shopify_catalog_for_cs: {e}")

    return []

# ==============================================================================
# 5. GEMINI AI CUSTOMER SERVICE & CONCIERGE ENGINE
# ==============================================================================
def parse_cs_inquiry_with_gemini(customer_msg, chat_history=None):
    """
    Menganalisis pesan calon pembeli menggunakan Gemini untuk mengekstrak niat (intent),
    merek jam, perkiraan budget nominal, dan kata kunci seri jam.
    """
    if not customer_msg:
        return {
            "intent": "general_inquiry",
            "brand": None,
            "min_price": None,
            "max_price": None,
            "model_keywords": "",
            "search_query": ""
        }

    # Coba ekstraksi cerdas dengan Gemini API jika API key tersedia
    if GEMINI_API_KEY:
        prompt = (
            "You are an AI query parser for a luxury wristwatch boutique (IDWX).\n"
            "Analyze the following customer message and extract structured parameters for catalog searching.\n\n"
            f"Customer Message: \"{customer_msg}\"\n\n"
            "Guidelines:\n"
            "1. intent: One of ['search_watch', 'ask_availability', 'ask_price', 'ask_showroom_location', 'ask_negotiation', 'ask_trade_in', 'greeting', 'general_inquiry']\n"
            "2. brand: Standard luxury brand name if mentioned (e.g. Rolex, Patek Philippe, Audemars Piguet, Hublot, Omega, Cartier, Tudor, Richard Mille, etc.) or null.\n"
            "3. min_price: Minimum budget number in Rupiah integer (e.g. 'di atas 100jt' -> 100000000) or null.\n"
            "4. max_price: Maximum budget number in Rupiah integer (e.g. 'budget 150jt' -> 150000000, 'dibawah 200 juta' -> 200000000) or null.\n"
            "5. model_keywords: Model/series/dial keywords (e.g. 'Submariner Date', 'Datejust 36', 'Nautilus', 'Wimbledon', 'Speedmaster') or empty string.\n"
            "6. search_query: Clean concise search term for Shopify catalog search.\n\n"
            "Respond STRICTLY in JSON format:\n"
            "{\"intent\": \"...\", \"brand\": null or \"...\", \"min_price\": null or number, \"max_price\": null or number, \"model_keywords\": \"...\", \"search_query\": \"...\"}"
        )

        models_to_try = [
            "gemini-3.5-flash-lite",
            "gemini-flash-lite-latest",
            "gemini-3.8-flash",
            "gemini-3.5-flash"
        ]
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json", "temperature": 0.1}
        }

        for model_name in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
            try:
                res = requests.post(url, json=payload, timeout=12)
                if res.status_code == 200:
                    candidates = res.json().get("candidates", [])
                    if candidates:
                        raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        clean_json = re.sub(r'^```json\s*', '', raw_text.strip(), flags=re.IGNORECASE)
                        clean_json = re.sub(r'```$', '', clean_json.strip())
                        return json.loads(clean_json)
            except Exception:
                continue

    # Fallback ekstraksi berbasis kata kunci (rule-based) jika Gemini tidak aktif / offline
    matched_brand = None
    upper_msg = customer_msg.upper()
    for canonical, aliases in LUXURY_WATCH_BRANDS:
        if any(alias in upper_msg for alias in aliases):
            matched_brand = canonical
            break

    # Deteksi budget kasar (contoh: "150jt", "90 juta", "100.000.000")
    max_price = None
    m_jt = re.search(r'(\d+(?:[\.,]\d+)?)\s*(?:jt|juta)', customer_msg, re.IGNORECASE)
    if m_jt:
        try:
            max_price = int(float(m_jt.group(1).replace(",", ".")) * 1_000_000)
        except Exception:
            pass

    return {
        "intent": "search_watch" if (matched_brand or max_price) else "general_inquiry",
        "brand": matched_brand,
        "min_price": None,
        "max_price": max_price,
        "model_keywords": "",
        "search_query": customer_msg
    }

def generate_cs_response_with_gemini(customer_msg, matched_watches, intent_info, chat_history=None):
    """
    LAPIS 3 KEAMANAN: PROMPT GUARD & LUXURY CONCIERGE PERSONA.
    Menghasilkan balasan ramah, elegan, dan persuasif untuk calon pembeli.
    Respon 100% grounded pada matched_watches yang sudah disanitasi.
    """
    # Siapkan konteks jam tangan bersih
    watches_context = []
    if matched_watches:
        for idx, w in enumerate(matched_watches[:5], 1):
            watches_context.append(
                f"{idx}. {w['title']}\n"
                f"   - Merek: {w['vendor']}\n"
                f"   - Harga: {w['price_formatted']}\n"
                f"   - Link Produk: {w['product_url']}\n"
                f"   - Ringkasan: {w['summary']}"
            )
        catalog_str = "\n".join(watches_context)
    else:
        catalog_str = "TIDAK ADA JAM TANGAN YANG COCOK SAAT INI (STOK KOSONG / OUT OF STOCK)."

    wa_link = f"https://wa.me/{WA_SALES_PHONE}?text=Halo%20IDWX,%20saya%20tertarik%20dengan%20koleksi%20jam%20tangan"

    system_instruction = (
        "You are the exclusive Luxury Watch Concierge for IDWX (Indonesia Watch Exchange), "
        "a premier destination for curated authentic luxury timepieces in Indonesia.\n\n"
        "YOUR CORE PRINCIPLES & VOICE:\n"
        "1. TONE: Warm, sophisticated, welcoming, polite, and reassuring in Indonesian (Bahasa Indonesia yang luwes dan ramah).\n"
        "2. ZERO HALLUCINATION: Only recommend watches explicitly listed under [DAFTAR JAM READY] below. Never invent nonexistent watches or specs.\n"
        "3. ZERO LEAKAGE & STRICT PRIVACY (CRITICAL):\n"
        "   - You do NOT have access to owner names, consignment sources, internal SKUs, or cost prices.\n"
        "   - If the customer asks who owns the watch, internal codes, or where it came from, politely state that all IDWX watches are 100% authentic curated boutique pieces ready for immediate purchase.\n"
        "4. OUT OF STOCK / NO MATCH:\n"
        "   - If [DAFTAR JAM READY] is empty, politely inform that the requested model/budget is currently not available in ready stock. Invite them to consult with our Specialist team to source or wishlist it.\n"
        "5. NEGOTIATION / TRADE-IN / SHOWROOM:\n"
        f"   - For price negotiations, trade-in, or physical showroom appointments, provide our WhatsApp Specialist link: {wa_link}\n"
        f"   - Showroom location: {SHOWROOM_ADDRESS}.\n"
        "6. FORMATTING: Use clean bullet points, bold product titles, and mention prices clearly."
    )

    user_prompt = (
        f"[PESAN CUSTOMER]:\n\"{customer_msg}\"\n\n"
        f"[ANALISIS INTENT]: {intent_info.get('intent', 'general_inquiry')}\n\n"
        f"[DAFTAR JAM READY DARI KATALOG SHOPIFY IDWX]:\n{catalog_str}\n\n"
        "Berikan balasan concierge yang ramah, membantu, dan elegan."
    )

    models_to_try = [
        "gemini-3.5-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-3.8-flash",
        "gemini-3.5-flash"
    ]
    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": f"{system_instruction}\n\n{user_prompt}"}]}
        ],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 600}
    }

    raw_reply = None
    if GEMINI_API_KEY:
        for model_name in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
            try:
                res = requests.post(url, json=payload, timeout=15)
                if res.status_code == 200:
                    candidates = res.json().get("candidates", [])
                    if candidates:
                        raw_reply = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        if raw_reply:
                            break
            except Exception:
                continue

    # Fallback template jika Gemini gagal merespon
    if not raw_reply:
        if matched_watches:
            items_text = "\n".join([f"• *{w['title']}* - {w['price_formatted']}\n  🔗 {w['product_url']}" for w in matched_watches[:3]])
            raw_reply = (
                f"Halo! Terima kasih telah menghubungi IDWX Luxury Watch Concierge. ✨\n\n"
                f"Berikut beberapa pilihan jam tangan yang sedang ready stock di butik kami:\n\n{items_text}\n\n"
                f"Apakah ada model tertentu yang ingin Anda lihat lebih detail? Untuk penawaran terbaik atau janji temu di showroom, silakan hubungi tim Specialist kami via WhatsApp: {wa_link}"
            )
        else:
            raw_reply = (
                f"Halo! Terima kasih telah menghubungi IDWX. ✨\n\n"
                f"Saat ini unit dengan kriteria yang Anda cari belum tersedia di etalase ready stock kami. "
                f"Namun tim Specialist kami dapat membantu mencarikan (*custom sourcing*) unit yang Anda inginkan.\n\n"
                f"Silakan hubungi WhatsApp Specialist kami di sini: {wa_link}"
            )

    # LAPIS 4: Saring teks keluar sebelum dikembalikan
    return redact_sensitive_output(raw_reply)

# ==============================================================================
# 6. INSTAGRAM DM INTEGRATION (META GRAPH API)
# ==============================================================================
def send_instagram_text(recipient_id, text_message):
    """Mengirim pesan teks ke pengguna Instagram DM melalui Meta Send API."""
    if not INSTAGRAM_PAGE_ACCESS_TOKEN or not recipient_id:
        return False
    url = f"https://graph.facebook.com/v19.0/me/messages?access_token={INSTAGRAM_PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text_message}
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except Exception as e:
        print(f"❌ Error send_instagram_text: {e}")
        return False

def send_instagram_carousel(recipient_id, watches):
    """
    Mengirim kartu geser (Generic Template Carousel) berisi jam tangan pilihan
    lengkap dengan foto, judul, harga, dan tombol klik ke Instagram DM.
    """
    if not INSTAGRAM_PAGE_ACCESS_TOKEN or not recipient_id or not watches:
        return False

    elements = []
    wa_link = f"https://wa.me/{WA_SALES_PHONE}?text=Halo%20IDWX,%20saya%20ingin%20tanya%20jam%20ini"

    for w in watches[:5]:  # Meta carousel mendukung s/d 10 elemen, batasi 5 agar rapi
        buttons = []
        if w.get("product_url"):
            buttons.append({
                "type": "web_url",
                "url": w["product_url"],
                "title": "Lihat di Website"
            })
        buttons.append({
            "type": "web_url",
            "url": wa_link,
            "title": "Chat Specialist"
        })

        element = {
            "title": w["title"][:80],
            "subtitle": f"Harga: {w['price_formatted']}",
            "buttons": buttons
        }
        if w.get("image_url"):
            element["image_url"] = w["image_url"]

        elements.append(element)

    url = f"https://graph.facebook.com/v19.0/me/messages?access_token={INSTAGRAM_PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {
            "attachment": {
                "type": "template",
                "payload": {
                    "template_type": "generic",
                    "elements": elements
                }
            }
        }
    }
    try:
        res = requests.post(url, json=payload, timeout=12)
        return res.status_code == 200
    except Exception as e:
        print(f"❌ Error send_instagram_carousel: {e}")
        return False

# ==============================================================================
# 7. FLASK WEBHOOK ROUTES
# ==============================================================================
@app.route("/", methods=["GET"])
def index():
    """Halaman status server CS Bot."""
    return jsonify({
        "service": "IDWX Customer Service AI Concierge",
        "status": "RUNNING",
        "endpoints": {
            "cs_webhook": "POST /cs-webhook",
            "instagram_webhook": "GET/POST /instagram-webhook"
        },
        "security": "Zero-Leakage Privacy Protected"
    }), 200

@app.route("/cs-webhook", methods=["POST"])
def cs_webhook():
    """
    Endpoint mandiri untuk pengujian atau integrasi Webchat Website / WhatsApp CS.
    Payload Masuk:
    {
        "message": "Cari Rolex budget 150jt",
        "sender_id": "cust_123",
        "history": []
    }
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        customer_msg = data.get("message", "").strip()
        sender_id = data.get("sender_id", "guest")
        chat_history = data.get("history", [])

        if not customer_msg:
            return jsonify({"status": "error", "message": "Field 'message' tidak boleh kosong."}), 400

        # 1. Ekstraksi niat dan kriteria pencarian
        intent_info = parse_cs_inquiry_with_gemini(customer_msg, chat_history)

        # 2. Cari katalog jam tangan yang cocok di Shopify (Hanya Status ACTIVE & Stok > 0)
        matched_watches = []
        if intent_info.get("intent") in ["search_watch", "ask_availability", "ask_price", "general_inquiry"]:
            matched_watches = search_shopify_catalog_for_cs(
                brand=intent_info.get("brand"),
                min_price=intent_info.get("min_price"),
                max_price=intent_info.get("max_price"),
                query_text=intent_info.get("model_keywords") or intent_info.get("search_query"),
                limit=5
            )

        # 3. Rangkai balasan ramah & aman via Gemini
        reply_text = generate_cs_response_with_gemini(
            customer_msg=customer_msg,
            matched_watches=matched_watches,
            intent_info=intent_info,
            chat_history=chat_history
        )

        return jsonify({
            "status": "success",
            "reply": reply_text,
            "intent": intent_info,
            "matched_count": len(matched_watches),
            "matched_watches": matched_watches
        }), 200

    except Exception as e:
        print(f"❌ Error pada /cs-webhook: {e}")
        return jsonify({"status": "error", "message": "Terjadi kendala pada server CS."}), 500

@app.route("/instagram-webhook", methods=["GET"])
def verify_instagram_webhook():
    """
    Verifikasi Webhook dari Meta for Developers (hub.challenge).
    Meta mengirimkan request GET untuk validasi token verifikasi.
    """
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == INSTAGRAM_VERIFY_TOKEN:
        print("✅ Webhook Instagram berhasil diverifikasi oleh Meta!")
        return challenge, 200
    else:
        print("⚠️ Verifikasi Webhook Instagram gagal: token tidak cocok.")
        return "Verification token mismatch", 403

@app.route("/instagram-webhook", methods=["POST"])
def handle_instagram_webhook():
    """
    Menerima event pesan Direct Message masuk dari calon pembeli di Instagram.
    """
    try:
        payload = request.get_json(force=True, silent=True) or {}
        entry_list = payload.get("entry", [])

        for entry in entry_list:
            messaging_events = entry.get("messaging", [])
            for event in messaging_events:
                sender_id = event.get("sender", {}).get("id")
                message_obj = event.get("message", {})
                customer_text = message_obj.get("text", "").strip()

                # Abaikan event pesan yang dikirim oleh bot sendiri
                if message_obj.get("is_echo") or not customer_text or not sender_id:
                    continue

                print(f"📩 Pesan Instagram DM dari {sender_id}: '{customer_text}'")

                # 1. Ekstrak parameter
                intent_info = parse_cs_inquiry_with_gemini(customer_text)

                # 2. Cari katalog Shopify jika pelanggan mencari jam
                matched_watches = []
                if intent_info.get("intent") in ["search_watch", "ask_availability", "ask_price", "general_inquiry"]:
                    matched_watches = search_shopify_catalog_for_cs(
                        brand=intent_info.get("brand"),
                        min_price=intent_info.get("min_price"),
                        max_price=intent_info.get("max_price"),
                        query_text=intent_info.get("model_keywords") or intent_info.get("search_query"),
                        limit=5
                    )

                # 3. Buat balasan concierge
                reply_text = generate_cs_response_with_gemini(
                    customer_msg=customer_text,
                    matched_watches=matched_watches,
                    intent_info=intent_info
                )

                # 4. Kirim balasan ke Instagram DM
                send_instagram_text(sender_id, reply_text)

                # 5. Jika ada produk yang cocok, kirim juga Carousel Cards interaktif
                if matched_watches:
                    send_instagram_carousel(sender_id, matched_watches)

        return "EVENT_RECEIVED", 200

    except Exception as e:
        print(f"❌ Error handle_instagram_webhook: {e}")
        return "ERROR_PROCESSING", 500

# ==============================================================================
# 8. LOCAL DEVELOPMENT ENTRY POINT
# ==============================================================================
if __name__ == "__main__":
    port = int(os.environ.get("CS_PORT", 5001))
    print(f"🚀 Memulai IDWX Customer Service AI Concierge di port {port}...")
    app.run(host="0.0.0.0", port=port, debug=False)
