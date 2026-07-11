"""Rotație round-robin pentru multiple Access Tokeni ChatGPT."""

import threading
from config import settings


class TokenManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._index = 0
        self._tokens: list[str] = []
        self._load()

    def _load(self):
        tokens: list[str] = []

        # 1. CHATGPT_ACCESS_TOKENS="tok1,tok2,tok3"
        if settings.chatgpt_access_tokens.strip():
            for t in settings.chatgpt_access_tokens.split(","):
                t = t.strip()
                if t:
                    tokens.append(t)

        # 2. Fallback: CHATGPT_ACCESS_TOKEN (singur)
        if not tokens and settings.chatgpt_access_token.strip():
            tokens.append(settings.chatgpt_access_token.strip())

        self._tokens = tokens
        print(f"[TokenManager] Loaded {len(self._tokens)} token(s)", flush=True)

    def get(self) -> str:
        """Returnează următorul token prin rotație round-robin."""
        if not self._tokens:
            raise Exception("No CHATGPT_ACCESS_TOKEN configured")
        with self._lock:
            token = self._tokens[self._index % len(self._tokens)]
            self._index += 1
            return token

    def count(self) -> int:
        return len(self._tokens)


token_manager = TokenManager()