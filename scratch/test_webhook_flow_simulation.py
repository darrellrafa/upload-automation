import sys
import os
import unittest
from unittest.mock import MagicMock, patch

for mod in ["flask", "requests", "bs4", "google", "google.oauth2", "google.oauth2.credentials", "googleapiclient", "googleapiclient.discovery"]:
    if mod not in sys.modules:
        m = MagicMock()
        if mod == "flask":
            app_inst = MagicMock()
            app_inst.route = lambda *args, **kwargs: (lambda f: f)
            m.Flask = MagicMock(return_value=app_inst)
            m.request = MagicMock()
            m.jsonify = lambda x: x
        sys.modules[mod] = m

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flask_app
from flask_app import wa_webhook, ACTIVE_IDENTIFIED_WATCHES

class TestWebhookFlowSimulation(unittest.TestCase):
    def setUp(self):
        ACTIVE_IDENTIFIED_WATCHES.clear()
        flask_app.TARGET_GROUP_ID = "test-group@g.us, 62817626104-1627455181@g.us"

    @patch("flask_app.kirim_balasan_wa")
    @patch("flask_app.get_watch_photo_url")
    @patch("flask_app.get_blogger_service")
    @patch("flask_app.resolve_watch_spreadsheet_location")
    @patch("flask_app.find_active_watch_in_shopify")
    @patch("flask_app.identify_watch_with_gemini")
    def test_photo_identification_then_abaikan(self, mock_gemini, mock_shopify, mock_sheet, mock_blog, mock_photo, mock_kirim_wa):
        chat_id = "test-group@g.us"
        mock_blog.return_value = None
        mock_photo.return_value = "https://example.com/photo.jpg"

        mock_gemini.return_value = {
            "brand": "Vacheron Constantin",
            "model": "Historiques American 1921",
            "dial_color": "Silver",
            "reference": "82035",
            "search_query": "Vacheron Constantin Historiques American 1921",
            "_image_bytes": b"fake_raw_image_bytes_12345"
        }
        mock_shopify.return_value = {
            "title": "HISTORIQUES AMERICAN 1921 ROSEGOLD SILVER DIAL (2026)",
            "sku": "3012154",
            "numeric_price": 678000000.0,
            "formatted_price": "Rp 678,000,000",
            "product_node": {"id": "123", "title": "HISTORIQUES AMERICAN 1921"},
            "variant_node": {"sku": "3012154"}
        }
        mock_sheet.return_value = ("PHOTO STUDIO (Baris 2819)", "Nama : Said\nNo Hp : 08118811159\nBrand/Ref No: Omega ed white 321")

        # 1. Staff sends watch photo with "identifikasi" keyword
        photo_payload = {
            "typeWebhook": "incomingMessageReceived",
            "idMessage": "msg-001",
            "senderData": {
                "chatId": chat_id,
                "senderName": "Dylan Baru"
            },
            "messageData": {
                "typeMessage": "imageMessage",
                "fileMessageData": {
                    "downloadUrl": "https://example.com/watch.jpg",
                    "caption": "identifikasi"
                }
            }
        }
        flask_app.request.get_json = MagicMock(return_value=photo_payload)

        res, code = wa_webhook()
        self.assertEqual(code, 200)
        # Verify JSON serializability (anti 'bytes is not JSON serializable')
        import json
        json_output = json.dumps(res)
        self.assertNotIn("fake_raw_image_bytes", json_output)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("action"), "identify_watch")
        self.assertEqual(res.get("form_content"), "Nama : Said\nNo Hp : 08118811159\nBrand/Ref No: Omega ed white 321")

        # Verify active session stored
        self.assertIn(chat_id, ACTIVE_IDENTIFIED_WATCHES)
        self.assertEqual(ACTIVE_IDENTIFIED_WATCHES[chat_id]["sku"], "3012154")
        self.assertEqual(ACTIVE_IDENTIFIED_WATCHES[chat_id]["sheet_info"], "PHOTO STUDIO (Baris 2819)")

        # Verify WA message sent to chat_id
        mock_kirim_wa.assert_called()
        last_wa_msg = mock_kirim_wa.call_args[0][1]
        self.assertIn("⌚ *IDENTIFIKASI JAM TANGAN IDWX*", last_wa_msg)
        self.assertIn("3012154", last_wa_msg)
        self.assertIn("📊 *Spreadsheet:* PHOTO STUDIO (Baris 2819)", last_wa_msg)
        self.assertIn("Nama : Said", last_wa_msg)
        self.assertIn("Brand/Ref No: Omega ed white 321", last_wa_msg)
        self.assertIn("• Ketik *batal* jika tidak ada tindakan", last_wa_msg)

        # 2. Staff replies "abaikan"
        abaikan_payload = {
            "typeWebhook": "incomingMessageReceived",
            "idMessage": "msg-002",
            "senderData": {
                "chatId": chat_id,
                "senderName": "Dylan Baru"
            },
            "messageData": {
                "typeMessage": "textMessage",
                "textMessageData": {
                    "textMessage": "abaikan"
                }
            }
        }
        flask_app.request.get_json = MagicMock(return_value=abaikan_payload)

        res_batal, code_batal = wa_webhook()
        self.assertEqual(code_batal, 200)
        self.assertEqual(res_batal.get("status"), "cancelled")

        # Session should now be empty
        self.assertNotIn(chat_id, ACTIVE_IDENTIFIED_WATCHES)

        # Verify WA message confirms cancellation
        last_wa_batal = mock_kirim_wa.call_args[0][1]
        self.assertIn("❌ *Identifikasi jam tangan dibatalkan.*", last_wa_batal)

    @patch("flask_app.kirim_balasan_wa")
    @patch("flask_app.get_watch_photo_url")
    @patch("flask_app.get_blogger_service")
    @patch("flask_app.resolve_watch_spreadsheet_location")
    @patch("flask_app.find_active_watch_in_shopify")
    @patch("flask_app.identify_watch_with_gemini")
    def test_photo_identification_slow_moving_with_owner(self, mock_gemini, mock_shopify, mock_sheet, mock_blog, mock_photo, mock_kirim_wa):
        chat_id = "test-group@g.us"
        mock_blog.return_value = None
        mock_photo.return_value = "https://example.com/photo.jpg"

        mock_gemini.return_value = {
            "brand": "Rolex",
            "model": "Datejust 28mm",
            "dial_color": "Silver Diamond",
            "search_query": "Rolex Datejust 28mm GW036128"
        }
        mock_shopify.return_value = {
            "title": "DATEJUST 28MM TWOTONE YELLOWGOLD SILVER DIAMOND STAR DIAL ROMAN ON IX (2018)",
            "sku": "GW036128",
            "numeric_price": 219800000.0,
            "formatted_price": "Rp 219,800,000",
            "product_node": {"id": "456", "title": "DATEJUST 28MM"},
            "variant_node": {"sku": "GW036128"}
        }
        mock_sheet.return_value = ("ALL STOCK (Baris 284)", "", "ES")

        photo_payload = {
            "typeWebhook": "incomingMessageReceived",
            "idMessage": "msg-sm-001",
            "senderData": {
                "chatId": chat_id,
                "senderName": "Dylan Baru"
            },
            "messageData": {
                "typeMessage": "imageMessage",
                "fileMessageData": {
                    "downloadUrl": "https://example.com/watch.jpg",
                    "caption": "identifikasi"
                }
            }
        }
        flask_app.request.get_json = MagicMock(return_value=photo_payload)

        res, code = wa_webhook()
        self.assertEqual(code, 200)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("action"), "identify_watch")
        self.assertEqual(res.get("owner"), "ES")

        mock_kirim_wa.assert_called()
        last_wa_msg = mock_kirim_wa.call_args[0][1]
        self.assertIn("📊 *Spreadsheet:* ALL STOCK (Baris 284)\n*Owner:* ES\n", last_wa_msg)
        self.assertNotIn("Nama :", last_wa_msg)
        self.assertIn("• Ketik *sold* untuk menandai laku", last_wa_msg)

    @patch("flask_app.kirim_balasan_wa")
    @patch("flask_app.get_watch_photo_url")
    @patch("flask_app.update_slow_moving_status_sheet")
    @patch("flask_app.update_consignment_status_sheet")
    @patch("flask_app.update_shopify_takedown")
    @patch("flask_app.get_blogger_service")
    def test_quick_sold_reply_uses_active_identified_watch(self, mock_blog, mock_shop_td, mock_sheet_cs, mock_sheet_sm, mock_photo, mock_kirim_wa):
        chat_id = "test-group@g.us"
        ACTIVE_IDENTIFIED_WATCHES[chat_id] = {
            "sku": "3012154",
            "title": "HISTORIQUES AMERICAN 1921",
            "formatted_price": "Rp 678,000,000",
            "numeric_price": 678000000.0,
            "sheet_info": "ALL STOCK (Baris 313)",
            "timestamp": 9999999999
        }

        mock_shop_td.return_value = {"status": "success", "product_title": "HISTORIQUES AMERICAN 1921", "matched_sku": "3012154"}
        mock_blog.return_value = None
        mock_photo.return_value = "https://example.com/photo.jpg"
        mock_sheet_cs.return_value = {"status": "not_found"}
        mock_sheet_sm.return_value = {"status": "success", "row": 313, "tab_name": "ALL STOCK"}

        # Staff replies simply "sold"
        sold_payload = {
            "typeWebhook": "incomingMessageReceived",
            "idMessage": "msg-003",
            "senderData": {
                "chatId": chat_id,
                "senderName": "Dylan Baru"
            },
            "messageData": {
                "typeMessage": "textMessage",
                "textMessageData": {
                    "textMessage": "sold"
                }
            }
        }
        flask_app.request.get_json = MagicMock(return_value=sold_payload)

        res, code = wa_webhook()
        self.assertEqual(code, 200)
        self.assertEqual(res.get("command"), "SOLD")
        self.assertEqual(res.get("sku"), "3012154")
        self.assertNotIn(chat_id, ACTIVE_IDENTIFIED_WATCHES)

    @patch("flask_app.identify_watch_with_gemini")
    def test_excluded_group_skips_identification(self, mock_gemini):
        chat_id = "62817626104-1627455181@g.us"
        photo_payload = {
            "typeWebhook": "incomingMessageReceived",
            "idMessage": "msg-004",
            "senderData": {
                "chatId": chat_id,
                "senderName": "Staff Studio"
            },
            "messageData": {
                "typeMessage": "imageMessage",
                "fileMessageData": {
                    "downloadUrl": "https://example.com/watch.jpg",
                    "caption": "identifikasi"
                }
            }
        }
        flask_app.request.get_json = MagicMock(return_value=photo_payload)

        res, code = wa_webhook()
        self.assertEqual(code, 200)
        self.assertEqual(res.get("status"), "ignored")
        self.assertEqual(res.get("reason"), "Excluded chat/group for watch identification")
        mock_gemini.assert_not_called()

    @patch("requests.post")
    @patch("flask_app.identify_watch_with_gemini")
    def test_excluded_group_still_processes_photo_studio_draft(self, mock_gemini, mock_post):
        chat_id = "62817626104-1627455181@g.us"
        mock_post_res = MagicMock()
        mock_post_res.status_code = 200
        mock_post_res.json.return_value = {"status": "success", "row": 150}
        mock_post.return_value = mock_post_res

        photo_payload = {
            "typeWebhook": "incomingMessageReceived",
            "idMessage": "msg-studio-001",
            "senderData": {
                "chatId": chat_id,
                "senderName": "DUALTIME | BANG TOMMY"
            },
            "messageData": {
                "typeMessage": "imageMessage",
                "fileMessageData": {
                    "downloadUrl": "https://example.com/studio_watch.jpg",
                    "caption": "Lange 1 Time Zone, Aug 2008 / 172521 / Franky"
                }
            }
        }
        flask_app.request.get_json = MagicMock(return_value=photo_payload)

        res, code = wa_webhook()
        self.assertEqual(code, 200)
        # Verify JSON serializability (anti 'bytes is not JSON serializable')
        import json
        json_output = json.dumps(res)
        self.assertNotIn("fake_raw_image_bytes", json_output)
        self.assertEqual(res.get("status"), "success")
        self.assertIn("sheets_response", res)
        # Pastikan Gemini Vision TIDAK dipanggil karena bukan perintah identifikasi
        mock_gemini.assert_not_called()
        # Pastikan request dikirim ke Apps Script History Foto Studio
        mock_post.assert_called_once()
        sent_payload = mock_post.call_args[1].get("json")
        self.assertEqual(sent_payload.get("action"), "insert_draft")
        self.assertEqual(sent_payload.get("serial_number"), "172521")
        self.assertEqual(sent_payload.get("name_in_creative"), "Lange 1 Time Zone, Aug 2008 / 172521 / Franky")

    @patch("flask_app.kirim_balasan_wa")
    @patch("flask_app.get_blogger_service")
    @patch("flask_app.resolve_watch_spreadsheet_location")
    @patch("flask_app.find_active_watch_in_shopify")
    @patch("flask_app.identify_watch_with_gemini")
    def test_photo_identification_with_bali_caption(self, mock_gemini, mock_shopify, mock_sheet, mock_blog, mock_kirim_wa):
        chat_id = "test-group@g.us"
        mock_blog.return_value = None
        mock_sheet.return_value = "PHOTO OWNER (Baris 52)"

        mock_gemini.return_value = {
            "brand": "Rolex",
            "model": "Yacht-Master II 44mm Twotone Rosegold",
            "search_query": "Rolex Yacht-Master II"
        }
        mock_shopify.return_value = {
            "title": "YACHT-MASTER II 44MM TWOTONE ROSEGOLD (2018)",
            "sku": "CPO-280826-03",
            "numeric_price": 359000000.0,
            "formatted_price": "Rp 359,000,000",
            "location": "Ready in Bali",
            "product_node": {"id": "101", "title": "YACHT-MASTER II"},
            "variant_node": {"sku": "CPO-280826-03"}
        }

        # Staff mengirim foto dengan caption "identifikasi ready in bali"
        photo_payload = {
            "typeWebhook": "incomingMessageReceived",
            "idMessage": "msg-bali-01",
            "senderData": {
                "chatId": chat_id,
                "senderName": "Staff Bali"
            },
            "messageData": {
                "typeMessage": "imageMessage",
                "fileMessageData": {
                    "downloadUrl": "https://example.com/bali_ym.jpg",
                    "caption": "identifikasi ready in bali"
                }
            }
        }
        flask_app.request.get_json = MagicMock(return_value=photo_payload)

        res, code = wa_webhook()
        self.assertEqual(code, 200)
        # Verify JSON serializability (anti 'bytes is not JSON serializable')
        import json
        json_output = json.dumps(res)
        self.assertNotIn("fake_raw_image_bytes", json_output)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("action"), "identify_watch")

        # find_active_watch_in_shopify harus dipanggil dengan user_caption="ready in bali"
        mock_shopify.assert_called_with(mock_gemini.return_value, user_caption="identifikasi ready in bali")

        # Pesan WA yang dikirimkan harus memuat status "Ready in Bali"
        mock_kirim_wa.assert_called()
        last_wa_msg = mock_kirim_wa.call_args[0][1]
        self.assertIn("📦 *Status:* AKTIF (Ready in Bali)", last_wa_msg)
        self.assertIn("CPO-280826-03", last_wa_msg)
        self.assertIn("Rp 359,000,000", last_wa_msg)

    @patch("flask_app.kirim_balasan_wa")
    @patch("flask_app.update_blogger_repost")
    @patch("flask_app.find_blogger_post_by_code")
    @patch("flask_app.get_blogger_service")
    def test_repost_command_flow_success(self, mock_blog_service, mock_find_post, mock_update_repost, mock_kirim_wa):
        chat_id = "test-group@g.us"
        mock_blog_service.return_value = MagicMock()
        mock_post = {
            "id": "post-3012154",
            "title": "VACHERON CONSTANTIN HISTORIQUES AMERICAN 1921",
            "labels": ["FEATURED"],
            "published": "2026-11-01T10:00:00Z"
        }
        mock_find_post.return_value = mock_post
        mock_update_repost.return_value = {
            "status": "success",
            "post_title": "VACHERON CONSTANTIN HISTORIQUES AMERICAN 1921",
            "publish_date": "20/11/26 12:30 WIB"
        }

        repost_payload = {
            "typeWebhook": "incomingMessageReceived",
            "idMessage": "msg-repost-001",
            "senderData": {
                "chatId": chat_id,
                "senderName": "Dylan Baru"
            },
            "messageData": {
                "typeMessage": "textMessage",
                "textMessageData": {
                    "textMessage": "Repost 3012154"
                }
            }
        }
        flask_app.request.get_json = MagicMock(return_value=repost_payload)

        res, code = wa_webhook()
        self.assertEqual(code, 200)
        # Verify JSON serializability (anti 'bytes is not JSON serializable')
        import json
        json_output = json.dumps(res)
        self.assertNotIn("fake_raw_image_bytes", json_output)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("command"), "REPOST")
        self.assertEqual(res.get("sku"), "3012154")
        self.assertIn("spreadsheet_slow_moving", res)
        self.assertEqual(res["spreadsheet_slow_moving"]["status"], "skipped")

        # Verify WA message
        mock_kirim_wa.assert_called()
        last_wa_msg = mock_kirim_wa.call_args[0][1]
        self.assertIn("🔁 *LAPORAN REPOST IDWX*", last_wa_msg)
        self.assertIn("3012154", last_wa_msg)
        self.assertIn("Dylan Baru", last_wa_msg)
        self.assertIn("Spreadsheet (Slow Moving):* Dilewati", last_wa_msg)

    @patch("flask_app.identify_watch_with_gemini")
    def test_forwarded_photo_without_identifikasi_keyword_is_ignored(self, mock_gemini):
        chat_id = "test-group@g.us"
        # Forwarded photo atau foto kiriman staff tanpa kata kunci 'identifikasi'
        photo_payload = {
            "typeWebhook": "incomingMessageReceived",
            "idMessage": "msg-fwd-01",
            "senderData": {
                "chatId": chat_id,
                "senderName": "Dylan Baru"
            },
            "messageData": {
                "typeMessage": "imageMessage",
                "fileMessageData": {
                    "downloadUrl": "https://example.com/watch.jpg",
                    "caption": "ready in bali"  # Tidak memuat kata 'identifikasi'
                }
            }
        }
        flask_app.request.get_json = MagicMock(return_value=photo_payload)

        res, code = wa_webhook()
        self.assertEqual(code, 200)
        self.assertEqual(res.get("status"), "ignored")
        # Pastikan Gemini Vision TIDAK dipanggil karena tidak ada kata 'identifikasi'
        mock_gemini.assert_not_called()

    @patch("flask_app.kirim_balasan_wa")
    def test_auto_cancel_timer_feedback_after_timeout(self, mock_kirim_wa):
        chat_id = "test-group@g.us"
        import time
        ts = time.time()
        session_data = {
            "sku": "5P87D725-1",
            "title": "DAYTONA STEEL BLACK DIAL CERAMIC BEZEL (2017)",
            "formatted_price": "Rp 430,000,000",
            "numeric_price": 430000000.0,
            "sheet_info": "PHOTO STUDIO (Baris 2856)",
            "timestamp": ts
        }
        # Simpan sesi
        ACTIVE_IDENTIFIED_WATCHES[chat_id] = session_data
        self.assertIn(chat_id, ACTIVE_IDENTIFIED_WATCHES)

        # Trigger auto cancel dengan wait_seconds=0.01 detik
        flask_app.schedule_session_auto_cancel(chat_id, ts, wait_seconds=0.01)
        import time
        time.sleep(0.05)

        # Sesi harus sudah terhapus otomatis
        self.assertNotIn(chat_id, ACTIVE_IDENTIFIED_WATCHES)
        mock_kirim_wa.assert_called()
        last_wa_msg = mock_kirim_wa.call_args[0][1]
        self.assertIn("⏱️ *SESI IDENTIFIKASI HABIS (2 MENIT)*", last_wa_msg)
        self.assertIn("DAYTONA STEEL BLACK DIAL CERAMIC BEZEL (2017)", last_wa_msg)
        self.assertIn("5P87D725-1", last_wa_msg)

    @patch("flask_app.kirim_balasan_wa")
    def test_expired_session_response_on_batal(self, mock_kirim_wa):
        chat_id = "test-group@g.us"
        import time
        old_ts = time.time() - 200  # 200 detik lalu (> 120s)
        # Langsung simpan sesi lama ke store
        store = flask_app.load_session_store_from_disk()
        store["active"][chat_id] = {
            "sku": "5P87D725-1",
            "title": "DAYTONA STEEL BLACK DIAL CERAMIC BEZEL (2017)",
            "timestamp": old_ts
        }
        flask_app.save_session_store_to_disk(store)

        batal_payload = {
            "typeWebhook": "incomingMessageReceived",
            "idMessage": "msg-batal-expired",
            "senderData": {"chatId": chat_id, "senderName": "Dylan Baru"},
            "messageData": {"typeMessage": "textMessage", "textMessageData": {"textMessage": "batal"}}
        }
        flask_app.request.get_json = MagicMock(return_value=batal_payload)

        res, code = wa_webhook()
        self.assertEqual(code, 200)
        self.assertEqual(res.get("status"), "cancelled")
        mock_kirim_wa.assert_called()
        last_wa_msg = mock_kirim_wa.call_args[0][1]
        self.assertIn("⏱️ *SESI IDENTIFIKASI SUDAH KEDALUWARSA (2 MENIT)*", last_wa_msg)
        self.assertIn("DAYTONA STEEL BLACK DIAL CERAMIC BEZEL (2017)", last_wa_msg)

    @patch("flask_app.kirim_balasan_wa")
    def test_expired_session_response_on_bare_action(self, mock_kirim_wa):
        chat_id = "test-group@g.us"
        import time
        old_ts = time.time() - 200  # 200 detik lalu (> 120s)
        store = flask_app.load_session_store_from_disk()
        store["active"][chat_id] = {
            "sku": "5P87D725-1",
            "title": "DAYTONA STEEL BLACK DIAL CERAMIC BEZEL (2017)",
            "timestamp": old_ts
        }
        flask_app.save_session_store_to_disk(store)

        sold_payload = {
            "typeWebhook": "incomingMessageReceived",
            "idMessage": "msg-sold-expired",
            "senderData": {"chatId": chat_id, "senderName": "Dylan Baru"},
            "messageData": {"typeMessage": "textMessage", "textMessageData": {"textMessage": "sold"}}
        }
        flask_app.request.get_json = MagicMock(return_value=sold_payload)

        res, code = wa_webhook()
        self.assertEqual(code, 200)
        self.assertEqual(res.get("status"), "expired")
        mock_kirim_wa.assert_called()
        last_wa_msg = mock_kirim_wa.call_args[0][1]
        self.assertIn("⏱️ *SESI IDENTIFIKASI KEDALUWARSA (2 MENIT)*", last_wa_msg)
        self.assertIn("DAYTONA STEEL BLACK DIAL CERAMIC BEZEL (2017)", last_wa_msg)

    @patch("flask_app.kirim_balasan_wa")
    def test_bare_action_without_any_session_returns_guidance(self, mock_kirim_wa):
        chat_id = "test-group@g.us"
        flask_app.clear_session_store()

        sold_payload = {
            "typeWebhook": "incomingMessageReceived",
            "idMessage": "msg-sold-no-sess",
            "senderData": {"chatId": chat_id, "senderName": "Dylan Baru"},
            "messageData": {"typeMessage": "textMessage", "textMessageData": {"textMessage": "sold"}}
        }
        flask_app.request.get_json = MagicMock(return_value=sold_payload)

        res, code = wa_webhook()
        self.assertEqual(code, 200)
        self.assertEqual(res.get("status"), "ignored")
        mock_kirim_wa.assert_called()
        last_wa_msg = mock_kirim_wa.call_args[0][1]
        self.assertIn("ℹ️ *Tidak ada sesi identifikasi jam tangan yang aktif.*", last_wa_msg)
        self.assertIn("sold [SKU]", last_wa_msg)

    @patch("flask_app.kirim_balasan_wa")
    @patch("flask_app.update_shopify_takedown")
    @patch("flask_app.get_blogger_service")
    @patch("flask_app.find_blogger_post_by_code")
    @patch("flask_app.delete_blogger_post")
    @patch("flask_app.update_consignment_status_sheet")
    def test_sold_takedown_without_blogspot_labels_falls_back_to_photo_studio(
        self, mock_sheet_status, mock_del_blog, mock_find_post, mock_get_blog, mock_shop_td, mock_kirim_wa
    ):
        chat_id = "test-group@g.us"
        sku = "09R8215"
        mock_shop_td.return_value = {"status": "success", "product_title": "TUDOR PELAGOS LHD TITANIUM BLACK", "matched_sku": sku}
        mock_get_blog.return_value = MagicMock()
        # Postingan di Blogspot ada, TAPI TIDAK punya label CONSIGNMENT_PS atau CONSIGNMENT_PO
        mock_find_post.return_value = {
            "id": "post-09r",
            "title": "[FOR SALE] TUDOR PELAGOS LHD TITANIUM BLACK (2026)",
            "labels": ["TUDOR", "FOR SALE", "WATCHES"],
            "published": "2026-07-23T10:00:00Z",
            "content": "Price: Rp 85,000,000Code: 09R8215 (Victor T)"
        }
        mock_del_blog.return_value = {"status": "success", "post_title": "[FOR SALE] TUDOR PELAGOS LHD TITANIUM BLACK (2026)"}
        mock_sheet_status.return_value = {"status": "success", "row": 2515, "tab_name": "PHOTO STUDIO"}

        sold_payload = {
            "typeWebhook": "incomingMessageReceived",
            "idMessage": "msg-sold-09r",
            "senderData": {"chatId": chat_id, "senderName": "Dylan Baru"},
            "messageData": {"typeMessage": "textMessage", "textMessageData": {"textMessage": f"sold {sku}"}}
        }
        flask_app.request.get_json = MagicMock(return_value=sold_payload)

        res, code = wa_webhook()
        self.assertEqual(code, 200)
        self.assertEqual(res.get("command"), "SOLD")
        self.assertEqual(res.get("sku"), sku)
        # Verifikasi bahwa spreadsheet tetap diupdate via Smart Fallback ke PHOTO STUDIO
        self.assertEqual(res["spreadsheet_consignment_ps"]["status"], "success")
        self.assertEqual(res["spreadsheet_consignment_ps"]["row"], 2515)

        # Verifikasi teks pesan WhatsApp
        mock_kirim_wa.assert_called()
        last_wa_msg = mock_kirim_wa.call_args[0][1]
        self.assertIn("✅ *Spreadsheet (Consignment PS):*", last_wa_msg)
        self.assertIn("Baris 2515, Tab PHOTO STUDIO", last_wa_msg)
        self.assertNotIn("Spreadsheet:* Dilewati", last_wa_msg)

    @patch("flask_app.kirim_balasan_wa")
    @patch("flask_app.update_consignment_sheet")
    @patch("flask_app.update_blogger_reprice")
    @patch("flask_app.update_shopify_reprice")
    @patch("flask_app.get_blogger_service")
    @patch("flask_app.find_blogger_post_by_code")
    def test_reprice_with_explicit_sku_without_active_session(
        self, mock_find_post, mock_get_blog, mock_shop_price, mock_blog_price, mock_sheet_reprice, mock_kirim_wa
    ):
        chat_id = "test-group@g.us"
        ACTIVE_IDENTIFIED_WATCHES.clear()

        mock_get_blog.return_value = MagicMock()
        mock_find_post.return_value = {
            "id": "post-reprice-584",
            "title": "[FOR SALE] PATEK PHILIPPE NAUTILUS (2020)",
            "labels": ["CONSIGNMENT_PS"],
            "content": "Price: Rp 2,200,000,000Code: 5846254/4664620"
        }
        mock_shop_price.return_value = {"status": "success", "title": "PATEK PHILIPPE NAUTILUS (2020)"}
        mock_blog_price.return_value = {"status": "success"}
        mock_sheet_reprice.return_value = {"status": "success", "row": 1500, "tab_name": "PHOTO STUDIO"}

        # User mengirim perintah langsung dengan SKU (tanpa sesi aktif, baris baru antar SKU dan harga)
        reprice_payload = {
            "typeWebhook": "incomingMessageReceived",
            "idMessage": "msg-reprice-direct",
            "senderData": {"chatId": chat_id, "senderName": "Dylan Baru"},
            "messageData": {
                "typeMessage": "textMessage",
                "textMessageData": {
                    "textMessage": "reprice 5846254/4664620\n2,068,000,000"
                }
            }
        }
        flask_app.request.get_json = MagicMock(return_value=reprice_payload)

        res, code = wa_webhook()
        self.assertEqual(code, 200)
        self.assertEqual(res.get("command"), "REPRICE")
        self.assertEqual(res.get("sku"), "5846254/4664620")
        self.assertEqual(res.get("numeric_price"), 2068000000.0)
        self.assertEqual(res.get("formatted_price"), "Rp 2,068,000,000")

        # Pastikan tidak ada balasan pesan "Tidak ada sesi identifikasi jam tangan yang aktif"
        mock_kirim_wa.assert_called()
        last_wa_msg = mock_kirim_wa.call_args[0][1]
        self.assertNotIn("Tidak ada sesi identifikasi", last_wa_msg)
        self.assertIn("LAPORAN REPRICE", last_wa_msg)
        self.assertIn("5846254/4664620", last_wa_msg)

    @patch("flask_app.kirim_balasan_wa")
    @patch("flask_app.update_shopify_takedown")
    @patch("flask_app.get_blogger_service")
    @patch("flask_app.find_blogger_post_by_code")
    @patch("flask_app.update_consignment_status_sheet")
    def test_transition_from_on_hold_to_sold_for_cpo_product(
        self, mock_sheet_status, mock_find_post, mock_get_blog, mock_shop_td, mock_kirim_wa
    ):
        chat_id = "test-group@g.us"
        sku = "CPO-091126-01"
        ACTIVE_IDENTIFIED_WATCHES.clear()

        # Blogspot post sudah di-trash sebelumnya saat on hold (sehingga find_post mengembalikan None)
        mock_get_blog.return_value = MagicMock()
        mock_find_post.return_value = None

        mock_shop_td.return_value = {
            "status": "success",
            "product_title": "PANTHÈRE S SILVER DIAL (2025)",
            "matched_sku": sku,
            "product_node": {
                "title": "PANTHÈRE S SILVER DIAL (2025)",
                "descriptionHtml": (
                    "CARTIER PANTHÈRE S SILVER DIAL<br>"
                    "Ref. WSPN0006<br>"
                    "Size 23mm x 30mm, Quartz Movement<br>"
                    "Box & Paper<br>"
                    "Warranty Until 2033<br>"
                    "Very Mint Condition"
                )
            }
        }
        mock_sheet_status.return_value = {
            "status": "success",
            "row": 1662,
            "tab_name": "PHOTO OWNER"
        }

        sold_payload = {
            "typeWebhook": "incomingMessageReceived",
            "idMessage": "msg-sold-cpo-transition",
            "senderData": {"chatId": chat_id, "senderName": "Dylan Baru"},
            "messageData": {
                "typeMessage": "textMessage",
                "textMessageData": {"textMessage": f"sold {sku}"}
            }
        }
        flask_app.request.get_json = MagicMock(return_value=sold_payload)

        res, code = wa_webhook()
        self.assertEqual(code, 200)
        self.assertEqual(res.get("command"), "SOLD")
        self.assertEqual(res.get("sku"), sku)
        self.assertEqual(res["spreadsheet_consignment_po"]["status"], "success")
        self.assertEqual(res["spreadsheet_consignment_po"]["row"], 1662)

        # Verifikasi teks pesan WhatsApp
        mock_kirim_wa.assert_called()
        last_wa_msg = mock_kirim_wa.call_args[0][1]
        self.assertIn("🏷️ *LAPORAN SOLD IDWX*", last_wa_msg)
        self.assertIn("CPO-091126-01", last_wa_msg)
        self.assertIn("✅ *Shopify:* PANTHÈRE S SILVER DIAL (2025)", last_wa_msg)
        self.assertIn("✅ *Blogspot:* Sudah di Sampah (Trash) sebelumnya", last_wa_msg)
        self.assertIn("✅ *Spreadsheet (Consignment PO):* Status diubah ke *Sold* (Baris 1662, Tab PHOTO OWNER)", last_wa_msg)
        self.assertNotIn("Spreadsheet:* Dilewati", last_wa_msg)
        self.assertIn("CARTIER PANTHÈRE S SILVER DIAL", last_wa_msg)
        self.assertIn("Ref. WSPN0006", last_wa_msg)

    @patch("requests.post")
    def test_bot_takedown_report_never_enters_photo_studio(self, mock_post):
        chat_id = "test-group@g.us"
        takedown_report_caption = (
            "🗑️ *LAPORAN TAKEDOWN IDWX*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🔢 *Kode / SKU:* 079\n"
            "👤 *Diupdate oleh:* Dylan Baru\n\n"
            "✅ *Shopify:* V32 BLUE TIFFANY (2026)\n"
            "   • Status: *DRAFT*\n"
            "   • Stock: *0*\n"
            "✅ *Blogspot:* Dipindahkan ke Sampah (Trash)\n"
            "   • Judul: [FOR SALE] FRANCK MULLER V32 BLUE TIFFANY (2026)\n"
            "   • Publish Date: 11 May 2026\n"
            "✅ *Spreadsheet (Consignment PS):* Status diubah ke *Takedown* (Baris 2262, Tab PHOTO STUDIO)\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "FRANCK MULLER V32 BLUE TIFFANY\n"
            "Ref. V32 SC AT FO AC13\n"
            "Size 32mm, Automatic Movement\n"
            "Box & Paper\n"
            "Warranty Until April 2028\n"
            "Never Been Worn Condition\n"
            "Price: Rp 88,000,000\n"
            "Code: 079"
        )
        photo_payload = {
            "typeWebhook": "incomingMessageReceived",
            "idMessage": "msg-takedown-report-001",
            "senderData": {
                "chatId": chat_id,
                "senderName": "Dylan Baru"
            },
            "messageData": {
                "typeMessage": "imageMessage",
                "fileMessageData": {
                    "downloadUrl": "https://example.com/franck_muller.jpg",
                    "caption": takedown_report_caption
                }
            }
        }
        flask_app.request.get_json = MagicMock(return_value=photo_payload)

        res, code = wa_webhook()
        self.assertEqual(code, 200)
        self.assertEqual(res.get("status"), "ignored")
        self.assertEqual(res.get("reason"), "Bot report or notification ignored")
        # Pastikan Apps Script History Foto Studio TIDAK PERNAH dipanggil!
        mock_post.assert_not_called()

    def test_is_valid_foto_studio_caption_validation(self):
        # Valid creative captions
        self.assertTrue(flask_app.is_valid_foto_studio_caption(
            "Lange 1 Time Zone, Aug 2008 / 172521 / Franky", "https://example.com/img.jpg"
        ))
        self.assertTrue(flask_app.is_valid_foto_studio_caption(
            "ROLEX DATEJUST 41 / 126333 / STAFF", "https://example.com/img.jpg"
        ))
        self.assertTrue(flask_app.is_valid_foto_studio_caption(
            "TAG HEUER CARRERA / CALIBRE 16", "https://example.com/img.jpg"
        ))

        # Invalid: Bot reports (Takedown, Sold, Reprice, Repost, Identifikasi)
        takedown_text = (
            "🗑️ *LAPORAN TAKEDOWN IDWX*\n━━━━━━━━━━━━━━━━━━\n🔢 *Kode / SKU:* 079\n👤 *Diupdate oleh:* Dylan Baru"
        )
        self.assertFalse(flask_app.is_valid_foto_studio_caption(takedown_text, "https://example.com/img.jpg"))

        sold_text = (
            "🏷️ *LAPORAN SOLD IDWX*\n━━━━━━━━━━━━━━━━━━\n🔢 *Kode / SKU:* 09R8215\n👤 *Diupdate oleh:* Dylan Baru"
        )
        self.assertFalse(flask_app.is_valid_foto_studio_caption(sold_text, "https://example.com/img.jpg"))

        identifikasi_text = (
            "⌚ *IDENTIFIKASI JAM TANGAN IDWX*\n━━━━━━━━━━━━━━━━━━\n📌 *Merek & Seri:* DATEJUST\n🔢 *Kode / SKU:* CPO-01"
        )
        self.assertFalse(flask_app.is_valid_foto_studio_caption(identifikasi_text, "https://example.com/img.jpg"))

        # Invalid: Multiline title before slash
        multiline_title = "Rolex Submariner\nYear 2020 / 123456 / John"
        self.assertFalse(flask_app.is_valid_foto_studio_caption(multiline_title, "https://example.com/img.jpg"))

        # Invalid: No image URL
        self.assertFalse(flask_app.is_valid_foto_studio_caption("Rolex Submariner / 123456", None))
        self.assertFalse(flask_app.is_valid_foto_studio_caption("Rolex Submariner / 123456", ""))

        # Invalid: Meeting / Chat messages
        self.assertFalse(flask_app.is_valid_foto_studio_caption("Meeting jam 2 / Zoom link", "https://example.com/img.jpg"))

    def test_register_sent_message_id_deduplication(self):
        test_id = "msg-unique-test-999"
        flask_app.register_sent_message_id(test_id)
        self.assertIn(test_id, flask_app.PROCESSED_MESSAGE_IDS)

        payload = {
            "typeWebhook": "incomingMessageReceived",
            "idMessage": test_id,
            "senderData": {"chatId": "test-group@g.us", "senderName": "Dylan Baru"},
            "messageData": {"typeMessage": "textMessage", "textMessageData": {"textMessage": "sold 123"}}
        }
        flask_app.request.get_json = MagicMock(return_value=payload)
        res, code = wa_webhook()
        self.assertEqual(code, 200)
        self.assertEqual(res.get("status"), "ignored")
        self.assertEqual(res.get("reason"), "Duplicate message ID")

if __name__ == "__main__":
    unittest.main()
