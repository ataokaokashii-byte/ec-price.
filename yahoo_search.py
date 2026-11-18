"""Yahoo!ショッピングをキーワードまたは JAN コードで検索し、結果をターミナルに表示する（読み取り専用）。

スプレッドシートや output/ には書き込まない。取得データの保存可否は利用規約を確認してから決める。
検索結果から監視対象を自動で選ぶことはしない。

使い方:
    python yahoo_search.py               # 「スニーカー」で3件
    python yahoo_search.py 腕時計 -n 5
    python yahoo_search.py --jan 4987035332602 -n 5 --sort price
"""

from __future__ import annotations

import argparse
import sys
import unicodedata

import config
from sources.yahoo import DEFAULT_ENDPOINT, MAX_RESULTS, SORT_OPTIONS, YahooClient, YahooError, YahooItem

_NAME_WIDTH = 40
_SORT_LABELS = {"score": "おすすめ順", "price": "価格の安い順", "-price": "価格の高い順"}
_ERROR_LABELS = {"input": "入力エラー", "auth": "認証エラー", "network": "通信エラー", "api": "API エラー"}


def _width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def _fit(text: str, width: int) -> str:
    """表示幅 width に収まるよう切り詰め、右を空白で埋める。"""
    if _width(text) > width:
        out = ""
        for c in text:
            if _width(out + c) > width - 1:  # 末尾の「…」の分を残す
                break
            out += c
        text = out + "…"
    return text + " " * (width - _width(text))


def print_items(condition: str, items: list[YahooItem]) -> None:
    print(f"\n検索条件: {condition} / 取得件数: {len(items)} 件\n")
    header = f"{'#':>2}  {_fit('商品名', _NAME_WIDTH)}  {' ' * 6}価格  在庫"
    print(header)
    print("-" * 72)
    for i, item in enumerate(items, 1):
        price = f"{item.price:,}円" if item.price is not None else "-"
        price = " " * (10 - _width(price)) + price  # 「円」は全角なので表示幅で右寄せ
        stock = {True: "あり", False: "なし", None: "不明"}[item.in_stock]
        print(f"{i:>2}  {_fit(item.name, _NAME_WIDTH)}  {price}  {stock}")
        print(f"    店舗      : {item.seller_name or '-'}（ストアID: {item.seller_id or '-'}）")
        print(f"    商品コード: {item.item_code or '-'}　JAN: {item.jan_code or '-'}")
        print(f"    監視用ID  : {item.product_id or '-（識別できません）'}")
        print(f"    URL       : {item.url}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Yahoo!ショッピングの商品をキーワードまたは JAN コードで検索して表示する")
    parser.add_argument("keyword", nargs="?", default="", help="検索キーワード（キーワードも --jan もなければ「スニーカー」）")
    # type=str のまま扱い、先頭の 0 を落とさない
    parser.add_argument("--jan", default="", help="JAN コード（8桁または13桁）。キーワードと併用すると AND 条件")
    parser.add_argument("-n", "--results", type=int, default=3, help=f"取得件数（1〜{MAX_RESULTS}、既定: 3）")
    parser.add_argument("--sort", choices=list(SORT_OPTIONS), default="score",
                        help="並び順: score=おすすめ順（既定）/ price=価格の安い順 / -price=価格の高い順")
    parser.add_argument("--in-stock", action="store_true", help="在庫ありの商品だけを検索する")
    args = parser.parse_args()
    keyword = args.keyword or ("" if args.jan else "スニーカー")
    condition = " / ".join(filter(None, [
        f"キーワード「{keyword}」" if keyword else "",
        f"JAN {args.jan}" if args.jan else "",
        _SORT_LABELS[args.sort],
    ]))

    config.load_env()
    try:
        client = YahooClient(config.env("YAHOO_APP_ID"), endpoint=config.env("YAHOO_ENDPOINT", DEFAULT_ENDPOINT))
        items = client.search(keyword, args.results, in_stock_only=args.in_stock, jan_code=args.jan, sort=args.sort)
    except YahooError as exc:
        print(f"{_ERROR_LABELS.get(exc.kind, 'エラー')}: {exc}", file=sys.stderr)
        return 1

    if not items:
        print(f"{condition} に一致する商品は見つかりませんでした。")
        return 0
    print_items(condition, items)
    if args.jan:
        print("※ JAN コードは商品の種類を表すもので、店舗の販売商品を一意に識別しません。")
        print("  同じ JAN でも店舗・入数（単品/ケース）・セット内容が異なる商品が含まれることがあります。")
        print("  監視対象に加える場合は「監視用ID（ストアID:商品コード）」を選んで指定してください（自動では登録しません）。\n")
    return 0 if all(item.product_id for item in items) else 1


if __name__ == "__main__":
    sys.exit(main())
