"""Discord の API を呼ぶ"""

from __future__ import annotations

import time
import urllib.parse
from typing import Any

import requests

API_BASE = "https://discord.com/api/v10"

# Discord は Bot からの通信にこの形の名乗りを求める。満たさないと入口で 403 になる
USER_AGENT = "DiscordBot (https://github.com/nagoya-godo-konshinkai/ngk2027s, 1.0)"

# 断られたときにやり直す回数。これを含めて何回呼ぶか
RETRY_LIMIT = 3

# 1項目に載せられる文字数の上限
FIELD_VALUE_LIMIT = 1024

# 埋め込み全体に載せられる文字数の上限。見出しと項目とフッターの合計で数える
EMBED_TOTAL_LIMIT = 6000

# 埋め込み全体で使ってよい文字数。上限そのままだと境目で弾かれるので少し下げる
EMBED_TOTAL_BUDGET = 5800

# 本文に載せられる文字数の上限
CONTENT_LIMIT = 2000

# 1度に取れるリアクションの人数
REACTION_PAGE_LIMIT = 100

# 1度に取れるメンバー検索の件数
MEMBER_SEARCH_LIMIT = 10

# スレッドの名前に使える文字数
THREAD_NAME_LIMIT = 100

# スレッドが自動で畳まれるまでの時間 (分)。Discord が受け付けるのは 60, 1440, 4320, 10080
THREAD_KEEP_MINUTES = 10080

# 切り詰めたことを示す文字列
TRUNCATED_MARK = "…(以下略。スプレッドシートを見てください)"

# 入りきらなかった項目の数を出す欄の名前
OMITTED_FIELD_NAME = "表示できなかった項目"


class DiscordError(RuntimeError):
    """Discord が 2xx 以外を返したときに投げる"""

    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status


