/**
 * フォームが送信された直後の処理
 *
 * 受付番号を採番し、受付メールを送り、シートに記録する
 * スタッフ専用チャンネルへの投稿は、コンテナで動く Python 側が行う
 */

/**
 * フォームが送信されたときに呼ばれる
 *
 * スプレッドシートの「フォーム送信時」トリガーから呼ぶ
 *
 * @param {!Object} e トリガーが渡すイベント
 */
function onFormSubmit(e) {
  const sheet = e.range.getSheet();
  const row = e.range.getRow();
  const name = sheet.getName();
  if (name === SHEET_NAMES.LT) {
    handleSubmit(sheet, row, 'LT');
  } else if (name === SHEET_NAMES.COMMUNITY) {
    handleSubmit(sheet, row, 'COMMUNITY');
  } else if (name === SHEET_NAMES.SPONSOR) {
    handleSubmit(sheet, row, 'SPONSOR');
  }
}

/**
 * その行がもう受け付け済みかを返す
 *
 * フォームの回答を編集しても送信のトリガーは走る。採番済みの行に二度目の処理をしない
 *
 * @param {!Sheet} sheet 対象のシート
 * @param {number} row 1始まりの行番号
 * @param {!Object<string, number>} map 列名から列番号への対応
 * @return {boolean} 受付番号が入っていれば true
 */
function alreadyHandled(sheet, row, map) {
  return String(sheet.getRange(row, map['受付番号']).getValue() || '') !== '';
}

/**
 * 受付番号を採番して書き込む
 *
 * 採択メールの送信とは別の鍵を使う。同じ鍵だと、メールの送信中に届いた申し込みが待たされて落ちる
 *
 * @param {!Sheet} sheet 対象のシート
 * @param {number} row 1始まりの行番号
 * @param {!Object<string, number>} map 列名から列番号への対応
 * @param {string} prefix 受付番号の接頭辞
 * @return {string} 採番した受付番号。ほかの実行が先に採番していたら空文字
 */
function assignReceiptNumber(sheet, row, map, prefix) {
  const lock = LockService.getDocumentLock();
  lock.waitLock(30000);
  try {
    // 鍵を待っている間に、別の実行が同じ行を採番していることがある
    if (String(sheet.getRange(row, map['受付番号']).getValue() || '') !== '') {
      return '';
    }
    const number = nextReceiptNumber(sheet, map, prefix);
    writeCell(sheet, row, map, '受付番号', number);
    SpreadsheetApp.flush();
    return number;
  } finally {
    lock.releaseLock();
  }
}

/**
 * 宛先が1つのメールアドレスの形をしているかを返す
 *
 * MailApp はカンマで区切った複数の宛先を受け付ける。入力をそのまま渡すと、
 * 1件の申し込みで何人にも実行委員会名義のメールが届く
 *
 * @param {string} text 宛先の文字列
 * @return {boolean} 1つのアドレスの形なら true
 */
function isSingleAddress(text) {
  return /^[^\s,;<>@]+@[^\s,;<>@]+\.[^\s,;<>@]+$/.test(String(text).trim());
}

/**
 * メールを送る
 *
 * 差出人のアドレスはスクリプトの持ち主のものになる。表示名だけ実行委員会にそろえる
 *
 * @param {string} to 宛先
 * @param {string} subject 件名
 * @param {string} body 本文
 * @throws {Error} 宛先が1つのメールアドレスの形でないとき
 */
function sendMail(to, subject, body) {
  if (!isSingleAddress(to)) {
    // 中身は書かない。失敗の通知メールと実行ログに申込者のアドレスが残る
    throw new Error('宛先が1つのメールアドレスの形をしていません');
  }
  MailApp.sendEmail({ to: to, subject: subject, body: body, name: MAIL_SENDER_NAME });
}

/**
 * 申し込みを受け付ける
 *
 * 受付番号を振り、受付メールを送る。Discord への投稿は Python 側が拾う
 *
 * @param {!Sheet} sheet 対象のシート
 * @param {number} row 1始まりの行番号
 * @param {string} formKey 'LT' か 'COMMUNITY' か 'SPONSOR'
 * @throws {Error} 採番かメール送信が失敗したとき
 */
function handleSubmit(sheet, row, formKey) {
  ensureAdminColumns(sheet);
  const map = headerMap(sheet);
  if (alreadyHandled(sheet, row, map)) {
    return;
  }
  const number = assignReceiptNumber(sheet, row, map, NUMBER_PREFIXES[formKey]);
  if (number === '') {
    // 待っている間に別の実行が採番した。受付メールもそちらが送る
    return;
  }
  const record = readRow(sheet, row, map);
  const values = { '受付番号': number, '送信日時': nowText() };

  let template;
  let to;
  if (formKey === 'LT') {
    template = MAIL_RECEIPT_LT;
    to = String(record[COL_LT.MAIL]);
  } else if (formKey === 'COMMUNITY') {
    template = MAIL_RECEIPT_COMMUNITY;
    to = String(record[COL_COMMUNITY.MAIL]);
  } else {
    template = MAIL_RECEIPT_SPONSOR;
    to = String(record[COL_SPONSOR.MAIL]);
  }

  sendMail(to, fillTemplate(template.subject, values), fillTemplate(template.body, values));
  writeCell(sheet, row, map, '受付メール送信', nowText());
}
