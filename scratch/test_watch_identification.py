import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Mock external modules if not installed locally
for mod in ["flask", "requests", "bs4", "google", "google.oauth2", "google.oauth2.credentials", "googleapiclient", "googleapiclient.discovery", "googleapiclient.http"]:
    if mod not in sys.modules:
        m = MagicMock()
        if mod == "flask":
            app_inst = MagicMock()
            app_inst.route = lambda *args, **kwargs: (lambda f: f)
            m.Flask = MagicMock(return_value=app_inst)
            m.request = MagicMock()
            m.jsonify = lambda x: x
        elif mod == "requests":
            res_m = MagicMock()
            res_m.status_code = 200
            res_m.json.return_value = {"access_token": "fake", "expires_in": 3600, "locations": []}
            m.post.return_value = res_m
            m.get.return_value = res_m
        sys.modules[mod] = m

# Ensure current dir in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flask_app
import upload_automation
from flask_app import (
    parse_reprice_chat,
    parse_takedown_chat,
    is_cancellation_chat,
    is_chat_excluded_from_identification,
    extract_sku_from_quoted_message,
    format_watch_identification_message,
    normalize_watch_model_title,
    detect_watch_brand,
    is_known_action_command,
    ACTIVE_IDENTIFIED_WATCHES
)

