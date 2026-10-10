"""3D obyekt rasmining fonini olib tashlash (shaffof PNG).

Rasm modeli obyektni toza oq fonda chizadi. Fon shu serverning o'zida olib tashlanadi — tashqi pullik
xizmat (fal va h.k.) kerak emas:

1. ISNet (`isnet-general-use.onnx`, rembg loyihasining ochiq modeli) — sun'iy intellekt obyektni fondan
   ajratadi; oq suyak yoki oq tishli obyekt ham oq fonga "erib" ketmaydi. Model birinchi ishlatilganda
   yuklab olinadi (~180 MB) va keyin diskda turadi.
2. Zaxira — oq fonni rasm chetidan boshlab "to'ldirish": faqat chetga tutashgan oq soha o'chadi. Model
   yuklanmasa yoki onnxruntime o'rnatilmagan bo'lsa ham xizmat to'xtamaydi.

Ikkala yo'lda ham obyekt chetidagi oq "hoshiya" tozalanadi: yarim shaffof piksellar rangi oq fondan
ajratiladi (to'q ko'k slaydda obyekt atrofida oq chiziq qolmaydi).
"""
import logging
import os
import threading
from typing import Optional, Tuple

import numpy as np
from PIL import Image, ImageFilter

log = logging.getLogger(__name__)

MODEL_URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet-general-use.onnx"
MODEL_PATH = os.getenv("PRO3D_CUTOUT_MODEL") or os.path.join(
    os.path.expanduser("~"), ".cache", "edufayl", "isnet-general-use.onnx")
MODEL_SIZE = 1024
MIN_MODEL_BYTES = 100_000_000      # chala yuklangan fayl model emas

# Oq fon: har uch kanal shundan yorug' va rangsiz (kulrang emas) bo'lsa.
WHITE = 238
GREY_SPREAD = 20

_session = None
_session_lock = threading.Lock()
_session_failed = False


def _download(path: str) -> bool:
    import requests

    os.makedirs(os.path.dirname(path), exist_ok=True)
    part = path + ".part"
    try:
        with requests.get(MODEL_URL, stream=True, timeout=(15, 300)) as resp:
            resp.raise_for_status()
            with open(part, "wb") as out:
                for chunk in resp.iter_content(1 << 20):
                    out.write(chunk)
        if os.path.getsize(part) < MIN_MODEL_BYTES:
            raise RuntimeError(f"fayl juda kichik ({os.path.getsize(part)} bayt)")
        os.replace(part, path)
        log.info("Fon olib tashlash modeli yuklandi: %s", path)
        return True
    except Exception as exc:
        log.warning("Fon olib tashlash modeli yuklanmadi: %s", exc)
        try:
            os.remove(part)
        except OSError:
            pass
        return False


def _model():
    """ONNX sessiyasi (bir marta ochiladi). Ochib bo'lmasa None — zaxira yo'l ishlaydi."""
    global _session, _session_failed
    if _session is not None or _session_failed:
        return _session
    with _session_lock:
        if _session is not None or _session_failed:
            return _session
        try:
            import onnxruntime as ort
        except Exception as exc:
            log.warning("onnxruntime yo'q — fon oddiy usulda olib tashlanadi: %s", exc)
            _session_failed = True
            return None
        if not (os.path.exists(MODEL_PATH) and os.path.getsize(MODEL_PATH) >= MIN_MODEL_BYTES):
            if not _download(MODEL_PATH):
                _session_failed = True
                return None
        try:
            options = ort.SessionOptions()
            options.intra_op_num_threads = max(1, min(4, os.cpu_count() or 1))
            _session = ort.InferenceSession(MODEL_PATH, options, providers=["CPUExecutionProvider"])
        except Exception as exc:
            log.warning("Fon olib tashlash modeli ochilmadi: %s", exc)
            _session_failed = True
        return _session


def warm() -> None:
    """Modelni oldindan (fon oqimida) yuklab ochadi — birinchi buyurtma kutib qolmasin."""
    threading.Thread(target=_model, name="pro3d-cutout-warm", daemon=True).start()


