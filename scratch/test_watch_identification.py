import sys
import os
import unittest
from unittest.mock import MagicMock

# Mock flask module if not installed locally
if "flask" not in sys.modules:
    flask_mock = MagicMock()
    app_instance = MagicMock()
    app_instance.route = lambda *args, **kwargs: (lambda f: f)
    flask_mock.Flask = MagicMock(return_value=app_instance)
    flask_mock.request = MagicMock()
    flask_mock.jsonify = lambda x: x
    sys.modules["flask"] = flask_mock

# Ensure current dir in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask_app import (
    parse_reprice_chat,
    parse_takedown_chat,
    is_cancellation_chat,
    is_chat_excluded_from_identification,
    extract_sku_from_quoted_message,
    format_watch_identification_message,
    ACTIVE_IDENTIFIED_WATCHES
)

class TestWatchIdentificationAndQuickReplies(unittest.TestCase):
    def test_excluded_group_for_identification(self):
        # Harus diabaikan
        self.assertTrue(is_chat_excluded_from_identification("62817626104-1627455181@g.us"))
        self.assertTrue(is_chat_excluded_from_identification("62817626104-1627455181"))
        self.assertTrue(is_chat_excluded_from_identification("62817626104-1627455181@c.us"))
        # Grup lain tidak boleh diabaikan
        self.assertFalse(is_chat_excluded_from_identification("120363000000000000@g.us"))
        self.assertFalse(is_chat_excluded_from_identification("628120000000@c.us"))
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
        self.assertIn("• Ketik *abaikan* / *batal* jika tidak ada tindakan", msg)

if __name__ == "__main__":
    unittest.main()
