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
- `Panduan_Penggunaan_Upload_Automation.html` — Panduan operasional lengkap Upload Automation (v2.0, printable A4)
- `Panduan_Penggunaan_WhatsApp_Bot.html` — Panduan operasional lengkap WhatsApp Bot (v2.0, printable A4)
- `Panduan_*.pdf` — arsip dokumen panduan format PDF
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

Server Flask ini dipakai untuk mengolah webhook WhatsApp (Green-API) secara real-time dengan parsing perintah yang sangat fleksibel (pemisah bisa berupa garis miring `/`, titik dua `:`, strip `-`, atau spasi):

- **REPRICE / HARGA BARU**:
  - Format standar: `REPRICE / SKU / HARGA` atau `HARGA BARU / SKU / HARGA`
  - Format cepat: `REPRICE SKU HARGA` (contoh: `REPRICE 32W8213 150JT` atau `HARGA BARU: 32W8213 150.000.000`)
  - *Fitur Cerdas*: Kebal terhadap teks `Retail Price:`, mencoret harga jual lama (`Price:`) secara tepat, dan otomatis memperbaiki (auto-heal) postingan lama yang formatnya sempat rusak.
- **SOLD**:
  - `SOLD / SKU`, `SOLD: SKU`, `SOLD - SKU`, atau `SOLD SKU`
  - Otomatis ubah status Shopify menjadi `DRAFT`, set inventory 0, pindahkan postingan Blogspot ke Trash, dan update spreadsheet CONSIGNMENT/SLOW MOVING.
- **ON HOLD**:
  - `ON HOLD / SKU`, `HOLD / SKU`, `ON HOLD: SKU`
  - Otomatis ubah status Shopify menjadi `DRAFT` dan set inventory 0 (postingan Blogspot tetap aktif).
- **TAKEDOWN**:
  - `TAKEDOWN / SKU` atau `TAKEDOWN: SKU`
  - Hapus produk dari live (Shopify `DRAFT` + stok 0 + Blogspot ke Trash).
- **REPOST**:
  - `REPOST / SKU` atau `REPOST: SKU`
  - Khusus postingan Blogspot yang **masih aktif** (bukan di Trash): ubah tanggal publish ke waktu sekarang agar naik ke urutan teratas blog, pasang label `REPOST`, dan catat tanggal `Last Post`. Di Shopify **tidak ada perubahan apa pun**. Spreadsheet consignment diupdate ke status `Reprice/post`.
- **FOTO**:
  - `FOTO SKU` atau `CEK SKU`
  - Menampilkan foto utama jam tangan dan ringkasan deskripsi langsung ke WhatsApp tanpa mengubah status apa pun.

### Fitur Keandalan Webhook:
- **Fast-path webhook handling**: Webhook status (non-incoming) langsung direspon dalam <1ms agar server tidak terbebani saat spam traffic.
- **Deduplikasi Pesan (LRU Cache)**: Mencegah eksekusi ganda jika Green-API mengirim ulang event yang sama.
- **Always 200 OK**: Exception internal selalu ditangkap dan dilaporkan ke WA tanpa melempar HTTP 500, mencegah Green-API melakukan perulangan (retry loop) setiap 60 detik.

## Workflow Aplikasi

### Upload automation

1. Script mengambil postingan terbaru dari Blogspot.
2. Cek label seperti `NEW ARRIVAL`.
3. Klasifikasi format berdasarkan label: `PHOTO STUDIO`, `PHOTO OWNER`, `TWP`, atau `NOTSYNC`.
4. Ekstrak data produk dari HTML artikel dengan **Dual-Layer Regex Safeguard** (mencegah salah ambil teks `Retail Price:` sebagai harga jual Shopify).
5. Upload ke Shopify dan update spreadsheet terkait.
6. Jika ada asset video di Google Drive, tambahkan ke antrean YouTube Shorts.

### WhatsApp / webhook bot

1. Menerima perintah dari chat target (Grup / Nomor yang diizinkan).
2. Mencari postingan Blogspot berdasarkan SKU dan mengambil foto jam tangan resolusi tinggi.
3. Mengupdate Blogspot, Shopify, dan spreadsheet sesuai perintah.
4. Mengirim balasan konfirmasi WhatsApp beserta foto jam tangan yang bersangkutan.

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

