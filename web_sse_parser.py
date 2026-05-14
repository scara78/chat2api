"""解析 ChatGPT Web 端 SSE 流，提取对话 ID 和图片资产。"""

import json
import re
from typing import Any
from urllib.parse import urlparse

# ---------- 正则 ----------

_CONVERSATION_ID_RE = re.compile(r'"conversation_id"\s*:\s*"([^"]+)"')
_FILE_ID_RE = re.compile(r"file[-_][A-Za-z0-9][A-Za-z0-9_-]{7,}")
_SEDIMENT_ID_RE = re.compile(r"sediment://([A-Za-z0-9_-]+)")
_ASSET_URL_RE = re.compile(
    r"https:\\?/\\?/(?:files\.oaiusercontent\.com|oaidalleapiprodscus\.blob\.core\.windows\.net)[^\"\\]+"
)


def parse_web_image_sse(text: str) -> tuple[str, list[str], list[str], list[str], str]:
    """解析 Web 端图片生成的 SSE 流。

    返回: (conversation_id, file_ids, sediment_ids, direct_urls, last_text)
    """
    conversation_id = ""
    last_text = ""
    file_ids: list[str] = []
    sediment_ids: list[str] = []
    direct_urls: list[str] = []
    data_lines: list[str] = []

    def flush():
        nonlocal conversation_id, last_text
        if not data_lines:
            return
        data = "\n".join(data_lines).strip()
        data_lines.clear()
        if not data or data == "[DONE]":
            return

        # 提取 conversation_id
        cid, fids, sids, durls = extract_web_image_ids(data)
        if cid and not conversation_id:
            conversation_id = cid
        _add_unique(file_ids, *fids)
        _add_unique(sediment_ids, *sids)
        _add_unique_urls(direct_urls, *durls)

        # 提取 tool message 中的 asset pointers
        try:
            parsed = json.loads(data)
            if isinstance(parsed, dict):
                tool_fids, tool_sids = extract_web_image_tool_ids(parsed)
                _add_unique(file_ids, *tool_fids)
                _add_unique(sediment_ids, *tool_sids)
        except (json.JSONDecodeError, TypeError):
            pass

        # 提取 direct URLs from SSE events
        _add_unique_urls(direct_urls, *extract_web_image_direct_urls(data))

        # 提取 assistant text
        text = _extract_assistant_text(data)
        if text:
            last_text = text

        # 处理 response.completed / output_item.done 中的图片
        try:
            ev = json.loads(data)
            if not isinstance(ev, dict):
                return
            ev_type = ev.get("type", "")

            if ev_type == "response.output_item.done":
                item = ev.get("item", {})
                if item.get("type"):
                    b64, url = _output_image_payload(item)
                    if url:
                        _add_unique_urls(direct_urls, url)
                    elif b64:
                        mime = _mime_for_format(item.get("output_format", ""))
                        _add_unique(direct_urls, f"data:{mime};base64,{b64}")

            elif ev_type == "response.completed":
                for out in ev.get("response", {}).get("output", []):
                    b64, url = _output_image_payload(out)
                    if url:
                        _add_unique_urls(direct_urls, url)
                    elif b64:
                        mime = _mime_for_format(out.get("output_format", ""))
                        _add_unique(direct_urls, f"data:{mime};base64,{b64}")

            elif ev_type == "response.image_generation_call.partial_image":
                b64 = ev.get("partial_image_b64", "")
                if b64:
                    mime = _mime_for_format(ev.get("output_format", ""))
                    _add_unique(direct_urls, f"data:{mime};base64,{b64}")

            # 也检查顶层 output 字段
            direct_output = ev.get("output", [])
            if isinstance(direct_output, list) and direct_output and ev_type == "":
                for out in direct_output:
                    if isinstance(out, dict):
                        b64, url = _output_image_payload(out)
                        if url:
                            _add_unique_urls(direct_urls, url)
                        elif b64:
                            mime = _mime_for_format(out.get("output_format", ""))
                            _add_unique(direct_urls, f"data:{mime};base64,{b64}")

        except (json.JSONDecodeError, TypeError, KeyError):
            pass

    for line in text.split("\n"):
        if line == "":
            flush()
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].strip())

    flush()
    return conversation_id, file_ids, sediment_ids, direct_urls, last_text


def extract_web_image_ids(payload: str) -> tuple[str, list[str], list[str], list[str]]:
    """从 payload 中提取 conversation_id, file_ids, sediment_ids, direct_urls。"""
    conversation_id = ""
    m = _CONVERSATION_ID_RE.search(payload)
    if m:
        conversation_id = m.group(1)

    file_ids = list(set(_FILE_ID_RE.findall(payload)))
    sediment_ids = list(set(m.group(1) for m in _SEDIMENT_ID_RE.finditer(payload)))

    direct_urls: list[str] = []
    for raw in _ASSET_URL_RE.findall(payload):
        u = raw.replace("\\/", "/").replace("\\u0026", "&")
        if "openaiassets.blob.core.windows.net/$web/chatgpt/" in u:
            continue
        _add_unique_urls(direct_urls, u)

    return conversation_id, file_ids, sediment_ids, direct_urls


def extract_web_image_direct_urls(payload: str) -> list[str]:
    _, _, _, urls = extract_web_image_ids(payload)
    return urls


