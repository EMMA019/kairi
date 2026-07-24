import urllib.request
import os
import ssl

ssl._create_default_https_context = ssl._create_unverified_context

url = "https://huggingface.co/Linaqruf/anylora/resolve/main/AnyLoRA_noVae_fp16-pruned.safetensors"
dest = r"d:\program\chat\tools\lora_studio\sd-webui-forge\models\Stable-diffusion\AnyLoRA.safetensors"

print(f"Downloading base model (AnyLoRA) to {dest}...")
print("This may take a few minutes as the file is around 2GB.")

try:
    urllib.request.urlretrieve(url, dest)
    print("Download complete!")
except Exception as e:
    print(f"Failed to download: {e}")
