"""回答シートの読み書き"""

from __future__ import annotations

import gspread
from google.oauth2.service_account import Credentials
from gspread.utils import ValueInputOption, rowcol_to_a1

from . import config

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class Book:
    """スプレッドシート全体を扱う"""

    def __init__(self, service_account_file: str, spreadsheet_id: str) -> None:
        """鍵とスプレッドシートIDを渡して開く

        Args:
            service_account_file: サービスアカウントの鍵ファイルのパス
            spreadsheet_id: スプレッドシートのID
        """
        credentials = Credentials.from_service_account_file(service_account_file, scopes=SCOPES)
        self._book = gspread.authorize(credentials).open_by_key(spreadsheet_id)

    def sheet(self, name: str) -> Sheet | None:
        """名前でシートを開く

        Args:
            name: シートの名前

        Returns:
            開いたシート。無ければ None
        """
        try:
            return Sheet(self._book.worksheet(name))
        except gspread.WorksheetNotFound:
            return None

    def write_heartbeat(self, text: str) -> None:
        """最終実行時刻を専用シートに書く

        止まっていないかをスタッフが確かめるために使う

        Args:
            text: 書き込む時刻の文字列
        """
        try:
            worksheet = self._book.worksheet(config.STATE_SHEET_NAME)
        except gspread.WorksheetNotFound:
            worksheet = self._book.add_worksheet(title=config.STATE_SHEET_NAME, rows=2, cols=2)
            worksheet.update_acell("A1", "最終実行時刻")
        worksheet.update_acell("B1", text)


class Sheet:
    """1つの回答シートを扱う"""

    def __init__(self, worksheet: gspread.Worksheet) -> None:
        """シートを渡して、中身をすべて読み込む

        Args:
            worksheet: gspread のシート
        """
        self._ws = worksheet
        values = worksheet.get_all_values()
        self._header: dict[str, int] = {}
        self._duplicates: list[str] = []
        if values:
            for index, name in enumerate(values[0]):
                cleaned = name.strip()
                if not cleaned:
                    continue
                if cleaned in self._header:
                    # 同じ名前の列が2つあると、どちらを読み書きするかが Apps Script 側とずれる
                    self._duplicates.append(cleaned)
                    continue
                self._header[cleaned] = index + 1
        self._values = values[1:] if values else []

    @property
    def header(self) -> dict[str, int]:
        """列名から1始まりの列番号への対応を返す"""
        return self._header

    @property
    def duplicate_columns(self) -> list[str]:
        """2つ以上あった列の名前を返す"""
        return self._duplicates

    def missing_columns(self, columns: list[str]) -> list[str]:
        """ヘッダに無い列の名前を集める

        Args:
            columns: 必要な列名

        Returns:
            見つからなかった列名
        """
        return [name for name in columns if name not in self._header]

    def rows(self) -> list[tuple[int, dict[str, str]]]:
        """全行を、行番号と列名から値への対応の組で返す

        Returns:
            1始まりの行番号と、その行の値
        """
        result: list[tuple[int, dict[str, str]]] = []
        for offset, values in enumerate(self._values):
            record = {
                name: (values[index - 1] if index - 1 < len(values) else "")
                for name, index in self._header.items()
            }
            result.append((offset + 2, record))
        return result

    def write(self, row: int, column_name: str, value: str) -> None:
        """1つのセルに、打ち込まれた文字をそのまま書く

        update_cell は画面から打ち込んだのと同じ解釈をする。19桁のDiscordのIDは
        数値になり、下の桁が別の値に化けるので使わない

        Args:
            row: 1始まりの行番号
            column_name: 書き込む列の名前
            value: 書き込む値
        """
        column = self._header[column_name]
        self._ws.update(
            range_name=rowcol_to_a1(row, column),
            values=[[value]],
            value_input_option=ValueInputOption.raw,
        )
        # 読み直さずに済むよう、手元の値も合わせておく
        index = column - 1
        values = self._values[row - 2]
        while len(values) <= index:
            values.append("")
        values[index] = value


def value_of(record: dict[str, str], columns: dict[str, str], key: str) -> str:
    """設定上の名前で行の値を1つ取り出す

    Args:
        record: その行の値
        columns: 設定上の名前から列名への対応
        key: 設定上の名前

    Returns:
        その列の値。無ければ空文字
    """
    return record.get(columns[key], "")
