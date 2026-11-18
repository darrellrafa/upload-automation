function getNotesColumnIndex(sheet, headerValues) {
  var headers = headerValues;
  if (!headers && sheet) {
    var lastCol = sheet.getLastColumn();
    if (lastCol >= 1) {
      headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0];
    }
  }
  if (headers && headers.length) {
    for (var c = 0; c < headers.length; c++) {
      var h = (headers[c] || "").toString().trim().toUpperCase();
      if (h === "NOTES" || h === "NOTE" || h.indexOf("NOTES") === 0) {
        return c + 1; // 1-based index (Col 7 di PHOTO STUDIO, Col 6 di PHOTO OWNER)
      }
    }
  }
  var sName = sheet ? (sheet.getName() || "").toUpperCase() : "";
  if (sName.indexOf("OWNER") !== -1) {
    return 6; // Column F di tab PHOTO OWNER
  }
  return 7; // Column G di tab PHOTO STUDIO
}

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
      
      for (var i = valuesReprice.length - 1; i >= 1; i--) {
        var statusVal = (valuesReprice[i][0] || "").toString().trim().toLowerCase();
        var isStatusValid = (statusVal === "available" || statusVal === "reprice" || statusVal === "repost" || statusVal === "reprice/post" || statusVal === "reprice / post");
        if (!isStatusValid) continue;

        // Cek Kolom C (index 2) dan Kolom G (index 6) terlebih dahulu
        var skuValC = (valuesReprice[i][2] || "").toString().trim().toLowerCase();
        var skuValG = (valuesReprice[i].length > 6 ? (valuesReprice[i][6] || "") : "").toString().trim().toLowerCase();
        var isSkuMatch = (skuValC === skuToFindReprice || skuValC === baseSkuToFindReprice || skuValC.replace(/\s+/g, '') === skuToFindReprice.replace(/\s+/g, '') ||
                          skuValG === skuToFindReprice || skuValG === baseSkuToFindReprice || skuValG.replace(/\s+/g, '') === skuToFindReprice.replace(/\s+/g, ''));
        
        if (!isSkuMatch) {
          for (var j = 0; j < valuesReprice[i].length; j++) {
            if (j === 2 || j === 6) continue;
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
      
      var rowRepriceVals = valuesReprice[foundRowReprice - 1];
      var isRepost = (data.command_type === "REPOST" || data.action === "repost_consignment");
      var newStatus = "Reprice/post";
      sheetReprice.getRange(foundRowReprice, 1).setValue(newStatus);
      
      var maxColsReprice = sheetReprice.getMaxColumns();
      var notesCol = getNotesColumnIndex(sheetReprice, valuesReprice[0]);
      
      // 1. PASTIKAN KOLOM NOTES SELALU DIISI (DEDUP JIKA SUDAH ADA DI BARIS TERAKHIR)
      var updatedNotes = "";
      if (maxColsReprice >= notesCol) {
        var existingNotes = (rowRepriceVals[notesCol - 1] || "").toString().trim();
        var defaultNote = isRepost ? ("REPOST (" + data.date_str + ")") : ("REPRICE " + (data.formatted_price || data.new_price) + " (" + data.date_str + ")");
        var noteEntry = data.notes_text || defaultNote;
        if (existingNotes) {
          var noteLines = existingNotes.split("\n").map(function(s) { return s.trim(); });
          if (noteLines[noteLines.length - 1] !== noteEntry.trim()) {
            updatedNotes = existingNotes + "\n" + noteEntry;
            sheetReprice.getRange(foundRowReprice, notesCol).setValue(updatedNotes);
          } else {
            updatedNotes = existingNotes;
          }
        } else {
          updatedNotes = noteEntry;
          sheetReprice.getRange(foundRowReprice, notesCol).setValue(updatedNotes);
        }
      }
      
      // Perlindungan kolom SKU (Kolom 7/G) di tab PHOTO OWNER:
      if (targetSheetName === "PHOTO OWNER" && maxColsReprice >= 7) {
        var col7Val = (rowRepriceVals[6] || "").toString().trim();
        if (col7Val.indexOf("\n") !== -1) {
          var cleanSkuCol7 = col7Val.split("\n")[0].trim();
          sheetReprice.getRange(foundRowReprice, 7).setValue(cleanSkuCol7);
        }
      }
      
      // 2. LOGIKA CENTANG TRACKING POST
      var checkedColName = "";
      if (targetSheetName === "PHOTO STUDIO" && maxColsReprice >= 15) {
        var colM = rowRepriceVals[12];
        var colN = rowRepriceVals[13];
        var colO = rowRepriceVals[14];
        
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
      } else if (targetSheetName === "PHOTO OWNER") {
        // Cek kolom REPOST/REPRICE WEB (Kolom 9/I)
        if (maxColsReprice >= 9) {
          sheetReprice.getRange(foundRowReprice, 9).setValue(true);
        }
        // Cek tracking post 2nd (Kolom 11/K), 3rd (Kolom 12/L), 4th (Kolom 13/M)
        if (maxColsReprice >= 13) {
          var colK = rowRepriceVals[10];
          var colL = rowRepriceVals[11];
          var colM = rowRepriceVals[12];
          
          if (colK !== true && colK !== "TRUE" && colK !== "true") {
            sheetReprice.getRange(foundRowReprice, 11).setValue(true);
            checkedColName = "2ND (Kolom K)";
          } else if (colL !== true && colL !== "TRUE" && colL !== "true") {
            sheetReprice.getRange(foundRowReprice, 12).setValue(true);
            checkedColName = "3RD (Kolom L)";
          } else if (colM !== true && colM !== "TRUE" && colM !== "true") {
            sheetReprice.getRange(foundRowReprice, 13).setValue(true);
            checkedColName = "4TH (Kolom M)";
          } else {
            checkedColName = "Centang penuh (Notes tetap terisi)";
          }
        } else {
          checkedColName = "Notes terisi (Tab " + targetSheetName + ")";
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
      
      var skuToFindNew = (data.sku || "").toString().trim();
      var dataRangeNew = sheetNew.getDataRange();
      var valuesNew = dataRangeNew.getValues();
      var skuFoundNew = false;
      
      for (var i = 0; i < valuesNew.length; i++) {
        var colG = (valuesNew[i].length > 6 ? valuesNew[i][6] : "").toString().trim();
        var colC = (valuesNew[i][2] || "").toString().trim();
        if (colG === skuToFindNew || colC === skuToFindNew) {
          sheetNew.getRange(i + 1, 9).setValue(true); // Kolom 9 (I) Web
          skuFoundNew = true;
          break;
        }
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
        // Cek kolom C (index 2) dan kolom G (index 6) terlebih dahulu
        var skuValC = (values[i][2] || "").toString().trim().toLowerCase();
        var skuValG = (values[i].length > 6 ? (values[i][6] || "") : "").toString().trim().toLowerCase();
        if (skuValC === skuToFind || skuValC === baseSkuToFind || skuValC.replace(/\s+/g, '') === skuToFind.replace(/\s+/g, '') ||
            skuValG === skuToFind || skuValG === baseSkuToFind || skuValG.replace(/\s+/g, '') === skuToFind.replace(/\s+/g, '')) {
          foundRow = i + 1;
          break;
        }
        // Jika tidak cocok di kolom C & G, periksa seluruh kolom lainnya
        var rowMatched = false;
        for (var j = 0; j < values[i].length; j++) {
          if (j === 2 || j === 6) continue;
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
      
      var rowStatusVals = values[foundRow - 1];
      var maxCols = sheetStatus.getMaxColumns();
      var oldStatus = (rowStatusVals[0] || "").toString().trim();
      var sheetPhotoUrl = "";
      
      // Ambil foto (PHOTO STUDIO di Col 2/B, PHOTO OWNER di Col 3/C)
      var photoCol = (targetSheetName === "PHOTO OWNER") ? 3 : 2;
      if (maxCols >= photoCol) {
        var photoVal = (rowStatusVals[photoCol - 1] || "").toString().trim();
        if (photoVal.indexOf("http") === 0) {
          sheetPhotoUrl = photoVal;
        } else {
          var photoCell = sheetStatus.getRange(foundRow, photoCol);
          var photoFormula = photoCell.getFormula() || "";
          var mPhoto = photoFormula.match(/=IMAGE\(["']([^"']+)["']\)/i);
          if (mPhoto) {
            sheetPhotoUrl = mPhoto[1];
          }
        }
      }
      
      // Ambil nama item (Kolom 4 / D)
      var itemCol = 4;
      var itemName = (rowStatusVals[itemCol - 1] || "").toString().trim();
      if (!itemName && targetSheetName === "PHOTO OWNER" && rowStatusVals.length >= 5) {
        itemName = (rowStatusVals[4] || "").toString().trim();
      }

      var newStatus = data.status_text || "Takedown";
      if (newStatus.toString().trim().toLowerCase().replace(/\s+/g, '') === "takedown") {
        newStatus = "Takedown";
      }
      sheetStatus.getRange(foundRow, 1).setValue(newStatus);
      
      // Hapus centang jadwal post yang belum dicentang (hanya pada cell yang tidak kosong)
      var removedCount = 0;
      var trackingCols = (targetSheetName === "PHOTO OWNER") ? [9, 10, 11, 12, 13] : [12, 13, 14, 15];
      for (var k = 0; k < trackingCols.length; k++) {
        var colIndex = trackingCols[k];
        if (colIndex <= maxCols) {
          var cellVal = rowStatusVals[colIndex - 1];
          if (cellVal !== true && cellVal !== "TRUE" && cellVal !== "true" && cellVal !== "" && cellVal !== null && cellVal !== undefined) {
            var cell = sheetStatus.getRange(foundRow, colIndex);
            if (typeof cell.removeCheckboxes === "function") {
              try { cell.removeCheckboxes(); } catch(e){}
            }
            try { cell.clearDataValidations(); } catch(e){}
            cell.setValue("");
            removedCount++;
          }
        }
      }
      
      // CATAT NOTES DI SPREADSHEET (DEDUP JIKA SUDAH ADA DI BARIS TERAKHIR)
      var notesCol = getNotesColumnIndex(sheetStatus, values[0]);
      var updatedNotes = "";
      if (maxCols >= notesCol) {
        var existingNotes = (rowStatusVals[notesCol - 1] || "").toString().trim();
        var noteEntry = data.notes_text || (newStatus.toUpperCase() + (data.date_str ? (" (" + data.date_str + ")") : ""));
        if (existingNotes) {
          var noteLines = existingNotes.split("\n").map(function(s) { return s.trim(); });
          if (noteLines[noteLines.length - 1] !== noteEntry.trim()) {
            updatedNotes = existingNotes + "\n" + noteEntry;
            sheetStatus.getRange(foundRow, notesCol).setValue(updatedNotes);
          } else {
            updatedNotes = existingNotes;
          }
        } else {
          updatedNotes = noteEntry;
          sheetStatus.getRange(foundRow, notesCol).setValue(updatedNotes);
        }
      }
      
      // Perlindungan kolom SKU (Kolom 7/G) di tab PHOTO OWNER:
      if (targetSheetName === "PHOTO OWNER" && maxCols >= 7) {
        var col7Val = (rowStatusVals[6] || "").toString().trim();
        if (col7Val.indexOf("\n") !== -1) {
          var cleanSkuCol7 = col7Val.split("\n")[0].trim();
          sheetStatus.getRange(foundRow, 7).setValue(cleanSkuCol7);
        }
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
