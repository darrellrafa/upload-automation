function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    
    // ==============================================================
    // 1. REPRICE / HARGA BARU / REPOST (TAB "PHOTO STUDIO" & "PHOTO OWNER")
    // ==============================================================
    if (data.action === "reprice_photo_studio" || data.action === "reprice_photo_owner" || data.action === "repost_consignment") {
      var targetSheetName = data.sheet_name || (data.action === "reprice_photo_owner" ? "PHOTO OWNER" : "PHOTO STUDIO");
      var sheetReprice = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(targetSheetName);
      
      if (!sheetReprice) {
        throw new Error("Tab '" + targetSheetName + "' tidak ditemukan.");
      }
      
      var skuToFindReprice = (data.sku || "").toString().trim().toLowerCase();
      var baseSkuToFindReprice = skuToFindReprice.replace(/-\d+$/, '');
      var dataRangeReprice = sheetReprice.getDataRange();
      var valuesReprice = dataRangeReprice.getValues();
      var foundRowReprice = -1;
      
      for (var i = 1; i < valuesReprice.length; i++) {
        var statusVal = (valuesReprice[i][0] || "").toString().trim().toLowerCase();
        var isStatusValid = (statusVal === "available" || statusVal === "reprice" || statusVal === "repost" || statusVal === "reprice/post" || statusVal === "reprice / post");
        if (!isStatusValid) continue;

        var skuVal = (valuesReprice[i][2] || "").toString().trim().toLowerCase();
        var isSkuMatch = (skuVal === skuToFindReprice || skuVal === baseSkuToFindReprice || skuVal.replace(/\s+/g, '') === skuToFindReprice.replace(/\s+/g, ''));
        
        if (!isSkuMatch) {
          for (var j = 0; j < valuesReprice[i].length; j++) {
            if (j === 2) continue;
            var cellVal = (valuesReprice[i][j] || "").toString().trim().toLowerCase();
            if (cellVal === skuToFindReprice || cellVal === baseSkuToFindReprice || cellVal.replace(/\s+/g, '') === skuToFindReprice.replace(/\s+/g, '')) {
              isSkuMatch = true;
              break;
            }
          }
        }
        
        if (isSkuMatch) {
          foundRowReprice = i + 1;
          break;
        }
      }
      
      if (foundRowReprice === -1) {
        throw new Error("SKU '" + data.sku + "' dengan status Available / Reprice/post tidak ditemukan di tab " + targetSheetName);
      }
      
      var isRepost = (data.command_type === "REPOST" || data.action === "repost_consignment");
      var newStatus = "Reprice/post";
      sheetReprice.getRange(foundRowReprice, 1).setValue(newStatus);
      
      var maxColsReprice = sheetReprice.getMaxColumns();
      
      // 1. PASTIKAN KOLOM NOTES (KOLOM G / 7) SELALU DIISI
      // Kolom Notes dijamin tetap terisi walaupun kolom centang sudah terisi penuh
      var updatedNotes = "";
      if (maxColsReprice >= 7) {
        var existingNotes = (sheetReprice.getRange(foundRowReprice, 7).getValue() || "").toString().trim();
        var defaultNote = isRepost ? ("REPOST (" + data.date_str + ")") : ("REPRICE " + (data.formatted_price || data.new_price) + " (" + data.date_str + ")");
        var noteEntry = data.notes_text || defaultNote;
        updatedNotes = existingNotes ? (existingNotes + String.fromCharCode(10) + noteEntry) : noteEntry;
        sheetReprice.getRange(foundRowReprice, 7).setValue(updatedNotes);
      }
      
      // 2. LOGIKA CENTANG TRACKING POST (KOLOM 13/M, 14/N, 15/O)
      var checkedColName = "";
      if (targetSheetName === "PHOTO STUDIO" && maxColsReprice >= 15) {
        var colM = sheetReprice.getRange(foundRowReprice, 13).getValue();
        var colN = sheetReprice.getRange(foundRowReprice, 14).getValue();
        var colO = sheetReprice.getRange(foundRowReprice, 15).getValue();
        
        if (colM !== true && colM !== "TRUE" && colM !== "true") {
          sheetReprice.getRange(foundRowReprice, 13).setValue(true);
          checkedColName = "2ND (Kolom M)";
        } else if (colN !== true && colN !== "TRUE" && colN !== "true") {
          sheetReprice.getRange(foundRowReprice, 14).setValue(true);
          checkedColName = "3RD (Kolom N)";
        } else if (colO !== true && colO !== "TRUE" && colO !== "true") {
          sheetReprice.getRange(foundRowReprice, 15).setValue(true);
          checkedColName = "4TH (Kolom O)";
        } else {
          checkedColName = "Centang penuh (Notes tetap terisi)";
        }
      } else {
        checkedColName = "Notes terisi (Tab " + targetSheetName + ")";
      }
      
      var actionDesc = isRepost ? "di-repost" : "di-reprice";
      return ContentService.createTextOutput(JSON.stringify({
        "status": "success",
        "message": "SKU " + data.sku + " berhasil " + actionDesc + " pada baris " + foundRowReprice + " (Tab " + targetSheetName + ")",
        "tab_name": targetSheetName,
        "row": foundRowReprice,
        "new_status": newStatus,
        "tracking_checked": checkedColName,
        "notes": updatedNotes
      })).setMimeType(ContentService.MimeType.JSON);
    }
    
    // ==============================================================
    // 2. LOGIKA CENTANG KOLOM WEB (KHUSUS TAB "PHOTO OWNER")
    // ==============================================================
    if (data.action === "check_web_owner") {
      var sheetNameNew = "PHOTO OWNER";
      var sheetNew = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(sheetNameNew);
      
      if (!sheetNew) {
        throw new Error("Tab '" + sheetNameNew + "' tidak ditemukan.");
      }
      
      var skuToFindNew = data.sku;
      var dataRangeNew = sheetNew.getDataRange();
      var valuesNew = dataRangeNew.getValues();
      var skuFoundNew = false;
      
      for (var i = 0; i < valuesNew.length; i++) {
        for (var j = 0; j < valuesNew[i].length; j++) {
          if (valuesNew[i][j] === skuToFindNew) {
            sheetNew.getRange(i + 1, j + 2).setValue(true);
            skuFoundNew = true;
            break;
          }
        }
        if (skuFoundNew) break;
      }
      
      if (!skuFoundNew) {
        throw new Error("SKU '" + skuToFindNew + "' tidak ditemukan di tab " + sheetNameNew);
      }
      
      return ContentService.createTextOutput(JSON.stringify({"status": "success", "message": "SKU " + skuToFindNew + " berhasil dicentang di Web."}))
        .setMimeType(ContentService.MimeType.JSON);
    }

    // ==============================================================
    // 3. UPDATE STATUS (SOLD / ON HOLD / TAKEDOWN) & HAPUS CHECKBOX KOSONG
    // ==============================================================
    if (data.action === "update_consignment_status" || data.action === "takedown_photo_studio") {
      var targetSheetName = data.sheet_name || "PHOTO STUDIO";
      var sheetStatus = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(targetSheetName);
      
      if (!sheetStatus) {
        throw new Error("Tab '" + targetSheetName + "' tidak ditemukan.");
      }
      
      var skuToFind = (data.sku || "").toString().trim().toLowerCase();
      var baseSkuToFind = skuToFind.replace(/-\d+$/, '');
      var dataRange = sheetStatus.getDataRange();
      var values = dataRange.getValues();
      var foundRow = -1;
      
      for (var i = values.length - 1; i >= 1; i--) {
        // Cek kolom C (index 2) terlebih dahulu
        var skuVal = (values[i][2] || "").toString().trim().toLowerCase();
        if (skuVal === skuToFind || skuVal === baseSkuToFind || skuVal.replace(/\s+/g, '') === skuToFind.replace(/\s+/g, '')) {
          foundRow = i + 1;
          break;
        }
        // Jika tidak cocok di kolom C, periksa seluruh kolom pada baris tersebut (misal tab PHOTO OWNER di Kolom B)
        var rowMatched = false;
        for (var j = 0; j < values[i].length; j++) {
          if (j === 2) continue;
          var cellVal = (values[i][j] || "").toString().trim().toLowerCase();
          if (cellVal === skuToFind || cellVal === baseSkuToFind || cellVal.replace(/\s+/g, '') === skuToFind.replace(/\s+/g, '')) {
            rowMatched = true;
            break;
          }
        }
        if (rowMatched) {
          foundRow = i + 1;
          break;
        }
      }
      
      if (foundRow === -1) {
        throw new Error("SKU '" + data.sku + "' tidak ditemukan di tab " + targetSheetName);
      }
      
      var maxCols = sheetStatus.getMaxColumns();
      var oldStatus = (sheetStatus.getRange(foundRow, 1).getValue() || "").toString().trim();
      var sheetPhotoUrl = "";
      if (maxCols >= 2) {
        var photoCell = sheetStatus.getRange(foundRow, 2);
        var photoFormula = photoCell.getFormula() || "";
        var photoVal = (photoCell.getValue() || "").toString().trim();
        var mPhoto = photoFormula.match(/=IMAGE\(["']([^"']+)["']\)/i);
        if (mPhoto) {
          sheetPhotoUrl = mPhoto[1];
        } else if (photoVal.indexOf("http") === 0) {
          sheetPhotoUrl = photoVal;
        }
      }
      var itemName = maxCols >= 4 ? (sheetStatus.getRange(foundRow, 4).getValue() || "").toString().trim() : "";

      var newStatus = data.status_text || "Takedown";
      if (newStatus.toString().trim().toLowerCase().replace(/\s+/g, '') === "takedown") {
        newStatus = "Takedown";
      }
      sheetStatus.getRange(foundRow, 1).setValue(newStatus);
      
      // Hapus centang jadwal post (hanya relevan untuk PHOTO STUDIO yang memiliki kolom tracking 12, 13, 14, 15)
      var removedCount = 0;
      if (targetSheetName === "PHOTO STUDIO") {
        var trackingCols = [12, 13, 14, 15];
        for (var k = 0; k < trackingCols.length; k++) {
          if (trackingCols[k] <= maxCols) {
            var cell = sheetStatus.getRange(foundRow, trackingCols[k]);
            var cellVal = cell.getValue();
            if (cellVal !== true && cellVal !== "TRUE" && cellVal !== "true") {
              if (typeof cell.removeCheckboxes === "function") {
                cell.removeCheckboxes();
              }
              cell.clearDataValidations();
              cell.setValue("");
              removedCount++;
            }
          }
        }
      }
      
      var updatedNotes = "";
      if (maxCols >= 7) {
        var existingNotes = (sheetStatus.getRange(foundRow, 7).getValue() || "").toString().trim();
        var noteEntry = newStatus.toUpperCase() + (data.date_str ? (" (" + data.date_str + ")") : "");
        updatedNotes = existingNotes ? (existingNotes + String.fromCharCode(10) + noteEntry) : noteEntry;
        sheetStatus.getRange(foundRow, 7).setValue(updatedNotes);
      }
      
      return ContentService.createTextOutput(JSON.stringify({
        "status": "success",
        "message": "SKU " + data.sku + " berhasil diubah status menjadi " + newStatus + " pada baris " + foundRow + " (Tab " + targetSheetName + ")",
        "tab_name": targetSheetName,
        "row": foundRow,
        "old_status": oldStatus,
        "new_status": newStatus,
        "photo_url": sheetPhotoUrl,
        "item_name": itemName,
        "removed_checkboxes": removedCount,
        "notes": updatedNotes
      })).setMimeType(ContentService.MimeType.JSON);
    }

    // ==============================================================
    // 4. LOGIKA LAMA (UPLOAD INITIAL CONSIGNMENT_PS)
    // ==============================================================
    var sheetName = data.sheet_name || "PHOTO STUDIO";
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(sheetName);
    
    if (!sheet) {
      throw new Error("Tab '" + sheetName + "' tidak ditemukan.");
    }
    
    var skuToFind = data.sku;
    var dataRange = sheet.getDataRange();
    var values = dataRange.getValues();
    var foundRow = -1;
    
    for (var i = 0; i < values.length; i++) {
      if (values[i][2] == skuToFind) { 
        foundRow = i + 1;
        break;
      }
    }
    
    if (foundRow === -1) {
      throw new Error("SKU / Serial Number '" + skuToFind + "' tidak ditemukan di draf Spreadsheet.");
    }
    
    var imageFormula = '=IMAGE("' + data.photo_url + '")';
    
    sheet.getRange(foundRow, 1).setValue("Available");
    sheet.getRange(foundRow, 2).setFormula(imageFormula);
    sheet.getRange(foundRow, 11).setValue(data.tanggal);
    sheet.getRange(foundRow, 12).setValue(true);
    
    return ContentService.createTextOutput(JSON.stringify({"status": "success", "message": "Baris " + foundRow + " terupdate."}))
      .setMimeType(ContentService.MimeType.JSON);
      
  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({"status": "error", "message": error.message}))
      .setMimeType(ContentService.MimeType.JSON);
  }
}