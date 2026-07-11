"""POST /v1/chat/completions — Chat Completions via ChatGPT Web."""

import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from config import settings
from http_client import build_session
from token_manager import token_manager
from web_fingerprint import WebFingerprint
from web_proof import build_legacy_requirements_token, build_proof_token

router = APIRouter()


@router.post("/v1/chat/completions")
async def chat_completions(request: Request):
    try:
        token = token_manager.get()
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": {"message": str(e)}})

    body: dict[str, Any] = await request.json()
    if "messages" not in body:
        return JSONResponse(status_code=400, content={"error": {"message": "messages is required"}})

    model = body.get("model", settings.web_chat_model)
    stream = body.get("stream", False)

    try:
        if stream:
            return StreamingResponse(
                _stream_chat(token, model, body),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
            )
        return await _complete_chat(token, model, body)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=502, content={"error": {"message": str(e)}})


async def _complete_chat(token: str, model: str, body: dict[str, Any]) -> JSONResponse:
    fp = WebFingerprint()
    base = settings.chatgpt_base_url.rstrip("/")

    async with build_session() as session:
        reqs = await _get_requirements(session, fp, base, token)
        conduit = await _prepare_conversation(session, fp, base, token, model, reqs)

        messages = body.get("messages", [])
        prompt = _messages_to_prompt(messages)

        path = "/backend-api/f/conversation"
        conv_body = _build_conversation_body(model, prompt)
        headers = fp.image_headers(token, path, reqs["token"], reqs["proof_token"], reqs["so_token"], conduit=conduit, accept="text/event-stream")

        resp = await session.post(f"{base}{path}", json=conv_body, headers=headers)
        if resp.status_code >= 400:
            return JSONResponse(status_code=resp.status_code, content={"error": {"message": f"upstream {resp.status_code}: {resp.text[:300]}"}})

        content = _parse_chat_response(resp.text)
        prompt_tokens = len(prompt) // 4 + 1
        completion_tokens = len(content) // 4 + 1

        return JSONResponse(status_code=200, content={
            "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "total_tokens": prompt_tokens + completion_tokens},
        })


