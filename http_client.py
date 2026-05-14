"""HTTP 客户端封装 — 使用 curl_cffi 模拟 Chrome TLS 指纹绕过 Cloudflare。"""

from curl_cffi.requests import AsyncSession, Response

from config import settings


def build_session() -> AsyncSession:
    """构造带 Chrome 指纹的异步 HTTP 会话。"""
    proxy = settings.proxy_url.strip() or None
    return AsyncSession(
        impersonate="chrome",
        proxy=proxy,
        verify=False,
        timeout=settings.timeout,
    )
