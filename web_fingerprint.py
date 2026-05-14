"""浏览器指纹模拟，用于 Web Cookie 模式。"""

import uuid


class WebFingerprint:
    """模拟 ChatGPT Web 端的浏览器指纹。"""

    def __init__(self):
        self.user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0"
        )
        self.device_id = str(uuid.uuid4())
        self.session_id = str(uuid.uuid4())
        self.client_version = "prod-be885abbfcfe7b1f511e88b3003d9ee44757fbad"
        self.build_number = "5955942"
        self.sec_ch_ua = '"Microsoft Edge";v="143", "Chromium";v="143", "Not A(Brand";v="24"'

    def base_headers(self, token: str = "", path: str = "") -> dict[str, str]:
        """构造基础 Web 请求头。"""
        h = {
            "User-Agent": self.user_agent,
            "Origin": "https://chatgpt.com",
            "Referer": "https://chatgpt.com/",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Priority": "u=1, i",
            "Sec-Ch-Ua": self.sec_ch_ua,
            "Sec-Ch-Ua-Arch": '"x86"',
            "Sec-Ch-Ua-Bitness": '"64"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Model": '""',
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Ch-Ua-Platform-Version": '"19.0.0"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "OAI-Device-Id": self.device_id,
            "OAI-Session-Id": self.session_id,
            "OAI-Language": "zh-CN",
            "OAI-Client-Version": self.client_version,
            "OAI-Client-Build-Number": self.build_number,
            "X-OpenAI-Target-Path": path,
            "X-OpenAI-Target-Route": path,
        }
        if token:
            h["Authorization"] = f"Bearer {token}"
        return h

    def image_headers(
        self,
        token: str,
        path: str,
        requirements_token: str,
        proof_token: str = "",
        so_token: str = "",
        conduit: str = "",
        accept: str = "*/*",
    ) -> dict[str, str]:
        """构造图片生成请求头（含 sentinel tokens）。"""
        h = self.base_headers(token, path)
        h["Content-Type"] = "application/json"
        h["Accept"] = accept
        h["OpenAI-Sentinel-Chat-Requirements-Token"] = requirements_token
        if proof_token:
            h["OpenAI-Sentinel-Proof-Token"] = proof_token
        if so_token:
            h["OpenAI-Sentinel-SO-Token"] = so_token
        if conduit:
            h["X-Conduit-Token"] = conduit
        if accept == "text/event-stream":
            h["X-Oai-Turn-Trace-Id"] = str(uuid.uuid4())
        return h
