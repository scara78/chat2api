"""GET /v1/models — OpenAI-compatible model listing."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from config import settings

router = APIRouter()

MODEL_CREATED = 1700000000


def _model_ids() -> list[str]:
    ids: list[str] = []
    for raw in settings.web_models.split(","):
        m = raw.strip()
        if m and m not in ids:
            ids.append(m)
    return ids


def _model_payload(model_id: str) -> dict:
    return {
        "id": model_id,
        "object": "model",
        "created": MODEL_CREATED,
        "owned_by": "chatgpt-web",
    }


@router.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [_model_payload(model_id) for model_id in _model_ids()],
    }


@router.get("/v1/models/{model_id}")
async def get_model(model_id: str):
    if model_id not in _model_ids():
        return JSONResponse(
            status_code=404,
            content={"error": {"message": f"model '{model_id}' not found", "type": "invalid_request_error"}},
        )
    return _model_payload(model_id)
