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

# Check all fields of OYSTER PERPETUAL
req_op = urllib.request.Request(
    f'https://{store}.myshopify.com/admin/api/2024-01/products/7807670091983.json',
    headers=headers
)
with urllib.request.urlopen(req_op, timeout=15) as res:
    p = json.loads(res.read().decode('utf-8')).get('product', {})
    print("=== OYSTER PERPETUAL 31MM BLUE DIAL ===")
    print(f"Title: {p.get('title')}")
    print(f"Status: {p.get('status')}")
    print(f"Updated at: {p.get('updated_at')}")
    print(f"Body HTML: {p.get('body_html')[:200]}...")
    print(f"Variants: {p.get('variants')}")
    print(f"Images count: {len(p.get('images', []))}")
    for img in p.get('images', [])[:3]:
        print(f"  Image ID: {img.get('id')}, Created: {img.get('created_at')}, Updated: {img.get('updated_at')}")

# Check inventory level updated_at
inv_item_id = p.get('variants', [{}])[0].get('inventory_item_id')
req_inv = urllib.request.Request(
    f'https://{store}.myshopify.com/admin/api/2024-01/inventory_levels.json?inventory_item_ids={inv_item_id}',
    headers=headers
)
with urllib.request.urlopen(req_inv, timeout=15) as res:
    inv = json.loads(res.read().decode('utf-8')).get('inventory_levels', [])
    print(f"Inventory Levels: {inv}")

