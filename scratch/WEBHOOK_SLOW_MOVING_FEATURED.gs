function doGet(e) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheets = ss.getSheets().map(function(s) { return s.getName(); });
  return ContentService.createTextOutput(JSON.stringify({
    "status": "active",
    "message": "Webhook Slow Moving Featured Apps Script is running (ALL STOCK ONLY)",
    "spreadsheet_name": ss.getName(),
    "available_tabs": sheets
  })).setMimeType(ContentService.MimeType.JSON);
}

function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return ContentService.createTextOutput(JSON.stringify({
        "status": "error",
        "message": "Empty post data"
      })).setMimeType(ContentService.MimeType.JSON);
    }

    var data = JSON.parse(e.postData.contents);

    // =========================================================================
    // HELPER: PEMETAAN KOLOM (MAPPING) TAB "ALL STOCK" (13 KOLOM)
    // =========================================================================
    // Layout Tab "ALL STOCK" (13 Kolom: A s/d M):
    // Col A (1) : Indikator Warna Cyan (Kosong)
    // Col B (2) : DATE (Tanggal)
    // Col C (3) : STATUS (DIBIARKAN TETAP KOSONG PADA SAAT UPLOAD JAM BARU!)
    // Col D (4) : NO (Nomor urut otomatis: 1, 2, 3...)
    // Col E (5) : OWNER (Nama Pemilik / Konsinyasi: AH, OMNI, ONELUXE, dll)
    // Col F (6) : BRAND (Merek: ROLEX, PATEK PHILIPPE, SEAMASTER, dll)
    // Col G (7) : DESCRIPTION (Deskripsi / Nama Jam)
    // Col H (8) : YEAR (Tahun / Tanggal Garansi)
    // Col I (9) : CONDITION (Kondisi: UNWORN, VERY MINT, WATCH ONLY, dll)
    // Col J (10): PRICE (Harga Angka numerik pemisah ribuan #,##0)
    // Col K (11): REFERENCE (Nomor Referensi Jam)
    // Col L (12): SERIAL NUMBER (SKU / Serial Number Jam)
    // Col M (13): LINK WEBSITE (URL Produk di Web dualtime.id)
    // =========================================================================
    function getSheetColumnMapping(sheet) {
      // Default layout tab ALL STOCK
      var mapping = {
        headerRow: 1,
        colIndicator: 1,  // A
        colDate: 2,       // B
        colStatus: 3,     // C (Wajib kosong saat upload)
        colNo: 4,         // D (Auto increment)
        colOwner: 5,      // E
        colBrand: 6,      // F
        colDesc: 7,       // G
        colYear: 8,       // H
        colCondition: 9,  // I
        colPrice: 10,     // J
        colReference: 11, // K
        colSerial: 12,    // L
        colLink: 13,      // M
        hasStatusCol: true,
        totalCols: 13
      };

      // Deteksi dinamis header baris 1 s/d 5 jika teks header tertera jelas
      var maxScanRows = Math.min(sheet.getLastRow(), 5);
      if (maxScanRows > 0) {
        var maxScanCols = Math.min(Math.max(sheet.getLastColumn(), 13), sheet.getMaxColumns());
        if (maxScanCols > 0) {
          var sampleRows = sheet.getRange(1, 1, maxScanRows, maxScanCols).getValues();
          for (var r = 0; r < sampleRows.length; r++) {
            var row = sampleRows[r];
            var matches = 0;
            var tempMap = {};
            for (var c = 0; c < row.length; c++) {
              var h = (row[c] || "").toString().trim().toUpperCase();
              if (h === "SERIAL NUMBER" || h === "SERIAL" || h === "SKU") { tempMap.colSerial = c + 1; matches++; }
              else if (h === "PRICE" || h === "HARGA") { tempMap.colPrice = c + 1; matches++; }
              else if (h === "STATUS") { tempMap.colStatus = c + 1; tempMap.hasStatusCol = true; matches++; }
              else if (h === "BRAND" || h === "BRAND/TYPE" || h === "MERK") { tempMap.colBrand = c + 1; matches++; }
              else if (h === "DESCRIPTION" || h === "DESKRIPSI" || h === "ITEM" || h === "NAMA BARANG") { tempMap.colDesc = c + 1; matches++; }
              else if (h === "OWNER" || h === "TITIP" || h === "NAMA TITIP") { tempMap.colOwner = c + 1; matches++; }
              else if (h === "DATE" || h === "TANGGAL") { tempMap.colDate = c + 1; matches++; }
              else if (h === "NO" || h === "NO." || h === "NOMOR") { tempMap.colNo = c + 1; matches++; }
              else if (h === "YEAR" || h === "TAHUN") { tempMap.colYear = c + 1; matches++; }
              else if (h === "CONDITION" || h === "KONDISI") { tempMap.colCondition = c + 1; matches++; }
              else if (h === "REFERENCE" || h === "REF" || h === "NO. REF") { tempMap.colReference = c + 1; matches++; }
              else if (h === "LINK WEBSITE" || h === "LINK" || h === "URL") { tempMap.colLink = c + 1; matches++; }
            }
            if (matches >= 3) {
              mapping.headerRow = r + 1;
              for (var k in tempMap) {
                mapping[k] = tempMap[k];
              }
              break;
            }
          }
        }
      }

      return mapping;
    }

    // =========================================================================
    // JALUR 1: REPRICE, HARGA BARU, ATAU UPDATE STATUS (HANYA TAB "ALL STOCK")
    // =========================================================================
    var isRepriceAction = (data.action === "reprice_slow_moving" || data.action === "reprice_featured");
    var isStatusAction = (data.action === "update_status_slow_moving" || data.action === "status_slow_moving" || data.action === "takedown_slow_moving" || data.action === "sold_slow_moving");

    if (isRepriceAction || isStatusAction) {
      var ss = SpreadsheetApp.getActiveSpreadsheet();

      // TARGET MUTLAK: HANYA tab "ALL STOCK" (Tidak mencari di NEW ARRIVAL)
      var targetTabName = "ALL STOCK";
      var currentSheet = ss.getSheetByName(targetTabName);

      if (!currentSheet) {
        return ContentService.createTextOutput(JSON.stringify({
          "status": "error",
          "message": "Tab 'ALL STOCK' tidak ditemukan di Spreadsheet ini."
        })).setMimeType(ContentService.MimeType.JSON);
      }

      var inputSku = (data.sku || "").toString().trim().toUpperCase();
      var canonicalSku = (data.canonical_sku || "").toString().trim().toUpperCase();
      var numericPrice = Number(data.numeric_price || 0);
      if (numericPrice <= 0) {
        var rawPriceVal = String(data.formatted_price || data.new_price || data.price || "").replace(/[^\d]/g, "");
        if (rawPriceVal) {
          numericPrice = Number(rawPriceVal);
        }
      }

      // Kumpulkan kandidat SKU (exact, base SKU, slash parts)
      var searchTerms = [];
      function addSearchTerm(val) {
        if (!val) return;
        var s = val.toString().trim().toUpperCase();
        if (s && searchTerms.indexOf(s) === -1) searchTerms.push(s);
        var base = s.replace(/-\d+$/, '').trim();
        if (base && searchTerms.indexOf(base) === -1) searchTerms.push(base);
        if (s.indexOf('/') !== -1) {
          var slashParts = s.split('/');
          for (var sp = 0; sp < slashParts.length; sp++) {
            var partClean = slashParts[sp].trim();
            if (partClean && searchTerms.indexOf(partClean) === -1) searchTerms.push(partClean);
          }
        }
      }
      addSearchTerm(inputSku);
      addSearchTerm(canonicalSku);

      var mapping = getSheetColumnMapping(currentSheet);
      var sheetValues = currentSheet.getDataRange().getValues();

      if (sheetValues.length <= mapping.headerRow) {
        return ContentService.createTextOutput(JSON.stringify({
          "status": "not_found",
          "message": "Tab 'ALL STOCK' tidak memiliki baris data."
        })).setMimeType(ContentService.MimeType.JSON);
      }

      var foundRow = -1;
      var foundSoldRow = -1; // Fallback jika baris berstatus SOLD namun ingin di-reprice
      var matchedCellSku = "";
      var matchedBrand = "";
      var matchedDesc = "";
      var oldPriceVal = "";
      var oldStatusVal = "";

      // Loop data dari baris terakhir ke atas agar mencocokkan data paling mutakhir
      for (var r = sheetValues.length - 1; r >= mapping.headerRow; r--) {
        var rowData = sheetValues[r];
        var statusCell = mapping.hasStatusCol && mapping.colStatus > 0 ? (rowData[mapping.colStatus - 1] || "").toString().trim().toUpperCase() : "";
        var serialCell = mapping.colSerial > 0 ? (rowData[mapping.colSerial - 1] || "").toString().trim().toUpperCase() : "";
        var refCell = mapping.colReference > 0 ? (rowData[mapping.colReference - 1] || "").toString().trim().toUpperCase() : "";

        var isMatch = false;

        if (serialCell) {
          // Level 1: Cocok persis
          for (var st = 0; st < searchTerms.length; st++) {
            if (serialCell === searchTerms[st]) {
              isMatch = true;
              break;
            }
          }

          // Level 2: Base SKU match (counter varian seperti 3012154 vs 3012154-1)
          if (!isMatch) {
            var cellBase = serialCell.replace(/-\d+$/, '').trim();
            for (var stB = 0; stB < searchTerms.length; stB++) {
              var termBase = searchTerms[stB].replace(/-\d+$/, '').trim();
              if (cellBase && termBase && cellBase === termBase) {
                isMatch = true;
                break;
              }
            }
          }

          // Level 3: Potongan garis miring (movement/case serial)
          if (!isMatch && (serialCell.indexOf('/') !== -1 || inputSku.indexOf('/') !== -1)) {
            var cellParts = serialCell.split('/');
            for (var cp = 0; cp < cellParts.length; cp++) {
              var cPart = cellParts[cp].trim();
              for (var st2 = 0; st2 < searchTerms.length; st2++) {
                if (cPart && cPart === searchTerms[st2]) {
                  isMatch = true;
                  break;
                }
              }
              if (isMatch) break;
            }
          }

          // Level 4: Normalized (abaikan spasi & simbol strip)
          if (!isMatch) {
            var normCell = serialCell.replace(/[^A-Z0-9]/g, "");
            var normInput = inputSku.replace(/[^A-Z0-9]/g, "");
            if (normCell && normInput && normCell === normInput) {
              isMatch = true;
            }
          }
        }

        // Fallback: jika Kolom Serial kosong / tidak cocok, coba cek Kolom Reference
        if (!isMatch && refCell) {
          for (var stR = 0; stR < searchTerms.length; stR++) {
            if (refCell === searchTerms[stR]) {
              isMatch = true;
              break;
            }
          }
        }

        if (isMatch) {
          // Jika aksi adalah REPRICE dan baris ini berstatus SOLD:
          // Simpan sebagai kandidat fallback (foundSoldRow), tetapi prioritaskan baris aktif jika ada
          if (isRepriceAction && statusCell === "SOLD") {
            if (foundSoldRow === -1) {
              foundSoldRow = r + 1;
            }
            continue;
          }

          foundRow = r + 1;
          matchedCellSku = serialCell || refCell;
          matchedBrand = mapping.colBrand > 0 ? (rowData[mapping.colBrand - 1] || "").toString().trim() : "";
          matchedDesc = mapping.colDesc > 0 ? (rowData[mapping.colDesc - 1] || "").toString().trim() : "";
          oldPriceVal = mapping.colPrice > 0 ? (rowData[mapping.colPrice - 1] || "").toString().trim() : "";
          oldStatusVal = statusCell;
          break; // Temukan baris aktif terbaik dan hentikan pencarian
        }
      }

      // Jika tidak ada baris aktif yang cocok, namun ada baris berstatus SOLD yang cocok saat REPRICE:
      // Gunakan baris SOLD tersebut (berarti jam aktif kembali dengan harga baru)
      if (foundRow === -1 && foundSoldRow !== -1 && isRepriceAction) {
        foundRow = foundSoldRow;
        var soldRowData = sheetValues[foundRow - 1];
        matchedCellSku = (mapping.colSerial > 0 ? soldRowData[mapping.colSerial - 1] : "") || "";
        matchedBrand = mapping.colBrand > 0 ? (soldRowData[mapping.colBrand - 1] || "").toString().trim() : "";
        matchedDesc = mapping.colDesc > 0 ? (soldRowData[mapping.colDesc - 1] || "").toString().trim() : "";
        oldPriceVal = mapping.colPrice > 0 ? (soldRowData[mapping.colPrice - 1] || "").toString().trim() : "";
        oldStatusVal = "SOLD";
      }

      if (foundRow === -1) {
        return ContentService.createTextOutput(JSON.stringify({
          "status": "not_found",
          "message": "SKU '" + data.sku + "' tidak ditemukan di tab ALL STOCK"
        })).setMimeType(ContentService.MimeType.JSON);
      }

      var newStatusApplied = oldStatusVal;

      // 1. Eksekusi jika Aksi REPRICE / HARGA BARU
      if (isRepriceAction) {
        // Pada Spreadsheet Slow Moving (Tab ALL STOCK):
        // Update nilai pada Kolom J (PRICE) dengan format ribuan #,##0
        if (mapping.colPrice > 0 && numericPrice > 0) {
          currentSheet.getRange(foundRow, mapping.colPrice).setValue(numericPrice);
          currentSheet.getRange(foundRow, mapping.colPrice).setNumberFormat("#,##0");
        }

        // Tulis "REPRICE" di Kolom C (STATUS) jika ada kolom STATUS
        var rawCmdType = (data.command_type || "").toString().trim().toUpperCase();
        if (mapping.hasStatusCol && mapping.colStatus > 0) {
          newStatusApplied = "REPRICE";
          currentSheet.getRange(foundRow, mapping.colStatus).setValue(newStatusApplied);
        }

        // Reset fill color merah (Kolom D sampai L) agar kembali normal karena jam aktif dijual kembali
        try {
          var startCol = 4; // Kolom D
          var endCol = 12;  // Kolom L
          var numCols = (endCol - startCol + 1); // 9 kolom (D s/d L)
          currentSheet.getRange(foundRow, startCol, 1, numCols).setBackground(null);
        } catch (eColor) {
          // Abaikan jika gagal reset warna
        }
      }

      // 2. Eksekusi jika Aksi UPDATE STATUS (SOLD / ON HOLD / TAKEDOWN)
      var fillApplied = false;
      if (isStatusAction && mapping.hasStatusCol && mapping.colStatus > 0) {
        newStatusApplied = (data.status_text || "SOLD").toString().trim().toUpperCase();
        currentSheet.getRange(foundRow, mapping.colStatus).setValue(newStatusApplied);

        // Jika status SOLD atau ON HOLD pada tab ALL STOCK: Atur fill color Kolom D sampai L (kolom 4 s/d 12) menjadi merah
        if (newStatusApplied === "SOLD" || newStatusApplied === "ON HOLD" || newStatusApplied === "HOLD") {
          var startCol = 4; // Kolom D
          var endCol = 12;  // Kolom L
          var numCols = (endCol - startCol + 1); // 9 kolom (D, E, F, G, H, I, J, K, L)
          currentSheet.getRange(foundRow, startCol, 1, numCols).setBackground("#ea4335");
          fillApplied = true;
        }
      }

      return ContentService.createTextOutput(JSON.stringify({
        "status": "success",
        "action": data.action,
        "tab_name": currentSheet.getName(),
        "row": foundRow,
        "sku": matchedCellSku,
        "brand": matchedBrand,
        "description": matchedDesc,
        "old_price": oldPriceVal,
        "new_price": numericPrice,
        "old_status": oldStatusVal,
        "new_status": newStatusApplied,
        "formatted_price": data.formatted_price,
        "fill_color": fillApplied ? "red (#ea4335) applied to Col D-L" : "none"
      })).setMimeType(ContentService.MimeType.JSON);
    }

    // =========================================================================
    // JALUR 2: INPUT JAM BARU (Upload Otomatis Khusus Featured -> Tab "ALL STOCK")
    // =========================================================================
    var targetTabName = "ALL STOCK";
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(targetTabName); 
    
    if (!sheet) {
      throw new Error("Tab 'ALL STOCK' tidak ditemukan di Spreadsheet ini.");
    }

    var mapping = getSheetColumnMapping(sheet);

    // Pastikan sheet memiliki jumlah kolom minimal 13 kolom
    if (sheet.getMaxColumns() < mapping.totalCols) {
      sheet.insertColumnsAfter(sheet.getMaxColumns(), mapping.totalCols - sheet.getMaxColumns());
    }

    // Konversi harga ke angka numerik murni
    var rawPrice = String(data.price || "").replace(/[^\d]/g, "");
    var numericPriceInput = rawPrice ? Number(rawPrice) : 0;

    // Cari baris terakhir yang terisi (gunakan kolom BRAND atau DESCRIPTION)
    var lastRow = sheet.getLastRow();
    var insertRow = lastRow + 1;
    if (lastRow > 1) {
      var checkCol = mapping.colBrand > 0 ? mapping.colBrand : (mapping.colDesc > 0 ? mapping.colDesc : 2);
      if (checkCol <= sheet.getLastColumn()) {
        var colVals = sheet.getRange(1, checkCol, lastRow, 1).getValues();
        for (var r = colVals.length - 1; r >= 0; r--) {
          if ((colVals[r][0] || "").toString().trim() !== "") {
            insertRow = r + 2;
            break;
          }
        }
      }
    }

    // Proteksi duplikasi: Jika serial_number sudah pernah ada di sheet ALL STOCK, update baris tersebut
    var existingRow = -1;
    var searchSerial = (data.serial_number || "").toString().trim().toUpperCase();
    var cleanSearchBase = searchSerial.replace(/-\d+$/, '').trim();

    if (searchSerial.length >= 2 && mapping.colSerial > 0 && lastRow > 1) {
      var serialList = sheet.getRange(1, mapping.colSerial, lastRow, 1).getValues();
      for (var sRow = serialList.length - 1; sRow >= 1; sRow--) {
        var cellSerial = (serialList[sRow][0] || "").toString().trim().toUpperCase();
        if (!cellSerial) continue;
        var cleanCellBase = cellSerial.replace(/-\d+$/, '').trim();
        if (cellSerial === searchSerial || (cleanSearchBase && cleanCellBase === cleanSearchBase)) {
          existingRow = sRow + 1;
          break;
        }
      }
    }

    var targetRow = (existingRow > 0) ? existingRow : insertRow;
    var actionMessage = (existingRow > 0) ? ("Diperbarui di baris " + targetRow) : ("Tersimpan rapi di baris " + targetRow);

    // Pastikan sheet memiliki baris yang cukup untuk targetRow (cegah error Range out of bounds)
    if (targetRow > sheet.getMaxRows()) {
      var rowsToAdd = (targetRow - sheet.getMaxRows()) + 10;
      sheet.insertRowsAfter(sheet.getMaxRows(), rowsToAdd);
    }

    // Buat susunan data sesuai pemetaan kolom
    var rowData = new Array(mapping.totalCols);
    for (var i = 0; i < rowData.length; i++) {
      rowData[i] = "";
    }

    // 1. Indikator Kolom A
    if (mapping.colIndicator > 0) {
      rowData[mapping.colIndicator - 1] = "";
    }

    // 2. Tanggal (Kolom B di ALL STOCK)
    if (mapping.colDate > 0) {
      rowData[mapping.colDate - 1] = data.date || "";
    }

    // 3. STATUS (Kolom C di ALL STOCK)
    // ATURAN KHUSUS: Kolom C (STATUS) DIBIARKAN TETAP KOSONG ("") PADA SAAT PROSES UPLOAD!
    if (mapping.colStatus > 0) {
      if (existingRow > 0) {
        // Jika hanya update baris lama yang sudah ada statusnya, pertahankan status sebelumnya
        rowData[mapping.colStatus - 1] = sheet.getRange(existingRow, mapping.colStatus).getValue();
      } else {
        // Jika jam baru di-upload: WAJIB KOSONG ("")
        rowData[mapping.colStatus - 1] = "";
      }
    }

    // 4. NO (Nomor urut: Kolom D di ALL STOCK)
    if (mapping.colNo > 0) {
      if (existingRow > 0) {
        // Pertahankan nomor urut lama jika update
        rowData[mapping.colNo - 1] = sheet.getRange(existingRow, mapping.colNo).getValue();
      } else {
        // Ambil nomor baris sebelumnya + 1
        var nextNo = 1;
        if (targetRow > 2) {
          var prevNo = sheet.getRange(targetRow - 1, mapping.colNo).getValue();
          if (typeof prevNo === 'number' && prevNo > 0) {
            nextNo = prevNo + 1;
          } else if (parseInt(prevNo, 10) > 0) {
            nextNo = parseInt(prevNo, 10) + 1;
          }
        }
        rowData[mapping.colNo - 1] = nextNo;
      }
    }

    // 5. OWNER (Kolom E di ALL STOCK)
    if (mapping.colOwner > 0) {
      rowData[mapping.colOwner - 1] = data.owner || "";
    }

    // 6. BRAND (Kolom F di ALL STOCK)
    if (mapping.colBrand > 0) {
      rowData[mapping.colBrand - 1] = data.brand || "";
    }

    // 7. DESCRIPTION (Kolom G di ALL STOCK)
    if (mapping.colDesc > 0) {
      rowData[mapping.colDesc - 1] = data.description || "";
    }

    // 8. YEAR (Kolom H di ALL STOCK)
    if (mapping.colYear > 0) {
      rowData[mapping.colYear - 1] = data.year || "";
    }

    // 9. CONDITION (Kolom I di ALL STOCK)
    if (mapping.colCondition > 0) {
      rowData[mapping.colCondition - 1] = data.condition || "";
    }

    // 10. PRICE (Kolom J di ALL STOCK)
    if (mapping.colPrice > 0) {
      rowData[mapping.colPrice - 1] = numericPriceInput > 0 ? numericPriceInput : (data.price || "");
    }

    // 11. REFERENCE (Kolom K di ALL STOCK)
    if (mapping.colReference > 0) {
      rowData[mapping.colReference - 1] = data.reference || "";
    }

    // 12. SERIAL NUMBER (Kolom L di ALL STOCK)
    if (mapping.colSerial > 0) {
      rowData[mapping.colSerial - 1] = data.serial_number || "";
    }

    // 13. LINK WEBSITE (Kolom M di ALL STOCK)
    if (mapping.colLink > 0) {
      rowData[mapping.colLink - 1] = data.link || "";
    }

    // Copy Format & Validasi data dari baris di atasnya (hanya jika baris baru)
    if (existingRow <= 0 && targetRow > 2) {
      var prevRow = targetRow - 1;
      var numColsToCopy = Math.min(sheet.getLastColumn(), rowData.length);
      var rangeToCopy = sheet.getRange(prevRow, 1, 1, numColsToCopy);
      var targetRange = sheet.getRange(targetRow, 1, 1, numColsToCopy);
      
      try {
        rangeToCopy.copyTo(targetRange, SpreadsheetApp.CopyPasteType.PASTE_FORMAT, false);
        rangeToCopy.copyTo(targetRange, SpreadsheetApp.CopyPasteType.PASTE_DATA_VALIDATION, false);
      } catch (errCopy) {
        // Abaikan jika tidak ada validasi khusus
      }

      // PENTING: Bersihkan background color dari format copy agar TIDAK mewarisi warna merah SOLD/ON HOLD
      try {
        targetRange.setBackground(null);
        // Pertahankan warna background indikator di Kolom A jika ada
        if (mapping.colIndicator > 0) {
          var prevBgA = sheet.getRange(prevRow, mapping.colIndicator).getBackground();
          if (prevBgA && prevBgA !== "#ffffff") {
            sheet.getRange(targetRow, mapping.colIndicator).setBackground(prevBgA);
          }
        }
      } catch (errBg) {
        // Abaikan jika gagal reset background
      }
    }
    
    // Tulis data ke Sheet
    sheet.getRange(targetRow, 1, 1, rowData.length).setValues([rowData]);

    // Format kolom DATE sebagai Plain Text agar tanggal tidak tertukar
    if (mapping.colDate > 0) {
      try {
        sheet.getRange(targetRow, mapping.colDate).setNumberFormat("@");
      } catch (eDateFmt) {}
    }

    // Format kolom PRICE dengan format pemisah ribuan (#,##0)
    if (mapping.colPrice > 0 && numericPriceInput > 0) {
      sheet.getRange(targetRow, mapping.colPrice).setNumberFormat("#,##0");
    }
    
    return ContentService.createTextOutput(JSON.stringify({
      "status": "success", 
      "message": actionMessage + " (Tab " + targetTabName + ")",
      "tab_name": targetTabName,
      "row": targetRow,
      "sku": searchSerial,
      "brand": data.brand || "",
      "price": numericPriceInput,
      "is_updated": (existingRow > 0)
    })).setMimeType(ContentService.MimeType.JSON);
      
  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({
      "status": "error", 
      "message": error.message
    })).setMimeType(ContentService.MimeType.JSON);
  }
}
