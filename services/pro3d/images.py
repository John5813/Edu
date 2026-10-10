"""3D obyektlar: Together modeli chizadi → fon olib tashlanadi → yorliq chiziqlari uchun nuqtalar topiladi.

Rasm modeli (sukut — FLUX.2 Pro, keyin Imagen 4 Ultra va boshqalar) obyektni toza oq fonda, studiya
yorug'ida chizadi. Fon serverning o'zida olib tashlanadi (`cutout`). "callouts" slaydida chiziq obyektning
qaysi joyiga borishini vision modeli (rasmni "ko'radigan" AI) aytadi; u javob bermasa — nuqta obyektning
o'sha tomondagi chetidan olinadi, shunda chiziq har doim obyektga tegadi.
"""
import asyncio
import base64
import io
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

from . import cutout

log = logging.getLogger(__name__)

DEFAULT_MODELS = ("black-forest-labs/FLUX.2-pro,google/imagen-4.0-ultra,black-forest-labs/FLUX.1.1-pro,"
                  "ByteDance-Seed/Seedream-4.0,black-forest-labs/FLUX.2-dev")
PARALLEL = 3            # bir vaqtda chiziladigan rasmlar
OUT_DIR = os.path.join("temp", "pro3d")

STYLE_PROMPT = {
    "realistic": ("Photorealistic high-detail 3D render of {obj}. A single isolated object, the whole object "
                  "fully visible and centred with a generous empty margin around it, on a plain pure white "
                  "background (#FFFFFF). Soft even studio lighting, subtle ambient occlusion, physically based "
                  "materials, sharp focus, no floor, no cast shadow on the background, no text, no labels, "
                  "no watermark."),
    "stylized": ("Cute stylized 3D render of {obj}, glossy clay-like materials, soft rounded shapes, Pixar-like "
                 "quality. A single isolated object, the whole object fully visible and centred with a generous "
                 "empty margin, on a plain pure white background (#FFFFFF). Soft studio lighting, no floor, no "
                 "cast shadow on the background, no text, no labels, no watermark."),
}


def models() -> List[str]:
    raw = os.getenv("PRO3D_IMAGE_MODELS") or DEFAULT_MODELS
    return [m.strip() for m in raw.split(",") if m.strip()]


@dataclass
class Picture:
    path: str                       # PNG (shaffof bo'lsa — RGBA)
    width: int
    height: int
    transparent: bool
    alpha: Optional[np.ndarray] = field(default=None, repr=False)   # 0..255, kichraytirilgan niqob


def prompt_for(obj: str, style: str) -> str:
    return STYLE_PROMPT.get(style, STYLE_PROMPT["realistic"]).format(obj=obj.strip().rstrip("."))


def _finish(raw_path: str) -> Optional[Picture]:
    """Chizilgan rasm → shaffof, chetlari kesilgan PNG."""
    try:
        image = Image.open(raw_path)
        image.load()
    except Exception as exc:
        log.warning("Rasm ochilmadi (%s): %s", raw_path, exc)
        return None
    cut, method = cutout.cut(image)
    transparent = bool(method) and cutout.is_transparent(cut)
    final = cutout.trim(cut) if transparent else image.convert("RGB")
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"obj_{uuid.uuid4().hex[:12]}.png")
    final.save(path, optimize=True)
    alpha = None
    if transparent:
        small = final.copy()
        small.thumbnail((240, 240))
        alpha = np.asarray(small.split()[-1])
    log.info("3D obyekt tayyor: %s (fon: %s, %dx%d)", path, method or "olib tashlanmadi", *final.size)
    return Picture(path, final.width, final.height, transparent, alpha)


async def draw(objects: Dict[str, str], style: str,
               progress: Optional[Callable[[int, int], None]] = None) -> Dict[str, Picture]:
    """Har obyekt uchun rasm: id → Picture. Chizilmaganlari natijada bo'lmaydi."""
    from services.together_service import get_together_service

    service = get_together_service()
    chain = models()
    loop = asyncio.get_running_loop()
    gate = asyncio.Semaphore(PARALLEL)
    done = {"n": 0}
    result: Dict[str, Picture] = {}

    async def one(oid: str, obj: str):
        async with gate:
            raw = None
            try:
                raw = await service.generate_with_models(prompt_for(obj, style), chain, stem="pro3d_raw")
                if raw:
                    picture = await loop.run_in_executor(None, _finish, raw)
                    if picture:
                        result[oid] = picture
            except Exception as exc:
                log.warning("3D obyekt chizilmadi (%s): %s", oid, exc)
            finally:
                if raw:
                    try:
                        os.remove(raw)
                    except OSError:
                        pass
                done["n"] += 1
                if progress:
                    try:
                        progress(done["n"], len(objects))
                    except Exception:
                        pass

    await asyncio.gather(*(one(oid, obj) for oid, obj in objects.items()))
    return result


