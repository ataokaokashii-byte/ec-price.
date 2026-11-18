"""取得データの加工（前回比・目標価格判定）と出力用の行データ組み立て。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from models import ProductRecord, WatchItem

# 日本時間（夏時間なし）。Windows では tzdata なしで ZoneInfo("Asia/Tokyo") が使えないため固定オフセットで持つ
JST = timezone(timedelta(hours=9), "JST")

LATEST_HEADER = [
    "取得日時", "ソース", "商品ID", "メモ", "商品名", "価格", "前回価格", "変動額", "変動率",
    "在庫", "在庫詳細", "目標価格", "目標以下", "URL", "エラー",
]
HISTORY_HEADER = ["取得日時", "ソース", "商品ID", "商品名", "価格", "在庫"]


def now_jst() -> str:
    """取得日時（日本時間・分単位）。PC のタイムゾーン設定に依存しない。"""
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M")


def _stock_label(in_stock: bool | None) -> str:
    return {True: "あり", False: "なし", None: "不明"}[in_stock]


def build_latest_rows(
    fetched_at: str,
    items: list[WatchItem],
    records: dict[tuple[str, str], ProductRecord],
    previous_prices: dict[tuple[str, str], int],
) -> list[list]:
    """「最新」シート用の行を watchlist の順で作る。

    取得できなかった商品も行を残し、エラー列に理由を入れる。
    """
    rows = []
    for item in items:
        rec = records.get(item.key)
        prev = previous_prices.get(item.key)
        if rec is None:
            rec = ProductRecord(item.source, item.product_id, "", None, None, "", "", error="取得失敗")

        price = rec.price
        diff = price - prev if price is not None and prev is not None else ""
        rate = round(diff / prev, 4) if diff != "" and prev else ""
        below = "" if price is None or item.target_price is None else ("○" if price <= item.target_price else "")

        rows.append([
            fetched_at,
            item.source,
            item.product_id,
            item.label,
            rec.title,
            "" if price is None else price,
            "" if prev is None else prev,
            diff,
            rate,
            _stock_label(rec.in_stock),
            rec.stock_note,
            "" if item.target_price is None else item.target_price,
            below,
            rec.url,
            rec.error,
        ])
    return rows


def build_history_rows(fetched_at: str, records: list[ProductRecord]) -> list[list]:
    """「履歴」シートに追記する行。エラーの商品は記録しない。"""
    return [
        [fetched_at, r.source, r.product_id, r.title, "" if r.price is None else r.price, _stock_label(r.in_stock)]
        for r in records
        if not r.error
    ]


def new_history_rows(existing: list[list], rows: list[list]) -> list[list]:
    """「履歴」に未記録の行だけを返す。

    (取得日 [日本時間], ソース, 商品ID) が同じ行は重複とみなし、1商品につき1日1行にする。
    同じ日に再実行しても追記せず、その日最初に記録した値を残す（既存行は書き換えない）。
    取得日時は日本時間の "YYYY-MM-DD HH:MM" で記録しているので、先頭10文字を日付とする。
    """
    seen = {_history_key(row) for row in existing}
    result = []
    for row in rows:
        key = _history_key(row)
        if key not in seen:
            seen.add(key)
            result.append(row)
    return result


def _history_key(row: list) -> tuple[str, str, str]:
    cells = [str(c) for c in row[:3]]
    cells += [""] * (3 - len(cells))
    return (cells[0].strip()[:10], cells[1], cells[2])


def previous_prices_from_rows(rows: list[list]) -> dict[tuple[str, str], int]:
    """前回の「最新」シートの内容から (ソース, 商品ID) → 価格 を作る。

    前回価格が取れなかった商品は、その時点の「前回価格」を引き継ぐ
    （在庫切れの間も、最後に確認できた価格と比較できるようにするため）。
    """
    if not rows:
        return {}
    header, body = rows[0], rows[1:]
    col = {name: i for i, name in enumerate(header)}
    needed = ("ソース", "商品ID", "価格", "前回価格")
    if any(name not in col for name in needed):
        return {}

    result = {}
    for row in body:
        cell = lambda name: row[col[name]] if col[name] < len(row) else ""  # noqa: E731
        for value in (cell("価格"), cell("前回価格")):
            price = _to_int(value)
            if price is not None:
                result[(str(cell("ソース")), str(cell("商品ID")))] = price
                break
    return result


def _to_int(value) -> int | None:
    if value in ("", None):
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except ValueError:
        return None
