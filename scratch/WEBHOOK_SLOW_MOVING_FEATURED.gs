function doGet(e) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheets = ss.getSheets().map(function(s) { return s.getName(); });
  return ContentService.createTextOutput(JSON.stringify({
    "status": "active",
    "message": "Webhook Slow Moving Featured Apps Script is running",
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
    // HELPER: PEMETAAN KOLOM (MAPPING) BERDASARKAN TAB & DETEKSI HEADER
    // =========================================================================
    // Layout Tab "ALL STOCK" (13 Kolom: A s/d M):
    // Col A (1) : Indikator Warna Cyan (Kosong)
    // Col B (2) : DATE (Tanggal)
    // Col C (3) : STATUS (DIBIARKAN TETAP KOSONG PADA SAAT UPLOAD!)
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
      var sheetName = sheet.getName();
      var isAllStock = (sheetName === "ALL STOCK");

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

      if (!isAllStock) {
        // Fallback untuk tab NEW ARRIVAL (Layout lama 10 kolom)
        mapping = {
          headerRow: 1,
          colIndicator: -1,
          colDate: 1,       // A
          colStatus: -1,
          colNo: -1,
          colOwner: 2,      // B
          colBrand: 3,      // C
          colDesc: 4,       // D
          colYear: 5,       // E
          colCondition: 6,  // F
          colPrice: 7,      // G
          colReference: 8,  // H
          colSerial: 9,     // I
          colLink: 10,      // J
          hasStatusCol: false,
          totalCols: 10
        };
      }

      // Deteksi dinamis header baris 1 s/d 5 jika teks header tertera jelas
      var maxScanRows = Math.min(sheet.getLastRow(), 5);
      if (maxScanRows > 0) {
        var sampleRows = sheet.getRange(1, 1, maxScanRows, Math.max(sheet.getLastColumn(), 13)).getValues();
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

      return mapping;
    }

    // =========================================================================
    // JALUR 1: REPRICE, HARGA BARU, ATAU UPDATE STATUS (SOLD / ON HOLD / TAKEDOWN)
    // =========================================================================
    var isRepriceAction = (data.action === "reprice_slow_moving" || data.action === "reprice_featured");
    var isStatusAction = (data.action === "update_status_slow_moving" || data.action === "status_slow_moving" || data.action === "takedown_slow_moving" || data.action === "sold_slow_moving");

    if (isRepriceAction || isStatusAction) {
      var ss = SpreadsheetApp.getActiveSpreadsheet();

      // Prioritas pencarian: Cek tab "ALL STOCK" terlebih dahulu, lalu "NEW ARRIVAL"
      var targetTabNames = ["ALL STOCK", "NEW ARRIVAL"];
      var candidateSheets = [];
      for (var t = 0; t < targetTabNames.length; t++) {
        var s = ss.getSheetByName(targetTabNames[t]);
        if (s) {
          candidateSheets.push(s);
        }
      }

      if (candidateSheets.length === 0) {
        return ContentService.createTextOutput(JSON.stringify({
          "status": "error",
          "message": "Tab 'ALL STOCK' maupun 'NEW ARRIVAL' tidak ditemukan di Spreadsheet ini."
        })).setMimeType(ContentService.MimeType.JSON);
      }

      var inputSku = (data.sku || "").toString().trim().toUpperCase();
      var canonicalSku = (data.canonical_sku || "").toString().trim().toUpperCase();
      var numericPrice = Number(data.numeric_price || 0);

      // Kumpulkan kandidat SKU (termasuk serial ganda dengan garis miring /)
      var searchTerms = [];
      if (inputSku) searchTerms.push(inputSku);
      if (canonicalSku && searchTerms.indexOf(canonicalSku) === -1) searchTerms.push(canonicalSku);

      if (inputSku.indexOf('/') !== -1) {
        var slashParts = inputSku.split('/');
        for (var sp = 0; sp < slashParts.length; sp++) {
          var partClean = slashParts[sp].trim();
          if (partClean && searchTerms.indexOf(partClean) === -1) {
            searchTerms.push(partClean);
          }
        }
      }

      var foundSheet = null;
      var foundRow = -1;
      var matchedCellSku = "";
      var matchedBrand = "";
      var matchedDesc = "";
      var oldPriceVal = "";
      var oldStatusVal = "";
      var matchedMapping = null;

      // Cari di tab ALL STOCK terlebih dahulu
      for (var sIdx = 0; sIdx < candidateSheets.length; sIdx++) {
        var currentSheet = candidateSheets[sIdx];
        var mapping = getSheetColumnMapping(currentSheet);
        var sheetValues = currentSheet.getDataRange().getValues();
        if (sheetValues.length <= mapping.headerRow) continue;

        // Loop data dari baris terakhir ke atas agar mencocokkan data paling mutakhir
        for (var r = sheetValues.length - 1; r >= mapping.headerRow; r--) {
          var rowData = sheetValues[r];
          var statusCell = mapping.hasStatusCol && mapping.colStatus > 0 ? (rowData[mapping.colStatus - 1] || "").toString().trim().toUpperCase() : "";
          var serialCell = mapping.colSerial > 0 ? (rowData[mapping.colSerial - 1] || "").toString().trim().toUpperCase() : "";

          // Jika aksi adalah REPRICE, lewati yang statusnya sudah SOLD
          if (isRepriceAction && statusCell === "SOLD") continue;

          var isMatch = false;
          if (serialCell) {
            // Level 1: Cocok persis
            for (var st = 0; st < searchTerms.length; st++) {
              if (serialCell === searchTerms[st]) {
                isMatch = true;
                break;
              }
            }

            // Level 2: Potongan garis miring (movement/case serial)
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

            // Level 3: Normalized (abaikan spasi & simbol strip)
            if (!isMatch) {
              var normCell = serialCell.replace(/[^A-Z0-9]/g, "");
              var normInput = inputSku.replace(/[^A-Z0-9]/g, "");
              if (normCell && normCell === normInput) {
                isMatch = true;
              }
            }
          }

          if (isMatch) {
            foundSheet = currentSheet;
            foundRow = r + 1;
            matchedCellSku = serialCell;
            matchedBrand = mapping.colBrand > 0 ? (rowData[mapping.colBrand - 1] || "").toString().trim() : "";
            matchedDesc = mapping.colDesc > 0 ? (rowData[mapping.colDesc - 1] || "").toString().trim() : "";
            oldPriceVal = mapping.colPrice > 0 ? (rowData[mapping.colPrice - 1] || "").toString().trim() : "";
            oldStatusVal = statusCell;
            matchedMapping = mapping;
            break;
          }
        }

        if (foundRow !== -1) {
          break; // Stop jika sudah ketemu di tab prioritas pertama
        }
      }

      if (foundRow === -1) {
        return ContentService.createTextOutput(JSON.stringify({
          "status": "not_found",
          "message": "SKU '" + data.sku + "' tidak ditemukan di tab ALL STOCK maupun NEW ARRIVAL" + (isRepriceAction ? " (atau berstatus SOLD)" : "")
        })).setMimeType(ContentService.MimeType.JSON);
      }

      var newStatusApplied = oldStatusVal;

      // 1. Eksekusi jika Aksi REPRICE / HARGA BARU
      if (isRepriceAction && matchedMapping) {
        if (matchedMapping.colPrice > 0 && numericPrice > 0) {
          foundSheet.getRange(foundRow, matchedMapping.colPrice).setValue(numericPrice);
          foundSheet.getRange(foundRow, matchedMapping.colPrice).setNumberFormat("#,##0");
        }

        // Tulis "REPRICE" di kolom Status jika ada kolom STATUS
        if (matchedMapping.hasStatusCol && matchedMapping.colStatus > 0 && data.command_type === "REPRICE") {
          newStatusApplied = "REPRICE";
          foundSheet.getRange(foundRow, matchedMapping.colStatus).setValue(newStatusApplied);
        }
      }

      // 2. Eksekusi jika Aksi UPDATE STATUS (SOLD / ON HOLD / TAKEDOWN)
      if (isStatusAction && matchedMapping && matchedMapping.hasStatusCol && matchedMapping.colStatus > 0) {
        newStatusApplied = (data.status_text || "SOLD").toString().trim().toUpperCase();
        foundSheet.getRange(foundRow, matchedMapping.colStatus).setValue(newStatusApplied);
      }

      return ContentService.createTextOutput(JSON.stringify({
        "status": "success",
        "action": data.action,
        "tab_name": foundSheet.getName(),
        "row": foundRow,
        "sku": matchedCellSku,
        "brand": matchedBrand,
        "description": matchedDesc,
        "old_price": oldPriceVal,
        "new_price": numericPrice,
        "old_status": oldStatusVal,
        "new_status": newStatusApplied,
        "formatted_price": data.formatted_price
      })).setMimeType(ContentService.MimeType.JSON);
    }

    // =========================================================================
    // JALUR 2: INPUT JAM BARU (Upload Otomatis Dari Blogspot -> Tab "ALL STOCK")
    // =========================================================================
    var targetTabName = "ALL STOCK";
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(targetTabName); 
    
    // Fallback otomatis ke NEW ARRIVAL jika tab ALL STOCK belum ada
    if (!sheet) {
      sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("NEW ARRIVAL");
      if (sheet) {
        targetTabName = "NEW ARRIVAL";
      }
    }

    if (!sheet) {
      throw new Error("Tab 'ALL STOCK' maupun 'NEW ARRIVAL' tidak ditemukan di Spreadsheet ini.");
    }

    var mapping = getSheetColumnMapping(sheet);

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

    // Proteksi duplikasi: Jika serial_number sudah pernah ada di sheet, update baris tersebut
    var existingRow = -1;
    var searchSerial = (data.serial_number || "").toString().trim().toUpperCase();
    if (searchSerial && mapping.colSerial > 0 && lastRow > 1) {
      var serialList = sheet.getRange(1, mapping.colSerial, lastRow, 1).getValues();
      for (var sRow = serialList.length - 1; sRow >= 1; sRow--) {
        var cellSerial = (serialList[sRow][0] || "").toString().trim().toUpperCase();
        if (cellSerial === searchSerial) {
          existingRow = sRow + 1;
          break;
        }
      }
    }

    var targetRow = (existingRow > 0) ? existingRow : insertRow;
    var actionMessage = (existingRow > 0) ? ("Diperbarui di baris " + targetRow) : ("Tersimpan rapi di baris " + targetRow);

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
    }
    
    // Tulis data ke Sheet
    sheet.getRange(targetRow, 1, 1, rowData.length).setValues([rowData]);

    // Format kolom PRICE dengan format pemisah ribuan (#,##0)
    if (mapping.colPrice > 0 && numericPriceInput > 0) {
      sheet.getRange(targetRow, mapping.colPrice).setNumberFormat("#,##0");
    }
    
    return ContentService.createTextOutput(JSON.stringify({
      "status": "success", 
      "message": actionMessage + " (Tab " + targetTabName + ")",
      "tab_name": targetTabName,
      "row": targetRow,
      "is_updated": (existingRow > 0)
    })).setMimeType(ContentService.MimeType.JSON);
      
  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({
      "status": "error", 
      "message": error.message
    })).setMimeType(ContentService.MimeType.JSON);
  }
}
