import os
import csv
import numpy as np
from PIL import Image
from pathlib import Path
import huggingface_hub
import onnxruntime as ort

print("🎯 [Kairi Vision Tagger] WD14 AI自動タグ付けエンジンを起動しています...")

# 1. モデルとタグCSVのダウンロード（またはキャッシュ読み込み）
repo_id = "SmilingWolf/wd-v1-4-convnextv2-tagger-v2"
print(f"  -> HuggingFace Hub ({repo_id}) からモデルを取得中...")
model_path = huggingface_hub.hf_hub_download(repo_id=repo_id, filename="model.onnx")
tags_path = huggingface_hub.hf_hub_download(repo_id=repo_id, filename="selected_tags.csv")

# 2. タグリストの読み取り
tags = []
with open(tags_path, "r", encoding="utf-8") as f:
    reader = csv.reader(f)
    next(reader)  # ヘッダーをスキップ
    for row in reader:
        # row: tag_id, name, category, count
        tags.append((row[1], int(row[2])))

# 3. ONNXセッションの準備 (安定のCPUモード、1枚0.1秒で高速処理)
providers = ['CPUExecutionProvider']
session = ort.InferenceSession(model_path, providers=providers)
input_name = session.get_inputs()[0].name
target_size = session.get_inputs()[0].shape[1]  # 448 or 512

# 画像フォルダ
img_dir = Path("d:/program/chat/img")
image_files = list(img_dir.glob("*.png")) + list(img_dir.glob("*.jpg"))

print(f"🖼️ {len(image_files)} 枚の画像を個別解析し、高精度の画像専用タグを生成します...")

# 常に先頭に付与するキャラクタートリガーワード
CORE_TRIGGER = "kairi, 1girl"

# 不要なタグまたは被るタグの除外リスト
EXCLUDE_TAGS = {"1girl", "kairi", "solo"}

count = 0
for img_path in image_files:
    try:
        # 画像の前処理 (BGR / RGB / Resize / Numpy normalize)
        img = Image.open(img_path).convert("RGBA")
        # 背景白塗り (RGBA->RGB)
        new_img = Image.new("RGBA", img.size, "WHITE")
        new_img.paste(img, (0, 0), img)
        img_rgb = new_img.convert("RGB")
        
        # サイズ調整とパディング (Square)
        max_dim = max(img_rgb.size)
        pad_img = Image.new("RGB", (max_dim, max_dim), (255, 255, 255))
        pad_img.paste(img_rgb, ((max_dim - img_rgb.width) // 2, (max_dim - img_rgb.height) // 2))
        pad_img = pad_img.resize((target_size, target_size), Image.Resampling.BICUBIC)
        
        # Array化してBGR並び替えと正規化 (0-255 -> BGR float32)
        img_arr = np.array(pad_img, dtype=np.float32)
        img_arr = img_arr[:, :, ::-1]  # RGB -> BGR
        img_arr = np.expand_dims(img_arr, axis=0)
        
        # ONNX推論実行
        probs = session.run(None, {input_name: img_arr})[0][0]
        
        # 確率0.35以上のタグを抽出 (一般タグカテゴリ category==0)
        selected = []
        for (tag_name, category), prob in zip(tags, probs):
            if category == 0 and prob > 0.35:
                # アンダースコアをスペースに
                clean_tag = tag_name.replace("_", " ")
                if clean_tag not in EXCLUDE_TAGS:
                    selected.append(clean_tag)
                    
        # トリガーワードと結合して保存
        final_tags_str = f"{CORE_TRIGGER}, " + ", ".join(selected)
        txt_path = img_path.with_suffix(".txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(final_tags_str)
            
        print(f"  [{count+1}/{len(image_files)}] {img_path.name} -> {final_tags_str[:60]}...")
        count += 1
    except Exception as e:
        print(f"  ⚠️ {img_path.name} の解析エラー: {e}")

print(f"\n🎉 すべての画像({count}枚)に対して、画像個別の高精度WD14タグ付けを完了しました！")
