import os
import io
import time
import random
import subprocess
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# Load .env
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
env = {}
with open(env_path, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip("\"'")

creds = Credentials(
    token=None,
    refresh_token=env["GCP_REFRESH_TOKEN"],
    token_uri="https://oauth2.googleapis.com/token",
    client_id=env["GCP_CLIENT_ID"],
    client_secret=env["GCP_CLIENT_SECRET"]
)
drive_service = build('drive', 'v3', credentials=creds)

DRIVE_AUDIO_FOLDER_ID = "1NO7JUz7kOzyjiKLqkZKJD18Tw0CSIB2K"
LOCAL_AUDIO_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "audio_tracks")
os.makedirs(LOCAL_AUDIO_DIR, exist_ok=True)

def sync_audio_tracks(drive_service):
    """Memeriksa folder audio di Google Drive dan mendownload lagu-lagu baru ke lokal."""
    print(f"🎵 Memeriksa folder audio di Google Drive ({DRIVE_AUDIO_FOLDER_ID})...")
    try:
        query = f"'{DRIVE_AUDIO_FOLDER_ID}' in parents and trashed = false"
        results = drive_service.files().list(
            q=query,
            fields="files(id, name, mimeType, size)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        
        files = results.get('files', [])
        print(f"   Ditemukan {len(files)} file di Google Drive.")
        
        downloaded = []
        for f in files:
            file_id = f.get('id')
            file_name = f.get('name')
            mime = f.get('mimeType', '').lower()
            
            # Hanya proses file audio
            if not (file_name.lower().endswith(('.mp3', '.m4a', '.wav', '.aac', '.ogg')) or 'audio' in mime):
                continue
                
            dest_path = os.path.join(LOCAL_AUDIO_DIR, file_name)
            if not os.path.exists(dest_path):
                print(f"   ⬇️ Mendownload audio baru: '{file_name}'...")
                req = drive_service.files().get_media(fileId=file_id)
                with io.FileIO(dest_path, 'wb') as fh:
                    downloader = MediaIoBaseDownload(fh, req, chunksize=5*1024*1024)
                    done = False
                    while not done:
                        status, done = downloader.next_chunk()
                print(f"   ✅ Audio tersimpan: {file_name}")
            else:
                print(f"   ℹ️ Audio sudah ada di cache lokal: {file_name}")
            downloaded.append(dest_path)
            
        return downloaded
    except Exception as e:
        print(f"   ⚠️ Error sinkronisasi audio Drive: {e}")
        # Fallback ke file lokal yang sudah ada
        local_files = [
            os.path.join(LOCAL_AUDIO_DIR, fn)
            for fn in os.listdir(LOCAL_AUDIO_DIR)
            if fn.lower().endswith(('.mp3', '.m4a', '.wav', '.aac', '.ogg'))
        ]
        return local_files

if __name__ == "__main__":
    audio_list = sync_audio_tracks(drive_service)
    print(f"\nTotal audio siap digunakan: {len(audio_list)}")
    if audio_list:
        chosen = random.choice(audio_list)
        print(f"Contoh lagu acak yang dipilih: {os.path.basename(chosen)}")
