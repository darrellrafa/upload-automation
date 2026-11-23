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

if __name__ == "__main__":
    unittest.main()
