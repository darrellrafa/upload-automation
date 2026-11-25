import urllib.request
import json
import os

env_vars = {}
with open('.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env_vars[k.strip()] = v.strip().strip('"').strip("'")

store = env_vars.get('SHOPIFY_STORE_NAME')
client_id = env_vars.get('SHOPIFY_CLIENT_ID')
client_secret = env_vars.get('SHOPIFY_CLIENT_SECRET')

token_data = json.dumps({
    'client_id': client_id,
    'client_secret': client_secret,
    'grant_type': 'client_credentials'
}).encode('utf-8')

req = urllib.request.Request(
    f'https://{store}.myshopify.com/admin/oauth/access_token',
    data=token_data,
    headers={'Content-Type': 'application/json'}
)

with urllib.request.urlopen(req, timeout=15) as res:
    token = json.loads(res.read().decode('utf-8')).get('access_token')

headers = {
    'X-Shopify-Access-Token': token,
    'Content-Type': 'application/json'
}

product_ids = [
    (7698096095439, "FORMULA 1"),
    (7716003381455, "NAVITIMER"),
    (7807670091983, "OYSTER PERPETUAL"),
    (7632651256015, "ALPINE EAGLE"),
    (7952500129999, "ROYAL OAK"),
    (7972579246287, "CARRERA CHRONO"),
    (7964098199759, "GMT MASTER-II"),
    (7784636088527, "AQUARACER"),
    (7864348311759, "CARRERA CALIBRE 1887")
]

for pid, title in product_ids:
    req_p = urllib.request.Request(
        f'https://{store}.myshopify.com/admin/api/2024-01/products/{pid}.json',
        headers=headers
    )
    with urllib.request.urlopen(req_p, timeout=15) as res:
        p = json.loads(res.read().decode('utf-8')).get('product', {})
        print(f"\n{title} (ID: {pid}): Product Updated At: {p.get('updated_at')}")
        images = p.get('images', [])
        for i, img in enumerate(images):
            up = img.get('updated_at')
            cr = img.get('created_at')
            if '2026-11-24' in str(up) or '2026-11-24' in str(cr):
                print(f"  Image #{i+1} ID {img.get('id')}: Created {cr} | Updated {up} | Alt: {img.get('alt')} | Width: {img.get('width')} | Height: {img.get('height')}")

