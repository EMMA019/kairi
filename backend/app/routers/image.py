"""
画像生成エンドポイント（Cloudflare Workers AI & Pollinations.ai 切替エンジン）。
"""
import urllib.parse
import os
import httpx
from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse, Response
from app.routers.settings import app_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

# Cloudflare Workers AI モデルID定義
CF_MODELS = {
    "cf-sdxl": "@cf/bytedance/stable-diffusion-xl-lightning",
    "cf-flux": "@cf/black-forest-labs/flux-1-schnell",
}


@router.get("/image/generate")
async def generate_image(
    prompt: str = Query(..., description="画像生成英語プロンプト"),
    width: int = Query(512, description="画像幅"),
    height: int = Query(512, description="画像高さ"),
):
    """
    設定されたエンジンに基づいて画像生成を行うエンドポイント。
    - pollinations: Pollinations.ai への307リダイレクト
    - cf-sdxl / cf-flux: Cloudflare Workers AI REST APIによる画像推論とバイナリストリーム返却
    """
    settings = app_settings.get()
    engine = settings.get("image_engine", "pollinations")
    cf_account_id = settings.get("cf_account_id") or os.environ.get("CF_ACCOUNT_ID") or "8b2e7549807032bdd0e92885d6349fa9"
    cf_api_token = settings.get("cf_api_token") or os.environ.get("CF_API_TOKEN") or ""

    # プロンプトのクオリティ強化とネガティブプロンプト
    enhanced_prompt = prompt
    if "masterpiece" not in enhanced_prompt.lower() and "best quality" not in enhanced_prompt.lower():
        enhanced_prompt += ", masterpiece, best quality, ultra-detailed, cinematic lighting, sharp focus"

    negative_prompt = "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry, mutation, deformed, ugly, extra limbs"

    # Pollinations.ai のURL生成（フォールバック時にも使用）
    encoded_prompt = urllib.parse.quote_plus(enhanced_prompt)
    pollinations_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&nologo=true&enhance=true"

    # Cloudflare Workers AI が選択されており、APIトークンが存在する場合
    if engine in CF_MODELS and cf_api_token and cf_account_id:
        model_id = CF_MODELS[engine]
        url = f"https://api.cloudflare.com/client/v4/accounts/{cf_account_id}/ai/run/{model_id}"
        headers = {
            "Authorization": f"Bearer {cf_api_token}",
            "Content-Type": "application/json",
        }
        
        # モデル種別に応じた最適なパラメータを付与
        if engine == "cf-sdxl":
            payload = {
                "prompt": enhanced_prompt,
                "negative_prompt": negative_prompt,
                "num_steps": 8,
                "width": width,
                "height": height
            }
        else:
            # cf-flux (FLUX.1-schnell)
            payload = {
                "prompt": enhanced_prompt,
                "num_steps": 8
            }

        try:
            logger.info(f"[ImageGen] Cloudflare Workers AI ({engine}: {model_id}) で画像を生成中... prompt='{prompt[:50]}...'")
            async with httpx.AsyncClient(timeout=45.0) as client:
                res = await client.post(url, headers=headers, json=payload)
                if res.status_code == 200 and len(res.content) > 1000:
                    content_type = res.headers.get("content-type", "image/png")
                    # JSONエラーでなくバイナリ画像が届いた場合のみ返却
                    if "image" in content_type or res.content[:4] in [b"\x89PNG", b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1"]:
                        return Response(content=res.content, media_type=content_type)
                    else:
                        logger.warning(f"[ImageGen] Cloudflare Workers AI から非画像レスポンス: {res.text[:200]}")
                else:
                    logger.warning(f"[ImageGen] Cloudflare Workers AI エラー (status={res.status_code}): {res.text[:200]}")
        except Exception as e:
            logger.error(f"[ImageGen] Cloudflare Workers AI 通信例外: {e}")

        logger.info("[ImageGen] Cloudflare Workers AI 生成失敗または未認証のため、Pollinations.ai に自動フォールバックします")

    # デフォルトまたはフォールバック：Pollinations.ai へリダイレクト
    return RedirectResponse(url=pollinations_url, status_code=307)
