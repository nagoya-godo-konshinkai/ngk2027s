"""環境変数から設定を読む"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """環境変数から読んだ設定をまとめたもの"""

    discord_token: str
    guild_id: str
    staff_channels: dict[str, str]
    public_channels: dict[str, str]
    log_channel: str
    ref_channels: dict[str, str]
    staff_role: str
    emojis: dict[str, str]
    roles: dict[str, str]
    spreadsheet_id: str
    service_account_file: str
    poll_interval_seconds: int
    only_numbers: frozenset[str]


def _required(name: str) -> str:
    """環境変数を1つ読む。未設定なら例外を投げる

    Args:
        name: 環境変数の名前

    Returns:
        設定された値
    """
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"環境変数 {name} が設定されていません")
    return value


def load_settings() -> Settings:
    """環境変数をすべて読んで設定を組み立てる

    Returns:
        組み立てた設定

    Raises:
        RuntimeError: 足りない環境変数があるとき
    """
    return Settings(
        discord_token=_required("DISCORD_BOT_TOKEN"),
        guild_id=_required("DISCORD_GUILD_ID"),
        staff_channels={
            "LT": _required("STAFF_CHANNEL_LT"),
            "COMMUNITY": _required("STAFF_CHANNEL_COMMUNITY"),
            "SPONSOR": _required("STAFF_CHANNEL_SPONSOR"),
        },
        public_channels={
            "LT": _required("PUBLIC_CHANNEL_LT"),
            "COMMUNITY": _required("PUBLIC_CHANNEL_COMMUNITY"),
        },
        log_channel=_required("LOG_CHANNEL_ID"),
        ref_channels={
            "lt_toudan": _required("CHANNEL_LT_TOUDAN"),
            "oshirase": _required("CHANNEL_OSHIRASE"),
            "community_sanka": _required("CHANNEL_COMMUNITY_SANKA"),
        },
        staff_role=_required("STAFF_ROLE_ID"),
        emojis={
            "yosasou": _required("EMOJI_YOSASOU"),
            "horyu": _required("EMOJI_HORYU"),
            "mail_done": _required("EMOJI_MAIL_DONE"),
            "discord_done": _required("EMOJI_DISCORD_DONE"),
            "role_done": _required("EMOJI_ROLE_DONE"),
            "ok": _required("EMOJI_OK"),
            "ok_done": _required("EMOJI_OK_DONE"),
        },
        roles={
            "lt_ippan": _required("ROLE_LT_IPPAN"),
            "community": _required("ROLE_COMMUNITY"),
            "community_year": _required("ROLE_COMMUNITY_YEAR"),
            "community_lt": _required("ROLE_COMMUNITY_LT"),
            "sponsor": _required("ROLE_SPONSOR"),
            "sponsor_year": _required("ROLE_SPONSOR_YEAR"),
            "sponsor_lt": _required("ROLE_SPONSOR_LT"),
        },
        spreadsheet_id=_required("SPREADSHEET_ID"),
        service_account_file=_required("GOOGLE_SERVICE_ACCOUNT_FILE"),
        poll_interval_seconds=int(os.environ.get("POLL_INTERVAL_SECONDS", "300")),
        only_numbers=_number_filter(),
    )


def _number_filter() -> frozenset[str]:
    """試すときだけ処理する受付番号を読む

    空なら全部の行を処理する。値があれば、その受付番号の行だけを処理する

    Returns:
        受付番号の集合。未設定なら空
    """
    raw = os.environ.get("ONLY_NUMBERS", "").strip()
    if not raw:
        return frozenset()
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


# 回答シートの名前
SHEET_NAMES: dict[str, str] = {
    "LT": "LT発表申込",
    "COMMUNITY": "コミュニティ参加申込",
    "SPONSOR": "企業スポンサー申込",
}

# 最終実行時刻を書くシートの名前
STATE_SHEET_NAME = "実行状態"

# 承認に必要な :yosasou: の数
APPROVAL_THRESHOLD = 2

# 一般向けチャンネルに差し込む、申込者が書いた文字の長さの上限
PUBLIC_TEXT_LIMIT = 100

# 申込の埋め込みの左端に出る帯の色。フォームごとに変えて、ひと目で見分けられるようにする
EMBED_COLORS: dict[str, int] = {
    "LT": 0x5865F2,
    "COMMUNITY": 0x57F287,
    "SPONSOR": 0xFEE75C,
}

# スクリプトが書き込む管理列。GAS 側の ADMIN_COLUMNS と同じ並びにする
ADMIN_COLUMNS: list[str] = [
    "受付番号",
    "受付メール送信",
    "discord自動投稿",
    "申込投稿ID",
    "承認確認",
    "採択メール送信",
    "採択メール確認",
    "採択discord送信",
    "採択投稿ID",
    "DiscordユーザーID",
    "ユーザー未特定通知",
    "OKリアクション確認",
    "ロール付与",
]

# LT発表申込フォームの列名
COL_LT: dict[str, str] = {
    "mail": "メールアドレス",
    "kind": "申込み種別",
    "speaker": "発表者名",
    "speaker_kana": "発表者名のよみかた（ひらがな）",
    "title": "LTタイトル",
    "title_kana": "LTタイトルのよみかた（ひらがな）",
    "summary": "LT概要",
    "count": "NGKでのLT発表は何回目ですか",
    "bad_time": "イベント当日(2027/01/16)に都合の悪い時間帯があれば記載してください。",
    "community": "コミュニティ名",
    "community_number": "コミュニティ参加 申し込み番号",
    "sponsor": "スポンサー 企業名",
    "connpass": "connpass ID",
    "connpass_number": "connpass 昼の部 受付番号",
    "discord": "Discord ユーザー名",
    "other": "その他、イベント主催者に連絡したいことがあれば記載してください。",
}

# コミュニティ参加申込フォームの列名
COL_COMMUNITY: dict[str, str] = {
    "mail": "メールアドレス",
    "name": "コミュニティ名",
    "url": "コミュニティのWebサイトURL",
    "owner": "担当者名（ハンドルネーム可）",
    "connpass": "担当者 connpass ID",
    "discord": "Discord ユーザー名",
    "style": "希望する参加形態（複数選択可）",
    "logo": "ロゴ・スライド等について",
    "other": "その他、イベント運営チームに連絡したいことがあれば記載してください",
}

# 企業スポンサー申込フォームの列名。補足の行がある質問はヘッダに改行ごと入る
COL_SPONSOR: dict[str, str] = {
    "mail": "メールアドレス",
    "plan": "希望するプラン",
    "company": "会社名（イベント告知ページに掲載します）",
    "owner": "ご担当者氏名",
    "url": "会社のWebサイトURL（イベント告知ページに掲載します）",
    "discord": "ご担当者 Discord ユーザー名",
    "tokai": "東海地方との関わりについて",
    "benefit": (
        "希望する特典（複数可）\n"
        "※ イベント中の紹介・イベント告知ページでのロゴ掲載については必ず行います。\n"
        "その他特典については任意となります。"
    ),
    "logo": "イベント告知ページへ掲載するロゴについて",
    "slide": "【スライドの配信を希望される場合のみ】\nスライドについて",
    "novelty": "【当日配布 チラシ・ノベルティを希望される場合のみ】\n配布予定のチラシ・ノベルティの内容、配布方法",
    "novelty_delivery": "【当日配布 チラシ・ノベルティを希望される場合のみ】\n配布予定のチラシ・ノベルティの受け渡し方法",
    "other": "その他、NGK実行委員会へのご連絡事項がありましたら記載してください。",
}

# 請求先の5列。どの文面でも使わない
SPONSOR_INVOICE_COLUMNS: list[str] = [
    "請求書に記載する請求先情報/担当者氏名",
    "請求書に記載する請求先情報/部署名",
    "請求書に記載する請求先情報/住所",
    "請求書送付先/メールアドレス",
    "請求書送付先/担当者氏名",
]

# コミュニティ参加の希望形態を見分ける文字列
COMMUNITY_STYLE_KEYWORDS: dict[str, str] = {
    "logo": "ロゴ掲載",
    "slide": "スライド",
    "lt": "LT",
}

# 「ロゴ・スライド等について」で Discord でやりとりすると答えたことを見分ける文字列
COMMUNITY_CONTACT_DISCORD = "Discord"

# 前回いただいたスポンサーのロゴの置き場所。会社名はフォームの入力と完全に一致させる
# 「以前と同じでOK」を選んだ会社がここに無いと、下書きに見つからない旨が出る
# 毎年、新しく申し込んだ会社の分を足す
SPONSOR_LOGO_URLS: dict[str, str] = {
    "合同会社コトイコンサルタンシー": "https://nagoya-godo-konshinkai.github.io/ngk2026s/img/sponsor/kxc.png",
    "デンキヤギ株式会社": "https://nagoya-godo-konshinkai.github.io/ngk2022s/img/sponsor/denkiyagi.png",
    "有限会社来栖川電算": "https://nagoya-godo-konshinkai.github.io/ngk2026s/img/sponsor/kci.png",
    "OSPN(Open Source People Network)": "https://nagoya-godo-konshinkai.github.io/ngk2026s/img/sponsor/ospn.png",
    "クラスメソッド株式会社": "https://nagoya-godo-konshinkai.github.io/ngk2026s/img/sponsor/classmethod.png",
    "株式会社SmartHR": "https://nagoya-godo-konshinkai.github.io/ngk2026s/img/sponsor/smarthr.png",
}

# 承認したときに付けるロールの、設定上の名前
# 年をまたいで残すロール (/ALL) と、その年だけのロール (/2027S) の両方を付ける
ROLE_KEYS_BY_KIND: dict[str, list[str]] = {
    "一般LT": ["lt_ippan"],
    "コミュニティLT": ["community", "community_year", "community_lt"],
    "スポンサーLT": ["sponsor", "sponsor_year", "sponsor_lt"],
    "コミュニティ参加": ["community", "community_year"],
}

# スタッフへの知らせに出すロールの表示名。ROLE_KEYS_BY_KIND と同じ並びにする
ROLE_NAMES_BY_KIND: dict[str, str] = {
    "一般LT": "一般LT登壇者/2027S",
    "コミュニティLT": "コミュニティ/ALL、コミュニティ/2027S、コミュニティLT登壇者/2027S",
    "スポンサーLT": "スポンサー/ALL、スポンサー/2027S、スポンサーLT登壇者/2027S",
    "コミュニティ参加": "コミュニティ/ALL、コミュニティ/2027S",
}
