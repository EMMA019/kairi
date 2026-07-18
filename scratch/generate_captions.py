import os
from pathlib import Path

# 画像フォルダ
img_dir = Path("d:/program/chat/img")

# 共通コアトリガーワード＆品質タグ
base_tags = "kairi, 1girl, anime style, long caramel brown twintails, amber eyes, japanese cute girl, energetic big smile, gyaru style, cute outfit, high quality, masterpiece"

# imgフォルダ内のすべての png/jpg ファイルに対して txt ファイルを自動作成
image_files = list(img_dir.glob("*.png")) + list(img_dir.glob("*.jpg"))

count = 0
for img_path in image_files:
    txt_path = img_path.with_suffix(".txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(base_tags)
    count += 1

print(f"✅ {count}枚の画像に対してLoRA学習用キャプション(.txt)を全自動作成しました！")
