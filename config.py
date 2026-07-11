"""Configurație aplicație."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Token singur (backward compat)
    chatgpt_access_token: str = ""
    # Multiple tokeni separați prin virgulă
    chatgpt_access_tokens: str = ""

    chatgpt_base_url: str = "https://chatgpt.com"
    proxy_url: str = ""
    port: int = 8700
    timeout: int = 600
    public_url: str = ""
    web_image_model: str = "gpt-5-5-thinking"
    web_chat_model: str = "gpt-4o"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()