class TestWatchIdentificationAndQuickReplies(unittest.TestCase):
    def test_excluded_group_for_identification(self):
        # Harus diabaikan
        self.assertTrue(is_chat_excluded_from_identification("62817626104-1627455181@g.us"))
        self.assertTrue(is_chat_excluded_from_identification("62817626104-1627455181"))
        self.assertTrue(is_chat_excluded_from_identification("62817626104-1627455181@c.us"))
        # Grup lain tidak boleh diabaikan
        self.assertFalse(is_chat_excluded_from_identification("99999999999-1234567890@g.us"))
        self.assertFalse(is_chat_excluded_from_identification("628123456789@c.us"))
        self.assertFalse(is_chat_excluded_from_identification(None))

    def test_cancellation_chat(self):
        self.assertTrue(is_cancellation_chat("abaikan"))
        self.assertTrue(is_cancellation_chat("batal"))
        self.assertTrue(is_cancellation_chat("BATAL"))
        self.assertTrue(is_cancellation_chat("cancel"))
        self.assertTrue(is_cancellation_chat("skip"))
        self.assertTrue(is_cancellation_chat("abaikan."))
        self.assertFalse(is_cancellation_chat("sold"))
        self.assertFalse(is_cancellation_chat("reprice 650jt"))

    def test_extract_sku_from_quoted_message(self):
        quoted = {
            "textMessage": "⌚ *IDENTIFIKASI JAM TANGAN IDWX*\n🔢 *Kode / SKU:* 3012154\n💰 *Harga Saat Ini:* Rp 678,000,000"
        }
        self.assertEqual(extract_sku_from_quoted_message(quoted), "3012154")

        quoted2 = {
            "extendedTextMessageData": {
                "text": "🔢 Kode / SKU: CPO-240626-02\n💰 Harga: Rp 150.000.000"
            }
        }
        self.assertEqual(extract_sku_from_quoted_message(quoted2), "CPO-240626-02")

    def test_takedown_quick_replies(self):
        fallback = "3012154"
        
        # 'sold' with fallback
        cmd_sold = parse_takedown_chat("sold", fallback_sku=fallback)
        self.assertIsNotNone(cmd_sold)
        self.assertEqual(cmd_sold["command_type"], "SOLD")
        self.assertEqual(cmd_sold["code"], "3012154")

        # 'laku' with fallback
        cmd_laku = parse_takedown_chat("laku", fallback_sku=fallback)
        self.assertIsNotNone(cmd_laku)
        self.assertEqual(cmd_laku["command_type"], "SOLD")
        self.assertEqual(cmd_laku["code"], "3012154")

        # 'on hold' with fallback
        cmd_hold = parse_takedown_chat("on hold", fallback_sku=fallback)
        self.assertIsNotNone(cmd_hold)
        self.assertEqual(cmd_hold["command_type"], "ON_HOLD")
        self.assertEqual(cmd_hold["code"], "3012154")

        # 'hold' with fallback
        cmd_hold2 = parse_takedown_chat("hold", fallback_sku=fallback)
        self.assertIsNotNone(cmd_hold2)
        self.assertEqual(cmd_hold2["command_type"], "ON_HOLD")

        # normal full command overrides fallback
        cmd_full = parse_takedown_chat("SOLD / 703", fallback_sku=fallback)
        self.assertIsNotNone(cmd_full)
        self.assertEqual(cmd_full["code"], "703")

    def test_reprice_quick_replies(self):
        fallback = "3012154"

        # 'reprice 650jt' with fallback
        cmd_rep = parse_reprice_chat("reprice 650jt", fallback_sku=fallback)
        self.assertIsNotNone(cmd_rep)
        self.assertEqual(cmd_rep["command_type"], "REPRICE")
        self.assertEqual(cmd_rep["code"], "3012154")
        self.assertEqual(cmd_rep["numeric_price"], 650000000.0)

        # 'reprice / 650jt' with fallback
        cmd_rep2 = parse_reprice_chat("reprice / 650jt", fallback_sku=fallback)
        self.assertIsNotNone(cmd_rep2)
        self.assertEqual(cmd_rep2["numeric_price"], 650000000.0)

        # 'harga baru 678.000.000' with fallback
        cmd_hb = parse_reprice_chat("harga baru Rp 678.000.000", fallback_sku=fallback)
        self.assertIsNotNone(cmd_hb)
        self.assertEqual(cmd_hb["numeric_price"], 678000000.0)

        # normal full command overrides fallback
        cmd_full = parse_reprice_chat("REPRICE / 136V34W8 / 250JT", fallback_sku=fallback)
        self.assertIsNotNone(cmd_full)
        self.assertEqual(cmd_full["code"], "136V34W8")
        self.assertEqual(cmd_full["numeric_price"], 250000000.0)

    def test_identification_message_format(self):
        msg = format_watch_identification_message(
            title="Vacheron Constantin Historiques American 1921",
            sku="3012154",
            formatted_price="Rp 678,000,000",
            sheet_info="ALL STOCK (Baris 313)"
        )
        self.assertIn("⌚ *IDENTIFIKASI JAM TANGAN IDWX*", msg)
        self.assertIn("📌 *Merek & Seri:* Vacheron Constantin Historiques American 1921", msg)
        self.assertIn("🔢 *Kode / SKU:* 3012154", msg)
        self.assertIn("💰 *Harga Saat Ini:* Rp 678,000,000", msg)
        self.assertIn("📦 *Status:* AKTIF (Ready di Toko)", msg)
        self.assertIn("📊 *Spreadsheet:* ALL STOCK (Baris 313)", msg)
        self.assertIn("👉 *Aksi Cepat (Balas pesan ini):*", msg)
        self.assertIn("• Ketik *sold* untuk menandai laku", msg)
        self.assertIn("• Ketik *on hold* untuk simpan/hold", msg)
        self.assertIn("• Ketik *reprice [harga]* untuk ubah harga", msg)
        self.assertIn("• Ketik *batal* jika tidak ada tindakan", msg)

    def test_identification_message_with_form_content(self):
        form_sample = (
            "Nama : Said\n"
            "No Hp : 08118811159\n"
            "Instagram :\n"
            "======================\n"
            "Brand/Ref No: Omega ed white 321\n"
            "Size/Year: 39.7 / jan 2022\n"
            "Status/Condition: Very Mint\n"
            "Location: Dualtime\n"
            "Open Price (excluding 2% commision): 240-2%\n"
            "Bottom Price (excluding 2% commision): by call\n"
            "Notes: Sudah terpasang anti gores\n"
            "Order received by : yusup"
        )
        msg = format_watch_identification_message(
            title="SPEEDMASTER MOONWATCH 321 'ED WHITE' (2022)",
            sku="88702793",
            formatted_price="Rp 235,000,000",
            sheet_info="PHOTO STUDIO (Baris 2819)",
            location="Ready di Toko",
            form_content=form_sample
        )
        self.assertIn("📊 *Spreadsheet:* PHOTO STUDIO (Baris 2819)", msg)
        self.assertIn("Nama : Said", msg)
        self.assertIn("Brand/Ref No: Omega ed white 321", msg)
        self.assertIn("Order received by : yusup", msg)
        # Pastikan letak form berada di antara Spreadsheet dan Aksi Cepat
        pos_sheet = msg.find("📊 *Spreadsheet:* PHOTO STUDIO (Baris 2819)")
        pos_form = msg.find("Nama : Said")
        pos_action = msg.find("👉 *Aksi Cepat (Balas pesan ini):*")
        self.assertTrue(pos_sheet < pos_form < pos_action)

    def test_resolve_watch_spreadsheet_location_with_form(self):
        from unittest.mock import patch, MagicMock
        from flask_app import resolve_watch_spreadsheet_location

        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = {
            "status": "success",
            "tab_name": "PHOTO STUDIO",
            "row": 2819,
            "form": "Nama : Said\nNo Hp : 08118811159\nBrand/Ref No: Omega ed white 321"
        }

        with patch("requests.post", return_value=mock_res):
            sheet_info, form, owner = resolve_watch_spreadsheet_location("88702793", blogger_post={"labels": ["CONSIGNMENT_PS"]}, return_form=True)
            self.assertEqual(sheet_info, "PHOTO STUDIO (Baris 2819)")
            self.assertIn("Nama : Said", form)
            self.assertEqual(owner, "")

            # Test backwards compatibility when return_form=False
            sheet_info_only = resolve_watch_spreadsheet_location("88702793", blogger_post={"labels": ["CONSIGNMENT_PS"]})
            self.assertEqual(sheet_info_only, "PHOTO STUDIO (Baris 2819)")

    def test_identification_message_with_owner_for_slow_moving(self):
        msg = format_watch_identification_message(
            title="DATEJUST 28MM TWOTONE YELLOWGOLD SILVER DIAMOND STAR DIAL ROMAN ON IX (2018)",
            sku="GW036128",
            formatted_price="Rp 219,800,000",
            sheet_info="ALL STOCK (Baris 284)",
            location="Ready di Toko",
            owner="ES"
        )
        self.assertIn("📊 *Spreadsheet:* ALL STOCK (Baris 284)\n*Owner:* ES\n", msg)
        self.assertIn("👉 *Aksi Cepat (Balas pesan ini):*", msg)
        self.assertNotIn("Nama :", msg)

    def test_resolve_watch_spreadsheet_location_returns_owner_for_all_stock(self):
        from unittest.mock import patch, MagicMock
        from flask_app import resolve_watch_spreadsheet_location

        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = {
            "status": "success",
            "tab_name": "ALL STOCK",
            "row": 284,
            "owner": "ES"
        }

        with patch("requests.post", return_value=mock_res):
            sheet_info, form, owner = resolve_watch_spreadsheet_location("GW036128", blogger_post=None, return_form=True)
            self.assertEqual(sheet_info, "ALL STOCK (Baris 284)")
            self.assertEqual(form, "")
            self.assertEqual(owner, "ES")

    def test_find_active_watch_cpo_preference_for_photo_owner(self):
        from unittest.mock import patch
        import flask_app

        # Mock Shopify GraphQL response returning both Studio and CPO watches for Air-King
        mock_gql_response = {
            "data": {
                "products": {
                    "edges": [
                        {
                            "node": {
                                "id": "gid://shopify/Product/1",
                                "title": "AIR KING (2025)",
                                "status": "ACTIVE",
                                "createdAt": "2026-09-09T03:36:20Z",
                                "featuredImage": {"url": "https://example.com/studio.jpg"},
                                "variants": {
                                    "edges": [
                                        {"node": {"id": "v1", "sku": "6F2Y6936", "price": "142500000", "inventoryQuantity": 1}}
                                    ]
                                }
                            }
                        },
                        {
                            "node": {
                                "id": "gid://shopify/Product/2",
                                "title": "AIR KING (2025)",
                                "status": "ACTIVE",
                                "createdAt": "2026-10-23T08:15:30Z",
                                "featuredImage": {"url": "https://example.com/cpo.jpg"},
                                "variants": {
                                    "edges": [
                                        {"node": {"id": "v2", "sku": "CPO-231026-02", "price": "135000000", "inventoryQuantity": 1}}
                                    ]
                                }
                            }
                        }
                    ]
                }
            }
        }

        with patch.object(flask_app, "get_shopify_token", return_value="fake_token"), \
             patch("requests.post") as mock_post:
            
            mock_post_res = MagicMock()
            mock_post_res.status_code = 200
            mock_post_res.json.return_value = mock_gql_response
            mock_post.return_value = mock_post_res

            # Kasus 1: Gemini mendeteksi foto sebagai 'photo_owner'
            gemini_owner = {
                "brand": "Rolex",
                "model": "Air King",
                "photo_type": "photo_owner",
                "search_query": "Rolex Air King"
            }
            res_owner = flask_app.find_active_watch_in_shopify(gemini_owner)
            self.assertIsNotNone(res_owner)
            # Harus memilih CPO-231026-02
            self.assertEqual(res_owner["sku"], "CPO-231026-02")
            self.assertEqual(res_owner["numeric_price"], 135000000.0)

            # Kasus 2: Gemini mendeteksi foto sebagai 'photo_studio'
            gemini_studio = {
                "brand": "Rolex",
                "model": "Air King",
                "photo_type": "photo_studio",
                "search_query": "Rolex Air King"
            }
            res_studio = flask_app.find_active_watch_in_shopify(gemini_studio)
            self.assertIsNotNone(res_studio)
            # Harus memilih 6F2Y6936
            self.assertEqual(res_studio["sku"], "6F2Y6936")
            self.assertEqual(res_studio["numeric_price"], 142500000.0)

    def test_visual_verification_tie_breaker(self):
        from unittest.mock import patch
        import flask_app

        # Dua kandidat dengan judul dan skor sama
        cand_a = {"title": "AIR KING (2025)", "sku": "6F2Y6936", "image_url": "https://example.com/a.jpg"}
        cand_b = {"title": "AIR KING (2025)", "sku": "CPO-231026-02", "image_url": "https://example.com/b.jpg"}

        with patch.object(flask_app, "verify_watch_visually_with_gemini", return_value="B"), \
             patch.object(flask_app, "get_shopify_token", return_value="fake_token"), \
             patch("requests.post") as mock_post:

            mock_post_res = MagicMock()
            mock_post_res.status_code = 200
            mock_post_res.json.return_value = {
                "data": {
                    "products": {
                        "edges": [
                            {"node": {"id": "1", "title": "AIR KING (2025)", "status": "ACTIVE", "createdAt": "2026-01-01T00:00:00Z", "featuredImage": {"url": "https://example.com/a.jpg"}, "variants": {"edges": [{"node": {"id": "v1", "sku": "6F2Y6936", "price": "142500000", "inventoryQuantity": 1}}]}}},
                            {"node": {"id": "2", "title": "AIR KING (2025)", "status": "ACTIVE", "createdAt": "2026-01-01T00:00:00Z", "featuredImage": {"url": "https://example.com/b.jpg"}, "variants": {"edges": [{"node": {"id": "v2", "sku": "CPO-231026-02", "price": "135000000", "inventoryQuantity": 1}}]}}}
                        ]
                    }
                }
            }
            mock_post.return_value = mock_post_res

            # Tanpa photo_type tertentu tapi ada image_bytes
            gemini_info = {
                "brand": "Rolex",
                "model": "Air King",
                "_image_bytes": b"fake_inquiry_image"
            }
            res = flask_app.find_active_watch_in_shopify(gemini_info)
            self.assertIsNotNone(res)
            # Tie-breaker memilih B
            self.assertEqual(res["sku"], "CPO-231026-02")

    def test_normalize_watch_model_title(self):
        t1 = "YACHT-MASTER II 44MM TWOTONE ROSEGOLD (2018)"
        t2 = "YACHT-MASTER II 44MM TWOTONE ROSEGOLD (2013)"
        norm1 = normalize_watch_model_title(t1)
        norm2 = normalize_watch_model_title(t2)
        self.assertEqual(norm1, norm2)
        self.assertEqual(norm1, "YACHT MASTER II 44MM TWOTONE ROSEGOLD")

        a1 = "AIR KING (2025)"
        a2 = "AIR KING (2023)"
        self.assertEqual(normalize_watch_model_title(a1), normalize_watch_model_title(a2))
        self.assertEqual(normalize_watch_model_title(a1), "AIR KING")

    def test_swatch_x_omega_brand_and_title_detection(self):
        # 1. Swatch X Omega Moonswatch
        t1 = "SWATCH X OMEGA MOONSWATCH MISSION TO THE SUN"
        v1, kw1 = upload_automation.detect_vendor_and_brand(t1)
        self.assertEqual(v1, "Swatch X Omega")
        self.assertEqual(kw1, "SWATCH X OMEGA")
        s1 = upload_automation.strip_brand_from_title(t1, vendor=v1, matched_keyword=kw1)
        self.assertEqual(s1, "MOONSWATCH MISSION TO THE SUN")

        # 2. Swatch X Omega Snoopy White
        t2 = "SWATCH X OMEGA MOONSWATCH MISSION TO THE MOONPHASE 'SNOOPY' WHITE"
        v2, kw2 = upload_automation.detect_vendor_and_brand(t2)
        self.assertEqual(v2, "Swatch X Omega")
        s2 = upload_automation.strip_brand_from_title(t2, vendor=v2, matched_keyword=kw2)
        self.assertEqual(s2, "MOONSWATCH MISSION TO THE MOONPHASE 'SNOOPY' WHITE")

        # 3. Omega X Swatch variasi terbalik
        t3 = "OMEGA X SWATCH MOONSWATCH MISSION TO MARS"
        v3, kw3 = upload_automation.detect_vendor_and_brand(t3)
        self.assertEqual(v3, "Swatch X Omega")

        # 4. Omega murni tetap Omega (tidak tertukar dengan Swatch X Omega)
        t4 = "OMEGA SPEEDMASTER PROFESSIONAL MOONWATCH 321"
        v4, kw4 = upload_automation.detect_vendor_and_brand(t4)
        self.assertEqual(v4, "Omega")
        self.assertEqual(kw4, "OMEGA")
        s4 = upload_automation.strip_brand_from_title(t4, vendor=v4, matched_keyword=kw4)
        self.assertEqual(s4, "SPEEDMASTER PROFESSIONAL MOONWATCH 321")

        # 5. Swatch X Blancpain
        t5 = "SWATCH X BLANCPAIN SCUBA FIFTY FATHOMS ARCTIC OCEAN"
        v5, kw5 = upload_automation.detect_vendor_and_brand(t5)
        self.assertEqual(v5, "Swatch X Blancpain")

    def test_flask_app_detect_watch_brand_swatch_x_omega(self):
        b1 = detect_watch_brand("SWATCH X OMEGA MOONSWATCH MISSION TO THE SUN (2021)")
        self.assertEqual(b1, "SWATCH X OMEGA")

        b2 = detect_watch_brand("OMEGA SPEEDMASTER 321 'ED WHITE' (2022)")
        self.assertEqual(b2, "OMEGA")

    def test_is_known_action_command(self):
        # Bukan action command (harus masuk ke identifikasi foto jam)
        self.assertFalse(is_known_action_command(""))
        self.assertFalse(is_known_action_command(None))
        self.assertFalse(is_known_action_command("ready in bali"))
        self.assertFalse(is_known_action_command("bali"))
        self.assertFalse(is_known_action_command("cek barang ini dong"))
        self.assertFalse(is_known_action_command("stok bali masih ada?"))

        # Merupakan action command (harus diarahkan ke action handler)
        self.assertTrue(is_known_action_command("sold"))
        self.assertTrue(is_known_action_command("laku"))
        self.assertTrue(is_known_action_command("on hold"))
        self.assertTrue(is_known_action_command("hold"))
        self.assertTrue(is_known_action_command("reprice 350jt"))
        self.assertTrue(is_known_action_command("harga baru 280.000.000"))
        self.assertTrue(is_known_action_command("abaikan"))
        self.assertTrue(is_known_action_command("batal"))
        self.assertTrue(is_known_action_command("cancel"))

    def test_location_status_formatting(self):
        # Default tanpa location
        msg_default = format_watch_identification_message(
            title="YACHT-MASTER II 44MM TWOTONE ROSEGOLD (2013)",
            sku="363273X6",
            formatted_price="Rp 280,000,000",
            sheet_info="PHOTO STUDIO (Baris 2760)"
        )
        self.assertIn("📦 *Status:* AKTIF (Ready di Toko)", msg_default)

        # Dengan lokasi Bali
        msg_bali = format_watch_identification_message(
            title="YACHT-MASTER II 44MM TWOTONE ROSEGOLD (2018)",
            sku="CPO-280826-03",
            formatted_price="Rp 359,000,000",
            sheet_info="PHOTO OWNER (Baris 52)",
            location="Ready in Bali"
        )
        self.assertIn("📦 *Status:* AKTIF (Ready in Bali)", msg_bali)

    def test_yacht_master_bali_detection_and_tie_breaker(self):
        from unittest.mock import patch
        import flask_app

        mock_gql_response = {
            "data": {
                "products": {
                    "edges": [
                        {
                            "node": {
                                "id": "gid://shopify/Product/101",
                                "title": "YACHT-MASTER II 44MM TWOTONE ROSEGOLD (2018)",
                                "tags": ["__label:Ready In Bali", "TitipOwner"],
                                "status": "ACTIVE",
                                "createdAt": "2026-08-28T10:00:00Z",
                                "featuredImage": {"url": "https://example.com/bali_ym2.jpg"},
                                "variants": {
                                    "edges": [
                                        {"node": {"id": "v101", "sku": "CPO-280826-03", "price": "359000000", "inventoryQuantity": 1}}
                                    ]
                                }
                            }
                        },
                        {
                            "node": {
                                "id": "gid://shopify/Product/102",
                                "title": "YACHT-MASTER II 44MM TWOTONE ROSEGOLD (2013)",
                                "tags": ["TitipIDWX"],
                                "status": "ACTIVE",
                                "createdAt": "2026-05-10T10:00:00Z",
                                "featuredImage": {"url": "https://example.com/studio_ym2.jpg"},
                                "variants": {
                                    "edges": [
                                        {"node": {"id": "v102", "sku": "363273X6", "price": "280000000", "inventoryQuantity": 1}}
                                    ]
                                }
                            }
                        }
                    ]
                }
            }
        }

        # Skenario 1: User mengirim foto dengan caption "ready in bali"
        with patch.object(flask_app, "get_shopify_token", return_value="fake_token"), \
             patch("requests.post") as mock_post:
            
            mock_post_res = MagicMock()
            mock_post_res.status_code = 200
            mock_post_res.json.return_value = mock_gql_response
            mock_post.return_value = mock_post_res

            gemini_info = {
                "brand": "Rolex",
                "model": "Yacht-Master II 44mm Twotone Rosegold",
                "photo_type": "photo_studio",
                "search_query": "Rolex Yacht-Master II"
            }
            res_caption = flask_app.find_active_watch_in_shopify(gemini_info, user_caption="ready in bali")
            self.assertIsNotNone(res_caption)
            self.assertEqual(res_caption["sku"], "CPO-280826-03")
            self.assertEqual(res_caption["title"], "YACHT-MASTER II 44MM TWOTONE ROSEGOLD (2018)")
            self.assertEqual(res_caption["location"], "Ready in Bali")
            self.assertEqual(res_caption["numeric_price"], 359000000.0)

        # Skenario 2: User mengirim HANYA foto (tanpa caption), tapi foto studio
        # Pemicu tie-breaker harus aktif karena model sama setelah normalisasi,
        # dan CPO di photo_studio tidak lagi terkena penalti artifisial -5000.
        # Kandidat A (top1) = 363273X6 (skor 25000), Kandidat B (top2) = CPO-280826-03 (skor 24500).
        # Verifikasi visual Gemini membandingkan foto dan memilih pemenang 'B' (karena foto inquiry cocok dengan listing CPO Bali).
        with patch.object(flask_app, "get_shopify_token", return_value="fake_token"), \
             patch.object(flask_app, "verify_watch_visually_with_gemini", return_value="B") as mock_visual, \
             patch("requests.post") as mock_post:

            mock_post_res = MagicMock()
            mock_post_res.status_code = 200
            mock_post_res.json.return_value = mock_gql_response
            mock_post.return_value = mock_post_res

            gemini_info_photo_only = {
                "brand": "Rolex",
                "model": "Yacht-Master II 44mm Twotone Rosegold",
                "photo_type": "photo_studio",
                "search_query": "Rolex Yacht-Master II",
                "_image_bytes": b"real_inquiry_photo_bytes"
            }
            res_photo_only = flask_app.find_active_watch_in_shopify(gemini_info_photo_only, user_caption="")
            self.assertIsNotNone(res_photo_only)
            # Tie-breaker visual terpanggil dan memilih kandidat A (Bali 2018)
            self.assertTrue(mock_visual.called)
            self.assertEqual(res_photo_only["sku"], "CPO-280826-03")
            self.assertEqual(res_photo_only["location"], "Ready in Bali")

    def test_gemini_vision_catalog_card_exact_matching(self):
        """
        Memastikan bahwa jika gambar adalah product card / screenshot katalog yang memuat text spesifik
        (seperti full_title_text, year, extracted_price, dan location_badge), sistem mencocokkan
        ke SKU yang 100% tepat tanpa tertukar dengan model tahun lain atau harga berbeda.
        """
        mock_gql_products = {
            "data": {
                "products": {
                    "edges": [
                        # Yacht-Master 2018 (Bali) vs 2013 (Studio)
                        {
                            "node": {
                                "id": "gid://shopify/Product/1",
                                "title": "YACHT-MASTER II 44MM TWOTONE ROSEGOLD (2018)",
                                "tags": ["__label:Ready In Bali", "TitipOwner"],
                                "status": "ACTIVE",
                                "createdAt": "2026-08-28T10:00:00Z",
                                "variants": {"edges": [{"node": {"id": "v1", "sku": "CPO-280826-03", "price": "359000000.00", "inventoryQuantity": 1}}]}
                            }
                        },
                        {
                            "node": {
                                "id": "gid://shopify/Product/2",
                                "title": "YACHT-MASTER II 44MM TWOTONE ROSEGOLD (2013)",
                                "tags": ["__label2:Consignment", "Men", "TitipIDWX"],
                                "status": "ACTIVE",
                                "createdAt": "2026-01-15T10:00:00Z",
                                "variants": {"edges": [{"node": {"id": "v2", "sku": "363273X6", "price": "280000000.00", "inventoryQuantity": 1}}]}
                            }
                        },
                        # Air King 2025 CPO (135jt) vs Air King 2025 Studio (142.5jt)
                        {
                            "node": {
                                "id": "gid://shopify/Product/3",
                                "title": "AIR KING (2025)",
                                "tags": ["TitipOwner"],
                                "status": "ACTIVE",
                                "createdAt": "2026-10-23T10:00:00Z",
                                "variants": {"edges": [{"node": {"id": "v3", "sku": "CPO-231026-02", "price": "135000000.00", "inventoryQuantity": 1}}]}
                            }
                        },
                        {
                            "node": {
                                "id": "gid://shopify/Product/4",
                                "title": "AIR KING (2025)",
                                "tags": ["Men"],
                                "status": "ACTIVE",
                                "createdAt": "2026-09-01T10:00:00Z",
                                "variants": {"edges": [{"node": {"id": "v4", "sku": "6F2Y6936", "price": "142500000.00", "inventoryQuantity": 1}}]}
                            }
                        },
                        # Datejust Wimbledon 2022 (Bali)
                        {
                            "node": {
                                "id": "gid://shopify/Product/5",
                                "title": "DATEJUST 41MM TWOTONE YELLOWGOLD WIMBLEDON DIAL (2022)",
                                "tags": ["__label:Ready In Bali", "TitipOwner"],
                                "status": "ACTIVE",
                                "createdAt": "2026-08-28T10:00:00Z",
                                "variants": {"edges": [{"node": {"id": "v5", "sku": "CPO-280826-04", "price": "249000000.00", "inventoryQuantity": 1}}]}
                            }
                        },
                        # Hublot Big Bang Unico 42mm (2026)
                        {
                            "node": {
                                "id": "gid://shopify/Product/6",
                                "title": "BIG BANG UNICO 42MM TITANIUM CERAMIC (2026)",
                                "tags": ["__label2:Consignment", "Men", "TitipIDWX"],
                                "status": "ACTIVE",
                                "createdAt": "2026-11-10T10:00:00Z",
                                "variants": {"edges": [{"node": {"id": "v6", "sku": "1636626", "price": "258000000.00", "inventoryQuantity": 1}}]}
                            }
                        }
                    ]
                }
            }
        }

        with patch.object(flask_app, "get_shopify_token", return_value="fake_token"), \
             patch("requests.post") as mock_post:

            mock_post_res = MagicMock()
            mock_post_res.status_code = 200
            mock_post_res.json.return_value = mock_gql_products
            mock_post.return_value = mock_post_res

            # 1. Yacht-Master II 2018 (Bali - 359jt) harus terpilih CPO-280826-03, bukan 363273X6 (2013 - 280jt)
            ym_info = {
                "brand": "Rolex",
                "model": "Yacht-Master II 44mm Twotone Rosegold",
                "year": "2018",
                "dial_color": "White",
                "reference": "",
                "extracted_price": 359000000,
                "location_badge": "Ready In Bali",
                "full_title_text": "YACHT-MASTER II 44MM TWOTONE ROSEGOLD (2018)",
                "search_query": "Yacht-Master II 44mm Twotone Rosegold 2018",
                "photo_type": "photo_studio"
            }
            res_ym = flask_app.find_active_watch_in_shopify(ym_info, user_caption="")
            self.assertEqual(res_ym["sku"], "CPO-280826-03")
            self.assertEqual(res_ym["location"], "Ready in Bali")
            self.assertEqual(res_ym["numeric_price"], 359000000.0)

            # 2. Air King 2025 dengan harga 135jt harus terpilih CPO-231026-02, bukan 6F2Y6936 (142.5jt)
            ak_info = {
                "brand": "Rolex",
                "model": "Air King",
                "year": "2025",
                "dial_color": "Black",
                "reference": "",
                "extracted_price": 135000000,
                "location_badge": "",
                "full_title_text": "AIR KING (2025)",
                "search_query": "Air King 2025",
                "photo_type": "photo_owner"
            }
            res_ak = flask_app.find_active_watch_in_shopify(ak_info, user_caption="")
            self.assertEqual(res_ak["sku"], "CPO-231026-02")
            self.assertEqual(res_ak["numeric_price"], 135000000.0)

            # 3. Datejust Wimbledon 2022 Bali 249jt harus terpilih CPO-280826-04
            dj_info = {
                "brand": "Rolex",
                "model": "Datejust 41",
                "year": "2022",
                "dial_color": "Wimbledon",
                "reference": "126333",
                "extracted_price": 249000000,
                "location_badge": "Ready In Bali",
                "full_title_text": "DATEJUST 41MM TWOTONE YELLOWGOLD WIMBLEDON DIAL (2022)",
                "search_query": "Rolex Datejust 41 Wimbledon 126333",
                "photo_type": "photo_studio"
            }
            res_dj = flask_app.find_active_watch_in_shopify(dj_info, user_caption="")
            self.assertEqual(res_dj["sku"], "CPO-280826-04")
            self.assertEqual(res_dj["location"], "Ready in Bali")
            self.assertEqual(res_dj["numeric_price"], 249000000.0)

            # 4. Hublot Big Bang Unico 42mm (2026) 258jt harus terpilih 1636626
            hb_info = {
                "brand": "Hublot",
                "model": "Big Bang Unico 42mm",
                "year": "2026",
                "dial_color": "Titanium Ceramic Skeleton",
                "reference": "",
                "extracted_price": 258000000,
                "location_badge": "Consignment",
                "full_title_text": "BIG BANG UNICO 42MM TITANIUM CERAMIC (2026)",
                "search_query": "Hublot Big Bang Unico 42mm Titanium Ceramic 2026",
                "photo_type": "photo_owner"
            }
            res_hb = flask_app.find_active_watch_in_shopify(hb_info, user_caption="")
            self.assertEqual(res_hb["sku"], "1636626")
            self.assertEqual(res_hb["numeric_price"], 258000000.0)

if __name__ == "__main__":
    unittest.main()
