/**
 * 最初に1度だけ手で動かす処理
 */

/** 設定しておく必要があるスクリプトプロパティ */
const REQUIRED_PROPERTIES = ['DISCORD_INVITE_URL'];

/** 承認を見に行く間隔 (分)。Google が受け付けるのは 1, 5, 10, 15, 30 のいずれか */
const MAIL_INTERVAL_MINUTES = 1;

/**
 * 管理列を足し、トリガーを作り直す
 *
 * スクリプトプロパティを設定してから動かす
 */
function setUp() {
  const missing = missingProperties();
  if (missing.length > 0) {
    throw new Error('スクリプトプロパティが足りません: ' + missing.join(', '));
  }
  const book = SpreadsheetApp.getActiveSpreadsheet();
  const names = [SHEET_NAMES.LT, SHEET_NAMES.COMMUNITY, SHEET_NAMES.SPONSOR];
  for (let i = 0; i < names.length; i++) {
    const sheet = book.getSheetByName(names[i]);
    if (!sheet) {
      throw new Error('シート ' + names[i] + ' が見つかりません');
    }
    ensureAdminColumns(sheet);
    formatAdminColumns(sheet);
  }
  removeTriggers();
  ScriptApp.newTrigger('onFormSubmit').forSpreadsheet(book).onFormSubmit().create();
  ScriptApp.newTrigger('sendApprovalMails').timeBased().everyMinutes(MAIL_INTERVAL_MINUTES).create();
  console.log('設定しました。トリガーを2つ作りました');
}

/**
 * このプロジェクトのトリガーをすべて消す
 *
 * setUp で作り直す前に呼ぶ。別の用途のトリガーを同じプロジェクトに置かない
 */
function removeTriggers() {
  const triggers = ScriptApp.getProjectTriggers();
  for (let i = 0; i < triggers.length; i++) {
    ScriptApp.deleteTrigger(triggers[i]);
  }
}

/**
 * 未設定のスクリプトプロパティを集める
 *
 * @return {!Array<string>} 未設定のプロパティ名
 */
function missingProperties() {
  const properties = PropertiesService.getScriptProperties();
  const missing = [];
  for (let i = 0; i < REQUIRED_PROPERTIES.length; i++) {
    if (!properties.getProperty(REQUIRED_PROPERTIES[i])) {
      missing.push(REQUIRED_PROPERTIES[i]);
    }
  }
  return missing;
}

/**
 * 設定とシートの列を確かめる
 *
 * 足りない設定と、見つからない列を実行ログに出す
 */
function checkSettings() {
  const missing = missingProperties();
  if (missing.length > 0) {
    console.log('足りないスクリプトプロパティ: ' + missing.join(', '));
  } else {
    console.log('スクリプトプロパティはそろっています');
  }

  const book = SpreadsheetApp.getActiveSpreadsheet();
  const sheetColumns = [
    [SHEET_NAMES.LT, COL_LT],
    [SHEET_NAMES.COMMUNITY, COL_COMMUNITY],
    [SHEET_NAMES.SPONSOR, COL_SPONSOR]
  ];
  for (let i = 0; i < sheetColumns.length; i++) {
    const sheet = book.getSheetByName(sheetColumns[i][0]);
    if (!sheet) {
      console.log('シート ' + sheetColumns[i][0] + ': ありません');
      continue;
    }
    const map = headerMap(sheet);
    const columns = sheetColumns[i][1];
    const notFound = [];
    for (const key in columns) {
      if (!map[columns[key]]) {
        notFound.push(columns[key]);
      }
    }
    for (let j = 0; j < ADMIN_COLUMNS.length; j++) {
      if (!map[ADMIN_COLUMNS[j]]) {
        notFound.push(ADMIN_COLUMNS[j]);
      }
    }
    if (!map[TIMESTAMP_COLUMN]) {
      notFound.push(TIMESTAMP_COLUMN);
    }
    if (notFound.length > 0) {
      console.log('シート ' + sheetColumns[i][0] + ': 次の列がありません / ' + notFound.join(' / '));
    } else {
      console.log('シート ' + sheetColumns[i][0] + ': 列はそろっています');
    }
    const duplicated = duplicateColumns(sheet);
    if (duplicated.length > 0) {
      console.log('シート ' + sheetColumns[i][0] + ': 同じ名前の列が2つ以上あります / ' + duplicated.join(' / '));
    }
  }
}

/**
 * 各シートのヘッダ行をそのまま実行ログに出す
 *
 * フォームの質問文に補足の行があると、ヘッダに改行ごと入る
 * `Config.gs` の列名を実物に合わせるときに使う
 */
function printHeaders() {
  const book = SpreadsheetApp.getActiveSpreadsheet();
  const names = [SHEET_NAMES.LT, SHEET_NAMES.COMMUNITY, SHEET_NAMES.SPONSOR];
  for (let i = 0; i < names.length; i++) {
    const sheet = book.getSheetByName(names[i]);
    if (!sheet) {
      console.log('--- ' + names[i] + ' はありません ---');
      continue;
    }
    const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
    console.log('--- ' + names[i] + ' ---');
    for (let j = 0; j < headers.length; j++) {
      console.log((j + 1) + ': ' + JSON.stringify(String(headers[j])));
    }
  }
}
