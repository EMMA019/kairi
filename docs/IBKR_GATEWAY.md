# IBKR 閲覧専用（TWS / Gateway）セットアップ

Kairi は **読み取りのみ**（残高・ポジション・直近約定）。発注 API のコードパスはありません。

## 前提

1. Interactive Brokers **Paper** 口座（デモ入金反映後）
2. **TWS** または **IB Gateway** を起動し、API を有効化
3. マシン上で Kairi backend が `127.0.0.1` に接続できること

## ポート

| モード | TWS | IB Gateway |
|--------|-----|------------|
| Paper（デモ） | **7497**（Kairi デフォルト） | 4002 |
| Live（本番） | 7496 | 4001 |

今日のセットアップが TWS paper なら `.env` は `IBKR_PORT=7497` のままでよい。  
Gateway paper に切り替えたら `IBKR_PORT=4002`。

## TWS / Gateway 側

1. ログイン（Paper Trading）
2. **Edit → Global Configuration → API → Settings**
   - Enable ActiveX and Socket Clients
   - Socket port = 上記表に合わせる
   - Trusted IPs に `127.0.0.1`（必要なら）
   - 「Read-Only API」をオンにできる場合はオン推奨
3. ダイアログで API 接続をブロックしない

## Kairi 側（`backend/.env`）

```env
IBKR_ENABLED=1
IBKR_HOST=127.0.0.1
IBKR_PORT=7497
IBKR_CLIENT_ID=100
```

- `IBKR_CLIENT_ID` はベース値。実際の接続 ID は `base + (pid % 10000)` でプロセスごとにずらす。
- 口座パスワードは Kairi に保存しない（TWS/Gateway ログインのみ）。

```bash
pip install ib_insync
```

## チャットツール

| ツール | 用途 |
|--------|------|
| `ibkr_account_summary` | NetLiquidation / Cash / BuyingPower 等 |
| `ibkr_positions` | 保有銘柄・数量・平均取得 |
| `ibkr_recent_fills` | 直近約定（既定 20・最大 50） |

未接続時は `{"ok": false, "error": "gateway_unavailable", ...}`。数値の推測埋めは禁止。

## 株価取得

- `IBKR_ENABLED=1` かつ TWS 接続時、`get_stock_quote` / `get_jp_market_snapshot` は **IBKR 優先**
- 不通・権限不足時は yfinance にフォールバック（`source` フィールドで判別）
- オフにする場合: `IBKR_MARKET_DATA=0`
- デモ口座は遅延気配になることがある

## 疎通チェック

1. TWS paper 起動・API 有効
2. `IBKR_ENABLED=1` で backend 再起動
3. チャットで「IBKRの残高は？」「ポジションは？」
4. Market Desk の Quote で `source: ibkr` が出るか確認

## やらないこと（意図的）

- 発注・取消・変更
- Client Portal Web API
- 本番 Live ポートの既定化
