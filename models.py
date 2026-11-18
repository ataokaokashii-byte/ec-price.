"""各モジュールで共有するデータ型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WatchItem:
    """監視対象の商品（watchlist.csv の1行）。"""

    source: str  # "keepa" / "rakuten" / "mock"
    product_id: str  # keepa: ASIN, rakuten: itemCode（"ショップ:商品"）
    label: str = ""
    target_price: int | None = None

    @property
    def key(self) -> tuple[str, str]:
        return (self.source, self.product_id)


@dataclass(frozen=True)
class ProductRecord:
    """データソースから取得した商品データ（加工前）。"""

    source: str
    product_id: str
    title: str
    price: int | None  # 円。価格が取れない（出品なし等）場合は None
    in_stock: bool | None  # 判定不能なら None
    stock_note: str
    url: str
    error: str = ""

    @property
    def key(self) -> tuple[str, str]:
        return (self.source, self.product_id)
