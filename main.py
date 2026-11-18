"""監視リストの商品データを取得し、Google スプレッドシートに反映する。

使い方:
    python main.py              # スプレッドシートに書き込む
    python main.py --dry-run    # output/ に CSV を書く（Google の設定なしで動作確認）
    python main.py --mock       # 監視リストの mock の行だけを処理する（実 API には接続しない）
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from pathlib import Path

import config
from config import ConfigError
from models import ProductRecord, WatchItem
from outputs import CsvOutput, GoogleSheetsOutput
from processing import build_history_rows, build_latest_rows, now_jst, previous_prices_from_rows

BASE_DIR = Path(__file__).resolve().parent
log = logging.getLogger("ec-price-tracker")


def setup_logging() -> None:
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler = logging.FileHandler(log_dir / "ec-price-tracker.log", encoding="utf-8")
    file_handler.setFormatter(fmt)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    log.setLevel(logging.INFO)
    log.addHandler(file_handler)
    log.addHandler(console)


def make_client(source: str):
    if source == "keepa":
        from sources.keepa import KeepaClient

        return KeepaClient(config.env("KEEPA_API_KEY"), domain=int(config.env("KEEPA_DOMAIN", "5")))
    if source == "rakuten":
        from sources.rakuten import DEFAULT_ENDPOINT, RakutenClient

        return RakutenClient(
            config.env("RAKUTEN_APPLICATION_ID"),
            config.env("RAKUTEN_ACCESS_KEY"),
            config.env("RAKUTEN_SITE_URL"),
            endpoint=config.env("RAKUTEN_ENDPOINT", DEFAULT_ENDPOINT),
        )
    from sources.mock import MockClient

    return MockClient()


def fetch_all(items: list[WatchItem]) -> tuple[list[ProductRecord], list[str]]:
    """ソースごとにまとめて取得する。1つのソースが失敗しても他は続行する。"""
    ids_by_source: dict[str, list[str]] = defaultdict(list)
    for item in items:
        ids_by_source[item.source].append(item.product_id)

    records: list[ProductRecord] = []
    failed: list[str] = []
    for source, ids in ids_by_source.items():
        try:
            got = make_client(source).fetch(ids)
        except Exception:
            log.exception("%s の取得に失敗しました（%d 件）", source, len(ids))
            failed.append(source)
            continue
        errors = [r for r in got if r.error]
        log.info("%s: %d 件取得（うちエラー %d 件）", source, len(got), len(errors))
        for r in errors:
            log.warning("  %s %s: %s", source, r.product_id, r.error)
        records.extend(got)
    return records, failed


def mock_only(items: list[WatchItem]) -> list[WatchItem]:
    """モックモード用に mock の行だけを残す。1件もなければ設定エラー。"""
    mocks = [i for i in items if i.source == "mock"]
    if not mocks:
        raise ConfigError("モックモードですが、監視リストに mock の行がありません")
    if len(mocks) < len(items):
        log.info("モックモード: mock 以外の %d 行は処理しません", len(items) - len(mocks))
    return mocks


def main() -> int:
    parser = argparse.ArgumentParser(description="EC サイトの商品データをスプレッドシートに反映する")
    parser.add_argument("--dry-run", action="store_true", help="スプレッドシートの代わりに output/ に CSV を書く")
    parser.add_argument("--watchlist", type=Path, default=BASE_DIR / "watchlist.csv", help="監視リスト CSV")
    parser.add_argument("--mock", action="store_true", help="監視リストの mock の行だけを処理する（実 API に接続しない）")
    args = parser.parse_args()

    setup_logging()
    config.load_env()

    try:
        items = config.load_watchlist(args.watchlist)
        if args.mock:
            items = mock_only(items)
        config.check_required({i.source for i in items}, use_sheets=not args.dry_run)
        output = (
            CsvOutput(BASE_DIR / "output")
            if args.dry_run
            else GoogleSheetsOutput(config.credentials_file(), config.env("SPREADSHEET_ID"))
        )
    except ConfigError as exc:
        log.error("設定エラー: %s", exc)
        return 2

    log.info("開始: %d 商品（出力先: %s%s）", len(items), "CSV" if args.dry_run else "Google スプレッドシート",
             "・モックモード" if args.mock else "")
    fetched_at = now_jst()
    records, failed = fetch_all(items)

    previous = previous_prices_from_rows(output.read_latest())
    by_key = {r.key: r for r in records}
    latest_rows = build_latest_rows(fetched_at, items, by_key, previous)
    output.write_latest(latest_rows)
    output.append_history(build_history_rows(fetched_at, records))

    hits = [row for row in latest_rows if row[12] == "○"]
    for row in hits:
        log.info("目標価格以下: %s %s（%s円 ≤ %s円）", row[2], row[3] or row[4], row[5], row[11])
    log.info("完了: %s", output.location)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