async def _stream_chat(token: str, model: str, body: dict[str, Any]):
    fp = WebFingerprint()
    base = settings.chatgpt_base_url.rstrip("/")

    try:
        async with build_session() as session:
            reqs = await _get_requirements(session, fp, base, token)
            conduit = await _prepare_conversation(session, fp, base, token, model, reqs)

            messages = body.get("messages", [])
            prompt = _messages_to_prompt(messages)

            path = "/backend-api/f/conversation"
            conv_body = _build_conversation_body(model, prompt)
            headers = fp.image_headers(token, path, reqs["token"], reqs["proof_token"], reqs["so_token"], conduit=conduit, accept="text/event-stream")

            resp = await session.post(f"{base}{path}", json=conv_body, headers=headers)
            if resp.status_code >= 400:
                error_chunk = json.dumps({"error": {"message": f"upstream {resp.status_code}: {resp.text[:300]}"}})
                yield f"data: {error_chunk}\n\n"
                return

            chat_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
            last_content = ""
            chunks: list[str] = []

            for line in resp.text.split("\n"):
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                new_content = _extract_content_from_web_chunk(payload)
                if new_content and len(new_content) > len(last_content):
                    delta = new_content[len(last_content):]
                    last_content = new_content
                    chunks.append(delta)

            for delta in chunks:
                chunk = {
                    "id": chat_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}],
                }
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

            finish_chunk = {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            yield f"data: {json.dumps(finish_chunk)}\n\n"
            yield "data: [DONE]\n\n"

    except Exception as e:
        import traceback
        traceback.print_exc()
        error_chunk = json.dumps({"error": {"message": str(e)}})
        yield f"data: {error_chunk}\n\n"
        yield "data: [DONE]\n\n"


async def _get_requirements(session, fp: WebFingerprint, base: str, token: str) -> dict[str, str]:
    path = "/backend-api/sentinel/chat-requirements"
    body = {"p": build_legacy_requirements_token(fp.user_agent)}
    headers = fp.base_headers(token, path)
    headers["Content-Type"] = "application/json"

    resp = await session.post(f"{base}{path}", json=body, headers=headers)
    if resp.status_code >= 400:
        raise Exception(f"Requirements failed: {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    req_token = data.get("token", "")
    if not req_token:
        raise Exception("Requirements missing token")

    proof = ""
    pow_data = data.get("proofofwork", {})
    if pow_data.get("required") and pow_data.get("seed") and pow_data.get("difficulty"):
        proof = build_proof_token(pow_data["seed"], pow_data["difficulty"], fp.user_agent)

    return {"token": req_token, "proof_token": proof, "so_token": data.get("so_token", "")}


async def _prepare_conversation(session, fp: WebFingerprint, base: str, token: str, model: str, reqs: dict[str, str]) -> str:
    path = "/backend-api/f/conversation/prepare"
    body = {
        "action": "next",
        "fork_from_shared_post": False,
        "parent_message_id": "client-created-root",
        "model": model,
        "client_prepare_state": "none",
        "timezone_offset_min": -480,
        "timezone": "Asia/Shanghai",
        "conversation_mode": {"kind": "primary_assistant"},
        "system_hints": [],
        "supports_buffering": True,
        "supported_encodings": ["v1"],
        "client_contextual_info": {"app_name": "chatgpt.com"},
        "thinking_effort": "standard",
    }
    headers = fp.image_headers(token, path, reqs["token"], reqs["proof_token"], reqs["so_token"], accept="*/*")
    resp = await session.post(f"{base}{path}", json=body, headers=headers)
    if resp.status_code >= 400:
        raise Exception(f"Prepare failed: {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    conduit = data.get("conduit_token", "")
    if not conduit:
        raise Exception("Prepare missing conduit token")
    return conduit


def _build_conversation_body(model: str, prompt: str) -> dict[str, Any]:
    return {
        "action": "next",
        "fork_from_shared_post": False,
        "parent_message_id": "client-created-root",
        "model": model,
        "client_prepare_state": "success",
        "timezone_offset_min": -480,
        "timezone": "Asia/Shanghai",
        "conversation_mode": {"kind": "primary_assistant"},
        "enable_message_followups": True,
        "system_hints": [],
        "supports_buffering": True,
        "supported_encodings": [],
        "client_contextual_info": {
            "is_dark_mode": False,
            "time_since_loaded": 30,
            "page_height": 1111,
            "page_width": 1731,
            "pixel_ratio": 1.5,
            "screen_height": 1440,
            "screen_width": 2560,
            "app_name": "chatgpt.com",
        },
        "paragen_cot_summary_display_override": "allow",
        "force_parallel_switch": "auto",
        "thinking_effort": "standard",
        "messages": [{
            "id": str(uuid.uuid4()),
            "author": {"role": "user"},
            "create_time": int(time.time()),
            "content": {"content_type": "text", "parts": [prompt]},
            "metadata": {
                "developer_mode_connector_ids": [],
                "selected_github_repos": [],
                "selected_all_github_repos": False,
                "serialization_metadata": {"custom_symbol_offsets": []},
            },
        }],
    }


def _messages_to_prompt(messages: list[dict]) -> str:
    parts = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            text_parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
            content = "\n".join(text_parts)
        if content:
            if role == "system":
                parts.append(f"[System]: {content}")
            elif role == "assistant":
                parts.append(f"[Assistant]: {content}")
            else:
                parts.append(content)
    return "\n\n".join(parts)


def _parse_chat_response(sse_text: str) -> str:
    last_content = ""
    for line in sse_text.split("\n"):
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        content = _extract_content_from_web_chunk(payload)
        if content and len(content) >= len(last_content):
            last_content = content
    return last_content


def _extract_content_from_web_chunk(payload: str) -> str:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return ""

    if not isinstance(data, dict):
        return ""

    msg = data.get("message")
    if not isinstance(msg, dict):
        v = data.get("v")
        if isinstance(v, dict):
            msg = v.get("message")
    if not isinstance(msg, dict):
        return ""

    author = msg.get("author")
    if not isinstance(author, dict) or author.get("role") != "assistant":
        return ""

    content = msg.get("content")
    if not isinstance(content, dict):
        return ""
    parts = content.get("parts", [])
    for part in reversed(parts):
        if isinstance(part, str):
            return part
    return ""