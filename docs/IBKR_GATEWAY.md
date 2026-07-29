# IBKR 閲覧専用（TWS / Gateway）セットアップ

Kairi は **読み取りのみ**（残高・ポジション・直近約定）。発注 API のコードパスはありません。

## ローカル vs Render（スマホ）

| 環境 | 想定 | 株価 |
|------|------|------|
| **ローカル** | PC + TWS 同居 | **IBKR Live 優先** |
| **Render** | 外部スマホからチャット | **Yahoo 即時**（~15分遅延可）。IBKR に繋がない |

Render では自宅 `127.0.0.1:7497` に届かない。不通待ち（8〜25s）でスマホの応答が途切れるのを防ぐため、`RENDER` 検知時は `IBKR_MARKET_DATA` 未設定なら **自動で株価 IBKR オフ**。チャット用の日本市況スナップショットも常に Yahoo 即時。

```env
# Render 推奨（明示しても可）
IBKR_ENABLED=0
# または誤って IBKR_ENABLED=1 でも株価だけ切る
IBKR_MARKET_DATA=0
```

強制上書き（通常不要）: `KAIRI_CLOUD=1` / `KAIRI_CLOUD=0`

## 前提

1. Interactive Brokers **Paper** または Live 口座（ローカル用）
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

## Kairi 側（ローカル `backend/.env`）

### ローカル・リアルタイム（推奨）

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

Yahoo（yfinance）は無料だが **約15分遅延**。ローカルのライブ更新には IBKR の **API 向けマーケットデータ購読** が必要。

US（SPY / QQQ / AAPL 等）で Error **10089** が出る場合:

1. IBKR Account Management → **Market Data Subscriptions**
2. 少なくとも US 株式の **Streaming（API）** パッケージを契約  
   （例: NYSE / NASDAQ / ARCA の Top of Book、または US Equity streaming bundle）
3. 「API」利用が許可されていることを確認（画面内のリンク「マーケットデータへの接続」）
4. TWS 再ログイン後、Kairi backend を再起動

日本株（TSEJ）は別途 **Tokyo Stock Exchange** 系の購読が必要（Error 354 / 162）。

## チャット / Desk ツール

| ツール | 用途 |
|--------|------|
| `ibkr_account_summary` | NetLiquidation / Cash / BuyingPower 等 |
| `ibkr_positions` | 保有銘柄・数量・平均取得 |
| `ibkr_recent_fills` | 直近約定（既定 20・最大 50） |
| `get_stock_quote` | 単銘柄（ローカル: IBKR live 優先 → Yahoo） |
| `get_stock_quotes` | **複数銘柄1接続**（Market Desk 用） |
| `get_jp_market_snapshot` | 日本指数・業種ETF（チャット注入は常に Yahoo） |

未接続時は `{"ok": false, "error": "gateway_unavailable", ...}`。数値の推測埋めは禁止。

## 株価取得の優先順位

1. **ローカル + IBKR Live**（購読あり）→ `source: ibkr`, `realtime: true`
2. 購読エラーは速失敗 → **yfinance**
3. **Render / クラウド** → 最初から yfinance（途切れ防止）
4. Market Desk ヘッダに `IBKR live` / `Yahoo ~15m` を表示

## 疎通チェック

1. TWS 起動・API 有効・必要購読済み（ローカル）
2. `IBKR_ENABLED=1` / `IBKR_MARKET_DATA_TYPE=1` で backend 再起動
3. チャットで「IBKRの残高は？」
4. Market Desk を Refresh → ヘッダが **`IBKR live`**
5. Render ではヘッダ／ログが Yahoo 即時で、IBKR connect が走らないこと

## やらないこと（意図的）

- 発注・取消・変更
- Client Portal Web API
- 本番 Live ポートの既定化（誤接続防止。明示設定のみ）
- Render から自宅 TWS へのトンネル（スマホ用途では不要）
