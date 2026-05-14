"""图片生成相关的工具函数。"""

from typing import Any

# ---------- size / quality 映射 ----------

SIZE_TABLE: dict[str, dict[str, str]] = {
    "1K": {
        "1:1": "1024x1024",
        "3:2": "1216x832",
        "2:3": "832x1216",
        "4:3": "1152x864",
        "3:4": "864x1152",
        "5:4": "1120x896",
        "4:5": "896x1120",
        "16:9": "1344x768",
        "9:16": "768x1344",
        "21:9": "1536x640",
    },
    "2K": {
        "1:1": "1248x1248",
        "3:2": "1536x1024",
        "2:3": "1024x1536",
        "4:3": "1440x1088",
        "3:4": "1088x1440",
        "5:4": "1392x1120",
        "4:5": "1120x1392",
        "16:9": "1664x928",
        "9:16": "928x1664",
        "21:9": "1904x816",
    },
    "4K": {
        "1:1": "2480x2480",
        "3:2": "3056x2032",
        "2:3": "2032x3056",
        "4:3": "2880x2160",
        "3:4": "2160x2880",
        "5:4": "2784x2224",
        "4:5": "2224x2784",
        "16:9": "3312x1872",
        "9:16": "1872x3312",
        "21:9": "3808x1632",
    },
}


def resolve_image_size(params: dict[str, Any], default: str = "1024x1024") -> str:
    """根据 size / ratio / resolution 参数推导最终尺寸。"""
    if size := _str(params, "size"):
        return size
    ratio = _str(params, "ratio") or _str(params, "aspect_ratio") or "1:1"
    tier = (_str(params, "resolution") or _str(params, "size_tier") or "1K").upper()
    by_ratio = SIZE_TABLE.get(tier, SIZE_TABLE["1K"])
    return by_ratio.get(ratio, by_ratio.get("1:1", default))


def parse_size(size: str) -> tuple[int, int]:
    parts = size.split("x")
    if len(parts) != 2:
        return 1024, 1024
    try:
        w, h = int(parts[0]), int(parts[1])
    except ValueError:
        return 1024, 1024
    return w if w > 0 else 1024, h if h > 0 else 1024


def _str(d: dict[str, Any] | None, key: str) -> str:
    if not d:
        return ""
    v = d.get(key)
    if isinstance(v, str) and v.strip():
        return v.strip()
    return ""
