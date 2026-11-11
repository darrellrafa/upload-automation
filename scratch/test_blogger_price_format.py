import sys
import os
import unittest.mock as mock

# Mock external packages so flask_app can be imported cleanly
for mod_name in ['requests', 'flask', 'bs4', 'googleapiclient', 'googleapiclient.discovery', 'google.oauth2', 'google.oauth2.credentials', 'google_auth_oauthlib', 'google_auth_oauthlib.flow']:
    sys.modules[mod_name] = mock.MagicMock()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask_app import format_rupiah, parse_price, parse_reprice_chat, update_blogger_reprice

print("--- Testing format_rupiah ---")
assert format_rupiah(120000000) == "Rp 120,000,000", f"Expected 'Rp 120,000,000' but got {format_rupiah(120000000)}"
assert format_rupiah(56800000) == "Rp 56,800,000", f"Expected 'Rp 56,800,000' but got {format_rupiah(56800000)}"
assert format_rupiah(1500000000) == "Rp 1,500,000,000", f"Expected 'Rp 1,500,000,000' but got {format_rupiah(1500000000)}"
print("✅ format_rupiah test passed!")

print("\n--- Testing parse_reprice_chat ---")
cmd1 = parse_reprice_chat("REPRICE / 136V34W8 / 120JT")
assert cmd1["formatted_price"] == "Rp 120,000,000", f"Got {cmd1['formatted_price']}"
print("Cmd 1 (120JT):", cmd1["formatted_price"])

cmd2 = parse_reprice_chat("HARGA BARU / 136V34W8 / Rp 120.000.000")
assert cmd2["formatted_price"] == "Rp 120,000,000", f"Got {cmd2['formatted_price']}"
print("Cmd 2 (Rp 120.000.000):", cmd2["formatted_price"])

cmd3 = parse_reprice_chat("REPRICE / 136V34W8 / 120,000,000")
assert cmd3["formatted_price"] == "Rp 120,000,000", f"Got {cmd3['formatted_price']}"
print("Cmd 3 (120,000,000):", cmd3["formatted_price"])

cmd4 = parse_reprice_chat("HARGA BARU 136V34W8 120000000")
assert cmd4["formatted_price"] == "Rp 120,000,000", f"Got {cmd4['formatted_price']}"
print("Cmd 4 (no slash):", cmd4["formatted_price"])

print("✅ parse_reprice_chat test passed!")

print("\n--- Testing update_blogger_reprice ---")
# Mock service
mock_service = mock.MagicMock()
patched_posts = []
def mock_patch(blogId, postId, body):
    m = mock.MagicMock()
    def mock_execute():
        patched_posts.append(body)
        return {"id": postId, "title": "Mock Title", "labels": body.get("labels", []), "content": body.get("content", "")}
    m.execute = mock_execute
    return m
mock_service.posts().patch = mock_patch

# Test 1: Original post with dots: "Price: Rp 158.000.000"
post1 = {
    "id": "12345",
    "title": "SUBMARINER 16610",
    "content": "ROLEX SUBMARINER DATE<br/>Price: Rp 158.000.000<br/>Code: 136V34W8",
    "labels": ["ROLEX", "CONSIGNMENT_PS", "NEW ARRIVAL"],
    "published": "2026-11-09T03:51:00Z"
}
update_blogger_reprice(mock_service, post1, "REPRICE", "Rp 120.000.000")
updated1 = patched_posts[-1]["content"]
print("Updated REPRICE Content 1:\n", updated1)
assert "Price: <strike>Rp 158,000,000</strike><br/>Reprice: <b>Rp 120,000,000</b>" in updated1
assert "158.000.000" not in updated1
assert "120.000.000" not in updated1
print("✅ REPRICE with dots converted to commas passed!")

# Test 2: HARGA BARU with dots
update_blogger_reprice(mock_service, post1, "HARGA_BARU", "Rp 120.000.000")
updated2 = patched_posts[-1]["content"]
print("Updated HARGA_BARU Content 2:\n", updated2)
assert "Price: Rp 120,000,000" in updated2
assert "120.000.000" not in updated2
print("✅ HARGA BARU with dots converted to commas passed!")

# Test 3: Existing Reprice post updated with new Reprice
post3 = {
    "id": "67890",
    "title": "SUBMARINER 16610",
    "content": "ROLEX SUBMARINER DATE<br/>Price: <strike>Rp 158.000.000</strike><br/>Reprice: <b>Rp 140.000.000</b><br/>Code: 136V34W8",
    "labels": ["ROLEX", "CONSIGNMENT_PS", "REPRICE"],
    "published": "2026-11-09T03:51:00Z"
}
update_blogger_reprice(mock_service, post3, "REPRICE", "Rp 120,000,000")
updated3 = patched_posts[-1]["content"]
print("Updated Existing Reprice Content 3:\n", updated3)
assert "Price: <strike>Rp 158,000,000</strike><br/>Reprice: <b>Rp 120,000,000</b>" in updated3
assert "158.000.000" not in updated3
assert "140.000.000" not in updated3
assert "120.000.000" not in updated3
print("✅ Updating existing Reprice post to new price passed!")

print("\n🎉 ALL TESTS PASSED SUCCESSFULLY!")
