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
    // JALUR 1: REPRICE / HARGA BARU (Khusus Item FEATURED dari Bot WA)
    // =========================================================================
    if (data.action === "reprice_slow_moving" || data.action === "reprice_featured") {
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
      var colPriceIndex = 9;   // Default Kolom I (PRICE)
      var colStatusIndex = 2;  // Default Kolom B (STATUS)
      var hasStatusCol = false;

      // Cari di antara tab: ALL STOCK atau NEW ARRIVAL
      for (var sIdx = 0; sIdx < candidateSheets.length; sIdx++) {
        var currentSheet = candidateSheets[sIdx];
        var sheetValues = currentSheet.getDataRange().getValues();
        if (sheetValues.length <= 1) continue;

        // Deteksi posisi kolom otomatis dari Baris 1 (Header)
        var headers = sheetValues[0];
        var colSerial = 11; // Default K
        var colPrice = 9;   // Default I
        var colStatus = 2;  // Default B
        var colBrand = 3;   // Default C (BRAND)
        var colDesc = 4;    // Default D (DESCRIPTION)
        var foundStatus = false;

        for (var h = 0; h < headers.length; h++) {
          var headerText = (headers[h] || "").toString().trim().toUpperCase();
          if (headerText === "SERIAL NUMBER" || headerText === "SERIAL" || headerText === "SKU") {
            colSerial = h + 1;
          } else if (headerText === "PRICE" || headerText === "HARGA") {
            colPrice = h + 1;
          } else if (headerText === "STATUS") {
            colStatus = h + 1;
            foundStatus = true;
          } else if (headerText === "BRAND" || headerText === "BRAND/TYPE" || headerText === "MERK") {
            colBrand = h + 1;
          } else if (headerText === "DESCRIPTION" || headerText === "DESKRIPSI" || headerText === "ITEM" || headerText === "NAMA BARANG") {
            colDesc = h + 1;
          }
        }

        // Loop data dari baris ke-2 (lewati header)
        for (var r = 1; r < sheetValues.length; r++) {
          var rowData = sheetValues[r];
          var statusCell = foundStatus ? (rowData[colStatus - 1] || "").toString().trim().toUpperCase() : "";
          var serialCell = (rowData[colSerial - 1] || "").toString().trim().toUpperCase();

          // Lewati jika status SOLD
          if (statusCell === "SOLD") continue;

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
                for (var st = 0; st < searchTerms.length; st++) {
                  if (cPart && cPart === searchTerms[st]) {
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
            matchedBrand = (rowData[colBrand - 1] || rowData[2] || "").toString().trim();
            matchedDesc = (rowData[colDesc - 1] || rowData[3] || "").toString().trim();
            oldPriceVal = (rowData[colPrice - 1] || "").toString().trim();
            colPriceIndex = colPrice;
            colStatusIndex = colStatus;
            hasStatusCol = foundStatus;
            break;
          }
        }

        if (foundRow !== -1) {
          break; // Stop jika sudah ketemu
        }
      }

      if (foundRow === -1) {
        return ContentService.createTextOutput(JSON.stringify({
          "status": "not_found",
          "message": "SKU '" + data.sku + "' tidak ditemukan di tab ALL STOCK maupun NEW ARRIVAL (atau berstatus SOLD)"
        })).setMimeType(ContentService.MimeType.JSON);
      }

      // 1. Update Harga Baru di Kolom PRICE
      foundSheet.getRange(foundRow, colPriceIndex).setValue(numericPrice);
      foundSheet.getRange(foundRow, colPriceIndex).setNumberFormat("#,##0");

      // 2. Update Status menjadi 'REPRICE' (jika ada kolom STATUS dan perintah REPRICE)
      if (hasStatusCol && data.command_type === "REPRICE") {
        foundSheet.getRange(foundRow, colStatusIndex).setValue("REPRICE");
      }

      return ContentService.createTextOutput(JSON.stringify({
        "status": "success",
        "tab_name": foundSheet.getName(),
        "row": foundRow,
        "sku": matchedCellSku,
        "brand": matchedBrand,
        "description": matchedDesc,
        "old_price": oldPriceVal,
        "new_price": numericPrice,
        "formatted_price": data.formatted_price
      })).setMimeType(ContentService.MimeType.JSON);
    }

    // =========================================================================
    // JALUR 2: INPUT JAM BARU (Upload Otomatis Dari Blogspot -> Tab "ALL STOCK")
    // =========================================================================
    var targetTabName = "ALL STOCK";
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(targetTabName); 
    
    // Fallback otomatis jika tab ALL STOCK belum dibuat
    if (!sheet) {
      sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("NEW ARRIVAL");
      if (sheet) {
        targetTabName = "NEW ARRIVAL";
      }
    }

    if (!sheet) {
      throw new Error("Tab 'ALL STOCK' maupun 'NEW ARRIVAL' tidak ditemukan di Spreadsheet ini.");
    }
    
    // Konversi harga ke angka numerik murni
    var rawPrice = String(data.price || "").replace(/[^\d]/g, "");
    var numericPriceInput = rawPrice ? Number(rawPrice) : 0;

    // Baca header baris 1 untuk pemetaan kolom otomatis
    var lastCol = Math.max(sheet.getLastColumn(), 10);
    var headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0];
    var rowData = new Array(headers.length);
    var hasMappedHeader = false;
    var priceColIndex = -1;

    for (var h = 0; h < headers.length; h++) {
      var headerText = (headers[h] || "").toString().trim().toUpperCase();
      if (headerText === "DATE" || headerText === "TANGGAL") {
        rowData[h] = data.date || "";
        hasMappedHeader = true;
      } else if (headerText === "STATUS") {
        rowData[h] = "Available";
        hasMappedHeader = true;
      } else if (headerText === "OWNER" || headerText === "TITIP" || headerText === "NAMA TITIP") {
        rowData[h] = data.owner || "";
        hasMappedHeader = true;
      } else if (headerText === "BRAND" || headerText === "BRAND/TYPE" || headerText === "MERK") {
        rowData[h] = data.brand || "";
        hasMappedHeader = true;
      } else if (headerText === "DESCRIPTION" || headerText === "DESKRIPSI" || headerText === "ITEM" || headerText === "NAMA BARANG") {
        rowData[h] = data.description || "";
        hasMappedHeader = true;
      } else if (headerText === "YEAR" || headerText === "TAHUN") {
        rowData[h] = data.year || "";
        hasMappedHeader = true;
      } else if (headerText === "CONDITION" || headerText === "KONDISI") {
        rowData[h] = data.condition || "";
        hasMappedHeader = true;
      } else if (headerText === "PRICE" || headerText === "HARGA") {
        rowData[h] = numericPriceInput > 0 ? numericPriceInput : (data.price || "");
        priceColIndex = h + 1;
        hasMappedHeader = true;
      } else if (headerText === "REFERENCE" || headerText === "REF" || headerText === "NO. REF") {
        rowData[h] = data.reference || "";
        hasMappedHeader = true;
      } else if (headerText === "SERIAL NUMBER" || headerText === "SERIAL" || headerText === "SKU") {
        rowData[h] = data.serial_number || "";
        hasMappedHeader = true;
      } else if (headerText === "LINK WEBSITE" || headerText === "LINK" || headerText === "URL") {
        rowData[h] = data.link || "";
        hasMappedHeader = true;
      } else {
        rowData[h] = "";
      }
    }

    // Jika header tidak dikenali, gunakan susunan kolom default (A s/d J)
    if (!hasMappedHeader) {
      rowData = [
        data.date,                              // A: DATE 
        data.owner,                             // B: OWNER
        data.brand,                             // C: BRAND/TYPE 
        data.description,                       // D: DESCRIPTION
        data.year,                              // E: YEAR
        data.condition,                         // F: CONDITION
        numericPriceInput > 0 ? numericPriceInput : data.price, // G: PRICE
        data.reference,                         // H: REFERENCE
        data.serial_number,                     // I: SERIAL NUMBER
        data.link                               // J: LINK WEBSITE
      ];
      priceColIndex = 7;
    }
    
    // Cari baris terakhir yang terisi (cepat & efisien tanpa scan sel kosong)
    var lastRow = sheet.getLastRow();
    var insertRow = lastRow + 1;
    if (lastRow > 1) {
      var checkCol = 3; // Kolom Brand/Type
      if (checkCol <= sheet.getLastColumn()) {
        var colVals = sheet.getRange(1, checkCol, lastRow, 1).getValues();
        for (var r = colVals.length - 1; r >= 0; r--) {
          if (colVals[r][0] !== "") {
            insertRow = r + 2;
            break;
          }
        }
      }
    }
    
    // Copy Format & Dropdown dari baris di atasnya
    if (insertRow > 2) {
      var prevRow = insertRow - 1;
      var numColsToCopy = Math.min(sheet.getLastColumn(), rowData.length);
      var rangeToCopy = sheet.getRange(prevRow, 1, 1, numColsToCopy);
      var targetRange = sheet.getRange(insertRow, 1, 1, numColsToCopy);
      
      try {
        rangeToCopy.copyTo(targetRange, SpreadsheetApp.CopyPasteType.PASTE_FORMAT, false);
        rangeToCopy.copyTo(targetRange, SpreadsheetApp.CopyPasteType.PASTE_DATA_VALIDATION, false);
      } catch (errCopy) {
        // Abaikan jika sheet belum memiliki validasi
      }
    }
    
    // Masukkan data baru
    sheet.getRange(insertRow, 1, 1, rowData.length).setValues([rowData]);

    // Format kolom PRICE dengan format pemisah ribuan (#,##0)
    if (priceColIndex > 0 && numericPriceInput > 0) {
      sheet.getRange(insertRow, priceColIndex).setNumberFormat("#,##0");
    }
    
    return ContentService.createTextOutput(JSON.stringify({
      "status": "success", 
      "message": "Tersimpan rapi di baris " + insertRow + " (Tab " + targetTabName + ")",
      "tab_name": targetTabName,
      "row": insertRow
    })).setMimeType(ContentService.MimeType.JSON);
      
  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({
      "status": "error", 
      "message": error.message
    })).setMimeType(ContentService.MimeType.JSON);
  }
}
