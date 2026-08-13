# 🎭 Kairi LoRA Studio & ストック画像自動生成ワンクリックパック

Windows / Python 3.11 / RTX 2060 12GB 向けに最適化した、完全自作LoRAの学習から大量ストック作成までのワンクリック環境ツールセットです。

---

## 🛠️ 入っているツール・スクリプト一覧（ダブルクリックで実行OK！）

### 1. `run_lora_setup_and_train.bat` （★これをダブルクリック！）
- **機能**: `.ps1` がメモ帳で開いてしまうWindowsの仕様を回避し、ダブルクリック一発で `setup_kohya_and_train.ps1` を起動させます！
- **使い方**:
  `run_lora_setup_and_train.bat` をダブルクリックして開いてください！

### 2. `run_forge_setup_and_batch_gen.bat` （★これをダブルクリック！）
- **機能**: ダブルクリック一発で SD WebUI Forge の自動ダウンロードと大量生成準備を開始します！
- **使い方**:
  `run_forge_setup_and_batch_gen.bat` をダブルクリックして開いてください！

---

## 🌟 ストック画像が出来上がったらどうする？
作成された画像は `img/` フォルダに保存されるので、
```powershell
git add .
git commit -m "feat: add new Kairi LoRA stock gallery images"
git push origin main
```
とプッシュするだけでクラウドの Kairi (`https://kairi-chat.pages.dev`) が自動で認識し、設定画面の **「📸 LoRA Curated Gallery」や「✨ Hybrid」モード** からいつでも呼び出せるようになります！
