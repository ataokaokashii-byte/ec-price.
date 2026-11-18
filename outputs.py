"""出力先。Google スプレッドシートと、動作確認用のローカル CSV の2種類。

どちらも同じインターフェース（read_latest / write_latest / append_history）を持つ。
"""

from __future__ import annotations

import csv
from pathlib import Path

from processing import HISTORY_HEADER, LATEST_HEADER, new_history_rows

LATEST_SHEET = "最新"
HISTORY_SHEET = "履歴"


class GoogleSheetsOutput:
    """サービスアカウントで Google スプレッドシートに書き込む。

    対象スプレッドシートをサービスアカウントのメールアドレスに「編集者」で共有しておくこと。
    """

    def __init__(self, credentials_file: str, spreadsheet_id: str) -> None:
        import gspread  # --dry-run 時は不要なので遅延 import

        self._gspread = gspread
        client = gspread.service_account(filename=credentials_file)
        self._book = client.open_by_key(spreadsheet_id)

    def _sheet(self, title: str, header: list[str]):
        try:
            ws = self._book.worksheet(title)
        except self._gspread.WorksheetNotFound:
            ws = self._book.add_worksheet(title=title, rows=1000, cols=len(header))
            ws.update([header], "A1")
            ws.freeze(rows=1)
        return ws

    def read_latest(self) -> list[list]:
        return self._sheet(LATEST_SHEET, LATEST_HEADER).get_all_values()

    def write_latest(self, rows: list[list]) -> None:
        ws = self._sheet(LATEST_SHEET, LATEST_HEADER)
        ws.clear()
        # RAW: 商品名が "=" で始まっても数式として解釈させない
        ws.update([LATEST_HEADER] + rows, "A1", value_input_option="RAW")
        ws.freeze(rows=1)
        # 変動率をパーセント表示に
        rate_col = chr(ord("A") + LATEST_HEADER.index("変動率"))
        ws.format(f"{rate_col}2:{rate_col}", {"numberFormat": {"type": "PERCENT", "pattern": "0.0%"}})

    def append_history(self, rows: list[list]) -> None:
        if not rows:
            return
        ws = self._sheet(HISTORY_SHEET, HISTORY_HEADER)
        # 重複判定に使う 取得日時・ソース・商品ID の列だけ読む
        rows = new_history_rows(ws.get("A:C"), rows)
        if rows:
            ws.append_rows(rows, value_input_option="RAW")

    @property
    def location(self) -> str:
        return self._book.url


class CsvOutput:
    """--dry-run 用。output/ 配下に同じ構成の CSV を書く。"""

    def __init__(self, directory: Path) -> None:
        self._dir = directory
        self._dir.mkdir(parents=True, exist_ok=True)
        self._latest = self._dir / "latest.csv"
        self._history = self._dir / "history.csv"

    def read_latest(self) -> list[list]:
        if not self._latest.exists():
            return []
        with self._latest.open(encoding="utf-8-sig", newline="") as f:
            return list(csv.reader(f))

    def write_latest(self, rows: list[list]) -> None:
        with self._latest.open("w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerows([LATEST_HEADER] + rows)

    def append_history(self, rows: list[list]) -> None:
        new_file = not self._history.exists()
        if not new_file:
            with self._history.open(encoding="utf-8-sig", newline="") as f:
                rows = new_history_rows(list(csv.reader(f)), rows)
        if not rows and not new_file:
            return
        with self._history.open("a", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            if new_file:
                writer.writerow(HISTORY_HEADER)
            writer.writerows(rows)

    @property
    def location(self) -> str:
        return str(self._dir.resolve())
