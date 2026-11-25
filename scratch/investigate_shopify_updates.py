import urllib.request
import json
import os
from datetime import datetime

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

print(f"=== RECENTLY UPDATED PRODUCTS (ORDER BY UPDATED_AT DESC) ===")
req_prods = urllib.request.Request(
    f'https://{store}.myshopify.com/admin/api/2024-01/products.json?limit=15&order=updated_at+desc',
    headers=headers
)
with urllib.request.urlopen(req_prods, timeout=15) as res:
    prods = json.loads(res.read().decode('utf-8')).get('products', [])

target_ids = []
for p in prods:
    print(f"ID: {p['id']} | Title: {p['title']} | Status: {p['status']} | Updated At: {p['updated_at']}")
    target_ids.append((p['id'], p['title']))

print("\n=== RECENT GENERAL EVENTS IN SHOPIFY (LAST 30 EVENTS) ===")
req_events = urllib.request.Request(
    f'https://{store}.myshopify.com/admin/api/2024-01/events.json?limit=30',
    headers=headers
)
try:
    with urllib.request.urlopen(req_events, timeout=15) as res:
        events = json.loads(res.read().decode('utf-8')).get('events', [])
        for ev in events:
            print(f"Event ID: {ev.get('id')} | Subject: {ev.get('subject_type')} ({ev.get('subject_id')}) | Verb: {ev.get('verb')} | Author: {ev.get('author')} | Created At: {ev.get('created_at')}")
            print(f"  Message: {ev.get('message')}")
            if ev.get('arguments'):
                print(f"  Arguments: {ev.get('arguments')}")
            print("---")
except Exception as e:
    print("Error fetching general events:", e)

# Also check product-specific events for the first 3 products
print("\n=== PRODUCT-SPECIFIC EVENTS FOR FIRST 3 PRODUCTS ===")
for pid, title in target_ids[:3]:
    print(f"\nChecking Events for Product: {title} (ID: {pid})")
    req_pe = urllib.request.Request(
        f'https://{store}.myshopify.com/admin/api/2024-01/products/{pid}/events.json?limit=10',
        headers=headers
    )
    try:
        with urllib.request.urlopen(req_pe, timeout=15) as res:
            p_events = json.loads(res.read().decode('utf-8')).get('events', [])
            for pev in p_events:
                print(f"  Event: {pev.get('verb')} by {pev.get('author')} at {pev.get('created_at')}")
                print(f"    Message: {pev.get('message')}")
                print(f"    Body: {pev.get('body')}")
    except Exception as e:
        print(f"  Error fetching events for product {pid}:", e)

