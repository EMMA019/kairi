# Kairi — グラウンディング付きローカルチャット（BYOK）

> 公開向けの英語 README は [README.md](README.md) です。ライセンスは [MIT](LICENSE)。

**LLM の回答に捏造を混ぜにくくする**ためのローカル BYOK 相棒です。引用契約・content-age・数値防御・違和感ログ→eval の一周が本体で、市況デスク（米日セッション／ニュースボード）はそのパイプラインを毎日回すリファレンスアプリです。

詳細: [docs/GROUNDING.md](docs/GROUNDING.md) · [デモ手順](docs/DEMO.md) · [SECURITY.md](SECURITY.md)

---

## すぐ試す

### Docker（キー不要デモ）

```bash
docker compose up --build
# http://127.0.0.1:8000/
```

既定で `KAIRI_DEMO=1`。チャットは LLM を呼ばず、固定フィクスチャの grounding 前後を見せます。本番会話は `.env` にキーを入れ、`KAIRI_DEMO` を外してください。

### 開発サーバー

```bash
cd backend && python -m venv .venv && source .venv/bin/activate  # Windows は Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

cd frontend && npm install && npm run dev
```

Windows ランチャー: `start_kairi.bat`。

---

## コントリビュート

いちばん嬉しいのは「幻覚の再現 → eval ケース1枚」です。

```bash
cd backend
python evals/from_violations.py --write
python evals/run_evals.py
```

[CONTRIBUTING.md](CONTRIBUTING.md) を参照。

---

## ライセンス

[MIT](LICENSE)。投資・医療・法律の助言ではありません。会話内容は、あなたが設定した LLM／検索プロバイダにのみ送られます。

日本語の有料 zip 配布がある場合でも、そのチャネル専用の文書はこの public ツリーには含みません。
