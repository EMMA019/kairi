import os
import json

def extract_png_text(path):
    # Quick pure python way to extract tEXt/iTXt chunks from a PNG without Pillow
    # (Since Pillow might not be in the base python environment or we want to be safe)
    try:
        from PIL import Image
        with Image.open(path) as img:
            return img.info.get("parameters", "")
    except Exception:
        # Fallback if PIL is not installed
        return "PIL not available to read metadata."

img_dir = r"d:\program\chat\img"
if not os.path.exists(img_dir):
    print("Dir not found.")
else:
    images = [f for f in os.listdir(img_dir) if f.endswith('.png')]
    if not images:
        print("No images found.")
    else:
        latest_img = max(images, key=lambda x: os.path.getctime(os.path.join(img_dir, x)))
        path = os.path.join(img_dir, latest_img)
        print(f"Checking metadata of {latest_img}:")
        
        info = extract_png_text(path)
        print("\n--- PNG Info Parameters ---")
        print(info)
        
        if "kairi_v1" in info or "Lora hashes" in info:
            print("\n✅ LoRA is mentioned in the metadata!")
        else:
            print("\n❌ LoRA might NOT be applied (not in metadata).")
