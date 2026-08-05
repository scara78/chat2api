"""Token status endpoint for multi-account deployments."""

import asyncio
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from config import settings
from http_client import build_session
from token_manager import token_manager
from web_fingerprint import WebFingerprint
from web_proof import build_legacy_requirements_token

router = APIRouter()


async def _check_token(index: int, token: str) -> dict[str, Any]:
    fp = WebFingerprint()
    path = "/backend-api/sentinel/chat-requirements"
    headers = fp.base_headers(token, path)
    headers["Content-Type"] = "application/json"
    body = {"p": build_legacy_requirements_token(fp.user_agent)}
    base = settings.chatgpt_base_url.rstrip("/")

    token_hint = token[-4:] if len(token) >= 4 else token

    try:
        async with build_session() as session:
            response = await session.post(f"{base}{path}", json=body, headers=headers)

        if 200 <= response.status_code < 300:
            return {
                "token_id": index + 1,
                "token_hint": token_hint,
                "available": True,
                "status_code": response.status_code,
            }
        return {
            "token_id": index + 1,
            "token_hint": token_hint,
            "available": False,
            "status_code": response.status_code,
            "reason": "upstream_rejected_token",
        }
    except Exception:
        return {
            "token_id": index + 1,
            "token_hint": token_hint,
            "available": False,
            "status_code": None,
            "reason": "connection_or_request_error",
        }


@router.get("/scara")
async def token_status():
    tokens = token_manager.all()
    if not tokens:
        return JSONResponse(
            status_code=503,
            content={"ok": False, "token_count": 0, "tokens": [], "message": "No tokens configured"},
        )

    results = await asyncio.gather(*(_check_token(index, token) for index, token in enumerate(tokens)))
    available = sum(1 for result in results if result["available"])
    return {
        "ok": available == len(results),
        "token_count": len(results),
        "available_count": available,
        "unavailable_count": len(results) - available,
        "tokens": results,
    }
