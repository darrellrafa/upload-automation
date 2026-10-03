import os
import requests
from bs4 import BeautifulSoup
import re
import time
import sys
import base64
import json
from datetime import datetime
from urllib.parse import urlparse

# Library Google API dengan metode Refresh Token
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# ==========================================
# 1. KONFIGURASI KREDENSIAL GOOGLE & SHOPIFY
# ==========================================
# Kredensial Google OAuth (Blogger API)
GCP_CLIENT_ID = "168252551277-pruc3o3n7q11rqiv4adhqqcmg5ddnc91.apps.googleusercontent.com"
GCP_CLIENT_SECRET = "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"
GCP_REFRESH_TOKEN = "1//04L7X62nYALV7CgYIARAAGAQSNwF-L9Ir_8FfDYCXTp-GfDnUtk61UASRAXWNzSmsK3xOR79zkPE9Pqw47UtrL_nxk-K8E_U4LKQ"
BLOG_ID = "4705513177871222706"

# Kredensial Shopify
SHOPIFY_STORE_NAME = "idwx"
API_VERSION = "2025-01"
SHOPIFY_CLIENT_ID = "39e6bd92b726c60b440a4d4c0555f935"
SHOPIFY_CLIENT_SECRET = "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"

# URL Webhook (Apps Script)
GOOGLE_WEB_APP_URL = "https://script.google.com/macros/s/AKfycbw-PV4bR4PhgJyjPvY_dHnz54fhmzEvSOIJJCDyyWOASeaBMcdOkcMxpftXfTHcqPf2/exec"
FEATURED_WEB_APP_URL = "https://script.google.com/macros/s/AKfycbymvWQh66pDkcSOe1fBC1rQ--VVsTKONFBM-o52qU-8sS0_aEV4JzxFBzEBx1dk-d6O_w/exec"
OWNER_APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbw-PV4bR4PhgJyjPvY_dHnz54fhmzEvSOIJJCDyyWOASeaBMcdOkcMxpftXfTHcqPf2/exec"

# Daftar Merek IDWX (gabungan dari semua script)
DAFTAR_MEREK_IDWX = {
    "ROLEX": "Rolex", "PATEK PHILIPPE": "Patek Philippe", "AUDEMARS PIGUET": "Audemars Piguet", "JAEGER": "Jaeger-LeCoultre",
    "OMEGA": "Omega", "TUDOR": "Tudor", "SEIKO": "Seiko", "GRAND SEIKO": "Grand Seiko", "BAUME": "Baume & Mercier", "BAUME & MERCIER": "Baume & Mercier",
    "CARTIER": "Cartier", "PANERAI": "Panerai", "IWC": "IWC", "BREITLING": "Breitling",
    "TAG HEUER": "Tag Heuer", "JAEGER-LECOULTRE": "Jaeger-LeCoultre", "JLC": "Jaeger-LeCoultre",
    "HUBLOT": "Hublot", "RICHARD MILLE": "Richard Mille", "VACHERON CONSTANTIN": "Vacheron Constantin",
    "BLANCPAIN": "Blancpain", "CHOPARD": "Chopard", "ZENITH": "Zenith", "LONGINES": "Longines",
    "TISSOT": "Tissot", "F.P. JOURNE": "F.P. Journe", "BVLGARI": "Bvlgari", "A. LANGE": "A. Lange & Söhne"
}

# ==========================================
# 2. DAFTAR URL UNTUK MASING-MASING MODE
# ==========================================
# Isi URL di dalam array di bawah ini sesuai dengan format postingannya
DAFTAR_URL_NOTSYNC = [
    # "https://www.dualtime.id/2026/10/for-sale-cartier-panthere-m-silver-dial.html",
]

DAFTAR_URL_STUDIO = [
    # "https://www.dualtime.id/2026/10/for-sale-rolex-datejust-31mm-twotone.html",
]

DAFTAR_URL_OWNER = [
    # "https://www.dualtime.id/2026/09/for-sale-rolex-daytona-white-panda_01570651495.html",
]

