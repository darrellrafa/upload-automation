import requests
import json
import os

env = {}
with open(".env") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip("\"'")

def get_shopify_access_token():
    tok_res = requests.post(
        f"https://{env['SHOPIFY_STORE_NAME']}.myshopify.com/admin/oauth/access_token",
        data={
            "grant_type": "client_credentials",
            "client_id": env["SHOPIFY_CLIENT_ID"],
            "client_secret": env["SHOPIFY_CLIENT_SECRET"]
        },
        timeout=30
    )
    if tok_res.status_code == 200:
        return tok_res.json().get("access_token")
    return None

def update_shopify_price(sku, command_type, new_numeric_price):
    token = get_shopify_access_token()
    if not token:
        return {"status": "error", "message": "Gagal mendapatkan token Shopify"}
        
    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
    graphql_url = f"https://{env['SHOPIFY_STORE_NAME']}.myshopify.com/admin/api/2025-01/graphql.json"
    
    # 1. Cari produk & variant berdasarkan SKU
    search_query = """
    query getProducts($query: String!) {
      products(first: 3, query: $query) {
        edges {
          node {
            id
            title
            variants(first: 5) {
              edges {
                node {
                  id
                  sku
                  price
                  compareAtPrice
                }
              }
            }
          }
        }
      }
    }
    """
    res = requests.post(graphql_url, headers=headers, json={"query": search_query, "variables": {"query": f"sku:{sku}"}}, timeout=30)
    data = res.json()
    edges = data.get("data", {}).get("products", {}).get("edges", [])
    
    if not edges:
        return {"status": "not_found", "message": f"Produk dengan SKU '{sku}' tidak ditemukan di Shopify."}
        
    p_node = edges[0]["node"]
    v_node = None
    for edge in p_node["variants"]["edges"]:
        vn = edge["node"]
        if vn.get("sku", "").strip().upper() == sku.strip().upper():
            v_node = vn
            break
            
    if not v_node:
        v_node = p_node["variants"]["edges"][0]["node"]
        
    variant_id = v_node["id"]
    current_price = float(v_node.get("price") or 0)
    current_compare = v_node.get("compareAtPrice")
    
    # 2. Tentukan price & compareAtPrice
    if command_type == "REPRICE":
        if current_compare is None or float(current_compare) == 0:
            compare_at_val = f"{current_price:.2f}"
        else:
            compare_at_val = current_compare
        price_val = f"{float(new_numeric_price):.2f}"
    else: # HARGA_BARU
        compare_at_val = None
        price_val = f"{float(new_numeric_price):.2f}"
        
    # Mutation input
    mutation = """
    mutation updateVariantPrice($input: ProductVariantInput!) {
      productVariantUpdate(input: $input) {
        productVariant {
          id
          price
          compareAtPrice
        }
        userErrors {
          field
          message
        }
      }
    }
    """
    m_input = {
        "id": variant_id,
        "price": price_val,
        "compareAtPrice": compare_at_val
    }
    
    print(f"Dry run mutation input: {m_input}")
    return {
        "status": "ready",
        "product_title": p_node["title"],
        "variant_id": variant_id,
        "old_price": current_price,
        "new_price": float(price_val),
        "compare_at_price": compare_at_val
    }

# Test query on SKU 6719884
res = update_shopify_price("6719884", "REPRICE", 62000000)
print(f"Result: {json.dumps(res, indent=2)}")
