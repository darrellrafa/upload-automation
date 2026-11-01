# Upload Automation

Automasi upload dan pemrosesan produk jam tangan dari postingan Blogger ke Shopify, dengan integrasi tambahan ke Google Drive, YouTube Shorts, dan webhook spreadsheet.

Project ini dibuat untuk mengotomatisasi alur kerja pemasaran dan penjualan produk luxury watch, termasuk klasifikasi format postingan (`NOTSYNC`, `TWP`, `PHOTO STUDIO`, `PHOTO OWNER`), pengolahan metadata produk, upload gambar, sinkronisasi stok, serta pengelolaan antrean video YouTube.

## Fitur Utama

- Pengambilan data postingan dari Blogger API
- Klasifikasi postingan berdasarkan label / format
- Ekstraksi judul, SKU, harga, tahun, vendor, dan gambar dari artikel
- Upload produk ke Shopify secara otomatis
- Integrasi dengan Google OAuth, Google Drive, dan YouTube
- Penjadwalan monitoring 5 menit untuk mengecek postingan baru
- Antrean video YouTube Shorts untuk file dari Google Drive
- Integrasi webhook ke Google Apps Script / Spreadsheet
- Manajemen status produk (`DRAFT`, `Sold`, `On Hold`, `Takedown`, `Reprice`, `Repost`)

## Struktur Repository

- `upload_automation.py` — script utama automasi upload produk ke Shopify dari Blogger
- `flask_app.py` — aplikasi Flask untuk menerima webhook WhatsApp / perintah update harga/status
- `requirements.txt` — dependency Python yang dibutuhkan
- `processed_urls.json` — daftar URL yang sudah diproses
- `processed_skus.json` — daftar SKU yang sudah diproses hari ini
- `pending_youtube_queue.json` — antrean video YouTube
- `Panduan_*.html` / `.pdf` — dokumentasi panduan penggunaan
- `*.ipynb` — notebook eksperimen / script prototipe
- `scratch/` — file sementara / eksperimen

## Tech Stack

- Python
- Flask
- BeautifulSoup
- Google API Client
- Shopify Admin API
- Blogger API
- Google Drive API
- YouTube Data API
- Requests

## Persyaratan Sistem

- Python 3.9+
- Pip / virtualenv
- Akses Google API (Blogger, Drive, YouTube)
- Akses Shopify Admin API
- Akun Google dengan OAuth Refresh Token
- FFMPEG (untuk penggabungan audio+video YouTube Shorts)

## Instalasi

1. Clone repository:

```bash
git clone https://github.com/darrellrafa/upload-automation.git
cd upload-automation
```

2. Buat environment virtual (opsional tapi disarankan):

```bash
python -m venv .venv
source .venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Buat file `.env` di root project dengan variabel berikut:

```env
GCP_CLIENT_ID=your_google_client_id
GCP_CLIENT_SECRET=your_google_client_secret
GCP_REFRESH_TOKEN=your_google_refresh_token
BLOG_ID=your_blogger_blog_id

SHOPIFY_STORE_NAME=idwx
SHOPIFY_CLIENT_ID=your_shopify_client_id
SHOPIFY_CLIENT_SECRET=your_shopify_client_secret

DRIVE_AUDIO_FOLDER_ID=your_google_drive_audio_folder_id

# Optional untuk Flask webhook / WhatsApp
GREEN_API_ID_INSTANCE=
GREEN_API_API_TOKEN=
TARGET_GROUP_ID=

APPS_SCRIPT_HISTORY_URL=
APPS_SCRIPT_CONSIGNMENT_URL=
APPS_SCRIPT_SLOW_MOVING_URL=
```

## Menjalankan Project

### 1) Script upload otomatis

```bash
python upload_automation.py
```

Script ini akan secara berkala mengecek postingan Blogger terbaru, mengklasifikasikannya, dan upload ke Shopify jika sesuai aturan.

### 2) Flask webhook

```bash
python flask_app.py
```

Server Flask ini dipakai untuk mengolah perintah seperti:

- `REPRICE / SKU / HARGA`
- `HARGA BARU / SKU / HARGA`
- `TAKEDOWN / SKU`
- `SOLD / SKU`
- `ON HOLD / SKU`
- `REPOST / SKU`

## Workflow Aplikasi

### Upload automation

1. Script mengambil postingan terbaru dari Blogspot
2. Cek label seperti `NEW ARRIVAL`
3. Klasifikasi format berdasarkan label: `PHOTO STUDIO`, `PHOTO OWNER`, `TWP`, atau `NOTSYNC`
4. Ekstrak data produk dari HTML artikel
5. Upload ke Shopify
6. Update spreadsheet terkait
7. Jika ada asset video di Google Drive, tambahkan ke antrean YouTube Shorts

### WhatsApp / webhook bot

1. Menerima perintah dari chat target
2. Mencari postingan Blogspot berdasarkan SKU
3. Mengupdate Blogspot, Shopify, dan spreadsheet sesuai perintah
4. Mengirim balasan status ke WhatsApp

## Catatan Penting

- File `.env` tidak boleh di-commit ke repo publik jika berisi credential sensitif.
- Pastikan token OAuth Google dan Shopify masih valid.
- FFMPEG perlu tersedia di system PATH jika akan memproses video YouTube Shorts.
- Beberapa URL Apps Script dan folder Google Drive bersifat environment-specific dan perlu disesuaikan dengan lingkungan Anda.

## License

Repository ini belum mencantumkan lisensi khusus. Jika Anda berencana membagikan project ini secara publik, disarankan untuk menambahkan file `LICENSE` sesuai kebutuhan.

## Kontribusi

Pull request dan perbaikan sangat terbuka. Jika Anda ingin menambahkan fitur baru atau memperbaiki flow automation, silakan buat branch baru lalu ajukan PR.

## Maintainer

Darrell Rafa

## Catatan

Project ini dibuat untuk kebutuhan operasional internal/automasi katalog produk watch dan dapat disesuaikan untuk kebutuhan bisnis serupa.