class DiscordClient:
    """Discord の API を呼ぶ窓口"""

    def __init__(self, token: str, guild_id: str) -> None:
        """トークンとサーバーIDを渡して窓口を作る

        Args:
            token: Bot のトークン
            guild_id: サーバーのID
        """
        self._guild_id = guild_id
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bot {token}",
                "User-Agent": USER_AGENT,
            }
        )

    def call(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        """API を呼んで、返ってきた JSON を返す

        Args:
            method: HTTP のメソッド
            path: `/channels/...` で始まるパス
            payload: 本文に載せる値。不要なら None

        Returns:
            返ってきた JSON。本文が空なら None

        Raises:
            DiscordError: 2xx 以外が返ったとき
        """
        url = API_BASE + path
        response = None
        for attempt in range(RETRY_LIMIT):
            response = self._session.request(method, url, json=payload, timeout=30)
            if response.status_code != 429:
                break
            # 投稿が立て込むと一時的に断られる。Discord が指定した時間だけ待ってやり直す
            time.sleep(_retry_wait_seconds(response))
        assert response is not None
        if not response.ok:
            # ? より後ろは落とす。検索のパスには申込者が入力したユーザー名が入っている
            raise DiscordError(
                f"Discord {method} {path.split('?')[0]} が {response.status_code} を返しました: {response.text}",
                response.status_code,
            )
        return response.json() if response.content else None

    def post_message(
        self,
        channel_id: str,
        content: str,
        embed: dict[str, Any] | None = None,
        mention_user_id: str | None = None,
        mention_role_id: str | None = None,
    ) -> str:
        """チャンネルへ投稿し、その投稿のIDを返す

        フォームの入力がそのまま本文に入る。`@everyone` と書かれても飛ばないよう、
        メンションの相手を明示したものだけに限る

        Args:
            channel_id: 投稿先チャンネルのID
            content: 本文。埋め込みだけを出すときは空文字
            embed: 埋め込み。不要なら None
            mention_user_id: メンションを届ける相手。誰にも届けないなら None
            mention_role_id: メンションを届けるロール。届けないなら None

        Returns:
            投稿のID
        """
        payload: dict[str, Any] = {
            "allowed_mentions": {
                "parse": [],
                "users": [mention_user_id] if mention_user_id else [],
                "roles": [mention_role_id] if mention_role_id else [],
            }
        }
        if content:
            payload["content"] = content[:CONTENT_LIMIT]
        if embed:
            payload["embeds"] = [embed]
        message = self.call("POST", f"/channels/{channel_id}/messages", payload)
        return str(message["id"])

    def reaction_counts(self, channel_id: str, message_id: str, emojis: dict[str, str]) -> dict[str, int]:
        """投稿に付いた絵文字の数をまとめて数える

        絵文字ごとに投稿を取りに行くと、呼び出しが数倍になる

        Args:
            channel_id: チャンネルのID
            message_id: 投稿のID
            emojis: 呼び名から絵文字の設定値への対応

        Returns:
            呼び名から付いた人数への対応。1つも無ければ 0
        """
        message = self.call("GET", f"/channels/{channel_id}/messages/{message_id}")
        reactions = message.get("reactions") or []
        counts: dict[str, int] = {}
        for name, emoji in emojis.items():
            counts[name] = 0
            target = emoji_key(emoji)
            for reaction in reactions:
                if emoji_key_of(reaction["emoji"]) == target:
                    counts[name] = normal_reaction_count(reaction)
        return counts

    def has_reaction_from(self, channel_id: str, message_id: str, emoji: str, user_id: str) -> bool:
        """指定の絵文字を付けた人の中に、そのユーザーがいるかを返す

        1度に100人までしか返らないので、最後の人のIDを足がかりに続きを取りに行く
        その絵文字が1つも付いていないと 404 が返る。その場合だけ付けていない扱いにする

        Args:
            channel_id: チャンネルのID
            message_id: 投稿のID
            emoji: `name:id` 形式のカスタム絵文字、または絵文字そのもの
            user_id: 探すユーザーのID

        Returns:
            付けていれば True

        Raises:
            DiscordError: 404 以外で失敗したとき
        """
        base = f"/channels/{channel_id}/messages/{message_id}/reactions/{emoji_for_api(emoji)}"
        after = ""
        while True:
            path = f"{base}?limit={REACTION_PAGE_LIMIT}"
            if after:
                path = f"{path}&after={after}"
            try:
                users = self.call("GET", path) or []
            except DiscordError as error:
                if error.status == 404:
                    return False
                raise
            if any(user["id"] == user_id for user in users):
                return True
            if len(users) < REACTION_PAGE_LIMIT:
                return False
            after = str(users[-1]["id"])

    def start_thread(self, channel_id: str, message_id: str, name: str) -> str:
        """投稿にスレッドをぶら下げて、そのIDを返す

        スレッドのIDは元の投稿のIDと同じ扱いで、投稿先のチャンネルIDとして使える

        Args:
            channel_id: 元の投稿があるチャンネルのID
            message_id: 元の投稿のID
            name: スレッドの名前

        Returns:
            作ったスレッドのID
        """
        payload = {"name": name[:THREAD_NAME_LIMIT], "auto_archive_duration": THREAD_KEEP_MINUTES}
        thread = self.call("POST", f"/channels/{channel_id}/messages/{message_id}/threads", payload)
        return str(thread["id"])

    def add_reaction(self, channel_id: str, message_id: str, emoji: str) -> None:
        """投稿に絵文字を付ける

        Args:
            channel_id: チャンネルのID
            message_id: 投稿のID
            emoji: `name:id` 形式のカスタム絵文字、または絵文字そのもの
        """
        path = f"/channels/{channel_id}/messages/{message_id}/reactions/{emoji_for_api(emoji)}/@me"
        self.call("PUT", path)

    def find_member_id(self, username: str) -> str | None:
        """ユーザー名からサーバーのメンバーを1人見つける

        突き合わせるのはユーザー名だけ。表示名とサーバーでのニックネームは誰でも同じ文字列に
        変えられるので、一致を見ると別人にロールが付く

        Args:
            username: フォームに入力されたユーザー名

        Returns:
            見つかったユーザーのID。見つからなければ None
        """
        name = str(username or "").strip().lstrip("@")
        if not name:
            return None
        query = urllib.parse.quote(name)
        path = f"/guilds/{self._guild_id}/members/search?limit={MEMBER_SEARCH_LIMIT}&query={query}"
        members = self.call("GET", path) or []
        lowered = name.lower()
        for member in members:
            found = member["user"].get("username")
            if found and str(found).lower() == lowered:
                return str(member["user"]["id"])
        return None

    def add_role(self, user_id: str, role_id: str) -> None:
        """メンバーにロールを付ける

        Args:
            user_id: 対象のユーザーID
            role_id: 付けるロールのID
        """
        self.call("PUT", f"/guilds/{self._guild_id}/members/{user_id}/roles/{role_id}")

    def message_link(self, channel_id: str, message_id: str) -> str:
        """投稿を開くリンクを組み立てる

        Args:
            channel_id: チャンネルのID
            message_id: 投稿のID

        Returns:
            ブラウザとアプリのどちらでも開けるリンク
        """
        return f"https://discord.com/channels/{self._guild_id}/{channel_id}/{message_id}"


def _retry_wait_seconds(response: requests.Response) -> float:
    """断られたときに待つ長さを返す

    Args:
        response: 429 を返した応答

    Returns:
        待つ秒数
    """
    try:
        seconds = float(response.json().get("retry_after", 0))
    except (ValueError, AttributeError):
        seconds = 0.0
    if seconds <= 0:
        return 2.0
    return min(seconds + 0.2, 10.0)


def emoji_for_content(emoji: str) -> str:
    """カスタム絵文字を本文へ埋め込む形に変える

    本文では <:name:id> と書かないと画像にならず、:name: のまま文字で出る

    Args:
        emoji: `name:id` 形式のカスタム絵文字、または絵文字そのもの

    Returns:
        本文に書ける形
    """
    return f"<:{emoji}>" if ":" in emoji else emoji


def emoji_for_api(emoji: str) -> str:
    """絵文字をリアクションのAPIパスに入れる形に変える

    Args:
        emoji: `name:id` 形式のカスタム絵文字、または絵文字そのもの

    Returns:
        URLエンコードした文字列
    """
    return urllib.parse.quote(emoji)


def emoji_key(emoji: str) -> str:
    """設定値の絵文字を、APIが返す絵文字と突き合わせるキーに変える

    カスタム絵文字はIDで、標準の絵文字は文字そのもので見分ける

    Args:
        emoji: `name:id` 形式のカスタム絵文字、または絵文字そのもの

    Returns:
        突き合わせに使う文字列
    """
    parts = emoji.split(":")
    return parts[1] if len(parts) == 2 else emoji


def emoji_key_of(emoji: dict[str, Any]) -> str:
    """APIが返した絵文字を、設定値と突き合わせるキーに変える

    Args:
        emoji: APIが返した emoji オブジェクト

    Returns:
        突き合わせに使う文字列
    """
    return str(emoji["id"]) if emoji.get("id") else str(emoji["name"])


def role_ref(role_id: str) -> str:
    """ロールIDを本文中のメンションに変える

    Args:
        role_id: ロールのID

    Returns:
        本文に書ける形
    """
    return f"<@&{role_id}>"


def channel_ref(channel_id: str) -> str:
    """チャンネルIDを本文中のチャンネル参照に変える

    本文に #名前 と書いても文字のままなので、<#id> に変えてリンクにする

    Args:
        channel_id: チャンネルのID

    Returns:
        本文に書ける形
    """
    return f"<#{channel_id}>"


def build_embed(title: str, pairs: list[tuple[str, Any]], footer: str, color: int) -> dict[str, Any]:
    """項目の組から埋め込みを組み立てる

    値が空の項目は出さない。1項目は1024文字、全体では6000文字までしか載せられない
    どちらかを超えると投稿そのものが断られるので、収まるところまで値を切る

    Args:
        title: 見出し
        pairs: 項目名と値の組
        footer: 下に出す説明
        color: 左端に出る帯の色。`0x5865F2` の形

    Returns:
        Discord へ渡す埋め込み
    """
    filled = [(name, value) for name, value in pairs if value not in ("", None)]
    budget = EMBED_TOTAL_BUDGET - len(title) - len(footer) - len(OMITTED_FIELD_NAME) - 40
    fields: list[dict[str, Any]] = []
    omitted = 0
    for index, (name, value) in enumerate(filled):
        if budget - len(name) <= len(TRUNCATED_MARK):
            omitted = len(filled) - index
            break
        budget -= len(name)
        text = str(value)[:FIELD_VALUE_LIMIT]
        if len(text) > budget:
            text = text[: budget - len(TRUNCATED_MARK)] + TRUNCATED_MARK
        budget -= len(text)
        fields.append({"name": name, "value": text, "inline": False})
    if omitted:
        # 入りきらずに消えた項目があることを出す。黙って消すと、全部出ていると思って承認される
        fields.append(
            {
                "name": OMITTED_FIELD_NAME,
                "value": f"{omitted}件。スプレッドシートを見てください",
                "inline": False,
            }
        )
    return {"title": title, "fields": fields, "footer": {"text": footer}, "color": color}


def normal_reaction_count(reaction: dict[str, Any]) -> int:
    """絵文字を付けた人数を返す

    count は通常とスーパーの合計なので、1人が両方を付けると2になる
    スーパーを除いた数が分かるときはそちらを使う

    Args:
        reaction: APIが返した reaction オブジェクト

    Returns:
        付けた人数
    """
    details = reaction.get("count_details") or {}
    return int(details.get("normal", reaction["count"]))


def escape_embed_value(text: str) -> str:
    """埋め込みの項目に出す値から、書式の記号を打ち消す

    `n_kats_` のようなユーザー名が斜体になり、記号が消えて読めなくなる
    メンションは埋め込みの中では通知を飛ばさないので、`@` と `#` は打ち消さない

    Args:
        text: 申込者が書いた値

    Returns:
        記号を打ち消した文字列
    """
    cut = str(text)
    for mark in ("\\", "*", "_", "~", "`", "|", "[", "]", ">"):
        cut = cut.replace(mark, "\\" + mark)
    return cut


def escape_markdown(text: str, limit: int) -> str:
    """申込者が書いた文字を、見た目の飾りにならない形にして短く切る

    一般向けチャンネルにそのまま出すと、太字やリンクとして描画される

    Args:
        text: もとの文字列
        limit: 残す文字数

    Returns:
        飾りの記号を打ち消し、長さを切り詰めた文字列
    """
    cut = str(text)[:limit]
    for mark in ("\\", "*", "_", "~", "`", "|", ">", "[", "]", "(", ")", "#", "@"):
        cut = cut.replace(mark, "\\" + mark)
    return cut
