# ec-price-tracker

EC サイトの商品の価格・在庫を定期的に取得し、Google スプレッドシートに反映するプロトタイプ。

```
watchlist.csv ─▶ sources/（Keepa / 楽天 / mock）─▶ processing.py（前回比・目標価格判定）─▶ outputs.py（Sheets / CSV）
```

## データソースの選定

| 対象 | 方法 | 備考 |
|---|---|---|
| Amazon | **Keepa API**（有料） | Amazon 本体のスクレイピングは利用規約で禁止。公式の PA-API 5.0 は 2026年5月に廃止。後継の Creators API はアソシエイトの売上実績が条件になるため、在庫・価格管理の用途では Keepa が現実的 |
| 楽天市場 | **楽天ウェブサービス 商品検索 API**（無料） | 2026年5月に新エンドポイントへ移行。applicationId + accessKey + 登録サイト URL（Referer/Origin）が必要 |
| mock | ダミーデータ | API キーなしで一連の流れを確認するため |

スクレイピングは利用しない方針。新しいソースを追加する場合は `sources/` に `fetch(ids) -> list[ProductRecord]` を持つクライアントを作り、`main.make_client` と `config` に登録する。

## セットアップ

```powershell
pip install -r requirements.txt
Copy-Item watchlist.example.csv watchlist.csv
Copy-Item .env.example .env
```

### 1. まず CSV で動作確認（設定不要）

```powershell
python main.py --dry-run     # output/latest.csv と output/history.csv ができる
python main.py --mock        # watchlist の mock の行だけを処理（--dry-run と併用可）
python -m pytest -q
```

### 2. Google スプレッドシートの準備

1. Google Cloud Console でプロジェクトを作成し、**Google Sheets API** を有効化
2. サービスアカウントを作成し、JSON 鍵をダウンロードして `service_account.json` としてこのフォルダに置く
3. 反映先のスプレッドシートを作り、サービスアカウントのメールアドレス（`xxx@xxx.iam.gserviceaccount.com`）に**編集者**で共有
4. `.env` の `SPREADSHEET_ID` に URL の `/d/<ID>/edit` の部分を設定
5. `python main.py` を実行 → 「最新」「履歴」シートが自動作成される

### 3. 実データの取得

- **Keepa**: https://keepa.com/#!api で API キーを購入し `KEEPA_API_KEY` に設定。watchlist に `keepa,<ASIN>,...` を追加
- **楽天**: https://webservice.rakuten.co.jp/ でアプリを登録し、`RAKUTEN_APPLICATION_ID` / `RAKUTEN_ACCESS_KEY` / `RAKUTEN_SITE_URL` を設定。watchlist に `rakuten,<ショップコード:商品コード>,...` を追加（商品 URL `item.rakuten.co.jp/<shop>/<item>/` の2つを `:` でつなぐ）

### Yahoo!ショッピング（読み取りテストのみ）

商品検索 API v3 でキーワード検索し、結果をターミナルに表示する。スプレッドシートや `output/` には書き込まない（取得データの保存に関する利用規約の確認が済むまで、`main.py` の監視対象には加えていない）。

```powershell
# .env に YAHOO_APP_ID（Client ID）を設定してから
python yahoo_search.py                 # 「スニーカー」で3件
python yahoo_search.py 腕時計 -n 5 --in-stock
python yahoo_search.py --jan 4987035332602 -n 5 --sort price   # JAN コード（8桁/13桁）で検索、価格の安い順
```

- JAN コードは文字列のまま扱い（先頭の 0 を保持）、送信前に桁数とチェックディジットを検証する
- `--sort`: `score`（おすすめ順、既定）/ `price`（安い順）/ `-price`（高い順）
- JAN コードは商品の**種類**を表すだけで、店舗の販売商品は一意に識別できない。同じ JAN でも店舗・入数（単品/ケース）・セット内容が異なる商品が混ざる
- そのため監視対象は **`ストアID:商品コード`**（表示の「監視用ID」）で識別する。検索結果から自動で監視対象を選ぶことはしない

## 監視リスト（watchlist.csv）

| 列 | 内容 |
|---|---|
| source | `keepa` / `rakuten` / `mock` |
| product_id | ASIN または楽天の itemCode |
| label | 自由メモ（シートの「メモ」列に出る） |
| target_price | 目標価格（円）。この価格以下で「目標以下」に ○ が付く。空欄可 |

`#` で始まる行は無視される。

## シートの構成

- **最新**: 実行のたびに上書き。価格・前回価格・変動額・変動率・在庫・目標価格判定・URL・エラー
- **履歴**: 1商品につき日本時間の1日1行を追記。時系列分析やグラフ作成に使う。取得日（日本時間）・ソース・商品IDが同じ行がすでにあれば追記しない（その日最初の値が残り、既存行は書き換えない）

取得日時は PC のタイムゾーン設定によらず日本時間で記録する。

在庫切れなどで価格が取れなかった商品は、最後に確認できた価格を「前回価格」として引き継ぐ。
1つのソースが失敗しても他のソースは反映され、終了コードは 1 になる（設定エラーは 2）。ログは `logs/` に出力。

## 定期実行

```powershell
powershell -ExecutionPolicy Bypass -File .\register_task.ps1 -Mock            # モックモードで毎日 9:00 に実行
powershell -ExecutionPolicy Bypass -File .\register_task.ps1 -Mock -At 07:30  # 時刻を指定
powershell -ExecutionPolicy Bypass -File .\register_task.ps1                  # 通常モード（watchlist の全ソース）
```

- `-Mock` を付けると `python main.py --mock` を実行する。watchlist の `mock` の行だけを処理し、実 API には接続しない
- 履歴は1日1行なので、実行は1日1回。同名タスクがあれば上書き登録する
- 手動実行: `Start-ScheduledTask -TaskName EcPriceTracker`。結果は `Get-ScheduledTaskInfo` の LastTaskResult（0=成功 / 1=一部ソース失敗 / 2=設定エラー）と `logs/ec-price-tracker.log` で確認

PC がログオン中のときだけ実行される。PC を起動していない時間帯も動かしたい場合は、GitHub Actions やクラウドのスケジューラーへの移行を検討する。

## 今後の拡張案

- 目標価格を下回ったら LINE / Slack に通知（slack-line-summarizer の line_client を流用可能）
- 監視リストをスプレッドシートの別シートで管理し、CSV を不要にする
- Keepa の価格履歴（csv 配列）を取り込み、過去の最安値・平均価格との比較列を追加
