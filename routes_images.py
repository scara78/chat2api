"""POST /v1/images/generations & /v1/images/edits — ChatGPT Web image generation."""

import base64
import os
import time
import uuid
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from config import settings
from image_utils import SIZE_TABLE, resolve_image_size
from token_manager import token_manager
from web_client import WebImageClient

router = APIRouter()

IMAGES_DIR = os.path.join(os.path.dirname(__file__), "images")
os.makedirs(IMAGES_DIR, exist_ok=True)


@router.post("/v1/images/generations")
async def image_generations(request: Request):
    body: dict[str, Any] = await request.json()
    return await _create_image(body, request)


@router.post("/v1/images/edits")
async def image_edits(request: Request):
    body: dict[str, Any] = await request.json()
    return await _create_image(body, request, edit=True)


async def _create_image(body: dict[str, Any], request: Request, edit: bool = False) -> JSONResponse:
    try:
        token = token_manager.get()
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": {"message": str(e)}})

    prompt = body.get("prompt", "")
    if not prompt:
        return JSONResponse(status_code=400, content={"error": {"message": "prompt is required"}})

    n = body.get("n", 1) or body.get("count", 1) or 1
    size = body.get("size", "1024x1024")
    ratio = body.get("ratio") or body.get("aspect_ratio") or ""
    web_model = body.get("web_model") or settings.web_image_model

    ref_images = body.get("ref_assets", []) or body.get("images", []) or []
    if body.get("image"):
        ref_images = [body["image"]] + ref_images

    if not ratio:
        ratio = _ratio_from_size(size)

    client = WebImageClient(
        session_token=token,
        base_url=settings.chatgpt_base_url,
        proxy_url=settings.proxy_url,
    )

    try:
        assets = await client.generate_image(
            prompt=prompt,
            size=size,
            ratio=ratio,
            n=n,
            ref_images=ref_images,
            web_model=web_model,
        )
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": {"message": str(e)}})

    if not assets:
        return JSONResponse(status_code=502, content={"error": {"message": "returned 0 images"}})

    data = []
    for asset in assets:
        url = asset["url"]
        mime = asset.get("mime", "image/png")
        ext = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}.get(mime, ".png")
        filename = f"{uuid.uuid4().hex}{ext}"
        filepath = os.path.join(IMAGES_DIR, filename)

        if url.startswith("data:"):
            _, b64_data = url.split(",", 1)
            img_bytes = base64.b64decode(b64_data)
            with open(filepath, "wb") as f:
                f.write(img_bytes)
        else:
            continue

        base_url = settings.public_url.rstrip("/") if settings.public_url else str(request.base_url).rstrip("/")
        local_url = f"{base_url}/images/{filename}"
        data.append({"url": local_url})

    if not data:
        return JSONResponse(status_code=502, content={"error": {"message": "failed to save images"}})

    return JSONResponse(status_code=200, content={"created": int(time.time()), "data": data})


def _ratio_from_size(size: str) -> str:
    size_to_ratio: dict[str, str] = {}
    for tier_sizes in SIZE_TABLE.values():
        for ratio, s in tier_sizes.items():
            size_to_ratio[s] = ratio
    return size_to_ratio.get(size.strip(), "1:1")