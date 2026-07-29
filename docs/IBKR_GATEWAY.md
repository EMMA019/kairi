# IBKR 閲覧専用（TWS / Gateway）セットアップ

Kairi は **読み取りのみ**（残高・ポジション・直近約定）。発注 API のコードパスはありません。

## 前提

1. Interactive Brokers **Paper** または Live 口座
2. **TWS** または **IB Gateway** を起動し、API を有効化
3. Kairi backend が Gateway/TWS に TCP 接続できること（同一マシンなら `127.0.0.1`）

## ポート

| モード | TWS | IB Gateway |
|--------|-----|------------|
| Paper（デモ） | **7497**（Kairi デフォルト） | 4002 |
| Live（本番） | 7496 | 4001 |

今日のセットアップが TWS paper なら `.env` は `IBKR_PORT=7497` のままでよい。  
Gateway paper に切り替えたら `IBKR_PORT=4002`。

## TWS / Gateway 側

1. ログイン（Paper / Live）
2. **Edit → Global Configuration → API → Settings**
   - Enable ActiveX and Socket Clients
   - Socket port = 上記表に合わせる
   - Trusted IPs に `127.0.0.1`（必要なら）
   - 「Read-Only API」をオンにできる場合はオン推奨
3. ダイアログで API 接続をブロックしない
4. **同時に別のライブセッションで同じデータの独占利用をしない**（Error 10197）

## Kairi 側（`backend/.env`）

### 本番リアルタイム（推奨）

```env
IBKR_ENABLED=1
IBKR_HOST=127.0.0.1
IBKR_PORT=7497
IBKR_CLIENT_ID=100
IBKR_MARKET_DATA=1
IBKR_MARKET_DATA_TYPE=1
```

| 変数 | 意味 |
|------|------|
| `IBKR_MARKET_DATA=1` | 株価を IBKR 優先（オフなら Yahoo のみ） |
| `IBKR_MARKET_DATA_TYPE=1` | **Live**（リアルタイム）。`3` は Delayed（〜15分） |

- `IBKR_CLIENT_ID` はベース値。実際の接続 ID は `base + (pid % 10000)` でプロセスごとにずらす。
- 口座パスワードは Kairi に保存しない（TWS/Gateway ログインのみ）。

```bash
pip install ib_insync
```

### リアルタイムに必要な購読（Account Management）

Yahoo（yfinance）は無料だが **約15分遅延**。本番のライブ更新には IBKR の **API 向けマーケットデータ購読** が必要。

US（SPY / QQQ / AAPL 等）で Error **10089** が出る場合:

1. IBKR Account Management → **Market Data Subscriptions**
2. 少なくとも US 株式の **Streaming（API）** パッケージを契約  
   （例: NYSE / NASDAQ / ARCA の Top of Book、または US Equity streaming bundle）
3. 「API」利用が許可されていることを確認（画面内のリンク「マーケットデータへの接続」）
4. TWS 再ログイン後、Kairi backend を再起動

日本株（TSEJ）は別途 **Tokyo Stock Exchange** 系の購読が必要（Error 354 / 162）。

### Render 等のクラウド backend

クラウド上の backend は自宅の `127.0.0.1:7497` に届かない。リアルタイムにするなら:

- backend を **TWS/Gateway と同じマシン**で動かす、または
- Gateway を常時起動できるホストに置き、`IBKR_HOST` をその到達可能アドレスにする

## チャット / Desk ツール

| ツール | 用途 |
|--------|------|
| `ibkr_account_summary` | NetLiquidation / Cash / BuyingPower 等 |
| `ibkr_positions` | 保有銘柄・数量・平均取得 |
| `ibkr_recent_fills` | 直近約定（既定 20・最大 50） |
| `get_stock_quote` | 単銘柄（IBKR live 優先 → Yahoo） |
| `get_stock_quotes` | **複数銘柄1接続**（Market Desk 用・本番向け） |
| `get_jp_market_snapshot` | 日本指数・業種ETF |

未接続時は `{"ok": false, "error": "gateway_unavailable", ...}`。数値の推測埋めは禁止。

## 株価取得の優先順位

1. **IBKR Live**（`IBKR_MARKET_DATA_TYPE=1`、購読あり）→ `source: ibkr`, `realtime: true`
2. 購読エラー（10089/354 等）は **速失敗** → **yfinance**（数値は出るが ~15分遅延）
3. Market Desk ヘッダに `IBKR live` / `Yahoo ~15m` を表示

口座だけ IBKR・株価は常に Yahoo にしたい場合:

```env
IBKR_ENABLED=1
IBKR_MARKET_DATA=0
```

## 疎通チェック

1. TWS 起動・API 有効・必要購読済み
2. `IBKR_ENABLED=1` / `IBKR_MARKET_DATA_TYPE=1` で backend 再起動
3. チャットで「IBKRの残高は？」
4. Market Desk を Refresh → ヘッダが **`IBKR live`**、ログが  
   `Fetching stock quotes batch n=… (yf=False, enrich=…)`  
   個々の quote に `"source": "ibkr", "realtime": true`

## やらないこと（意図的）

- 発注・取消・変更
- Client Portal Web API
- 本番 Live ポートの既定化（誤接続防止。明示設定のみ）
