"""GPT Proxy — Web Cookie Mode cu rotație multi-token."""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request as StarletteRequest

from config import settings
from routes_chat import router as chat_router
from routes_images import router as images_router, IMAGES_DIR
from token_manager import token_manager

app = FastAPI(
    title="GPT Proxy (Web Mode)",
    description="Personal ChatGPT Web Reverse Proxy",
    version="2.1.0",
    docs_url="/docs",
)


@app.middleware("http")
async def fix_forwarded_host(request: StarletteRequest, call_next):
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if forwarded_proto and forwarded_host:
        request.scope["scheme"] = forwarded_proto
        request.scope["server"] = (forwarded_host.split(":")[0], 443 if forwarded_proto == "https" else 80)
    return await call_next(request)


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
    count = token_manager.count()
    return JSONResponse(content={
        "ok": count > 0,
        "mode": "web_cookie",
        "token_count": count,
        "public_url": settings.public_url or "(not set)",
        "port": settings.port,
    })


app.include_router(chat_router)
app.include_router(images_router)
app.mount("/images", StaticFiles(directory=IMAGES_DIR), name="images")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.port,
        log_level="info",
    )