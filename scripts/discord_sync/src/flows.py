"""申し込みの処理

標準出力には受付番号と処理名だけを出す。氏名やメールアドレスは Discord のログ用チャンネルにも出さない
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from . import config, messages, sponsor_mail
from .config import Settings
from .discord_api import (
    DiscordClient,
    DiscordError,
    build_embed,
    channel_ref,
    emoji_for_content,
    escape_embed_value,
    escape_markdown,
    role_ref,
)
from .sheets import Sheet, value_of

JST = ZoneInfo("Asia/Tokyo")

# 申込者がサーバーに居ないことの知らせの名前
MEMBER_NOT_FOUND = "ユーザー未特定通知"

# DiscordのユーザーIDの桁数。17桁から始まり、増える見込みがあるので上は広めに取る
USER_ID_DIGITS = range(17, 21)

# 承認の決まりを載せる、埋め込みの最後の項目の名前
NOTE_FIELD_NAME = "この後の流れ"

# ログ用チャンネルに出す名前の長さの上限。1行が長くなると流れが追えなくなる
NAME_LIMIT = 40

# 下書きを分けて出すときの、1つあたりの文字数。本文の上限2000字から囲みと見出しの分を引く
DRAFT_CHUNK_LIMIT = 1800


def now_text() -> str:
    """今の時刻を日本時間の文字列にする

    Returns:
        `2027/01/16 12:00:00` の形
    """
    return datetime.now(JST).strftime("%Y/%m/%d %H:%M:%S")


class Logger:
    """作業の記録をログ用チャンネルに残す"""

    def __init__(self, client: DiscordClient, channel_id: str, staff_role: str) -> None:
        """投稿先を決める

        Args:
            client: Discord の窓口
            channel_id: ログ用チャンネルのID
            staff_role: 呼び出すスタッフのロールのID
        """
        self._client = client
        self._channel_id = channel_id
        self._staff_role = staff_role

    def record(  # noqa: PLR0913
        self,
        number: str,
        step: str,
        detail: str = "",
        call_staff: bool = False,
        who: str = "",
    ) -> None:
        """1行を記録する

        残せなかったときは例外を投げる。記録が欠けたまま動き続けると、何が済んだか追えなくなる
        名前はログ用チャンネルにだけ出す。標準出力はPCのディスクに残るので受付番号で追う

        Args:
            number: 受付番号
            step: 何をしたか
            detail: 投稿のリンクなど。無ければ空文字
            call_staff: スタッフのロールを呼び出すなら True。手を動かす必要があるときだけ
            who: 誰についての記録か。無ければ空文字
        """
        print(f"{number} {step}", flush=True)
        text = f"`{number}` {step}"
        if who:
            text = f"`{number}` {who} {step}"
        if detail:
            text = f"{text} {detail}"
        if not call_staff:
            self._client.post_message(self._channel_id, text)
            return
        self._client.post_message(
            self._channel_id,
            f"{role_ref(self._staff_role)}\n{text}",
            mention_role_id=self._staff_role,
        )


@dataclass(frozen=True)
class Context:
    """処理の間ずっと使うものをまとめたもの

    `notified` は、同じ知らせを5分おきに出し続けないための覚え書き
    コンテナを入れ直すと忘れるので、消えて困る記録はシートの列に書く
    """

    settings: Settings
    client: DiscordClient
    logger: Logger
    notified: set[tuple[str, str]] = field(default_factory=set)

    def notify_once(self, number: str, step: str) -> bool:
        """その受付番号とその処理について、まだ知らせていなければ True を返す

        Args:
            number: 受付番号
            step: 処理の名前

        Returns:
            今回が初めてなら True
        """
        key = (number, step)
        if key in self.notified:
            return False
        self.notified.add(key)
        return True


def report_failure(ctx: Context, channel_id: str, number: str, step: str, error: Any, link: str) -> bool:
    """処理が止まったことをスタッフ専用チャンネルとログに知らせる

    知らせること自体に失敗しても、ここでは投げ直さない。呼び出し元が失敗として数える

    Args:
        ctx: 処理の文脈
        channel_id: 投稿先チャンネルのID
        number: 受付番号
        step: 失敗した処理の名前
        error: 起きたエラー
        link: 元の申し込み投稿へのリンク。まだ無ければ空文字

    Returns:
        知らせられたら True
    """
    content = messages.fill(
        messages.POST_FAILED,
        {
            "受付番号": number,
            "失敗した処理": step,
            "エラー内容": str(error)[:500],
            "元投稿リンク": link,
            "対応": messages.FAILURE_ACTIONS.get(step, messages.FAILURE_ACTION_DEFAULT),
        },
    )
    return tell_staff(ctx, channel_id, number, f"{step}に失敗しました", content, str(error)[:200])


def tell_staff(  # noqa: PLR0913
    ctx: Context, channel_id: str, number: str, step: str, content: str, detail: str, who: str = ""
) -> bool:
    """スタッフ専用チャンネルとログ用チャンネルの両方へ知らせる

    片方が通らなくても、もう片方には残す。チャンネルごとに権限が違うため、
    一方だけ投稿できない状況が起こる

    Args:
        ctx: 処理の文脈
        channel_id: スタッフ専用チャンネルのID
        number: 受付番号
        step: 何が起きたかの名前
        content: スタッフ専用チャンネルへ出す本文
        detail: ログ用チャンネルに添える短い説明
        who: 誰についての知らせか。無ければ空文字

    Returns:
        どちらか一方にでも残せたら True
    """
    posted = True
    try:
        # 人が見て手を動かさないと進まない。呼び出しを付ける
        post_to_staff(ctx, channel_id, content, None, True)
    except Exception as error:  # noqa: BLE001
        posted = False
        print(f"{number} スタッフ専用チャンネルへ知らせられませんでした: {error}", flush=True)
    logged = True
    try:
        note = detail if posted else f"{detail} / スタッフ専用チャンネルへは出せませんでした"
        # 人が手を動かす必要があるので、ログ用チャンネルでも呼び出す
        ctx.logger.record(number, step, note, call_staff=True, who=who)
    except Exception as error:  # noqa: BLE001
        logged = False
        print(f"{number} ログ用チャンネルへ知らせられませんでした: {error}", flush=True)
    return posted or logged


def notice_once(ctx: Context, channel_id: str, number: str, name: str, detail: str, link: str) -> None:
    """止まってはいないが見てほしいことを、1度だけスタッフ専用チャンネルに知らせる

    知らせられなかったときは覚え書きを取り消す。覚えたまま失敗すると、その知らせは二度と出ない

    Args:
        ctx: 処理の文脈
        channel_id: 投稿先チャンネルのID
        number: 受付番号
        name: 何が起きたかの名前
        detail: スタッフに読んでもらう説明
        link: 元の申し込み投稿へのリンク。まだ無ければ空文字
    """
    if not ctx.notify_once(number, name):
        return
    content = messages.fill(
        messages.POST_NOTICE,
        {"受付番号": number, "知らせの名前": name, "説明": detail, "元投稿リンク": link},
    )
    if not tell_staff(ctx, channel_id, number, name, content, ""):
        # どこにも残せなかった。覚えたままにすると、この知らせが二度と出ない
        ctx.notified.discard((number, name))


def skip_row(ctx: Context, number: str) -> bool:
    """試すときに、その行を飛ばすかを返す

    `ONLY_NUMBERS` を設定している間は、挙げた受付番号の行しか処理しない
    本番に混ざった申し込みへ、試している途中の連絡が飛ぶのを防ぐ

    Args:
        ctx: 処理の文脈
        number: 受付番号

    Returns:
        飛ばすなら True
    """
    if not ctx.settings.only_numbers:
        return False
    return number not in ctx.settings.only_numbers


def post_to_staff(
    ctx: Context, channel_id: str, content: str, embed: dict[str, Any] | None, call_staff: bool
) -> str:
    """スタッフ専用チャンネルへ投稿する

    呼び出しを付けるのは、人が手を動かさないと進まないときだけ
    新しい申し込み、失敗、確認の依頼が当たる。処理が進んだだけの記録では鳴らさない

    Args:
        ctx: 処理の文脈
        channel_id: 投稿先チャンネルのID
        content: 本文。埋め込みだけを出すときは空文字
        embed: 埋め込み。不要なら None
        call_staff: スタッフのロールを呼び出すなら True

    Returns:
        投稿のID
    """
    if not call_staff:
        return ctx.client.post_message(channel_id, content, embed)
    role = ctx.settings.staff_role
    body = f"{role_ref(role)}\n{content}" if content else role_ref(role)
    return ctx.client.post_message(channel_id, body, embed, mention_role_id=role)


def handle_lost_post(ctx: Context, channel_id: str, number: str, error: Exception) -> bool:
    """スタッフ専用チャンネルの投稿が消えていたら、1度だけ知らせる

    消された投稿を相手にし続けると、同じ失敗が5分おきに積み上がる

    Args:
        ctx: 処理の文脈
        channel_id: スタッフ専用チャンネルのID
        number: 受付番号
        error: 起きたエラー

    Returns:
        投稿が見つからなかったときに True
    """
    if not isinstance(error, DiscordError) or error.status != 404:
        return False
    notice_once(ctx, channel_id, number, "申込投稿が見つかりません", messages.HINT_POST_LOST, "")
    return True


def post_sponsor_draft(
    ctx: Context, channel_id: str, message_id: str, number: str, record: dict[str, str]
) -> None:
    """企業スポンサーへ手で送るメールの下書きを、申込投稿のスレッドに出す

    申し込みの内容で要る節が変わるので、人が選ぶと抜けが出る
    2000字を超えると投稿できないので、節の切れ目で分けて続けて出す

    Args:
        ctx: 処理の文脈
        channel_id: 申込投稿があるチャンネルのID
        message_id: 申込投稿のID
        number: 受付番号
        record: その行の値
    """
    company = value_of(record, config.COL_SPONSOR, "company")
    thread_id = ctx.client.start_thread(channel_id, message_id, f"{number} {company}")
    draft = sponsor_mail.build(record)
    chunks: list[str] = []
    current = ""
    for part in draft.split("\n\n"):
        candidate = f"{current}\n\n{part}" if current else part
        if len(candidate) > DRAFT_CHUNK_LIMIT and current:
            chunks.append(current)
            current = part
            continue
        current = candidate
    if current:
        chunks.append(current)

    total = len(chunks)
    for index, chunk in enumerate(chunks, start=1):
        head = "送付用の下書き" if total == 1 else f"送付用の下書き ({index}/{total})"
        ctx.client.post_message(thread_id, f"{head}\n```\n{chunk}\n```")


def display_name(record: dict[str, str], form_key: str) -> str:
    """ログ用チャンネルに出す、その申し込みの名前を返す

    誰についての記録かが分かるようにする。メールアドレスは出さない
    Discordアカウントを特定できた行には、名前のうしろにメンションを足す

    Args:
        record: その行の値
        form_key: 'LT' か 'COMMUNITY' か 'SPONSOR'

    Returns:
        発表者名、コミュニティ名と担当者名、または会社名。特定済みならメンション付き
    """
    if form_key == "LT":
        name = value_of(record, config.COL_LT, "speaker")
    elif form_key == "SPONSOR":
        name = value_of(record, config.COL_SPONSOR, "company")
    else:
        community = value_of(record, config.COL_COMMUNITY, "name")
        owner = value_of(record, config.COL_COMMUNITY, "owner")
        name = f"{community} / {owner}" if community and owner else community or owner
    user_id = record.get("DiscordユーザーID", "")
    if looks_like_user_id(user_id):
        # 本人を特定できた行だけ。チャンネルに居なくても表示名で出る
        # メンションは切らない。途中で切れると、ただの文字列として出る
        return f"{name[:NAME_LIMIT]} <@{user_id}>"
    return name[:NAME_LIMIT]


def role_ids_for(settings: Settings, kind: str) -> list[str]:
    """承認したときに付けるロールのIDを返す

    Args:
        settings: 設定
        kind: 申込み種別、または「コミュニティ参加」

    Returns:
        ロールIDの配列。対応が無ければ空
    """
    return [settings.roles[key] for key in config.ROLE_KEYS_BY_KIND.get(kind, [])]


def role_names_for(kind: str) -> str:
    """承認したときに付けるロールの名前を返す

    Args:
        kind: 申込み種別、または「コミュニティ参加」

    Returns:
        読点で並べたロール名
    """
    return config.ROLE_NAMES_BY_KIND.get(kind, "")


def field_value(record: dict[str, str], columns: dict[str, str], key: str) -> str:
    """埋め込みの項目に出す、申込者が書いた値を取り出す

    そのまま出すと `n_kats_` のようなユーザー名が斜体になり、記号が消える

    Args:
        record: その行の値
        columns: 設定上の名前から列名への対応
        key: 設定上の名前

    Returns:
        書式の記号を打ち消した値
    """
    return escape_embed_value(value_of(record, columns, key))


def join_with_kana(name: str, kana: str) -> str:
    """名前とよみかたを1つの文字列にする

    Args:
        name: 名前
        kana: よみかた

    Returns:
        `名前（よみかた）` の形。名前が空なら空文字
    """
    if not name:
        return ""
    return f"{name}（{kana}）" if kana else name


def staff_note(ctx: Context, kind: str) -> str:
    """スタッフ専用チャンネルの投稿に出す、承認の決まりの説明を作る

    Args:
        ctx: 処理の文脈
        kind: 申込み種別、または「コミュニティ参加」

    Returns:
        投稿の本文に載せる説明
    """
    return messages.fill(
        messages.STAFF_POST_NOTE,
        {
            "よさそう": emoji_for_content(ctx.settings.emojis["yosasou"]),
            "保留": emoji_for_content(ctx.settings.emojis["horyu"]),
            "必要数": str(config.APPROVAL_THRESHOLD),
            "ロール名": role_names_for(kind),
        },
    )


def lt_embed(record: dict[str, str], number: str, note: str) -> dict[str, Any]:
    """LT発表申込の埋め込みを組み立てる

    承認の決まりは最後の項目に置く。申し込みの内容より前に出ると、何の投稿か分かりにくい

    Args:
        record: その行の値
        number: 受付番号
        note: 承認の決まりの説明

    Returns:
        Discord へ渡す埋め込み
    """
    columns = config.COL_LT
    return build_embed(
        "📋 LT発表申込を受け付けました！",
        [
            ("受付番号", number),
            ("申込み種別", field_value(record, columns, "kind")),
            (
                "発表者名",
                join_with_kana(
                    field_value(record, columns, "speaker"), field_value(record, columns, "speaker_kana")
                ),
            ),
            (
                "LTタイトル",
                join_with_kana(
                    field_value(record, columns, "title"), field_value(record, columns, "title_kana")
                ),
            ),
            ("LT概要", field_value(record, columns, "summary")),
            ("NGKでのLT発表回数", field_value(record, columns, "count")),
            ("コミュニティ名", field_value(record, columns, "community")),
            ("コミュニティ受付番号", field_value(record, columns, "community_number")),
            ("スポンサー企業名", field_value(record, columns, "sponsor")),
            ("connpass ID", field_value(record, columns, "connpass")),
            ("connpass 昼の部受付番号", field_value(record, columns, "connpass_number")),
            ("Discordユーザー名", field_value(record, columns, "discord")),
            ("都合の悪い時間帯", field_value(record, columns, "bad_time")),
            ("その他連絡", field_value(record, columns, "other")),
            (NOTE_FIELD_NAME, note),
        ],
        "NGK2027S LT発表申込フォームより自動送信",
        config.EMBED_COLORS["LT"],
    )


def community_embed(record: dict[str, str], number: str, note: str) -> dict[str, Any]:
    """コミュニティ参加申込の埋め込みを組み立てる

    Args:
        record: その行の値
        number: 受付番号
        note: 承認の決まりの説明

    Returns:
        Discord へ渡す埋め込み
    """
    columns = config.COL_COMMUNITY
    return build_embed(
        "🤝 コミュニティ参加申込を受け付けました！",
        [
            ("受付番号", number),
            ("コミュニティ名", field_value(record, columns, "name")),
            ("WebサイトURL", field_value(record, columns, "url")),
            ("担当者名", field_value(record, columns, "owner")),
            ("希望する参加形態", field_value(record, columns, "style")),
            ("ロゴ・スライド等", field_value(record, columns, "logo")),
            ("connpass ID", field_value(record, columns, "connpass")),
            ("Discordユーザー名", field_value(record, columns, "discord")),
            ("その他連絡", field_value(record, columns, "other")),
            (NOTE_FIELD_NAME, note),
        ],
        "NGK2027S コミュニティ参加申込フォームより自動送信",
        config.EMBED_COLORS["COMMUNITY"],
    )


def sponsor_embed(record: dict[str, str], number: str) -> dict[str, Any]:
    """企業スポンサー申込の埋め込みを組み立てる

    請求先の5列は載せない。スプレッドシートで確認する
    """
    columns = config.COL_SPONSOR
    return build_embed(
        "💰 企業スポンサー申込を受け付けました！",
        [
            ("受付番号", number),
            ("会社名", field_value(record, columns, "company")),
            ("希望するプラン", field_value(record, columns, "plan")),
            ("ご担当者氏名", field_value(record, columns, "owner")),
            ("会社WebサイトURL", field_value(record, columns, "url")),
            ("Discordユーザー名", field_value(record, columns, "discord")),
            ("東海地方との関わり", field_value(record, columns, "tokai")),
            ("希望する特典", field_value(record, columns, "benefit")),
            ("ロゴについて", field_value(record, columns, "logo")),
            ("スライドについて", field_value(record, columns, "slide")),
            ("チラシ・ノベルティの内容", field_value(record, columns, "novelty")),
            ("チラシ・ノベルティの受け渡し方法", field_value(record, columns, "novelty_delivery")),
            ("その他連絡", field_value(record, columns, "other")),
            ("請求先", messages.STAFF_POST_INVOICE_SPONSOR),
            (NOTE_FIELD_NAME, messages.STAFF_POST_NOTE_SPONSOR),
        ],
        "NGK2027S 企業スポンサー申込フォームより自動送信",
        config.EMBED_COLORS["SPONSOR"],
    )


def post_new_submissions(ctx: Context, sheet: Sheet, form_key: str) -> list[str]:
    """まだ投稿していない申し込みをスタッフ専用チャンネルへ出す

    Args:
        ctx: 処理の文脈
        sheet: 対象のシート
        form_key: 'LT' か 'COMMUNITY' か 'SPONSOR'

    Returns:
        失敗した処理の説明
    """
    failures: list[str] = []
    channel_id = ctx.settings.staff_channels[form_key]
    for row, record in sheet.rows():
        number = record.get("受付番号", "")
        if not number or record.get("申込投稿ID", "") or skip_row(ctx, number):
            continue
        try:
            if form_key == "LT":
                kind = value_of(record, config.COL_LT, "kind")
                embed = lt_embed(record, number, staff_note(ctx, kind))
            elif form_key == "COMMUNITY":
                embed = community_embed(record, number, staff_note(ctx, "コミュニティ参加"))
            else:
                embed = sponsor_embed(record, number)
            # 新しい申し込みは見てもらわないと承認が進まないので、呼び出しを付ける
            message_id = post_to_staff(ctx, channel_id, "", embed, True)
            sheet.write(row, "申込投稿ID", message_id)
            sheet.write(row, "discord自動投稿", now_text())
            ctx.logger.record(
                number,
                "申し込みを投稿しました",
                ctx.client.message_link(channel_id, message_id),
                who=display_name(record, form_key),
            )
            if form_key == "SPONSOR":
                # 承認の仕組みが無いので、スタッフが手で送る。その下書きをスレッドに用意する
                post_sponsor_draft(ctx, channel_id, message_id, number, record)
        except Exception as error:  # noqa: BLE001
            report_failure(ctx, channel_id, number, "discord自動投稿", error, "")
            failures.append(f"{number} discord自動投稿: {error}")
    return failures


def process_approvals(ctx: Context, sheet: Sheet, form_key: str) -> list[str]:
    """承認された申し込みに、採択の連絡とロール付与を行う

    1件が失敗しても残りは処理する

    Args:
        ctx: 処理の文脈
        sheet: 対象のシート
        form_key: 'LT' か 'COMMUNITY'

    Returns:
        失敗した処理の説明
    """
    failures: list[str] = []
    channel_id = ctx.settings.staff_channels[form_key]
    watched = {
        "yosasou": ctx.settings.emojis["yosasou"],
        "horyu": ctx.settings.emojis["horyu"],
    }
    for row, record in sheet.rows():
        message_id = record.get("申込投稿ID", "")
        number = record.get("受付番号", "")
        if not message_id or record.get("承認確認", "") or skip_row(ctx, number):
            continue
        try:
            counts = ctx.client.reaction_counts(channel_id, message_id, watched)
        except DiscordError as error:
            if handle_lost_post(ctx, channel_id, number, error):
                continue
            failures.append(f"{number} リアクションの読み取り: {error}")
            continue
        if counts["horyu"] > 0 or counts["yosasou"] < config.APPROVAL_THRESHOLD:
            continue
        try:
            sheet.write(row, "承認確認", now_text())
            ctx.logger.record(
                number,
                f"承認を確認しました ({counts['yosasou']}件)",
                who=display_name(record, form_key),
            )
        except Exception as error:  # noqa: BLE001
            failures.append(f"{number} 承認の記録: {error}")
    return failures


def process_approved_rows(ctx: Context, sheet: Sheet, form_key: str) -> list[str]:
    """採択メールが送られた行に、一般向けチャンネルへの投稿を行う

    採択メールは Google Apps Script が送る。その列に時刻が入ったものだけを引き受ける
    ロール付与は投稿が済んだ行を別に拾う

    Args:
        ctx: 処理の文脈
        sheet: 対象のシート
        form_key: 'LT' か 'COMMUNITY'

    Returns:
        失敗した処理の説明
    """
    failures: list[str] = []
    channel_id = ctx.settings.staff_channels[form_key]
    for row, record in sheet.rows():
        if not record.get("採択メール送信", "") or record.get("採択discord送信", ""):
            continue
        if skip_row(ctx, record.get("受付番号", "")):
            continue
        failure = approve_row(ctx, sheet, row, record, form_key)
        if failure:
            failures.append(failure)
    return failures


def approve_row(ctx: Context, sheet: Sheet, row: int, record: dict[str, str], form_key: str) -> str | None:
    """採択メールが送られた1行を、一般向けチャンネルに知らせる

    途中で失敗したらそこで止める。済んだところまでは列と完了の絵文字に残る
    申込者がまだサーバーに居ないときは失敗にしない。参加するまで待って、次の周でやり直す

    Args:
        ctx: 処理の文脈
        sheet: 対象のシート
        row: 1始まりの行番号
        record: その行の値
        form_key: 'LT' か 'COMMUNITY'

    Returns:
        失敗した処理の説明。最後まで進んだときと、申込者の参加を待つときは None
    """
    channel_id = ctx.settings.staff_channels[form_key]
    message_id = record["申込投稿ID"]
    number = record["受付番号"]
    link = ctx.client.message_link(channel_id, message_id)
    kind = value_of(record, config.COL_LT, "kind") if form_key == "LT" else "コミュニティ参加"

    if not record.get("採択メール確認", ""):
        try:
            ctx.client.add_reaction(channel_id, message_id, ctx.settings.emojis["mail_done"])
            sheet.write(row, "採択メール確認", now_text())
            ctx.logger.record(
                number, "採択メールの送信を確認しました", who=display_name(record, form_key)
            )
        except Exception as error:  # noqa: BLE001
            if handle_lost_post(ctx, channel_id, number, error):
                return None
            report_failure(ctx, channel_id, number, "メール完了の絵文字", error, link)
            return f"{number} メール完了の絵文字: {error}"

    columns = config.COL_LT if form_key == "LT" else config.COL_COMMUNITY
    username = value_of(record, columns, "discord")
    try:
        user_id = ctx.client.find_member_id(username)
    except Exception as error:  # noqa: BLE001
        report_failure(ctx, channel_id, number, "Discordユーザーの検索", error, link)
        return f"{number} Discordユーザーの検索: {error}"
    if not user_id:
        return wait_for_member(ctx, sheet, row, record, form_key, username, kind, link)

    public_id = ctx.settings.public_channels[form_key]
    try:
        # 投稿より先に印を立てる。投稿してから書くと、書けなかったときに申込者へ2回メンションが飛ぶ
        sheet.write(row, "DiscordユーザーID", user_id)
        sheet.write(row, "採択discord送信", now_text())
        # 手元の値は周回の最初に読んだもの。以降のログにメンションを出すため、ここでも入れる
        record["DiscordユーザーID"] = user_id
    except Exception as error:  # noqa: BLE001
        # まだ何も送っていない。次の周でやり直す
        report_failure(ctx, channel_id, number, "採択discord送信の準備", error, link)
        return f"{number} 採択discord送信の準備: {error}"

    try:
        post_id = ctx.client.post_message(
            public_id,
            build_approval_post(ctx, form_key, kind, record, user_id, number),
            mention_user_id=user_id,
        )
    except Exception as error:  # noqa: BLE001
        if not clear_send_mark(ctx, sheet, row, channel_id, number, link):
            return f"{number} 採択discord送信: 投稿に失敗し、印も消せませんでした"
        report_failure(ctx, channel_id, number, "採択discord送信", error, link)
        return f"{number} 採択discord送信: {error}"

    try:
        sheet.write(row, "採択投稿ID", post_id)
        ctx.client.add_reaction(channel_id, message_id, ctx.settings.emojis["discord_done"])
        ctx.logger.record(
            number,
            "採択を知らせる投稿をしました",
            ctx.client.message_link(public_id, post_id),
            who=display_name(record, form_key),
        )
    except Exception as error:  # noqa: BLE001
        # 投稿は届いている。ここでやり直すと2回目のメンションになるので、印は立てたままにする
        report_failure(ctx, channel_id, number, "採択投稿の記録", error, link)
        return f"{number} 採択投稿の記録: {error}"
    return None


def clear_send_mark(
    ctx: Context, sheet: Sheet, row: int, channel_id: str, number: str, link: str
) -> bool:
    """立てたばかりの送信済みの印を消して、やり直せる状態に戻す

    消せなかったら、その行はもう誰も拾わない。手で直してもらうしかないので知らせる

    Args:
        ctx: 処理の文脈
        sheet: 対象のシート
        row: 1始まりの行番号
        channel_id: スタッフ専用チャンネルのID
        number: 受付番号
        link: 元の申し込み投稿へのリンク

    Returns:
        消せたら True
    """
    try:
        sheet.write(row, "採択discord送信", "")
    except Exception as error:  # noqa: BLE001
        report_failure(ctx, channel_id, number, "採択discord送信の取り消し", error, link)
        return False
    return True


def wait_for_member(
    ctx: Context,
    sheet: Sheet,
    row: int,
    record: dict[str, str],
    form_key: str,
    username: str,
    kind: str,
    link: str,
) -> str | None:
    """申込者がまだサーバーに居ないことをスタッフに1度だけ知らせる

    採択メールで初めて招待リンクを送るので、この時点で未参加なのはふつうのこと
    知らせたことを列に残し、以降は黙って参加を待つ

    Args:
        ctx: 処理の文脈
        sheet: 対象のシート
        row: 1始まりの行番号
        record: その行の値
        form_key: 'LT' か 'COMMUNITY'
        username: フォームに入力されたDiscordユーザー名
        kind: 申込み種別、または「コミュニティ参加」
        link: 元の申し込み投稿へのリンク

    Returns:
        知らせること自体に失敗した説明。知らせ済みと、知らせられたときは None
    """
    number = record["受付番号"]
    if record.get("ユーザー未特定通知", ""):
        return None
    if (number, MEMBER_NOT_FOUND) in ctx.notified:
        # 投稿は通ったが列に書けなかった。同じ知らせをもう一度出さない
        return None
    channel_id = ctx.settings.staff_channels[form_key]
    content = messages.fill(
        messages.POST_MEMBER_NOT_FOUND,
        {
            "受付番号": number,
            "Discordユーザー名": username,
            "ロール名": role_names_for(kind),
            "元投稿リンク": link,
        },
    )
    step = "申込者がまだサーバーに居ません。参加を待ちます"
    if not tell_staff(ctx, channel_id, number, step, content, "", display_name(record, form_key)):
        return f"{number} ユーザー不明の知らせ: どこにも残せませんでした"
    # 知らせが通ってから覚える。先に覚えると、出せなかった知らせが二度と出ない
    ctx.notified.add((number, MEMBER_NOT_FOUND))
    try:
        sheet.write(row, "ユーザー未特定通知", now_text())
    except Exception as error:  # noqa: BLE001
        return f"{number} ユーザー未特定の記録: {error}"
    return None


def looks_like_user_id(value: str) -> bool:
    """DiscordのユーザーIDとして使える形かを返す

    `isdigit` だけでは全角数字も通る。URLに全角のまま入れるとDiscordが相手を見つけられない

    Args:
        value: 「DiscordユーザーID」列から読んだ値

    Returns:
        半角数字だけで、桁数も合っていれば True
    """
    return value.isascii() and value.isdigit() and len(value) in USER_ID_DIGITS


def process_role_grants(ctx: Context, sheet: Sheet, form_key: str) -> list[str]:
    """一般向けチャンネルへの投稿が済んだ行に、ロールを付ける

    投稿とは別に拾う。投稿の後で絵文字やログが失敗しても、ロール付与は次の周でやり直せる
    手で対応した行は DiscordユーザーID が空なので引き受けない

    Args:
        ctx: 処理の文脈
        sheet: 対象のシート
        form_key: 'LT' か 'COMMUNITY'

    Returns:
        失敗した処理の説明
    """
    failures: list[str] = []
    channel_id = ctx.settings.staff_channels[form_key]
    for row, record in sheet.rows():
        user_id = record.get("DiscordユーザーID", "")
        if not record.get("採択discord送信", "") or not user_id or record.get("ロール付与", ""):
            continue
        if skip_row(ctx, record.get("受付番号", "")):
            continue
        number = record.get("受付番号", "")
        message_id = record.get("申込投稿ID", "")
        link = ctx.client.message_link(channel_id, message_id)
        if not looks_like_user_id(user_id):
            # そのまま使うと知らない人にロールが付く。全角数字は isdigit を通るので別に見る
            notice_once(
                ctx, channel_id, number, "DiscordユーザーIDが読めません", messages.HINT_BROKEN_ID, link
            )
            continue
        kind = value_of(record, config.COL_LT, "kind") if form_key == "LT" else "コミュニティ参加"
        try:
            role_ids = role_ids_for(ctx.settings, kind)
            if not role_ids:
                # 付けるロールが1つも無いのは設定の取り違え。黙って通すとロール無しで完了になる
                raise RuntimeError(f"申込み種別「{kind}」に対応するロールの設定がありません")
            for role_id in role_ids:
                ctx.client.add_role(user_id, role_id)
            sheet.write(row, "ロール付与", now_text())
            ctx.client.add_reaction(channel_id, message_id, ctx.settings.emojis["role_done"])
            ctx.logger.record(
                number,
                f"ロールを付与しました ({role_names_for(kind)})",
                who=display_name(record, form_key),
            )
        except Exception as error:  # noqa: BLE001
            report_failure(ctx, channel_id, number, "ロール付与", error, link)
            failures.append(f"{number} ロール付与: {error}")
    return failures


def build_approval_post(  # noqa: PLR0913
    ctx: Context, form_key: str, kind: str, record: dict[str, str], user_id: str, number: str
) -> str:
    """承認を知らせる投稿の本文を組み立てる

    Args:
        ctx: 処理の文脈
        form_key: 'LT' か 'COMMUNITY'
        kind: 申込み種別、または「コミュニティ参加」
        record: その行の値
        user_id: メンションする相手のユーザーID
        number: 受付番号

    Returns:
        投稿の本文
    """
    settings = ctx.settings
    ok = emoji_for_content(settings.emojis["ok"])
    if form_key == "LT":
        template = (
            messages.POST_APPROVED_SPONSOR_LT if kind == "スポンサーLT" else messages.POST_APPROVED_LT
        )
        return messages.fill(
            template,
            {
                "メンション": f"<@{user_id}>",
                "受付番号": number,
                "申込み種別": kind,
                "lt登壇チャンネル": channel_ref(settings.ref_channels["lt_toudan"]),
                "お知らせチャンネル": channel_ref(settings.ref_channels["oshirase"]),
                "OK絵文字": ok,
            },
        )
    columns = config.COL_COMMUNITY
    style = value_of(record, columns, "style")
    # 申込者が書いた文字をそのまま出すと、太字やリンクとして描画される
    limit = config.PUBLIC_TEXT_LIMIT
    return messages.fill(
        messages.POST_APPROVED_COMMUNITY,
        {
            "メンション": f"<@{user_id}>",
            "受付番号": number,
            "コミュニティ名": escape_markdown(value_of(record, columns, "name"), limit),
            "参加形態": escape_markdown(style, limit),
            "お願いする作業": community_task(record),
            "community参加チャンネル": channel_ref(settings.ref_channels["community_sanka"]),
            "Discordやりとりの案内": community_guide(record),
            "OK絵文字": ok,
        },
    )


def needs_image(record: dict[str, str]) -> bool:
    """ロゴかスライドを新しく用意してもらう必要があるかを返す

    「以前と同じでOK」を選んだ人は、去年のものをそのまま使うので用意は要らない

    Args:
        record: その行の値

    Returns:
        用意してもらう必要があれば True
    """
    columns = config.COL_COMMUNITY
    style = value_of(record, columns, "style")
    wants = (
        config.COMMUNITY_STYLE_KEYWORDS["logo"] in style
        or config.COMMUNITY_STYLE_KEYWORDS["slide"] in style
    )
    return wants and config.COMMUNITY_CONTACT_DISCORD in value_of(record, columns, "logo")


def community_task(record: dict[str, str]) -> str:
    """コミュニティ参加の承認の投稿に出す、お願いする作業の文を返す

    画像の用意とLT発表申込フォームへの記入は、別々の条件で決まる
    「以前と同じでOK」を選んだ人でもコミュニティLTには申し込める

    Args:
        record: その行の値

    Returns:
        本文に差し込む1文
    """
    image = needs_image(record)
    lt = wants_community_lt(value_of(record, config.COL_COMMUNITY, "style"))
    if image and lt:
        return messages.TASK_IMAGE_AND_LT
    if lt:
        return messages.TASK_LT_ONLY
    if image:
        return messages.TASK_IMAGE_ONLY
    return messages.TASK_NONE


def community_guide(record: dict[str, str]) -> str:
    """コミュニティ参加者へのお願いを組み立てる

    ロゴとスライドの節は、Discordでのやりとりを選んだ人にだけ出す
    LTの節は、ロゴ・スライドのやり取り方法と関係なく、LTを希望した人に出す

    Args:
        record: その行の値

    Returns:
        本文に差し込む文字列。出す節が無ければ空文字
    """
    columns = config.COL_COMMUNITY
    style = value_of(record, columns, "style")
    guide = ""
    if config.COMMUNITY_CONTACT_DISCORD in value_of(record, columns, "logo"):
        if config.COMMUNITY_STYLE_KEYWORDS["logo"] in style:
            guide += messages.COMMUNITY_GUIDE_LOGO
        if config.COMMUNITY_STYLE_KEYWORDS["slide"] in style:
            guide += messages.COMMUNITY_GUIDE_SLIDE
    if wants_community_lt(style):
        guide += messages.COMMUNITY_GUIDE_LT
    return guide


def wants_community_lt(style: str) -> bool:
    """希望する参加形態にコミュニティLTが含まれるかを返す

    Args:
        style: 「希望する参加形態」の回答

    Returns:
        含まれていれば True
    """
    return config.COMMUNITY_STYLE_KEYWORDS["lt"] in style


def process_ok_reactions(ctx: Context, sheet: Sheet, form_key: str) -> list[str]:
    """承認を知らせた投稿に、申込者が確認のリアクションを付けたかを見る

    受け取ったら、スタッフ専用チャンネルの申込投稿に `:ok_done:` を付ける
    ほかの3つの完了の絵文字と同じ場所に並ぶので、どこまで進んだか一目で分かる

    Args:
        ctx: 処理の文脈
        sheet: 対象のシート
        form_key: 'LT' か 'COMMUNITY'

    Returns:
        失敗した処理の説明
    """
    failures: list[str] = []
    public_id = ctx.settings.public_channels[form_key]
    staff_id = ctx.settings.staff_channels[form_key]
    ok = ctx.settings.emojis["ok"]
    for row, record in sheet.rows():
        post_id = record.get("採択投稿ID", "")
        user_id = record.get("DiscordユーザーID", "")
        number = record.get("受付番号", "")
        if not post_id or not user_id or record.get("OKリアクション確認", ""):
            continue
        if skip_row(ctx, number):
            continue
        try:
            if not ctx.client.has_reaction_from(public_id, post_id, ok, user_id):
                continue
        except Exception as error:  # noqa: BLE001
            failures.append(f"{number} 確認リアクションの読み取り: {error}")
            continue
        try:
            sheet.write(row, "OKリアクション確認", now_text())
            message_id = record.get("申込投稿ID", "")
            if message_id:
                ctx.client.add_reaction(staff_id, message_id, ctx.settings.emojis["ok_done"])
            ctx.logger.record(
                number, "申込者の確認リアクションを受け取りました", who=display_name(record, form_key)
            )
        except Exception as error:  # noqa: BLE001
            failures.append(f"{number} 確認リアクションの記録: {error}")
    return failures