# ==========================================
# 3. AUTENTIKASI OAUTH BLOGGER
# ==========================================
def get_blogger_service():
    print("Memulai autentikasi Google Blogger API dengan Refresh Token...")
    creds = Credentials(
        token=None,
        refresh_token=GCP_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GCP_CLIENT_ID,
        client_secret=GCP_CLIENT_SECRET
    )
    blogger_service = build('blogger', 'v3', credentials=creds)
    print("✅ Autentikasi Google berhasil tanpa perlu login!")
    return blogger_service

# ==========================================
# 4. FUNGSI API SHOPIFY & HELPER
# ==========================================
def get_shopify_access_token():
    print("Meminta token akses API baru dari Shopify...")
    token_url = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/oauth/access_token"
    payload = {
        "grant_type": "client_credentials",
        "client_id": SHOPIFY_CLIENT_ID,
        "client_secret": SHOPIFY_CLIENT_SECRET
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(token_url, headers=headers, data=payload)
    if response.status_code == 200:
        return response.json().get('access_token')
    else:
        print(f"❌ Gagal mendapatkan token: {response.text}")
        sys.exit()

# Inisialisasi token & header secara global
SHOPIFY_ACCESS_TOKEN = get_shopify_access_token()
HEADERS_SHOPIFY = {
    "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
    "Content-Type": "application/json"
}
GRAPHQL_URL = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{API_VERSION}/graphql.json"
SHOPIFY_UPLOAD_ENDPOINT = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{API_VERSION}/products.json"


def get_target_location(target_location_name):
    url = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{API_VERSION}/locations.json"
    res = requests.get(url, headers=HEADERS_SHOPIFY)
    if res.status_code == 200:
        for loc in res.json().get('locations', []):
            if loc.get('name') == target_location_name:
                return loc['id']
    return None

def get_category_id():
    query = '{ taxonomy { categories(search: "Watches", first: 1) { edges { node { id fullName } } } } }'
    res = requests.post(GRAPHQL_URL, headers=HEADERS_SHOPIFY, json={"query": query})
    if res.status_code == 200:
        edges = res.json().get('data', {}).get('taxonomy', {}).get('categories', {}).get('edges', [])
        if edges: return edges[0]['node']['id']
    return None

def get_existing_data():
    print("Mendownload database SKU dan Handle dari Shopify...")
    skus = set()
    handles = set()
    endpoint = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{API_VERSION}/products.json"
    params = {"limit": 250, "fields": "handle,variants"}
    while endpoint:
        response = requests.get(endpoint, headers=HEADERS_SHOPIFY, params=params)
        if response.status_code != 200: break
        for product in response.json().get('products', []):
            if product.get('handle'): handles.add(product.get('handle'))
            for variant in product.get('variants', []):
                if variant.get('sku'): skus.add(variant.get('sku'))

        link_header = response.headers.get('Link')
        endpoint = None
        if link_header:
            for link in link_header.split(','):
                if 'rel="next"' in link:
                    endpoint = link[link.find("<")+1:link.find(">")]
                    break
    return skus, handles

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

# Variabel Global Database Shopify
LOCATION_ID_BLOK_M = get_target_location("DUALTIME - BLOK M PLAZA")
LOCATION_ID_OWNER = get_target_location("OWNER (S)")
CATEGORY_ID = get_category_id()
EXISTING_SKUS, EXISTING_HANDLES = get_existing_data()

# ==========================================
# 5. FUNGSI PROSES UNTUK NOTSYNC
# ==========================================
def process_notsync(blogger_service, urls):
    if not urls:
        return
        
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
            clean_title = re.sub(r'\[FOR SALE\]\s*', '', raw_title, flags=re.IGNORECASE).strip()
            if not clean_title: continue

            soup = BeautifulSoup(raw_html, 'html.parser')

            # --- EKSTRAKSI GAMBAR ---
            raw_image_urls = []
            image_urls = []
            potongan_kata = clean_title.split()[:3]
            alt_text_rapi = " ".join(potongan_kata).title()
            nama_file_dasar = alt_text_rapi.replace(" ", "-")

            for img in soup.find_all('img'):
                if 'src' in img.attrs:
                    img_url = img['src']
                    parent_a = img.find_parent('a')
                    if parent_a and 'href' in parent_a.attrs and re.search(r'\.(jpg|jpeg|png|webp)$', parent_a['href'], re.IGNORECASE):
                        img_url = parent_a['href']
                    high_res_url = re.sub(r'/(?:s\d+|w\d+-h\d+[^/]*)/([^/]+)$', r'/s0/\1', img_url)
                    if high_res_url not in raw_image_urls: raw_image_urls.append(high_res_url)

            for i, img_url in enumerate(raw_image_urls):
                try:
                    img_res = requests.get(img_url, timeout=10)
                    if img_res.status_code == 200:
                        image_urls.append({
                            "attachment": base64.b64encode(img_res.content).decode('utf-8'),
                            "filename": f"{nama_file_dasar}-{i+1}.jpg",
                            "alt": alt_text_rapi
                        })
                except Exception: pass

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
            sku_match = re.search(r'Code:\s*([\w\-]+)', body_text, re.IGNORECASE)
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
            if year_match: year = year_match.group(1)

            # --- MENYUSUN TAGS & DESKRIPSI ---
            tags_list = ['NotSync']
            desc_lines = []
            for line in lines:
                if re.search(r'^(Price|Code|Last Post|Order Received|Form|Notes):', line, re.IGNORECASE): break
                desc_lines.append(line)
            if desc_lines: desc_lines[0] = f"<strong>{desc_lines[0]}</strong>"
            final_description_html = "<p>" + "<br>".join(desc_lines) + "</p>"

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

            shopify_res = requests.post(SHOPIFY_UPLOAD_ENDPOINT, headers=HEADERS_SHOPIFY, json=product_payload)

            if shopify_res.status_code == 201:
                prod_data = shopify_res.json()['product']
                new_id = prod_data['id']
                graphql_product_id = f"gid://shopify/Product/{new_id}"
                print(f"   🎉 Sukses diunggah! Product ID: {new_id}")

                if CATEGORY_ID:
                    mutation = "mutation productUpdate($input: ProductInput!) { productUpdate(input: $input) { userErrors { message } } }"
                    requests.post(GRAPHQL_URL, headers=HEADERS_SHOPIFY, json={"query": mutation, "variables": {"input": {"id": graphql_product_id, "category": CATEGORY_ID}}})

                res_pubs = requests.post(GRAPHQL_URL, headers=HEADERS_SHOPIFY, json={"query": "{ publications(first: 20) { edges { node { id name } } } }"})
                if res_pubs.status_code == 200:
                    pub_inputs = [{"publicationId": edge['node']['id']} for edge in res_pubs.json().get('data', {}).get('publications', {}).get('edges', [])]
                    if pub_inputs:
                        mutation_pub = "mutation publishablePublish($id: ID!, $input: [PublicationInput!]!) { publishablePublish(id: $id, input: $input) { userErrors { message } } }"
                        requests.post(GRAPHQL_URL, headers=HEADERS_SHOPIFY, json={"query": mutation_pub, "variables": {"id": graphql_product_id, "input": pub_inputs}})

                if LOCATION_ID_BLOK_M:
                    inv_url = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{API_VERSION}/inventory_levels/set.json"
                    requests.post(inv_url, headers=HEADERS_SHOPIFY, json={"location_id": LOCATION_ID_BLOK_M, "inventory_item_id": prod_data['variants'][0]['inventory_item_id'], "available": 1})
            else:
                print(f"   ❌ Gagal mengunggah. Error: {shopify_res.text}")

        except Exception as e:
            print(f"   ❌ Error saat memproses {url}: {e}")

        time.sleep(1)
    
    print("✅ SEMUA PROSES (NOTSYNC) SELESAI!")


# ==========================================
# 6. FUNGSI PROSES UNTUK PHOTO STUDIO
# ==========================================
def process_photo_studio(blogger_service, urls):
    if not urls:
        return
        
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
            custom_handle = buat_handle_url(clean_title, year, EXISTING_HANDLES)

            soup = BeautifulSoup(raw_html, 'html.parser')

            raw_image_urls, image_urls, first_image_url = [], [], ""
            potongan_kata = clean_title.split()[:3]
            alt_text_rapi = " ".join(potongan_kata).title()
            nama_file_dasar = alt_text_rapi.replace(" ", "-")

            for img in soup.find_all('img'):
                if 'src' in img.attrs:
                    raw_url = img['src']
                    parent_a = img.find_parent('a')
                    if parent_a and 'href' in parent_a.attrs and re.search(r'\.(jpg|jpeg|png|webp)$', parent_a['href'], re.IGNORECASE): raw_url = parent_a['href']
                    high_res_url = re.sub(r'/(?:s\d+|w\d+-h\d+[^/]*)/([^/]+)$', r'/s0/\1', raw_url)
                    if high_res_url not in raw_image_urls: raw_image_urls.append(high_res_url)

            for i, img_url in enumerate(raw_image_urls):
                try:
                    img_res = requests.get(img_url, timeout=10)
                    if img_res.status_code == 200:
                        img_base64 = base64.b64encode(img_res.content).decode('utf-8')
                        image_urls.append({"attachment": img_base64, "filename": f"{nama_file_dasar}-{i+1}.jpg", "alt": alt_text_rapi})
                        if i == 0: first_image_url = img_url
                except: pass

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
            final_description_html = "<p>" + "<br>".join(desc_lines) + "</p>" + youtube_embed_placeholder

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
            shopify_res = requests.post(SHOPIFY_UPLOAD_ENDPOINT, headers=HEADERS_SHOPIFY, json=product_payload)

            if shopify_res.status_code == 201:
                prod_data = shopify_res.json()['product']
                new_id = prod_data['id']
                graphql_product_id = f"gid://shopify/Product/{new_id}"
                print(f"   🎉 Sukses diunggah! Product ID: {new_id}")

                if CATEGORY_ID:
                    requests.post(GRAPHQL_URL, headers=HEADERS_SHOPIFY, json={"query": "mutation productUpdate($input: ProductInput!) { productUpdate(input: $input) { userErrors { message } } }", "variables": {"input": {"id": graphql_product_id, "category": CATEGORY_ID}}})

                res_pubs = requests.post(GRAPHQL_URL, headers=HEADERS_SHOPIFY, json={"query": "{ publications(first: 20) { edges { node { id name } } } }"})
                if res_pubs.status_code == 200:
                    pub_inputs = [{"publicationId": edge['node']['id']} for edge in res_pubs.json().get('data', {}).get('publications', {}).get('edges', [])]
                    if pub_inputs: requests.post(GRAPHQL_URL, headers=HEADERS_SHOPIFY, json={"query": "mutation publishablePublish($id: ID!, $input: [PublicationInput!]!) { publishablePublish(id: $id, input: $input) { userErrors { message } } }", "variables": {"id": graphql_product_id, "input": pub_inputs}})

                if LOCATION_ID_BLOK_M:
                    requests.post(f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{API_VERSION}/inventory_levels/set.json", headers=HEADERS_SHOPIFY, json={"location_id": LOCATION_ID_BLOK_M, "inventory_item_id": prod_data['variants'][0]['inventory_item_id'], "available": 1})

                # POST KE GOOGLE SHEETS VIA WEBHOOK
                if is_featured:
                    print(f"   ⭐ Item FEATURED. Mengirim data ke Spreadsheet Slow Moving...")
                    try:
                        tanggal_hari_ini = datetime.now().strftime("%d/%m/%Y")
                        payload_featured = {
                            "date": tanggal_hari_ini, "owner": owner.upper() if owner else "", "brand": vendor.upper(),
                            "description": display_title_no_year.upper(), "year": year, "condition": condition.upper(),
                            "price": price, "reference": reference, "serial_number": base_sku if base_sku else sku, "link": url
                        }
                        res_feat = requests.post(FEATURED_WEB_APP_URL, json=payload_featured)
                        try:
                            res_feat_data = res_feat.json()
                            if res_feat.status_code == 200 and res_feat_data.get("status") == "success": print(f"   📊 Berhasil! {res_feat_data.get('message')}")
                            else: print(f"   ⚠️ Gagal update Sheets Featured: {res_feat_data.get('message')}")
                        except: pass
                    except Exception as e: print(f"   ⚠️ Error Webhook Featured Sheets: {e}")
                elif is_consign_item:
                    print(f"   📝 Item Consign. Update SKU Asli '{base_sku}' di Google Sheets Photo Studio...")
                    try:
                        now = datetime.now()
                        tanggal_hari_ini = now.strftime(f"%A, {now.day} %B %Y")
                        sku_pencarian = base_sku if base_sku else sku
                        payload_sheets = {
                            "sheet_name": "PHOTO STUDIO", "sku": sku_pencarian, "tanggal": tanggal_hari_ini, "photo_url": first_image_url
                        }
                        requests.post(GOOGLE_WEB_APP_URL, json=payload_sheets)
                    except Exception as e: print(f"   ⚠️ Error Webhook Sheets: {e}")
            else:
                print(f"   ❌ Gagal mengunggah. Error: {shopify_res.text}")

        except Exception as e:
            print(f"   ❌ Error saat memproses {url}: {e}")

        time.sleep(1)

    print("✅ SEMUA PROSES (PHOTO STUDIO) SELESAI!")


# ==========================================
# 7. FUNGSI PROSES UNTUK PHOTO OWNER
# ==========================================
def process_photo_owner(blogger_service, urls):
    if not urls:
        return
        
    print(f"\nMemulai proses pemindahan data untuk {len(urls)} item (Format Photo Owner)...")
    for idx, url in enumerate(urls, 1):
        print(f"\n[{idx}/{len(urls)}] Memproses: {url}")
        try:
            parsed_url = urlparse(url)
            post_path = parsed_url.path

            request = blogger_service.posts().getByPath(blogId=BLOG_ID, path=post_path)
            response = request.execute()

            raw_title = response.get('title', '')
            clean_title = re.sub(r'\[FOR SALE\]\s*', '', raw_title, flags=re.IGNORECASE).strip()
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
                year_match_title = re.search(r'\b(19\d{2}|20\d{2})\b', clean_title)
                if year_match_title:
                    year = year_match_title.group(1)

            vendor = "Unknown"
            for keyword in sorted(DAFTAR_MEREK_IDWX.keys(), key=len, reverse=True):
                if keyword in clean_title.upper():
                    vendor = DAFTAR_MEREK_IDWX[keyword]
                    break
            if vendor == "Unknown": vendor = clean_title.split()[0].title()

            seo_page_title = f"{clean_title} ({year})" if year else clean_title
            short_display_title = re.sub(f"^{vendor}\s+", "", clean_title, flags=re.IGNORECASE).strip()
            if year: short_display_title = f"{short_display_title} ({year})"

            custom_handle = buat_handle_url(clean_title, year, EXISTING_HANDLES)

            raw_image_urls = []
            image_urls = []

            potongan_kata = clean_title.split()[:3]
            alt_text_rapi = " ".join(potongan_kata).title()
            nama_file_dasar = alt_text_rapi.replace(" ", "-")

            for img in soup.find_all('img'):
                if 'src' in img.attrs:
                    raw_url = img['src']
                    parent_a = img.find_parent('a')
                    if parent_a and 'href' in parent_a.attrs and re.search(r'\.(jpg|jpeg|png|webp)$', parent_a['href'], re.IGNORECASE):
                        raw_url = parent_a['href']
                    high_res_url = re.sub(r'/(?:s\d+|w\d+-h\d+[^/]*)/([^/]+)$', r'/s0/\1', raw_url)

                    if high_res_url not in raw_image_urls:
                        raw_image_urls.append(high_res_url)

            for i, img_url in enumerate(raw_image_urls):
                try:
                    img_res = requests.get(img_url, timeout=10)
                    if img_res.status_code == 200:
                        img_base64 = base64.b64encode(img_res.content).decode('utf-8')
                        custom_filename = f"{nama_file_dasar}-{i+1}.jpg"
                        image_urls.append({
                            "attachment": img_base64,
                            "filename": custom_filename,
                            "alt": alt_text_rapi
                        })
                except Exception as e:
                    print(f"   ⚠️ Gagal memproses gambar {i+1}: {e}")

            sku = ""
            sku_match = re.search(r'Code:\s*([\w\-]+)', body_text, re.IGNORECASE)
            if sku_match:
                base_sku = sku_match.group(1)
                sku = base_sku
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
            final_description_html = "<p>" + "<br>".join(desc_lines) + "</p>"

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
            shopify_res = requests.post(SHOPIFY_UPLOAD_ENDPOINT, headers=HEADERS_SHOPIFY, json=product_payload)

            if shopify_res.status_code == 201:
                prod_data = shopify_res.json()['product']
                new_id = prod_data['id']
                graphql_product_id = f"gid://shopify/Product/{new_id}"
                print(f"   🎉 Sukses diunggah! Product ID: {new_id}")

                if CATEGORY_ID:
                    mutation = "mutation productUpdate($input: ProductInput!) { productUpdate(input: $input) { userErrors { message } } }"
                    variables = {"input": {"id": graphql_product_id, "category": CATEGORY_ID}}
                    requests.post(GRAPHQL_URL, headers=HEADERS_SHOPIFY, json={"query": mutation, "variables": variables})
                    print(f"   🏷️  Kategori diatur ke 'Watches'.")

                query_pubs = "{ publications(first: 20) { edges { node { id name } } } }"
                res_pubs = requests.post(GRAPHQL_URL, headers=HEADERS_SHOPIFY, json={"query": query_pubs})
                if res_pubs.status_code == 200:
                    edges = res_pubs.json().get('data', {}).get('publications', {}).get('edges', [])
                    pub_inputs = [{"publicationId": edge['node']['id']} for edge in edges]

                    if pub_inputs:
                        mutation_pub = "mutation publishablePublish($id: ID!, $input: [PublicationInput!]!) { publishablePublish(id: $id, input: $input) { userErrors { message } } }"
                        vars_pub = {"id": graphql_product_id, "input": pub_inputs}
                        requests.post(GRAPHQL_URL, headers=HEADERS_SHOPIFY, json={"query": mutation_pub, "variables": vars_pub})
                        print(f"   📢 Berhasil dipublikasikan ke {len(pub_inputs)} Sales Channels.")

                if LOCATION_ID_OWNER:
                    inventory_item_id = prod_data['variants'][0]['inventory_item_id']
                    inv_url = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{API_VERSION}/inventory_levels/set.json"
                    inv_payload = {"location_id": LOCATION_ID_OWNER, "inventory_item_id": inventory_item_id, "available": 1}
                    requests.post(inv_url, headers=HEADERS_SHOPIFY, json=inv_payload)
                    print(f"   📦 Stok disetel ke 1 untuk OWNER (S).")

                print(f"   🔍 Mengirim perintah ke Spreadsheet untuk mencentang SKU '{sku}'...")
                try:
                    payload_ke_gsheets = {"action": "check_web_owner", "sku": sku}
                    app_res = requests.post(OWNER_APPS_SCRIPT_URL, json=payload_ke_gsheets)

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

            else:
                print(f"   ❌ Gagal mengunggah ke Shopify. Error: {shopify_res.text}")

        except Exception as e:
            print(f"   ❌ Error saat memproses {url}: {e}")

        time.sleep(1)

    print("✅ SEMUA PROSES (PHOTO OWNER) SELESAI!")


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
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()

def save_processed_skus(skus, filepath="processed_skus.json"):
    with open(filepath, "w") as f:
        json.dump(list(skus), f)

PROCESSED_SKUS = load_processed_skus()

def get_todays_archive_url():
    now = datetime.now()
    date_str = now.strftime("%Y_%m_%d")
    return f"https://www.dualtime.id/{date_str}_archive.html"

def extract_post_links(archive_url):
    try:
        res = requests.get(archive_url, timeout=15)
        if res.status_code != 200:
            print(f"⚠️ Halaman arsip belum tersedia (Status: {res.status_code}): {archive_url}")
            return []
        soup = BeautifulSoup(res.text, 'html.parser')
        post_links = set()
        for a in soup.find_all('a'):
            href = a.get('href')
            if href and href.startswith("https://www.dualtime.id/20") and href.endswith(".html") and "_archive.html" not in href:
                post_links.add(href)
        return list(post_links)
    except Exception as e:
        print(f"⚠️ Error saat mengambil halaman arsip: {e}")
        return []

def classify_and_process_url(blogger_service, url):
    try:
        parsed_url = urlparse(url)
        post_path = parsed_url.path
        request = blogger_service.posts().getByPath(blogId=BLOG_ID, path=post_path)
        response = request.execute()
        
        labels = response.get('labels', [])
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
        sku_match = re.search(r'Code:\s*([\w\-]+)', body_text, re.IGNORECASE)
        if sku_match:
            sku = sku_match.group(1).upper()
            
        if sku and sku in PROCESSED_SKUS:
            print(f"⏭️ {url} dilewati karena SKU '{sku}' sudah terupload di sesi ini.")
            return True # Dianggap sukses agar link masuk processed_urls
        
        is_consignment = any('CONSIGNMENT' in label.upper() for label in labels)
        is_featured = any('FEATURED' in label.upper() for label in labels)
        
        if is_consignment or is_featured:
            print(f"📌 {url} diklasifikasikan sebagai: PHOTO STUDIO (ditemukan label Consignment/Featured)")
            process_photo_studio(blogger_service, [url])
            if sku:
                PROCESSED_SKUS.add(sku)
                save_processed_skus(PROCESSED_SKUS)
            return True
            
        raw_image_urls = []
        for img in soup.find_all('img'):
            if 'src' in img.attrs:
                img_url = img['src']
                parent_a = img.find_parent('a')
                if parent_a and 'href' in parent_a.attrs and re.search(r'\.(jpg|jpeg|png|webp)$', parent_a['href'], re.IGNORECASE):
                    img_url = parent_a['href']
                high_res_url = re.sub(r'/(?:s\d+|w\d+-h\d+[^/]*)/([^/]+)$', r'/s0/\1', img_url)
                if high_res_url not in raw_image_urls:
                    raw_image_urls.append(high_res_url)
                    
        image_count = len(raw_image_urls)
        
        if sku.startswith("CPO"):
            if image_count == 1:
                print(f"📌 {url} diklasifikasikan sebagai: NOTSYNC (SKU {sku}, {image_count} Gambar)")
                process_notsync(blogger_service, [url])
            else:
                print(f"📌 {url} diklasifikasikan sebagai: PHOTO OWNER (SKU {sku}, {image_count} Gambar)")
                process_photo_owner(blogger_service, [url])
        else:
            print(f"⚠️ {url} tidak dapat diklasifikasikan otomatis (SKU '{sku}', bukan awalan CPO). Akan diproses default sebagai PHOTO STUDIO.")
            process_photo_studio(blogger_service, [url])
            
        if sku:
            PROCESSED_SKUS.add(sku)
            save_processed_skus(PROCESSED_SKUS)
            
        return True
            
    except Exception as e:
        print(f"❌ Gagal mengklasifikasikan atau memproses {url}: {e}")
        return False

# ==========================================
# 9. PROGRAM UTAMA
# ==========================================
if __name__ == "__main__":
    print("="*50)
    print("🚀 MEMULAI OTOMASI UPLOAD IDWX (MODE CONTINUOUS)")
    print("="*50)
    
    blogger_service = get_blogger_service()
    
    # Menjalankan proses sesuai URL manual (jika ada yang diisi di atas)
    if DAFTAR_URL_NOTSYNC:
        process_notsync(blogger_service, DAFTAR_URL_NOTSYNC)
    if DAFTAR_URL_STUDIO:
        process_photo_studio(blogger_service, DAFTAR_URL_STUDIO)
    if DAFTAR_URL_OWNER:
        process_photo_owner(blogger_service, DAFTAR_URL_OWNER)
        
    print("\nMemasuki mode monitoring otomatis setiap 5 menit...")
    
    while True:
        try:
            processed_urls = load_processed_urls()
            archive_url = get_todays_archive_url()
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Mengecek: {archive_url}")
            
            new_links = extract_post_links(archive_url)
            
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
                        
            print("Menunggu 5 menit sebelum pengecekan berikutnya...")
            time.sleep(300)
            
        except KeyboardInterrupt:
            print("\nProgram dihentikan oleh user.")
            break
        except Exception as e:
            print(f"⚠️ Terjadi kesalahan pada loop utama: {e}")
            time.sleep(60)