def extract_web_image_tool_ids(v: Any) -> tuple[list[str], list[str]]:
    """递归遍历 JSON 结构，提取 tool message 中的 file_ids 和 sediment_ids。"""
    file_ids: list[str] = []
    sediment_ids: list[str] = []
    _walk_web_image_tool_messages(v, file_ids, sediment_ids)
    return file_ids, sediment_ids


def is_generated_web_asset_url(raw_url: str) -> bool:
    """判断 URL 是否为生成的图片资产。"""
    try:
        u = urlparse(raw_url.strip())
    except Exception:
        return False
    if not u.hostname:
        return False
    host = u.hostname.lower()
    path = u.path.lower()

    if "openaiassets.blob.core.windows.net" in host:
        return False
    if any(x in path for x in ("/$web/chatgpt/", "filled-plus-icon", "icon", "logo")):
        return False

    return (
        "files.oaiusercontent.com" in host
        or "oaidalleapiprodscus.blob.core.windows.net" in host
        or (host.endswith(".blob.core.windows.net") and "/$web/" not in path)
    )


# ---------- 内部工具 ----------


def _output_image_payload(item: dict) -> tuple[str, str]:
    """从 output item 中提取 (b64_data, url)。"""
    for key in ("result", "b64_json", "image_b64"):
        if v := item.get(key, ""):
            return v, ""
    if v := item.get("url", ""):
        return "", v
    for content in item.get("content", []):
        if isinstance(content, dict):
            for key in ("result", "b64_json", "image_b64"):
                if v := content.get(key, ""):
                    return v, ""
            if v := content.get("url", ""):
                return "", v
    return "", ""


def _mime_for_format(fmt: str) -> str:
    fmt = (fmt or "").lower().strip()
    if fmt in ("jpeg", "jpg"):
        return "image/jpeg"
    if fmt == "webp":
        return "image/webp"
    return "image/png"


def _walk_web_image_tool_messages(v: Any, file_ids: list[str], sediment_ids: list[str]):
    if isinstance(v, dict):
        msg = _as_web_message_map(v)
        if msg and _is_web_image_asset_message(msg):
            _extract_web_asset_pointers(msg, file_ids, sediment_ids)
        for val in v.values():
            _walk_web_image_tool_messages(val, file_ids, sediment_ids)
    elif isinstance(v, list):
        for val in v:
            _walk_web_image_tool_messages(val, file_ids, sediment_ids)


def _as_web_message_map(m: dict) -> dict | None:
    if "message" in m and isinstance(m["message"], dict):
        return m["message"]
    if "author" in m and isinstance(m["author"], dict):
        return m
    return None


def _is_web_image_asset_message(msg: dict) -> bool:
    author = msg.get("author", {})
    metadata = msg.get("metadata", {})
    content = msg.get("content", {})
    role = str(author.get("role", "")).lower().strip()
    task_type = str(metadata.get("async_task_type", "") or metadata.get("task_type", "")).lower().strip()
    content_type = str(content.get("content_type", "")).lower().strip()

    if role not in ("tool", "assistant"):
        return False
    if task_type and "image" not in task_type and "picture" not in task_type:
        return False
    return "text" in content_type or "image" in content_type


def _extract_web_asset_pointers(msg: dict, file_ids: list[str], sediment_ids: list[str]):
    content = msg.get("content", {})
    _walk_web_asset_pointers(content, file_ids, sediment_ids)


def _walk_web_asset_pointers(v: Any, file_ids: list[str], sediment_ids: list[str]):
    if isinstance(v, dict):
        ptr = str(v.get("asset_pointer", "")).strip()
        if ptr:
            _add_web_asset_pointer(ptr, file_ids, sediment_ids)
        for val in v.values():
            _walk_web_asset_pointers(val, file_ids, sediment_ids)
    elif isinstance(v, list):
        for val in v:
            _walk_web_asset_pointers(val, file_ids, sediment_ids)
    elif isinstance(v, str):
        _add_web_asset_pointer(v, file_ids, sediment_ids)


def _add_web_asset_pointer(ptr: str, file_ids: list[str], sediment_ids: list[str]):
    if ptr.startswith("file-service://"):
        fid = ptr[len("file-service://"):]
        if fid and fid != "file_upload":
            _add_unique(file_ids, fid)
    elif ptr.startswith("sediment://"):
        sid = ptr[len("sediment://"):]
        if sid:
            _add_unique(sediment_ids, sid)


def _extract_assistant_text(payload: str) -> str:
    try:
        ev = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(ev, dict):
        return ""
    # Handle {"v": {"message": ...}} wrapper
    if "v" in ev and isinstance(ev["v"], dict):
        ev = ev["v"]
    return _find_first_string_by_key(ev, "parts")


def _find_first_string_by_key(v: Any, key: str) -> str:
    if isinstance(v, dict):
        if key in v:
            val = v[key]
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, str) and item.strip():
                        return item.strip()
        for val in v.values():
            s = _find_first_string_by_key(val, key)
            if s:
                return s
    elif isinstance(v, list):
        for val in v:
            s = _find_first_string_by_key(val, key)
            if s:
                return s
    return ""


def _add_unique(dst: list[str], *vals: str):
    for v in vals:
        if v and v not in dst:
            dst.append(v)


def _add_unique_urls(dst: list[str], *vals: str):
    for v in vals:
        if is_generated_web_asset_url(v):
            _add_unique(dst, v)
