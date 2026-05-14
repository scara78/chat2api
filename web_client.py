"""ChatGPT Web Cookie 模式客户端。

模拟浏览器访问 chatgpt.com 的内部 API 来生成图片。
使用 curl_cffi 模拟 Chrome TLS 指纹绕过 Cloudflare。
"""

import asyncio
import base64
import json
import time
import uuid
from typing import Any
from urllib.parse import quote, urlparse

from config import settings
from http_client import build_session
from web_fingerprint import WebFingerprint
from web_proof import build_legacy_requirements_token, build_proof_token
from web_sse_parser import (
    extract_web_image_ids,
    extract_web_image_tool_ids,
    is_generated_web_asset_url,
    parse_web_image_sse,
)


class WebImageClient:
    """通过 ChatGPT Web 端生成图片的客户端。"""

    def __init__(self, session_token: str, base_url: str = "https://chatgpt.com", proxy_url: str = ""):
        self.session_token = session_token
        self.base_url = base_url.rstrip("/")
        self.proxy_url = proxy_url or None
        self.fp = WebFingerprint()

    async def generate_image(
        self,
        prompt: str,
        size: str = "1024x1024",
        ratio: str = "1:1",
        n: int = 1,
        ref_images: list[str] | None = None,
        web_model: str = "gpt-5-5-thinking",
    ) -> list[dict[str, Any]]:
        """生成图片，返回 [{"url": "data:...", "mime": "image/png"}, ...]"""
        ref_images = ref_images or []
        prompt = self._build_prompt(prompt, ratio, size)

        async with build_session() as session:
            # 1. Bootstrap
            await self._bootstrap(session)

            # 2. 获取 requirements token
            reqs = await self._get_requirements(session)

            # 3. 上传参考图（如果有）
            refs: list[dict[str, Any]] = []
            for i, ref in enumerate(ref_images):
                meta = await self._upload_image(session, ref, f"image_{i + 1}.png")
                refs.append(meta)

            # 4. 生成图片
            assets: list[dict[str, Any]] = []
            for _ in range(n):
                if len(assets) >= n:
                    break
                result = await self._generate_one(session, reqs, prompt, web_model, refs)
                assets.extend(result)

            return assets[:n]

    async def _bootstrap(self, session):
        """模拟浏览器首次访问。"""
        headers = self.fp.base_headers()
        headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        resp = await session.get(f"{self.base_url}/", headers=headers)
        if resp.status_code >= 400:
            raise Exception(f"Web bootstrap failed: {resp.status_code}")

    async def _get_requirements(self, session) -> dict[str, str]:
        """获取 chat-requirements token 和 proof-of-work token。"""
        path = "/backend-api/sentinel/chat-requirements"
        body = {"p": build_legacy_requirements_token(self.fp.user_agent)}
        headers = self.fp.base_headers(self.session_token, path)
        headers["Content-Type"] = "application/json"

        resp = await session.post(f"{self.base_url}{path}", json=body, headers=headers)
        if resp.status_code >= 400:
            raise Exception(f"Web requirements failed: {resp.status_code}: {resp.text[:320]}")

        data = resp.json()
        if data.get("arkose", {}).get("required"):
            raise Exception("Web requires arkose challenge (not supported)")
        token = data.get("token", "")
        if not token:
            raise Exception("Web requirements missing token")

        proof = ""
        pow_data = data.get("proofofwork", {})
        if pow_data.get("required") and pow_data.get("seed") and pow_data.get("difficulty"):
            proof = build_proof_token(pow_data["seed"], pow_data["difficulty"], self.fp.user_agent)

        return {
            "token": token,
            "proof_token": proof,
            "so_token": data.get("so_token", ""),
        }

    async def _prepare_conversation(self, session, reqs: dict[str, str], prompt: str, model: str, refs: list[dict]) -> str:
        """准备对话，获取 conduit token。"""
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
            "system_hints": ["picture_v2"],
            "attachment_mime_types": ["image/png"],
            "supports_buffering": True,
            "supported_encodings": [],
            "client_contextual_info": {"app_name": "chatgpt.com"},
            "thinking_effort": "standard",
        }
        headers = self.fp.image_headers(
            self.session_token, path, reqs["token"], reqs["proof_token"], reqs["so_token"], accept="*/*"
        )
        resp = await session.post(f"{self.base_url}{path}", json=body, headers=headers)
        if resp.status_code >= 400:
            raise Exception(f"Web prepare failed: {resp.status_code}: {resp.text[:320]}")

        data = resp.json()
        conduit = data.get("conduit_token", "")
        if not conduit:
            raise Exception("Web prepare missing conduit token")
        return conduit

    async def _start_generation(self, session, reqs: dict[str, str], conduit: str, prompt: str, model: str, refs: list[dict]) -> tuple[str, list[str], list[str], list[str], str]:
        """发起图片生成对话。"""
        path = "/backend-api/f/conversation"
        content, metadata = self._build_message_content(prompt, refs)
        message_id = str(uuid.uuid4())

        body = {
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
                "time_since_loaded": 51,
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
                "id": message_id,
                "author": {"role": "user"},
                "create_time": int(time.time()),
                "content": content,
                "metadata": metadata,
            }],
        }

        headers = self.fp.image_headers(
            self.session_token, path, reqs["token"], reqs["proof_token"], reqs["so_token"],
            conduit=conduit, accept="text/event-stream",
        )

        resp = await session.post(f"{self.base_url}{path}", json=body, headers=headers)
        if resp.status_code >= 400:
            raise Exception(f"Web conversation failed: {resp.status_code}: {resp.text[:320]}")

        conversation_id, file_ids, sediment_ids, direct_urls, last_text = parse_web_image_sse(resp.text)
        file_ids, sediment_ids, direct_urls = self._filter_generated_ids(file_ids, sediment_ids, direct_urls, refs)
        return conversation_id, file_ids, sediment_ids, direct_urls, last_text

    async def _generate_one(self, session, reqs: dict[str, str], prompt: str, model: str, refs: list[dict]) -> list[dict[str, Any]]:
        """生成一张图片的完整流程。"""
        conduit = await self._prepare_conversation(session, reqs, prompt, model, refs)
        conversation_id, file_ids, sediment_ids, direct_urls, last_text = await self._start_generation(
            session, reqs, conduit, prompt, model, refs
        )

        assets: list[dict[str, Any]] = []
        deadline = time.time() + 9 * 60
        poll_count = 0

        while True:
            if conversation_id:
                poll_fids, poll_sids, poll_urls = await self._poll_conversation(session, conversation_id, refs)
                poll_count += 1
                _add_unique(file_ids, *poll_fids)
                _add_unique(sediment_ids, *poll_sids)
                _add_unique(direct_urls, *poll_urls)

                if poll_count == 1 or poll_count % 6 == 0:
                    lib_ids = await self._poll_library(session, conversation_id, refs)
                    _add_unique(file_ids, *lib_ids)

            urls = await self._resolve_image_urls(session, conversation_id, file_ids, sediment_ids, refs)
            _add_unique(urls, *[u for u in direct_urls if is_generated_web_asset_url(u) or u.startswith("data:")])

            for u in urls:
                if u.startswith("data:"):
                    mime = u.split(";")[0].split(":")[1] if ":" in u else "image/png"
                    assets.append({"url": u, "mime": mime})
                    continue
                data_url, mime = await self._download_as_data_url(session, u)
                if data_url:
                    assets.append({"url": data_url, "mime": mime})

            if assets or not conversation_id or time.time() > deadline:
                break

            await asyncio.sleep(5)

        if not assets and last_text:
            raise Exception(f"Web produced text instead of image: {last_text[:220]}")

        return assets

    async def _poll_conversation(self, session, conversation_id: str, refs: list[dict]) -> tuple[list[str], list[str], list[str]]:
        """轮询对话获取图片 ID。"""
        path = f"/backend-api/conversation/{conversation_id}"
        headers = self.fp.base_headers(self.session_token, path)
        headers["Accept"] = "application/json"
        try:
            resp = await session.get(f"{self.base_url}{path}", headers=headers)
            if resp.status_code >= 400:
                return [], [], []
            raw = resp.text
            _, fids, sids, _ = extract_web_image_ids(raw)
            tool_fids, tool_sids = extract_web_image_tool_ids(resp.json())
            _add_unique(fids, *tool_fids)
            _add_unique(sids, *tool_sids)
            _, _, _, durls = extract_web_image_ids(raw)
            fids, sids, durls = self._filter_generated_ids(fids, sids, durls, refs)
            return fids, sids, durls
        except Exception:
            return [], [], []

    async def _poll_library(self, session, conversation_id: str, refs: list[dict]) -> list[str]:
        """从 library 获取生成的图片 ID。"""
        path = "/backend-api/files/library"
        headers = self.fp.base_headers(self.session_token, path)
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"
        try:
            resp = await session.post(f"{self.base_url}{path}", json={"limit": 20, "cursor": None}, headers=headers)
            if resp.status_code >= 400:
                return []
            data = resp.json()
            ids: list[str] = []
            for item in data.get("items", []):
                fid = item.get("file_id", "")
                if not fid or item.get("origination_thread_id") != conversation_id:
                    continue
                state = (item.get("state") or "").lower()
                if state and state != "ready":
                    continue
                category = (item.get("library_file_category") or "").lower()
                if category and category != "image":
                    continue
                mime = (item.get("mime_type") or "").lower()
                if mime and not mime.startswith("image/"):
                    continue
                _add_unique(ids, fid)
            ids, _, _ = self._filter_generated_ids(ids, [], [], refs)
            return ids
        except Exception:
            return []

    async def _resolve_image_urls(self, session, conversation_id: str, file_ids: list[str], sediment_ids: list[str], refs: list[dict]) -> list[str]:
        """将 file_ids / sediment_ids 解析为可下载的 URL。"""
        exclude = set()
        for ref in refs:
            if ref.get("file_id"):
                exclude.add(ref["file_id"])
            if ref.get("library_file_id"):
                exclude.add(ref["library_file_id"])

        urls: list[str] = []
        seen: set[str] = set()

        for fid in file_ids:
            if not fid or fid == "file_upload" or fid in exclude or f"file:{fid}" in seen:
                continue
            seen.add(f"file:{fid}")
            path = f"/backend-api/files/download/{fid}"
            if conversation_id:
                path += f"?conversation_id={quote(conversation_id)}&inline=false"
            url = await self._get_download_url(session, path)
            if url:
                urls.append(url)

        if not conversation_id:
            return urls

        for sid in sediment_ids:
            if not sid or sid in exclude or f"sed:{sid}" in seen:
                continue
            seen.add(f"sed:{sid}")
            path = f"/backend-api/conversation/{conversation_id}/attachment/{sid}/download"
            url = await self._get_download_url(session, path)
            if url:
                urls.append(url)

        return urls

    async def _get_download_url(self, session, path: str) -> str:
        """获取文件下载 URL。"""
        headers = self.fp.base_headers(self.session_token, path)
        headers["Accept"] = "application/json"
        try:
            resp = await session.get(f"{self.base_url}{path}", headers=headers)
            if resp.status_code >= 400:
                return ""
            data = resp.json()
            return data.get("download_url", "") or data.get("url", "")
        except Exception:
            return ""

    async def _download_as_data_url(self, session, raw_url: str) -> tuple[str, str]:
        """下载图片并转为 data URL。"""
        download_url = raw_url
        if download_url.startswith("/"):
            download_url = f"{self.base_url}{download_url}"

        headers = {}
        if self._should_use_web_headers(download_url):
            parsed = urlparse(download_url)
            headers = self.fp.base_headers(self.session_token, parsed.path)
            headers["Accept"] = "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"

        try:
            resp = await session.get(download_url, headers=headers)
            if resp.status_code >= 400 or not resp.content:
                return "", ""
            mime = resp.headers.get("content-type", "")
            if ";" in mime:
                mime = mime.split(";")[0]
            if not mime or not mime.startswith("image/"):
                if resp.content[:8] == b"\x89PNG\r\n\x1a\n":
                    mime = "image/png"
                elif resp.content[:2] == b"\xff\xd8":
                    mime = "image/jpeg"
                elif resp.content[:4] == b"RIFF":
                    mime = "image/webp"
                else:
                    mime = "image/png"
            b64 = base64.b64encode(resp.content).decode()
            return f"data:{mime};base64,{b64}", mime
        except Exception:
            return "", ""

    async def _upload_image(self, session, ref: str, name: str) -> dict[str, Any]:
        """上传参考图到 ChatGPT。"""
        data, mime = await self._read_ref_image(session, ref)
        width, height = self._detect_image_size(data)

        # Step 1: 创建文件元数据
        path = "/backend-api/files"
        meta_body = {"file_name": name, "file_size": len(data), "use_case": "multimodal", "width": width, "height": height}
        headers = self.fp.base_headers(self.session_token, path)
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"

        resp = await session.post(f"{self.base_url}{path}", json=meta_body, headers=headers)
        if resp.status_code >= 400:
            raise Exception(f"Upload meta failed: {resp.status_code}")
        meta = resp.json()
        file_id = meta.get("file_id", "")
        upload_url = meta.get("upload_url", "")
        if not file_id or not upload_url:
            raise Exception("Upload missing file metadata")

        # Step 2: 上传到 blob storage
        put_headers = {
            "Content-Type": mime,
            "x-ms-blob-type": "BlockBlob",
            "x-ms-version": "2020-04-08",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/",
            "User-Agent": self.fp.user_agent,
        }
        resp = await session.put(upload_url, content=data, headers=put_headers)
        if resp.status_code >= 400:
            raise Exception(f"Upload blob failed: {resp.status_code}")

        # Step 3: 确认上传
        confirm_path = f"/backend-api/files/{file_id}/uploaded"
        headers = self.fp.base_headers(self.session_token, confirm_path)
        headers["Content-Type"] = "application/json"
        resp = await session.post(f"{self.base_url}{confirm_path}", content=b"{}", headers=headers)
        if resp.status_code >= 400:
            raise Exception(f"Upload confirm failed: {resp.status_code}")

        # Step 4: 处理上传流
        library_file_id = await self._process_upload_stream(session, file_id, name)

        return {
            "file_id": file_id,
            "library_file_id": library_file_id,
            "file_name": name,
            "file_size": len(data),
            "mime": mime,
            "width": width,
            "height": height,
        }

    async def _process_upload_stream(self, session, file_id: str, file_name: str) -> str:
        """处理上传后的 stream，获取 library_file_id。"""
        path = "/backend-api/files/process_upload_stream"
        body = {
            "file_id": file_id,
            "use_case": "multimodal",
            "index_for_retrieval": False,
            "file_name": file_name,
            "library_persistence_mode": "opportunistic",
            "metadata": {"store_in_library": True},
            "entry_surface": "chat_composer",
        }
        headers = self.fp.base_headers(self.session_token, path)
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "text/event-stream"

        resp = await session.post(f"{self.base_url}{path}", json=body, headers=headers)
        if resp.status_code >= 400:
            raise Exception(f"Process upload failed: {resp.status_code}")

        library_file_id = ""
        for line in resp.text.split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
                mid = ev.get("extra", {}).get("metadata_object_id", "")
                if mid:
                    library_file_id = mid
            except (json.JSONDecodeError, TypeError):
                pass
        return library_file_id

    async def _read_ref_image(self, session, ref: str) -> tuple[bytes, str]:
        """读取参考图（支持 data URL 和 HTTP URL）。"""
        if ref.startswith("data:"):
            header, b64_data = ref.split(",", 1)
            data = base64.b64decode(b64_data)
            mime = header.replace("data:", "").split(";")[0]
            if not mime:
                mime = "image/png"
            return data, mime

        resp = await session.get(ref)
        if resp.status_code >= 400:
            raise Exception(f"Download ref image failed: {resp.status_code}")
        mime = resp.headers.get("content-type", "")
        if ";" in mime:
            mime = mime.split(";")[0]
        if not mime or not mime.startswith("image/"):
            mime = "image/png"
        return resp.content, mime

    def _detect_image_size(self, data: bytes) -> tuple[int, int]:
        """简单检测图片尺寸（PNG）。"""
        if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
            w = int.from_bytes(data[16:20], "big")
            h = int.from_bytes(data[20:24], "big")
            return w, h
        return 1024, 1024

    def _build_prompt(self, prompt: str, ratio: str, size: str) -> str:
        prompt = prompt.strip()
        if not prompt:
            prompt = "生成一张高质量图片"
        ratio = self._ratio_from_size(size, ratio).strip()
        if not ratio or ratio == "1:1":
            return prompt
        return f"{prompt}\n\n将宽高比设为 {ratio}"

    def _ratio_from_size(self, size: str, fallback: str) -> str:
        size_to_ratio = {
            "1024x1024": "1:1", "1248x1248": "1:1", "2480x2480": "1:1",
            "1216x832": "3:2", "1536x1024": "3:2", "832x1216": "2:3",
            "1024x1536": "2:3", "1344x768": "16:9", "768x1344": "9:16",
        }
        return size_to_ratio.get(size.strip(), fallback.strip())

    def _build_message_content(self, prompt: str, refs: list[dict]) -> tuple[dict, dict]:
        if not refs:
            content = {"content_type": "text", "parts": [prompt]}
        else:
            parts: list[Any] = []
            for ref in refs:
                fid = ref["file_id"]
                parts.append({
                    "content_type": "image_asset_pointer",
                    "asset_pointer": f"sediment://file_{fid.removeprefix('file_')}",
                    "width": ref.get("width", 1024),
                    "height": ref.get("height", 1024),
                    "size_bytes": ref.get("file_size", 0),
                })
            parts.append(prompt)
            content = {"content_type": "multimodal_text", "parts": parts}

        attachments = []
        for ref in refs:
            att: dict[str, Any] = {
                "id": ref["file_id"],
                "mime_type": ref.get("mime", "image/png"),
                "name": ref.get("file_name", "image.png"),
                "size": ref.get("file_size", 0),
                "width": ref.get("width", 1024),
                "height": ref.get("height", 1024),
                "source": "library",
                "is_big_paste": False,
            }
            if ref.get("library_file_id"):
                att["library_file_id"] = ref["library_file_id"]
            attachments.append(att)

        metadata: dict[str, Any] = {
            "developer_mode_connector_ids": [],
            "selected_github_repos": [],
            "selected_all_github_repos": False,
            "system_hints": ["picture_v2"],
            "serialization_metadata": {"custom_symbol_offsets": []},
        }
        if attachments:
            metadata["attachments"] = attachments

        return content, metadata

    def _filter_generated_ids(self, file_ids: list[str], sediment_ids: list[str], direct_urls: list[str], refs: list[dict]) -> tuple[list[str], list[str], list[str]]:
        exclude = set()
        for ref in refs:
            if ref.get("file_id"):
                exclude.add(ref["file_id"])
            if ref.get("library_file_id"):
                exclude.add(ref["library_file_id"])

        def _filter(ids: list[str]) -> list[str]:
            seen: set[str] = set()
            out: list[str] = []
            for v in ids:
                if v and v not in exclude and v not in seen:
                    seen.add(v)
                    out.append(v)
            return out

        return _filter(file_ids), _filter(sediment_ids), _filter(direct_urls)

    def _should_use_web_headers(self, raw_url: str) -> bool:
        try:
            u = urlparse(raw_url)
        except Exception:
            return False
        if not u.scheme and u.path.startswith("/backend-api/"):
            return True
        if "/backend-api/" not in u.path:
            return False
        base_host = urlparse(self.base_url).hostname or "chatgpt.com"
        return (u.hostname or "").lower() == base_host.lower()


def _add_unique(dst: list[str], *vals: str):
    for v in vals:
        if v and v not in dst:
            dst.append(v)
