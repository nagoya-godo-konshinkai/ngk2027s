"""決まった間隔で申し込みを処理し続ける

コンテナの中でずっと動かす。1周ごとに失敗を集め、あれば標準エラーに出して次の周へ進む
"""

from __future__ import annotations

import sys
import time

from . import config, flows
from .config import load_settings
from .discord_api import DiscordClient
from .flows import Context, Logger, now_text
from .sheets import Book, Sheet


def run_once(ctx: Context, book: Book) -> list[str]:
    """1周分の処理を行う

    Args:
        ctx: 処理の文脈
        book: スプレッドシート

    Returns:
        失敗した処理の説明
    """
    failures: list[str] = []
    for form_key, sheet_name in config.SHEET_NAMES.items():
        sheet = book.sheet(sheet_name)
        if sheet is None:
            failures.append(f"シート {sheet_name} がありません")
            continue
        problem = check_columns(sheet, sheet_name)
        if problem:
            failures.append(problem)
            # 標準エラーだけだと気づけない。心拍は動き続けるので、止まって見えない
            if ctx.notify_once(sheet_name, "列の確認"):
                try:
                    ctx.logger.record("列の確認", problem)
                except Exception as error:  # noqa: BLE001
                    ctx.notified.discard((sheet_name, "列の確認"))
                    print(f"列の問題を知らせられませんでした: {type(error).__name__}", file=sys.stderr, flush=True)
            continue
        failures += flows.post_new_submissions(ctx, sheet, form_key)
        if form_key == "SPONSOR":
            # スポンサーには承認の仕組みが無い。投稿だけで終わる
            continue
        failures += flows.process_approvals(ctx, sheet, form_key)
        failures += flows.process_approved_rows(ctx, sheet, form_key)
        failures += flows.process_role_grants(ctx, sheet, form_key)
        failures += flows.process_ok_reactions(ctx, sheet, form_key)
    book.write_heartbeat(now_text())
    return failures


def check_columns(sheet: Sheet, sheet_name: str) -> str | None:
    """そのシートを処理してよいかを確かめる

    管理列は Apps Script の setUp が作る。足りないまま書き込むと別の列を壊す

    Args:
        sheet: 対象のシート
        sheet_name: シートの名前

    Returns:
        見つかった問題の説明。問題が無ければ None
    """
    missing = sheet.missing_columns(config.ADMIN_COLUMNS)
    if missing:
        return f"シート {sheet_name} に管理列がありません: {' / '.join(missing)}"
    if sheet.duplicate_columns:
        names = " / ".join(sheet.duplicate_columns)
        return f"シート {sheet_name} に同じ名前の列が2つ以上あります: {names}"
    return None


def main() -> None:
    """設定を読み、決まった間隔で処理を繰り返す"""
    settings = load_settings()
    client = DiscordClient(settings.discord_token, settings.guild_id)
    logger = Logger(client, settings.log_channel, settings.staff_role)
    ctx = Context(settings=settings, client=client, logger=logger)
    print(f"{now_text()} 開始しました。{settings.poll_interval_seconds}秒ごとに見に行きます", flush=True)
    if settings.only_numbers:
        # 見落とすと本番の申し込みが止まったままになるので、毎回出す
        numbers = " ".join(sorted(settings.only_numbers))
        print(f"試しの設定が入っています。次の受付番号だけを処理します: {numbers}", flush=True)

    while True:
        try:
            book = Book(settings.service_account_file, settings.spreadsheet_id)
            failures = run_once(ctx, book)
            for failure in failures:
                print(f"失敗: {failure}", file=sys.stderr, flush=True)
        except Exception as error:  # noqa: BLE001
            # 1周が丸ごと落ちても止めない。次の周で拾い直す
            print(f"{now_text()} 1周分の処理が落ちました: {type(error).__name__}", file=sys.stderr, flush=True)
        time.sleep(settings.poll_interval_seconds)


if __name__ == "__main__":
    main()