# ───────────────────────────────────────────── yorliq chiziqlari qayerga boradi

LOCATE_PROMPT = """The image shows: {obj}.
For each part below, give the point on the image where a label line should touch that part
(a clearly visible spot ON the part itself). Coordinates are normalised 0-1000: x from the left edge,
y from the top edge of the image. If a part is hidden, give the closest visible spot of the object where it
would be.
Parts:
{parts}
JSON only: {{"points": [{{"n": 1, "x": 500, "y": 300}}]}}"""


def _data_url(picture: Picture, side: int = 768) -> str:
    image = Image.open(picture.path).convert("RGBA")
    image.thumbnail((side, side))
    canvas = Image.new("RGB", image.size, (255, 255, 255))
    canvas.paste(image, mask=image.split()[-1])
    buffer = io.BytesIO()
    canvas.save(buffer, "JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def _on_object(picture: Picture, x: float, y: float) -> Tuple[float, float]:
    """Nuqtani obyektning ustiga tushiradi (shaffof joyga tushsa — eng yaqin obyekt nuqtasiga)."""
    alpha = picture.alpha
    if alpha is None:
        return x, y
    h, w = alpha.shape
    px, py = min(w - 1, max(0, int(x * w))), min(h - 1, max(0, int(y * h)))
    if alpha[py, px] > 96:
        return x, y
    ys, xs = np.nonzero(alpha > 96)
    if not len(xs):
        return x, y
    k = int(np.argmin((xs - px) ** 2 + (ys - py) ** 2))
    return (xs[k] + 0.5) / w, (ys[k] + 0.5) / h


def edge_points(picture: Picture, sides: List[str], rows: List[float]) -> List[Tuple[float, float]]:
    """Zaxira: har yorliq uchun obyektning o'sha tomondagi cheti (biroz ichkarida), berilgan balandlikda."""
    alpha = picture.alpha
    out = []
    for side, row in zip(sides, rows):
        if alpha is None:
            out.append((0.3 if side == "left" else 0.7, row))
            continue
        h, w = alpha.shape
        y = min(h - 1, max(0, int(row * h)))
        found = None
        for dy in range(0, h):
            for yy in (y - dy, y + dy):
                if 0 <= yy < h:
                    xs = np.nonzero(alpha[yy] > 96)[0]
                    if len(xs):
                        found = (yy, xs)
                        break
            if found:
                break
        if not found:
            out.append((0.5, row))
            continue
        yy, xs = found
        edge = xs.min() if side == "left" else xs.max()
        inward = max(2, int((xs.max() - xs.min()) * 0.12))
        x = edge + inward if side == "left" else edge - inward
        out.append(((x + 0.5) / w, (yy + 0.5) / h))
    return out


def locate(picture: Picture, obj: str, parts: List[str]) -> List[Optional[Tuple[float, float]]]:
    """Vision modeli bilan har qism nuqtasi (0..1). Javob bo'lmasa — None lar (zaxira chaqiruvchida)."""
    from services.premium_presentation import llm_client

    if not parts:
        return []
    listing = "\n".join(f"{i}. {p}" for i, p in enumerate(parts, 1))
    payload = {
        "temperature": 0,
        "max_tokens": 400,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": LOCATE_PROMPT.format(obj=obj[:200], parts=listing)},
            {"type": "image_url", "image_url": {"url": _data_url(picture)}},
        ]}],
    }
    try:
        data = llm_client._request("vision", payload, timeout=90)
        raw = llm_client._clean_json(llm_client._content(data))
        points = json.loads(raw).get("points") or []
    except Exception as exc:
        log.warning("Yorliq nuqtalari topilmadi (vision): %s", exc)
        return [None] * len(parts)
    out: List[Optional[Tuple[float, float]]] = [None] * len(parts)
    for i, item in enumerate(points):
        try:
            n = int(item.get("n", i + 1)) - 1
            x, y = float(item["x"]) / 1000.0, float(item["y"]) / 1000.0
        except (TypeError, ValueError, KeyError, AttributeError):
            continue
        if 0 <= n < len(parts) and 0 <= x <= 1 and 0 <= y <= 1:
            out[n] = _on_object(picture, x, y)
    return out
