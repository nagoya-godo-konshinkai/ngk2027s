/**
 * 設定値の読み出しと、スクリプト全体で使う定数
 *
 * Discord の操作はコンテナで動く Python 側が行う。ここには Discord の設定を置かない
 */

/** フォームの回答シート名。スプレッドシートのシート名と一致させる */
const SHEET_NAMES = {
  LT: 'LT発表申込',
  COMMUNITY: 'コミュニティ参加申込',
  SPONSOR: '企業スポンサー申込'
};

/** 受付番号の接頭辞 */
const NUMBER_PREFIXES = {
  LT: 'LT-',
  COMMUNITY: 'COMMUNITY-',
  SPONSOR: 'SPONSOR-'
};

/** 受付番号の桁数 */
const NUMBER_DIGITS = 3;

/** フォームが回答のたびに書き込む列。行が申し込みかどうかの見分けに使う */
const TIMESTAMP_COLUMN = 'タイムスタンプ';

/** スクリプトが書き込む管理列。Python 側の ADMIN_COLUMNS と同じ並びにする */
const ADMIN_COLUMNS = [
  '受付番号',
  '受付メール送信',
  'discord自動投稿',
  '申込投稿ID',
  '承認確認',
  '採択メール送信',
  '採択メール確認',
  '採択discord送信',
  '採択投稿ID',
  'DiscordユーザーID',
  'ユーザー未特定通知',
  'OKリアクション確認',
  'ロール付与'
];

/** このスクリプトが値を書く列。ほかの列は Python 側が書く */
const OWNED_COLUMNS = ['受付番号', '受付メール送信', '採択メール送信'];

/** メールの差出人として表示する名前。From のアドレスはスクリプトの持ち主のものになる */
const MAIL_SENDER_NAME = 'NGK実行委員会';

/** LT発表申込フォームの列名。フォームの質問文を変えたらここも変える */
const COL_LT = {
  MAIL: 'メールアドレス',
  KIND: '申込み種別',
  SPEAKER: '発表者名',
  SPEAKER_KANA: '発表者名のよみかた（ひらがな）',
  TITLE: 'LTタイトル',
  TITLE_KANA: 'LTタイトルのよみかた（ひらがな）',
  SUMMARY: 'LT概要',
  COUNT: 'NGKでのLT発表は何回目ですか',
  BAD_TIME: 'イベント当日(2027/01/16)に都合の悪い時間帯があれば記載してください。',
  COMMUNITY: 'コミュニティ名',
  COMMUNITY_NUMBER: 'コミュニティ参加 申し込み番号',
  SPONSOR: 'スポンサー 企業名',
  CONNPASS: 'connpass ID',
  CONNPASS_NUMBER: 'connpass 昼の部 受付番号',
  DISCORD: 'Discord ユーザー名',
  OTHER: 'その他、イベント主催者に連絡したいことがあれば記載してください。'
};

/** コミュニティ参加申込フォームの列名 */
const COL_COMMUNITY = {
  MAIL: 'メールアドレス',
  NAME: 'コミュニティ名',
  URL: 'コミュニティのWebサイトURL',
  OWNER: '担当者名（ハンドルネーム可）',
  CONNPASS: '担当者 connpass ID',
  DISCORD: 'Discord ユーザー名',
  STYLE: '希望する参加形態（複数選択可）',
  LOGO: 'ロゴ・スライド等について',
  OTHER: 'その他、イベント運営チームに連絡したいことがあれば記載してください'
};

/** 企業スポンサー申込フォームの列名。補足の行がある質問はヘッダに改行ごと入る */
const COL_SPONSOR = {
  MAIL: 'メールアドレス',
  PLAN: '希望するプラン',
  COMPANY: '会社名（イベント告知ページに掲載します）',
  OWNER: 'ご担当者氏名',
  URL: '会社のWebサイトURL（イベント告知ページに掲載します）',
  DISCORD: 'ご担当者 Discord ユーザー名',
  TOKAI: '東海地方との関わりについて',
  BENEFIT: '希望する特典（複数可）\n※ イベント中の紹介・イベント告知ページでのロゴ掲載については必ず行います。\nその他特典については任意となります。',
  LOGO: 'イベント告知ページへ掲載するロゴについて',
  SLIDE: '【スライドの配信を希望される場合のみ】\nスライドについて',
  NOVELTY: '【当日配布 チラシ・ノベルティを希望される場合のみ】\n配布予定のチラシ・ノベルティの内容、配布方法',
  NOVELTY_DELIVERY: '【当日配布 チラシ・ノベルティを希望される場合のみ】\n配布予定のチラシ・ノベルティの受け渡し方法',
  OTHER: 'その他、NGK実行委員会へのご連絡事項がありましたら記載してください。'
};

/**
 * スクリプトプロパティを1つ読む
 *
 * @param {string} key プロパティ名
 * @return {string} 設定された値
 * @throws {Error} 未設定のとき
 */
function getProperty(key) {
  const value = PropertiesService.getScriptProperties().getProperty(key);
  if (!value) {
    throw new Error('スクリプトプロパティ ' + key + ' が設定されていません');
  }
  return value;
}

/**
 * 今の時刻を日本時間の文字列にする
 *
 * @return {string} `2027/01/16 12:00:00` の形
 */
function nowText() {
  return Utilities.formatDate(new Date(), 'Asia/Tokyo', 'yyyy/MM/dd HH:mm:ss');
}
