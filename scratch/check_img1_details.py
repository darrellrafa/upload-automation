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

req_p = urllib.request.Request(
    f'https://{store}.myshopify.com/admin/api/2024-01/products/7807670091983.json',
    headers=headers
)
with urllib.request.urlopen(req_p, timeout=15) as res:
    p = json.loads(res.read().decode('utf-8')).get('product', {})
    img1 = p.get('images', [])[0]
    print(json.dumps(img1, indent=2))