def _model_mask(image: Image.Image) -> Optional[np.ndarray]:
    """ISNet niqobi (0..1, rasm o'lchamida) yoki None."""
    session = _model()
    if session is None:
        return None
    small = image.convert("RGB").resize((MODEL_SIZE, MODEL_SIZE), Image.LANCZOS)
    arr = np.asarray(small, dtype=np.float32)
    arr = arr / max(float(arr.max()), 1e-6) - 0.5            # rembg: mean 0.5, std 1.0
    tensor = arr.transpose(2, 0, 1)[None].astype(np.float32)
    try:
        out = session.run(None, {session.get_inputs()[0].name: tensor})[0][0, 0]
    except Exception as exc:
        log.warning("Fon olib tashlash modeli ishlamadi: %s", exc)
        return None
    low, high = float(out.min()), float(out.max())
    if high - low < 1e-6:
        return None
    pred = ((out - low) / (high - low) * 255).astype(np.uint8)
    mask = Image.fromarray(pred, "L").resize(image.size, Image.LANCZOS)
    return np.asarray(mask, dtype=np.float32) / 255.0


def _white_background(rgb: np.ndarray) -> np.ndarray:
    """Rasm chetiga tutashgan oq soha (True — fon)."""
    low, high = rgb.min(axis=2), rgb.max(axis=2)
    white = (low >= WHITE) & (high - low <= GREY_SPREAD)
    try:
        import cv2

        count, labels = cv2.connectedComponents(white.astype(np.uint8), connectivity=4)
        border = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
        border = border[border != 0]
        return np.isin(labels, border) & white
    except Exception:
        # cv2 bo'lmasa: oddiy "to'lqin" bilan chetdan to'ldirish.
        from collections import deque

        h, w = white.shape
        seen = np.zeros_like(white)
        queue = deque()
        for y in range(h):
            for x in (0, w - 1):
                if white[y, x] and not seen[y, x]:
                    seen[y, x] = True
                    queue.append((y, x))
        for x in range(w):
            for y in (0, h - 1):
                if white[y, x] and not seen[y, x]:
                    seen[y, x] = True
                    queue.append((y, x))
        while queue:
            y, x = queue.popleft()
            for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= ny < h and 0 <= nx < w and white[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    queue.append((ny, nx))
        return seen


def _decontaminate(rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """Yarim shaffof chetdagi oq aralashmani ajratadi: c = (c - (1-a)·255) / a."""
    a = alpha[..., None]
    edge = (a > 0.02) & (a < 0.98)
    clean = np.where(edge, (rgb - (1.0 - a) * 255.0) / np.maximum(a, 0.02), rgb)
    return np.clip(clean, 0, 255)


def cut(image: Image.Image) -> Tuple[Image.Image, str]:
    """(shaffof RGBA rasm, usul nomi). Usul: "model", "oq fon" yoki "" (fon olib tashlanmadi)."""
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    background = _white_background(rgb.astype(np.uint8))
    mask = _model_mask(image)
    method = "model"
    if mask is None:
        method = "oq fon"
        mask = (~background).astype(np.float32)
        # Qirralarni yumshatish: 1 pikselli o'tish.
        mask = np.asarray(Image.fromarray((mask * 255).astype(np.uint8), "L")
                          .filter(ImageFilter.GaussianBlur(1.0)), dtype=np.float32) / 255.0
    else:
        # Model ishonchsiz joyda (0.1-0.6) chetga tutashgan toza oq piksel — fon.
        mask = np.where(background & (mask < 0.6), 0.0, mask)
    coverage = float((mask > 0.5).mean())
    if coverage < 0.02 or coverage > 0.97:
        log.warning("Fon ajratilmadi (obyekt ulushi %.1f%%) — rasm o'zgarishsiz", coverage * 100)
        return image.convert("RGBA"), ""
    clean = _decontaminate(rgb, mask)
    rgba = np.dstack([clean, mask * 255.0]).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA"), method


def trim(image: Image.Image, margin: float = 0.02, max_side: int = 1400) -> Image.Image:
    """Shaffof chetlarni kesadi (obyekt chegarasigacha) va juda katta rasmni kichraytiradi."""
    rgba = image.convert("RGBA")
    alpha = np.asarray(rgba.split()[-1])
    ys, xs = np.nonzero(alpha > 12)
    if len(xs):
        pad_x, pad_y = int(rgba.width * margin), int(rgba.height * margin)
        box = (max(0, xs.min() - pad_x), max(0, ys.min() - pad_y),
               min(rgba.width, xs.max() + 1 + pad_x), min(rgba.height, ys.max() + 1 + pad_y))
        rgba = rgba.crop(box)
    scale = max_side / max(rgba.size)
    if scale < 1:
        rgba = rgba.resize((max(1, int(rgba.width * scale)), max(1, int(rgba.height * scale))), Image.LANCZOS)
    return rgba


def is_transparent(image: Image.Image) -> bool:
    if image.mode != "RGBA":
        return False
    alpha = np.asarray(image.split()[-1])
    return float((alpha < 16).mean()) > 0.05
