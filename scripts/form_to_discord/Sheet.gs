/**
 * 回答シートの読み書き
 */

/**
 * ヘッダ行から、列名と列番号の対応を作る
 *
 * @param {!Sheet} sheet 対象のシート
 * @return {!Object<string, number>} 列名から1始まりの列番号への対応
 */
function headerMap(sheet) {
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const map = {};
  for (let i = 0; i < headers.length; i++) {
    const name = String(headers[i]).trim();
    // 同じ名前が2つあったら左を採る。Python 側と採り方をそろえないと読み書きする列がずれる
    if (name && !map[name]) {
      map[name] = i + 1;
    }
  }
  return map;
}

/**
 * ヘッダ行で2つ以上ある列の名前を集める
 *
 * @param {!Sheet} sheet 対象のシート
 * @return {!Array<string>} 重なっている列名
 */
function duplicateColumns(sheet) {
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const seen = {};
  const found = [];
  for (let i = 0; i < headers.length; i++) {
    const name = String(headers[i]).trim();
    if (!name) {
      continue;
    }
    if (seen[name]) {
      found.push(name);
    }
    seen[name] = true;
  }
  return found;
}

/**
 * 管理列がヘッダ行に無ければ右端に足す
 *
 * 足した列は文字列の書式にする。19桁のDiscordのIDを数値として入れると下の桁が化ける
 *
 * @param {!Sheet} sheet 対象のシート
 */
function ensureAdminColumns(sheet) {
  const map = headerMap(sheet);
  let column = sheet.getLastColumn();
  for (let i = 0; i < ADMIN_COLUMNS.length; i++) {
    if (!map[ADMIN_COLUMNS[i]]) {
      column += 1;
      sheet.getRange(1, column).setValue(ADMIN_COLUMNS[i]);
      sheet.getRange(2, column, sheet.getMaxRows() - 1, 1).setNumberFormat('@');
    }
  }
}

/**
 * 管理列をすべて文字列の書式にする
 *
 * setUp から呼ぶ。既にある列には ensureAdminColumns の書式設定が効かない
 *
 * @param {!Sheet} sheet 対象のシート
 */
function formatAdminColumns(sheet) {
  const map = headerMap(sheet);
  for (let i = 0; i < ADMIN_COLUMNS.length; i++) {
    const column = map[ADMIN_COLUMNS[i]];
    if (column) {
      sheet.getRange(2, column, sheet.getMaxRows() - 1, 1).setNumberFormat('@');
    }
  }
}

/**
 * 1行を、列名から値への対応として読む
 *
 * @param {!Sheet} sheet 対象のシート
 * @param {number} row 1始まりの行番号
 * @param {!Object<string, number>} map 列名から列番号への対応
 * @return {!Object<string, *>} 列名から値への対応
 */
function readRow(sheet, row, map) {
  const values = sheet.getRange(row, 1, 1, sheet.getLastColumn()).getValues()[0];
  const record = {};
  for (const name in map) {
    record[name] = values[map[name] - 1];
  }
  return record;
}

/**
 * 1つのセルに値を書く
 *
 * @param {!Sheet} sheet 対象のシート
 * @param {number} row 1始まりの行番号
 * @param {!Object<string, number>} map 列名から列番号への対応
 * @param {string} columnName 書き込む列の名前
 * @param {string} value 書き込む値
 */
function writeCell(sheet, row, map, columnName, value) {
  const cell = sheet.getRange(row, map[columnName]);
  // DiscordのIDは19桁。そのまま書くと数値になり、下の桁が別の値に化ける
  cell.setNumberFormat('@');
  cell.setValue(value);
}

/**
 * そのシートの次の受付番号を作る
 *
 * 既に入っている番号の最大値に1を足す。行数から作ると、行を消したときに番号が重なる
 *
 * @param {!Sheet} sheet 対象のシート
 * @param {!Object<string, number>} map 列名から列番号への対応
 * @param {string} prefix 受付番号の接頭辞
 * @return {string} 次の受付番号
 */
function nextReceiptNumber(sheet, map, prefix) {
  const lastRow = sheet.getLastRow();
  let max = 0;
  if (lastRow >= 2) {
    const values = sheet.getRange(2, map['受付番号'], lastRow - 1, 1).getValues();
    for (let i = 0; i < values.length; i++) {
      const text = String(values[i][0]);
      if (text.indexOf(prefix) === 0) {
        const number = parseInt(text.substring(prefix.length), 10);
        if (!isNaN(number) && number > max) {
          max = number;
        }
      }
    }
  }
  let digits = String(max + 1);
  while (digits.length < NUMBER_DIGITS) {
    digits = '0' + digits;
  }
  return prefix + digits;
}

/**
 * 指定した列が空で、別の列が埋まっている行の番号を集める
 *
 * @param {!Sheet} sheet 対象のシート
 * @param {!Object<string, number>} map 列名から列番号への対応
 * @param {string} filledColumn 埋まっていることを求める列の名前
 * @param {string} emptyColumn 空であることを求める列の名前
 * @return {!Array<number>} 条件に合う行番号の配列
 */
function findRows(sheet, map, filledColumn, emptyColumn) {
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return [];
  }
  const filled = sheet.getRange(2, map[filledColumn], lastRow - 1, 1).getValues();
  const empty = sheet.getRange(2, map[emptyColumn], lastRow - 1, 1).getValues();
  const rows = [];
  for (let i = 0; i < filled.length; i++) {
    if (String(filled[i][0]) !== '' && String(empty[i][0]) === '') {
      rows.push(i + 2);
    }
  }
  return rows;
}
