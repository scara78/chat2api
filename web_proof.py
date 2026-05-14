"""Proof-of-Work token 生成，用于通过 ChatGPT 的反滥用验证。"""

import base64
import hashlib
import json
import random
import time
import uuid
from datetime import datetime, timezone, timedelta


def build_legacy_requirements_token(user_agent: str) -> str:
    """构造 legacy requirements token（用于 /sentinel/chat-requirements 请求体）。"""
    seed = f"{random.random():.16f}"
    config = _build_config(user_agent)
    answer, _ = _pow_generate(seed, "0fffff", config)
    return "gAAAAAC" + answer


def build_proof_token(seed: str, difficulty: str, user_agent: str) -> str:
    """根据上游返回的 seed 和 difficulty 计算 PoW token。"""
    config = _build_config(user_agent)
    answer, solved = _pow_generate(seed, difficulty, config)
    if not solved:
        fallback = base64.b64encode(json.dumps(seed).encode()).decode()
        return "gAAAAAB" + fallback
    return "gAAAAAB" + answer


def _build_config(user_agent: str) -> list:
    """构造 PoW 计算所需的 config 数组。"""
    est = timezone(timedelta(hours=-5))
    now_est = datetime.now(est)
    time_str = now_est.strftime("%a %b %d %Y %H:%M:%S") + " GMT-0500 (Eastern Standard Time)"
    now_ns = time.time_ns()

    return [
        3000 + random.randint(0, 2) * 1000,
        time_str,
        4294705152,
        0,
        user_agent,
        "https://chatgpt.com/backend-api/sentinel/sdk.js",
        "",
        "en-US",
        "en-US,es-US,en,es",
        0,
        "webdriver\u226Dfalse",
        "location",
        "window",
        now_ns / 1e6,
        str(uuid.uuid4()),
        "",
        16,
        now_ns / 1e6,
    ]


def _pow_generate(seed: str, difficulty: str, config: list) -> tuple[str, bool]:
    """执行 Proof-of-Work 计算（hashcash 风格，使用 SHA3-512）。"""
    diff_bytes = _hex_to_bytes(difficulty)
    if not diff_bytes:
        fallback = base64.b64encode(json.dumps(seed).encode()).decode()
        return fallback, False

    static1 = json.dumps(config[:3])
    static1 = static1.rstrip("]") + ","

    static2 = "," + json.dumps(config[4:9]).lstrip("[").rstrip("]") + ","

    static3 = "," + json.dumps(config[10:]).lstrip("[")

    seed_bytes = seed.encode()

    for i in range(500000):
        final = static1 + str(i) + static2 + str(i >> 1) + static3
        encoded = base64.b64encode(final.encode()).decode()
        h = hashlib.sha3_512(seed_bytes + encoded.encode()).digest()
        if h[: len(diff_bytes)] <= bytes(diff_bytes):
            return encoded, True

    fallback = base64.b64encode(json.dumps(seed).encode()).decode()
    return fallback, False


def _hex_to_bytes(s: str) -> bytes:
    """将十六进制字符串转为 bytes。"""
    if len(s) % 2 == 1:
        s = "0" + s
    try:
        return bytes.fromhex(s)
    except ValueError:
        return b""
