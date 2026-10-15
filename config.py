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
    # 可选：手动固定设备指纹（跨重启稳定，减少反滥用误判）
    oai_device_id: str = ""
    oai_session_id: str = ""
    web_image_model: str = "auto"
    web_image_model_fallbacks: str = "gpt-5-1-thinking,gpt-5-1,gpt-5-thinking,gpt-5,gpt-4o"
    web_chat_model: str = "gpt-4o"
    # Modele expuse prin GET /v1/models (separate prin virgulă)
    web_models: str = "gpt-4o,gpt-4o-mini,gpt-5,gpt-5-1,gpt-5-thinking,gpt-5-1-thinking,auto,dall-e-3"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()