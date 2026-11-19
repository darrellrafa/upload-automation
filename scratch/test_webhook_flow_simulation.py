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
            "search_query": "Vacheron Constantin Historiques American 1921"
        }
        mock_shopify.return_value = {
            "title": "HISTORIQUES AMERICAN 1921 ROSEGOLD SILVER DIAL (2026)",
            "sku": "3012154",
            "numeric_price": 678000000.0,
            "formatted_price": "Rp 678,000,000",
            "product_node": {"id": "123", "title": "HISTORIQUES AMERICAN 1921"},
            "variant_node": {"sku": "3012154"}
        }
        mock_sheet.return_value = "ALL STOCK (Baris 313)"

        # 1. Staff sends watch photo without caption
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
                    "caption": ""
                }
            }
        }
        flask_app.request.get_json = MagicMock(return_value=photo_payload)

        res, code = wa_webhook()
        self.assertEqual(code, 200)
        self.assertEqual(res.get("status"), "success")
        self.assertEqual(res.get("action"), "identify_watch")

        # Verify active session stored
        self.assertIn(chat_id, ACTIVE_IDENTIFIED_WATCHES)
        self.assertEqual(ACTIVE_IDENTIFIED_WATCHES[chat_id]["sku"], "3012154")

        # Verify WA message sent to chat_id
        mock_kirim_wa.assert_called()
        last_wa_msg = mock_kirim_wa.call_args[0][1]
        self.assertIn("⌚ *IDENTIFIKASI JAM TANGAN IDWX*", last_wa_msg)
        self.assertIn("3012154", last_wa_msg)
        self.assertIn("• Ketik *abaikan* / *batal* jika tidak ada tindakan", last_wa_msg)

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
                    "caption": ""
                }
            }
        }
        flask_app.request.get_json = MagicMock(return_value=photo_payload)

        res, code = wa_webhook()
        self.assertEqual(code, 200)
        self.assertEqual(res.get("status"), "ignored")
        self.assertEqual(res.get("reason"), "Excluded chat/group for watch identification")
        mock_gemini.assert_not_called()

if __name__ == "__main__":
    unittest.main()
