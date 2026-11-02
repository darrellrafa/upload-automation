# Upload Automation

Automated upload and processing of watch products from Blogger posts to Shopify, with additional integrations to Google Drive, YouTube Shorts, and spreadsheet webhooks.

This project is designed to automate the marketing and sales workflow for luxury watch products, including classification of post formats (`NOTSYNC`, `TWP`, `PHOTO STUDIO`, `PHOTO OWNER`), product metadata extraction, image upload, stock synchronization, and YouTube video queue management.

Indonesian version: [README.md](README.md)

## Main Features

- Fetch blog posts from the Blogger API
- Classify posts based on labels and formats
- Extract title, SKU, price, year, vendor, and images from articles
- Automatically upload products to Shopify
- Integrate with Google OAuth, Google Drive, and YouTube
- Monitor new posts every 5 minutes
- Queue YouTube Shorts videos from Google Drive assets
- Integrate with Google Apps Script / spreadsheet webhooks
- Manage product status (`DRAFT`, `Sold`, `On Hold`, `Takedown`, `Reprice`, `Repost`)

## Repository Structure

- `upload_automation.py` — main automation script for uploading products from Blogger to Shopify
- `flask_app.py` — Flask app for WhatsApp webhook and price/status update commands
- `requirements.txt` — required Python dependencies
- `processed_urls.json` — list of processed URLs
- `processed_skus.json` — list of processed SKUs for the day
- `pending_youtube_queue.json` — YouTube queue data
- `Panduan_*.html` / `.pdf` — usage guides
- `*.ipynb` — notebooks and experimental scripts
- `scratch/` — temporary or experimental files

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

## System Requirements

- Python 3.9+
- pip / virtualenv
- Google API access (Blogger, Drive, YouTube)
- Shopify Admin API access
- Google account with OAuth refresh token
- FFMPEG (for combining audio and video in YouTube Shorts)

## Installation

1. Clone the repository:

```bash
git clone https://github.com/darrellrafa/upload-automation.git
cd upload-automation
```

2. Create a virtual environment (optional but recommended):

```bash
python -m venv .venv
source .venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Create a `.env` file at the project root with the following variables:

```env
GCP_CLIENT_ID=your_google_client_id
GCP_CLIENT_SECRET=your_google_client_secret
GCP_REFRESH_TOKEN=your_google_refresh_token
BLOG_ID=your_blogger_blog_id

SHOPIFY_STORE_NAME=idwx
SHOPIFY_CLIENT_ID=your_shopify_client_id
SHOPIFY_CLIENT_SECRET=your_shopify_client_secret

DRIVE_AUDIO_FOLDER_ID=your_google_drive_audio_folder_id

# Optional for Flask webhook / WhatsApp
GREEN_API_ID_INSTANCE=
GREEN_API_API_TOKEN=
TARGET_GROUP_ID=

APPS_SCRIPT_HISTORY_URL=
APPS_SCRIPT_CONSIGNMENT_URL=
APPS_SCRIPT_SLOW_MOVING_URL=
```

## Running the Project

### 1) Upload automation script

```bash
python upload_automation.py
```

This script periodically checks for new Blogger posts, classifies them, and uploads valid products to Shopify.

### 2) Flask webhook app

```bash
python flask_app.py
```

The Flask server is used for commands such as:

- `REPRICE / SKU / PRICE`
- `HARGA BARU / SKU / PRICE`
- `TAKEDOWN / SKU`
- `SOLD / SKU`
- `ON HOLD / SKU`
- `REPOST / SKU`

## Application Workflow

### Upload Automation

1. Fetch newest posts from Blogger
2. Check labels such as `NEW ARRIVAL`
3. Classify the post format: `PHOTO STUDIO`, `PHOTO OWNER`, `TWP`, or `NOTSYNC`
4. Extract product data from HTML content
5. Upload to Shopify
6. Update related spreadsheet data
7. If Google Drive assets are found, add the item to the YouTube Shorts queue

### WhatsApp / Webhook Bot

1. Receive commands from the target chat
2. Find the matching Blogger post by SKU
3. Update Blogger, Shopify, and spreadsheet entries as needed
4. Send status reports back to WhatsApp

## Important Notes

- The `.env` file should never be committed if it contains sensitive credentials.
- Make sure Google OAuth and Shopify tokens remain valid.
- FFMPEG must be available in the system PATH if YouTube Shorts video processing is used.
- Some Apps Script URLs and Google Drive folders are environment-specific and may need adjustment for your setup.

## License

This repository does not currently include a dedicated license file. If you plan to publish this project publicly, it is recommended to add a proper `LICENSE` file.

## Contributing

Pull requests and improvements are welcome. If you want to add a feature or fix the workflow, create a new branch and open a PR.

## Maintainer

Darrell Rafa

## Note

This project was built for internal operational automation of watch product catalogs and can be adapted for similar business workflows.
