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

# Check GraphQL query for detailed audit
query = """
query($id: ID!) {
  product(id: $id) {
    id
    title
    status
    createdAt
    updatedAt
    publishedAt
    totalInventory
    vendor
    productType
    tags
    collections(first: 10) {
      edges {
        node {
          id
          title
          updatedAt
        }
      }
    }
    resourcePublicationsV2(first: 10) {
      edges {
        node {
          publication {
            id
            name
          }
          isPublished
          publishDate
        }
      }
    }
  }
}
"""

pids = [
    7698096095439, # FORMULA 1 (17:11:22)
    7716003381455, # NAVITIMER (17:11:22)
    7807670091983, # OYSTER PERPETUAL (17:11:30 - draft)
    7784636088527, # AQUARACER (17:12:01)
]

for pid in pids:
    gid = f"gid://shopify/Product/{pid}"
    req_gql = urllib.request.Request(
        f'https://{store}.myshopify.com/admin/api/2024-01/graphql.json',
        data=json.dumps({"query": query, "variables": {"id": gid}}).encode('utf-8'),
        headers=headers
    )
    with urllib.request.urlopen(req_gql, timeout=15) as res:
        data = json.loads(res.read().decode('utf-8'))
        p = data.get('data', {}).get('product', {})
        print(f"\n--- {p.get('title')} ({pid}) ---")
        print(f"Status: {p.get('status')} | UpdatedAt: {p.get('updatedAt')} | PublishedAt: {p.get('publishedAt')}")
        print("Collections:")
        for col in p.get('collections', {}).get('edges', []):
            cnode = col['node']
            print(f"  - Collection: {cnode.get('title')} (ID: {cnode.get('id')}, UpdatedAt: {cnode.get('updatedAt')})")
        print("Publications / Channels:")
        for pub in p.get('resourcePublicationsV2', {}).get('edges', []):
            pnode = pub['node']
            print(f"  - Channel: {pnode.get('publication', {}).get('name')} | isPublished: {pnode.get('isPublished')} | publishDate: {pnode.get('publishDate')}")

