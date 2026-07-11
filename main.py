"""GPT 反代网关 — 纯 Web Cookie 模式。

通过 ChatGPT 网页端 Access Token 调用，走订阅额度。
对外暴露 OpenAI 兼容接口。

启动：
    cd gpt
    pip install -r requirements.txt
    cp .env.example .env  # 填入你的 Access Token
    python main.py
"""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from config import settings
from routes_chat import router as chat_router
from routes_images import router as images_router
from routes_images import IMAGES_DIR

app = FastAPI(
    title="GPT Proxy (Web Mode)",
    description="个人 ChatGPT Web 反代网关",
    version="2.0.0",
    docs_url="/docs",
)

# Trust proxy headers from EasyPanel/nginx reverse proxy
from starlette.middleware import Middleware
from starlette.requests import Request as StarletteRequest

@app.middleware("http")
async def fix_forwarded_host(request: StarletteRequest, call_next):
    # EasyPanel sends X-Forwarded-Host and X-Forwarded-Proto
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if forwarded_proto and forwarded_host:
        request.scope["scheme"] = forwarded_proto
        request.scope["server"] = (forwarded_host.split(":")[0], 443 if forwarded_proto == "https" else 80)
    return await call_next(request)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
@app.get("/v1/health")
async def health():
    has_token = bool(settings.chatgpt_access_token.strip())
    return JSONResponse(content={"ok": has_token, "mode": "web_cookie", "has_token": has_token})


# 路由
app.include_router(chat_router)
app.include_router(images_router)

# 静态文件：提供生成的图片
app.mount("/images", StaticFiles(directory=IMAGES_DIR), name="images")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.port,
        log_level="info",
    )
