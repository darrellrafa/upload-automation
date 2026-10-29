import re
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))

def parse_price(price_str):
    """
    Mengubah format harga string menjadi float angka:
    Contoh:
    '92.000.000' -> 92000000.0
    '92jt' -> 92000000.0
    'Rp 92.000.000' -> 92000000.0
    '92,5jt' -> 92500000.0
    '470.000.000' -> 470000000.0
    """
    clean = re.sub(r'[^\d,\.]', '', price_str.lower().replace('jt', '000000')).strip()
    if 'jt' in price_str.lower():
        # Handle like 92.5jt or 92jt
        m = re.search(r'([\d,\.]+)\s*jt', price_str.lower())
        if m:
            val_str = m.group(1).replace('.', '').replace(',', '.')
            return float(val_str) * 1_000_000
            
    # Standar angka rupiah dengan titik
    numeric_str = re.sub(r'[^\d]', '', price_str)
    if numeric_str:
        return float(numeric_str)
    return 0.0

def format_rupiah(num):
    return f"Rp {int(num):,}".replace(",", ".")

def parse_reprice_chat(message_text):
    """
    Memvalidasi dan mengekstrak perintah chat:
    1. REPRICE / [KODE] / [HARGA]
    2. HARGA BARU / [KODE] / [HARGA]
    """
    if not message_text or "/" not in message_text:
        return None
        
    parts = [p.strip() for p in message_text.split('/') if p.strip()]
    if len(parts) < 3:
        return None
        
    cmd = parts[0].upper().strip()
    if cmd not in ["REPRICE", "HARGA BARU", "HARGA_BARU"]:
        return None
        
    code = parts[1].strip()
    raw_price = parts[2].strip()
    
    numeric_price = parse_price(raw_price)
    if numeric_price <= 0:
        return None
        
    cmd_type = "REPRICE" if cmd == "REPRICE" else "HARGA_BARU"
    
    return {
        "command_type": cmd_type,
        "code": code,
        "raw_price": raw_price,
        "numeric_price": numeric_price,
        "formatted_price": format_rupiah(numeric_price)
    }

def update_blogger_content_and_labels(current_html, current_labels, command_type, formatted_price):
    """
    Memperbarui HTML konten dan labels Blogspot:
    - Labels: hapus 'NEW ARRIVAL', tambahkan 'REPRICE'
    - REPRICE: Price jadi strikethrough, tambah line Reprice: <b>Rp ...</b>
    - HARGA BARU: Price diganti bersih, hapus baris Reprice
    """
    # 1. Update Labels
    new_labels = [l for l in current_labels if l.strip().upper() != "NEW ARRIVAL"]
    if not any(l.strip().upper() == "REPRICE" for l in new_labels):
        new_labels.append("REPRICE")
        
    # Cek label consignment_ps
    is_consign_ps = any("CONSIGNMENT_PS" in l.upper() or "CONSINGMENT_PS" in l.upper() for l in current_labels)
    
    # 2. Update HTML Content
    updated_html = current_html
    
    # Pattern untuk mendeteksi baris Price
    # Contoh: Price: Rp 98,000,000 atau Price: Rp 98.000.000 atau Price: <strike>...</strike>
    price_pattern = r'(Price\s*:\s*)(.*?)(?=<br|</p|</div>|\n|$)'
    reprice_pattern = r'(?:<br\s*/?>|\n)?\s*Reprice\s*:\s*<b>.*?</b>'
    
    if command_type == "REPRICE":
        # Ambil harga lama jika ada
        m = re.search(price_pattern, updated_html, re.IGNORECASE)
        old_price_text = ""
        if m:
            raw_val = m.group(2)
            # Jika belum dicoret
            if "<strike>" not in raw_val.lower() and "<s>" not in raw_val.lower():
                old_price_text = raw_val.strip()
            else:
                # Sudah pernah dicoret sebelumnya, ambil teks dalam strike
                strike_m = re.search(r'<(?:strike|s)>(.*?)</(?:strike|s)>', raw_val, re.IGNORECASE)
                if strike_m:
                    old_price_text = strike_m.group(1).strip()
                    
        # Hapus baris reprice lama jika sudah ada
        updated_html = re.sub(reprice_pattern, '', updated_html, flags=re.IGNORECASE)
        
        # Ganti baris Price menjadi dicoret dan tambahkan Reprice di bawahnya
        if m:
            if old_price_text:
                replacement = f"Price: <strike>{old_price_text}</strike><br/>Reprice: <b>{formatted_price}</b>"
            else:
                replacement = f"Price: <strike>{formatted_price}</strike><br/>Reprice: <b>{formatted_price}</b>"
            updated_html = re.sub(price_pattern, replacement, updated_html, count=1, flags=re.IGNORECASE)
        else:
            # Jika tidak ada baris Price sebelumnya
            updated_html += f"<br/>Price: <strike>{formatted_price}</strike><br/>Reprice: <b>{formatted_price}</b>"
            
    else: # HARGA_BARU
        # Hapus baris reprice jika ada
        updated_html = re.sub(reprice_pattern, '', updated_html, flags=re.IGNORECASE)
        # Ganti baris Price menjadi bersih
        replacement = f"Price: {formatted_price}"
        if re.search(price_pattern, updated_html, re.IGNORECASE):
            updated_html = re.sub(price_pattern, replacement, updated_html, count=1, flags=re.IGNORECASE)
        else:
            updated_html += f"<br/>Price: {formatted_price}"
            
    return {
        "updated_html": updated_html,
        "new_labels": new_labels,
        "is_consign_ps": is_consign_ps
    }

# Test pengujian logic
if __name__ == "__main__":
    t1 = parse_reprice_chat("REPRICE / Y563525 / 92.000.000")
    print("Test 1 Chat:", t1)
    
    sample_html = "Ref. 16264<br/>Size 36mm<br/>Price: Rp 98.000.000<br/>Mint Condition"
    sample_labels = ["CONSIGNMENT_PS", "NEW ARRIVAL", "ROLEX"]
    
    res_reprice = update_blogger_content_and_labels(sample_html, sample_labels, t1["command_type"], t1["formatted_price"])
    print("\nResult REPRICE HTML:\n", res_reprice["updated_html"])
    print("Result Labels:\n", res_reprice["new_labels"])
    print("Is Consign PS:\n", res_reprice["is_consign_ps"])
    
    t2 = parse_reprice_chat("HARGA BARU / 0N3F4863 / 470.000.000")
    res_hargabaru = update_blogger_content_and_labels(res_reprice["updated_html"], res_reprice["new_labels"], t2["command_type"], t2["formatted_price"])
    print("\nResult HARGA BARU HTML:\n", res_hargabaru["updated_html"])
    print("Result Labels:\n", res_hargabaru["new_labels"])
