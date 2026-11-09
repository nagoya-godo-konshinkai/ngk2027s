/**
 * 承認された申し込みに採択メールを送り、受付の取りこぼしを拾う
 *
 * 承認の検知と Discord の操作は、コンテナで動く Python 側が行う
 * 採択メールは「承認確認」に時刻が入り、まだメールを送っていない行だけを引き受ける
 */

/**
 * 送信から救済までに置く間隔 (ミリ秒)
 *
 * 送信直後の行はフォーム送信の処理が進めている。短くすると、遅れているだけの行を
 * 拾い直してしまい、同じ受付メールが2通届く
 */
const RESCUE_DELAY_MS = 600000;

/**
 * 1分ごとのトリガーから呼ばれる
 *
 * 1件でも失敗したら最後に例外を投げる。Google からの通知メールで気づけるようにするため
 *
 * @throws {Error} いずれかの行の処理が失敗したとき
 */
function sendApprovalMails() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(0)) {
    // 前の回がまだ動いている。待って入ると同じ行に2回送るので、この回は何もしない
    return;
  }
  let failures = [];
  try {
    const book = SpreadsheetApp.getActiveSpreadsheet();
    failures = failures
      .concat(rescueUnnumbered(book))
      .concat(sendForSheet(book.getSheetByName(SHEET_NAMES.LT), 'LT'))
      .concat(sendForSheet(book.getSheetByName(SHEET_NAMES.COMMUNITY), 'COMMUNITY'));
  } finally {
    lock.releaseLock();
  }
  if (failures.length > 0) {
    throw new Error(failures.join(' / '));
  }
}

/**
 * 受付番号が振られないまま残っている行を拾い直す
 *
 * フォーム送信のトリガーが落ちると、その申し込みは受付メールも Discord 投稿も無いまま埋もれる
 * 受付番号を見分けの印にしているので、空の行は誰からも拾われない
 *
 * @param {!Spreadsheet} book スプレッドシート
 * @return {!Array<string>} 失敗した処理の説明
 */
function rescueUnnumbered(book) {
  const failures = [];
  const keys = ['LT', 'COMMUNITY', 'SPONSOR'];
  for (let i = 0; i < keys.length; i++) {
    const name = SHEET_NAMES[keys[i]];
    const sheet = book.getSheetByName(name);
    if (!sheet || sheet.getLastRow() < 2) {
      continue;
    }
    const map = headerMap(sheet);
    if (!map[TIMESTAMP_COLUMN] || !map['受付番号']) {
      // 列が無いまま findRows を呼ぶと例外が出て、採択メールの送信まで巻き添えで止まる
      failures.push(name + ': 列 ' + TIMESTAMP_COLUMN + ' か 受付番号 がありません');
      continue;
    }
    const rows = findRows(sheet, map, TIMESTAMP_COLUMN, '受付番号');
    for (let j = 0; j < rows.length; j++) {
      const stamp = sheet.getRange(rows[j], map[TIMESTAMP_COLUMN]).getValue();
      if (stamp instanceof Date && Date.now() - stamp.getTime() < RESCUE_DELAY_MS) {
        // 届いたばかり。フォーム送信の処理がまだ動いている
        continue;
      }
      try {
        handleSubmit(sheet, rows[j], keys[i]);
      } catch (error) {
        failures.push(name + ' ' + rows[j] + '行目 受付の取りこぼし: ' + error);
      }
    }
  }
  return failures;
}

/**
 * 1つのシートについて、承認済みで未送信の行にメールを送る
 *
 * @param {?Sheet} sheet 対象のシート。無ければ何もしない
 * @param {string} formKey 'LT' か 'COMMUNITY'
 * @return {!Array<string>} 失敗した処理の説明
 */
function sendForSheet(sheet, formKey) {
  const failures = [];
  if (!sheet || sheet.getLastRow() < 2) {
    return failures;
  }
  const map = headerMap(sheet);
  if (!map['承認確認'] || !map['採択メール送信']) {
    failures.push(sheet.getName() + ': 列 承認確認 か 採択メール送信 がありません');
    return failures;
  }
  const rows = findRows(sheet, map, '承認確認', '採択メール送信');
  for (let i = 0; i < rows.length; i++) {
    const row = rows[i];
    const record = readRow(sheet, row, map);
    const number = String(record['受付番号']);
    // 送る前に印を立てる。送ってから書くと、書けなかったときに同じメールが2通届く
    try {
      writeCell(sheet, row, map, '採択メール送信', nowText());
      SpreadsheetApp.flush();
    } catch (error) {
      failures.push(number + ' 採択メール送信の準備: ' + error);
      continue;
    }
    try {
      sendApprovalMail(formKey, record);
    } catch (error) {
      failures.push(number + ' 採択メール送信: ' + error);
      // まだ送れていないので印を消す。消せたら次の回でやり直す
      try {
        writeCell(sheet, row, map, '採択メール送信', '');
        SpreadsheetApp.flush();
      } catch (inner) {
        failures.push(number + ' 採択メール送信の取り消し: ' + inner);
      }
    }
  }
  return failures;
}

/**
 * 種別に応じた採択メールを送る
 *
 * @param {string} formKey 'LT' か 'COMMUNITY'
 * @param {!Object<string, *>} record その行の値
 */
function sendApprovalMail(formKey, record) {
  const invite = getProperty('DISCORD_INVITE_URL');
  if (formKey === 'COMMUNITY') {
    const communityValues = {
      '受付番号': record['受付番号'],
      'コミュニティ名': record[COL_COMMUNITY.NAME],
      '担当者名': record[COL_COMMUNITY.OWNER],
      'Discord招待リンク': invite
    };
    sendMail(
      String(record[COL_COMMUNITY.MAIL]),
      fillTemplate(MAIL_APPROVED_COMMUNITY.subject, communityValues),
      fillTemplate(MAIL_APPROVED_COMMUNITY.body, communityValues)
    );
    return;
  }
  const kind = String(record[COL_LT.KIND]);
  const template = kind === 'スポンサーLT' ? MAIL_APPROVED_SPONSOR_LT : MAIL_APPROVED_LT;
  const values = {
    '受付番号': record['受付番号'],
    'LT種別': kind,
    '発表者名': record[COL_LT.SPEAKER],
    'Discord招待リンク': invite
  };
  sendMail(String(record[COL_LT.MAIL]), fillTemplate(template.subject, values), fillTemplate(template.body, values));
}
