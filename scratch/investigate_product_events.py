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

products_to_check = [
    (7784636088527, "AQUARACER 500M"),
    (7964098199759, "GMT MASTER-II BLACK PANTHER"),
    (7807670091983, "OYSTER PERPETUAL 31MM BLUE DIAL"),
    (7698096095439, "FORMULA 1 QUARTZ CHRONOGRAPH"),
]

for pid, title in products_to_check:
    print(f"\n==========================================")
    print(f"Product: {title} (ID: {pid})")
    print(f"==========================================")
    
    # 1. Product details
    req_p = urllib.request.Request(
        f'https://{store}.myshopify.com/admin/api/2024-01/products/{pid}.json',
        headers=headers
    )
    with urllib.request.urlopen(req_p, timeout=15) as res:
        p_data = json.loads(res.read().decode('utf-8')).get('product', {})
        print(f"Status: {p_data.get('status')}")
        print(f"Updated At: {p_data.get('updated_at')}")
        print(f"Tags: {p_data.get('tags')}")
        print(f"Variants count: {len(p_data.get('variants', []))}")
        for v in p_data.get('variants', []):
            print(f"  Variant ID: {v.get('id')}, SKU: {v.get('sku')}, Price: {v.get('price')}, Inventory Item ID: {v.get('inventory_item_id')}, Updated At: {v.get('updated_at')}")

    # 2. Product events
    req_pe = urllib.request.Request(
        f'https://{store}.myshopify.com/admin/api/2024-01/products/{pid}/events.json?limit=15',
        headers=headers
    )
    try:
        with urllib.request.urlopen(req_pe, timeout=15) as res:
            events = json.loads(res.read().decode('utf-8')).get('events', [])
            print(f"\nEvents count: {len(events)}")
            for ev in events:
                print(f"  Event ID: {ev.get('id')} | Verb: {ev.get('verb')} | Author: {ev.get('author')} | Created At: {ev.get('created_at')}")
                print(f"    Message: {ev.get('message')}")
                print(f"    Arguments: {ev.get('arguments')}")
                print(f"    Body: {ev.get('body')}")
    except Exception as e:
        print(f"Error getting events: {e}")

