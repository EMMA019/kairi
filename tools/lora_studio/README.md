# 🎭 Kairi LoRA Studio & ストック画像自動生成ワンクリックパック

NaoさんのPC環境（Windows / Python 3.11 / RTX 2060 12GB）に最適化した、完全自作LoRAの学習から大量ストック作成までのワンクリック環境ツールセットです！

---

## 🛠️ 入っているツール・スクリプト一覧

### 1. `setup_kohya_and_train.ps1` （自作LoRA学習ワンクリック実行）
- **機能**: `sd-scripts (Kohya_ss)` を自動クローンし、今回の `img/` ディレクトリ内の25枚の画像＋タグ(`.txt`)をセットアップし、RTX 2060 (12GB) の性能を100%引き出す設定でLoRAモデルを学習させます。
- **使い方**:
  PowerShell で開いて `.\setup_kohya_and_train.ps1` を実行するか、右クリックで「PowerShell で実行」を選択してください。
- **出力先**:
  学習が終わると `output/kairi_v1.safetensors` にあなただけの最強 Kairi LoRA モデルが保存されます！

### 2. `setup_webui_forge_and_batch_generate.ps1` （SD WebUI Forge 構築＆大量ストック生成）
- **機能**: 超高速で VRAM 消費が少ない最新版の `Stable Diffusion WebUI Forge` を自動クローンし、学習した LoRA を自動配置、さらに30枚〜100枚のストック画像を全自動生成する Python バッチスクリプトを作成します。
- **使い方**:
  1. `.\setup_webui_forge_and_batch_generate.ps1` を実行して Forge を準備。
  2. Forge フォルダ内の `webui-user.bat` の `COMMANDLINE_ARGS=` に `--api` を追記してダブルクリックで起動。
  3. `python run_batch_generator.py` を実行すれば、PCがお仕事して `img/` フォルダに最高画質の Kairi 画像がザクザク追加されていきます！

---

## 🌟 ストック画像が出来上がったらどうする？
作成された画像は `img/` フォルダに保存されるので、
```powershell
git add .
git commit -m "feat: add new Kairi LoRA stock gallery images"
git push origin main
```
とプッシュするだけでクラウドの Kairi (`https://kairi-chat.pages.dev`) が自動で認識し、設定画面の **「📸 LoRA Curated Gallery」や「✨ Hybrid」モード** からいつでも呼び出せるようになります！
