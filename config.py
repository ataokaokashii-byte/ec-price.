"""環境変数と watchlist.csv の読み込み・検証。

必要な環境変数は watchlist に含まれるソースと出力先によって変わるため、
実際に使うものだけを検証する。不足があれば ConfigError を送出する。
"""

from __future__ import annotations

import csv
import os
from pathlib import Path

from dotenv import load_dotenv

from models import WatchItem

SUPPORTED_SOURCES = ("keepa", "rakuten", "mock")

_REQUIRED_BY_SOURCE = {
    "keepa": ["KEEPA_API_KEY"],
    "rakuten": ["RAKUTEN_APPLICATION_ID", "RAKUTEN_ACCESS_KEY", "RAKUTEN_SITE_URL"],
    "mock": [],
}
_REQUIRED_FOR_SHEETS = ["SPREADSHEET_ID"]


class ConfigError(Exception):
    """設定の不足・不正を表す例外。"""


def load_env() -> None:
    load_dotenv()


def env(key: str, default: str = "") -> str:
    return os.environ.get(key) or default


def check_required(sources: set[str], use_sheets: bool) -> None:
    keys = [k for s in sorted(sources) for k in _REQUIRED_BY_SOURCE[s]]
    if use_sheets:
        keys += _REQUIRED_FOR_SHEETS
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        raise ConfigError(
            "必須の環境変数が設定されていません: "
            + ", ".join(missing)
            + "（.env を確認してください。.env.example を参考にしてください）"
        )
    if use_sheets:
        cred = credentials_file()
        if not Path(cred).exists():
            raise ConfigError(f"サービスアカウントの鍵ファイルが見つかりません: {cred}")


def credentials_file() -> str:
    return env("GOOGLE_CREDENTIALS_FILE", "service_account.json")


def load_watchlist(path: Path) -> list[WatchItem]:
    """watchlist.csv（source,product_id,label,target_price）を読み込む。"""
    if not path.exists():
        raise ConfigError(f"監視リストが見つかりません: {path}（watchlist.example.csv をコピーして作成してください）")

    items: list[WatchItem] = []
    seen: set[tuple[str, str]] = set()
    with path.open(encoding="utf-8-sig", newline="") as f:
        for lineno, row in enumerate(csv.DictReader(f), start=2):
            source = (row.get("source") or "").strip().lower()
            product_id = (row.get("product_id") or "").strip()
            if not source or source.startswith("#"):
                continue
            if source not in SUPPORTED_SOURCES:
                raise ConfigError(f"{path}:{lineno} 未対応の source です: {source!r}（{', '.join(SUPPORTED_SOURCES)}）")
            if not product_id:
                raise ConfigError(f"{path}:{lineno} product_id が空です")

            target_raw = (row.get("target_price") or "").replace(",", "").strip()
            try:
                target = int(target_raw) if target_raw else None
            except ValueError as exc:
                raise ConfigError(f"{path}:{lineno} target_price は整数で指定してください: {target_raw!r}") from exc

            item = WatchItem(source, product_id, (row.get("label") or "").strip(), target)
            if item.key in seen:
                continue
            seen.add(item.key)
            items.append(item)

    if not items:
        raise ConfigError(f"監視リストに商品がありません: {path}")
    return items
