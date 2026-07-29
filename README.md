# Kairi — 自律型AIエージェント（Chat + IDE）

<div align="center">
  
![UI](https://img.shields.io/badge/UI-React_19_%2B_Tailwind_v4-blue)
![Backend](https://img.shields.io/badge/Backend-FastAPI_%2B_SQLite-green)
![Models](https://img.shields.io/badge/Models-DeepSeek_V4_%2F_GPT_%2F_Gemini-orange)
![Cache](https://img.shields.io/badge/Cache-SQLite_Semantic-purple)

**チャット・開発・市況ブリーフィングに対応した、自律型AIエージェント**

</div>

---

## 📋 概要

Kairiは「チャット」と「開発（IDE）」に特化したAIエージェントです。ユーザーが「〇〇を作って」「〇〇を修正して」と指示すると、Supervisor（思考担当）が計画を立て、Executor（実行担当）がコードを生成・修正・テスト実行まで自律的に行います。

**チャット・開発に加え、Market Desk 向けの市況ブリーフィング配信**まで扱う AI エージェントです。

### 本命 / 実験 / 運用

| 区分 | 内容 |
|------|------|
| **本命** | 検索で裏取りする回答、task 実装ループ、**明示時のみ** KV 記憶、寄り前/大引け後ブリーフィング |
| **実験** | char 画像ギャラリー、radar アラート、ギャル文字、integrity 装飾 UI |
| **運用** | `KAIRI_API_TOKEN`、`python -m evals.run_evals`、`POST /api/kv/purge-junk`、[docs/BRIEFING_OPS.md](docs/BRIEFING_OPS.md) |

未知の事実への対策は「検索 → 出典強制 → 未ヒットなら埋めない」が基本です（RL再学習・複数モデル交差は対象外）。  
リポジトリ分割の詳細は [docs/REPO_SEPARATION.md](docs/REPO_SEPARATION.md) を参照。

---

## ✨ 主要機能

### 1. デュアルエージェント・アーキテクチャ

| 役割 | モデル | 責務 |
|------|--------|------|
| **Supervisor** | DeepSeek V4 Pro / Claude Opus | ユーザーの意図分析、実装計画策定、検索判断、KVメモリ更新 |
| **Executor** | DeepSeek V4 Flash / Gemini | コード生成・修正、コマンド実行、ファイル操作、テスト実行 |

SupervisorはJSON形式で回答方針を出力し、Executorがそれに厳密に従って実行します。「口頭でやったふり」をするとExecutorは自動で差し戻されます。

### 2. 自律実行ループ（New）

コード生成→エラー検出→Supervisor分析→修正→再実行のサイクルを**完全自動**で行います。

```
指示「ReactのTODOアプリ作って」
  → Supervisor: 実装プラン作成（3ファイル構成）
  → Executor: ファイル作成 + コマンド実行
  → エラー検出 → Supervisorがログ分析
  → 修正指示 → Executorが再実行
  → 成功確認 → 完了報告
```

### 3. スマートなコード編集

- **新規作成**: `<file path="...">` タグでファイル全体を作成
- **差分修正**: `<replace>` タグで既存ファイルの一部分だけを修正
- **フォールバック置換**: SEARCH対象が見つからない場合、空白・句読点を正規化して再試行、さらに範囲マッチでリカバリ
- **構文チェック**: Python / JSON / TSXの自動リント、エラー時は自動ロールバック

### 4. 2段階コンテキスト圧縮（New）

長大な会話履歴を自動圧縮してトークンを節約：
- **第1段階**: コードブロックは先頭10行+末尾10行を保持
- **第2段階**: 古い会話ターンを圧縮、最新6ターンを完全保持

### 5. LLM応答キャッシュ（New）

**KVメモリの勝手参照は絶対に行わず**、同じ質問+同じコンテキストのLLM応答をキャッシュ：
- セマンティックキャッシュ（クエリ正規化→MD5ハッシュ→SQLite保存）
- 検索結果キャッシュ（60秒TTL）
- コマンド実行キャッシュ（git hashベース）
- 定型応答ショートサーキット（「おはよう」等はSupervisor呼び出しゼロ）

### 6. ニュースプールと市況ブリーフィング

RSS を並列取得し、72時間のローリングプールに蓄積します（ペイウォール記事は無料ソースで差し替え）。

| 項目 | 内容 |
|------|------|
| **寄り前** | JST 08:15 — 米国確定値（DIA/SPY/QQQ/SOXX/USDJPY）＋解説＋ヘッドライン |
| **大引け後** | JST 16:00 — 日経/TOPIX スナップショット＋前日比＋解説＋ヘッドライン |
| **UI** | Market Desk → Briefing タブ（一覧・プレビュー・手動生成・フィード健全性） |
| **配信** | Discord Webhook へ全文分割送信（未設定時はログのみ） |

手動生成例:

```bash
curl -X POST -H "X-API-Token: $KAIRI_API_TOKEN" \
  "$KAIRI_BACKEND_URL/api/briefing/generate?kind=preopen"
```

試験運用チェックリスト: [docs/BRIEFING_OPS.md](docs/BRIEFING_OPS.md)

### 7. デュアルモードUI

| モード | 説明 |
|--------|------|
| **💬 チャット** | 画面全体でAIと会話。挨拶・雑談・質問・実装依頼まで全てここから |
| **💻 IDE** | 左にチャット、右にMonaco Editor + ファイルエクスプローラー。コードをリアルタイム編集・保存 |
| **📈 Market** | Market Desk（紙トレード概況）と Briefing パネル |

- **コードパネル**: AIが生成したコードをMonaco Editorで直接編集・保存
- **Markdown/Mermaid/HTMLプレビュー**: コードブロックをその場でプレビュー
- **ファイルエクスプローラー**: ワークスペースのファイルを表示・選択
- **リサイズ可能**: チャットエリアの幅をドラッグで調整

### 8. ギャル文字コンパイラ（おまけ）

「ギャルモードON！」で起動する3レイヤー・コンパイラ。LLMのIQを落とさずに、出力だけを極限ギャル文字に変換します。

### 9. マルチLLM対応

| プロバイダ | モデル例 | 用途 |
|-----------|---------|------|
| DeepSeek | V4 Pro / V4 Flash | デフォルト（高コスパ） |
| Anthropic | Claude Opus / Haiku | 高品質思考 |
| OpenAI | GPT-5.5 | 汎用 |
| Gemini | 3.1 Pro / Flash | 高品質・低コスト |
| ローカル | Ollama / llama3 | オフライン |

---

## 🚀 クイックスタート

### バックエンド

```bash
cd backend
python -m venv venv

# Windows
.\venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

`.env` にAPIキーを設定（最低1つ）:
```
DEEPSEEK_API_KEY=sk-xxxxx
# または
ANTHROPIC_API_KEY=sk-xxxxx
# または
GEMINI_API_KEY=xxxxx
```

起動:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### フロントエンド

```bash
cd frontend
npm install
npm run dev
```

ブラウザで `http://localhost:5173` にアクセス。

---

## 🏗️ アーキテクチャ

```
                           ┌────────────────────────┐
                           │    User Input           │
                           └───────────┬────────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    │                  │                  │
              定型応答?             指示?              雑談?
            (ショートサーキット)       │                  │
                    │                  ▼                  │
                    │    ┌──────────────────────┐        │
                    │    │  Search Planner      │        │
                    │    │  (検索判定 + Intent   │        │
                    │    │   Routing)           │        │
                    │    └──────────┬───────────┘        │
                    │               │                    │
                    │    ┌──────────▼───────────┐        │
                    │    │  Supervisor (思考)    │        │
                    │    │  - 意図分析           │        │
                    │    │  - 検索/メモリ判断    │        │
                    │    │  - 実装プラン作成     │        │
                    │    │  - エラー分析         │        │
                    │    └──────────┬───────────┘        │
                    │               │                    │
                    │               ▼                    │
                    │    ┌──────────────────────┐        │
                    │    │  Executor (実行)      │◄───────┘
                    │    │  - ファイル作成/編集  │
                    │    │  - コマンド実行       │
                    │    │  - 検索/スクレイピング │
                    │    └──────────┬───────────┘
                    │               │
                    │    ┌──────────▼───────────┐
                    │    │  ToolHandler         │
                    │    │  - XMLタグパース      │
                    │    │  - Docker Sandbox     │
                    │    │  - Git Snapshot       │
                    │    │  - 構文チェック       │
                    │    └──────────┬───────────┘
                    │               │
                    │    ┌──────────▼───────────┐
                    │    │  Auto-Execution Loop  │
                    │    │  エラー検出→修正→再実行│
                    │    └──────────────────────┘
                    │
                    ▼
            ┌────────────────┐
            │   Response     │
            │  (SSE Stream)  │
            └────────────────┘
```

### キャッシュ戦略

```
User Input → Normalize → Hash → Cache Hit? → 応答
                                    ↓
                               Cache Miss
                                    ↓
                              Supervisor Call
                                    ↓
                              Cacheに保存
```

---

## 🗂️ ディレクトリ構成

```
backend/
├── app/
│   ├── main.py                     # FastAPI エントリーポイント
│   ├── core/
│   │   ├── briefing/               # 寄り前/大引け後ブリーフィング生成
│   │   ├── news/                   # RSS プール・ペイウォール差し替え
│   │   ├── notify/discord.py       # Discord Webhook（アラート＋全文配信）
│   │   ├── supervisor.py           # 思考モデル (プロンプト+実行)
│   │   ├── executor.py             # 実行モデル (プロンプト+ストリーミング)
│   │   ├── cache_manager.py        # セマンティックキャッシュ
│   │   ├── auto_execution_loop.py   # 自律実行ループ
│   │   ├── multi_file_coordinator.py # マルチファイル一貫変更
│   │   ├── context_compressor.py   # 2段階コンテキスト圧縮
│   │   ├── file_edit_fallback.py   # ファイル編集フォールバック
│   │   ├── auto_test_pipeline.py   # 自動テスト実行
│   │   ├── kv_store.py             # KVメモリ管理
│   │   ├── llm_client.py           # マルチLLM統合ラッパー
│   │   ├── gyaru.py                # ギャル文字コンパイラ
│   │   ├── sandbox.py              # Dockerサンドボックス
│   │   └── search/
│   │       ├── router.py           # 検索ルーター（天気/Wiki/Brave/News）
│   │       ├── reranker.py         # キーワードリランカー
│   │       └── providers/          # 各検索プロバイダ
│   ├── routers/
│   │   ├── chat.py                 # チャットAPI（SSEストリーミング）
│   │   ├── history.py              # 会話履歴API
│   │   ├── memory.py               # KVメモリAPI
│   │   ├── workspace.py            # ワークスペースAPI
│   │   ├── news_health.py          # ニュース健全性・ブリーフィング API
│   │   └── settings.py             # 設定API
│   └── utils/
│       ├── logger.py               # 構造化ログ
│       └── parser.py               # XML/JSONパース
├── cache/                          # LLM応答・検索結果キャッシュ
├── storage/                        # 会話履歴DB・briefings/
└── requirements.txt

frontend/
├── src/
│   ├── App.tsx                     # メインアプリケーション
│   ├── components/
│   │   ├── ChatArea.tsx            # 会話表示エリア
│   │   ├── InputArea.tsx           # 入力欄
│   │   ├── IDEView.tsx             # IDEモード全体
│   │   ├── MarketDesk.tsx          # 市況デスク
│   │   ├── BriefingPanel.tsx       # ブリーフィング一覧・生成
│   │   ├── CodePanel.tsx           # Monacoエディタ+プレビュー
│   │   ├── FileExplorer.tsx        # ファイルエクスプローラー
│   │   └── Sidebar.tsx             # サイドバー
│   └── hooks/
│       ├── useChat.ts              # チャットAPI連携
│       └── useStreaming.ts         # SSEストリーミング受信
└── package.json
```

---

## ⚙️ 設定

`.env` ファイルで設定可能:

| 変数 | 説明 | デフォルト |
|------|------|-----------|
| `DEEPSEEK_API_KEY` | DeepSeek APIキー | - |
| `ANTHROPIC_API_KEY` | Claude APIキー | - |
| `GEMINI_API_KEY` | Gemini APIキー | - |
| `OPENAI_API_KEY` | OpenAI APIキー | - |
| `BRAVE_API_KEY` | Brave Search APIキー（検索用） | - |
| `DISCORD_WEBHOOK_URL` | ブリーフィング/アラート Discord 配信 | - |
| `LLM_PROVIDER` | デフォルトLLM | `deepseek` |
| `KAIRI_API_TOKEN` | API 認証トークン（本番必須） | - |

---

## 📝 ライセンス

MIT License

---

*Created by Kairi*