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

# 1. Check all events in Shopify store around 17:00 to 17:30
print("=== SHOPIFY GENERAL EVENTS AROUND 17:00 - 17:30 ===")
req_events = urllib.request.Request(
    f'https://{store}.myshopify.com/admin/api/2024-01/events.json?created_at_min=2026-11-24T10:00:00Z&limit=100',
    headers=headers
)
try:
    with urllib.request.urlopen(req_events, timeout=15) as res:
        events = json.loads(res.read().decode('utf-8')).get('events', [])
        print(f"Events found: {len(events)}")
        for ev in events:
            print(f"[{ev.get('created_at')}] {ev.get('subject_type')} ({ev.get('subject_id')}) | {ev.get('verb')} by '{ev.get('author')}' | {ev.get('message')}")
except Exception as e:
    print("Error fetching events:", e)

# 2. Check how many total products were updated between 17:11:00 and 17:12:10
print("\n=== PRODUCTS UPDATED AT 17:11 - 17:13 ===")
req_prods = urllib.request.Request(
    f'https://{store}.myshopify.com/admin/api/2024-01/products.json?updated_at_min=2026-11-24T17:11:00%2B07:00&updated_at_max=2026-11-24T17:13:00%2B07:00&limit=50',
    headers=headers
)
try:
    with urllib.request.urlopen(req_prods, timeout=15) as res:
        prods = json.loads(res.read().decode('utf-8')).get('products', [])
        print(f"Total products updated in this 2-minute window: {len(prods)}")
        for p in prods:
            print(f"  {p['id']} | {p['title']} | updated_at: {p['updated_at']}")
except Exception as e:
    print("Error fetching products in window:", e)

# 3. Check metafields for one of these products (AQUARACER 500M and OYSTER PERPETUAL 31MM)
print("\n=== METAFIELDS FOR AQUARACER 500M (7784636088527) ===")
req_mf = urllib.request.Request(
    f'https://{store}.myshopify.com/admin/api/2024-01/products/7784636088527/metafields.json',
    headers=headers
)
try:
    with urllib.request.urlopen(req_mf, timeout=15) as res:
        mfs = json.loads(res.read().decode('utf-8')).get('metafields', [])
        print(f"Metafields count: {len(mfs)}")
        for m in mfs:
            print(f"  Namespace: {m.get('namespace')}, Key: {m.get('key')}, Value: {m.get('value')[:50] if m.get('value') else ''}, Updated At: {m.get('updated_at')}")
except Exception as e:
    print("Error fetching metafields:", e)

