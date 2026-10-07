"""Saytda yaratilgan zamonaviy taqdimotning saqlangan nusxasi: sahifalar, suratlar, tarix.

Mijoz taqdimotni yuklab olmasdan avval brauzerda varaqlab ko'radi va istalgan sahifani AI ga qayta
yozdiradi. Buning uchun taqdimotning yakuniy HTML sahifalari (PPTX bilan bir xil) va har sahifaning
surati diskda saqlanadi. Hammasi buyurtma fayli bilan birga `JOB_TTL_HOURS` dan keyin o'chadi.

Papka: `<RESULTS_DIR>/decks/<job_id>/` — `deck.json` (sahifalar, reja, tarix) va `p01.jpg` ... suratlar.
"""
import asyncio
import io
import json
import logging
import os
import re
import shutil
import time
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

PREVIEW_W = 1280          # brauzerga beriladigan surat kengligi (16:9)
PREVIEW_H = 720
_locks: Dict[str, asyncio.Lock] = {}
_ID = re.compile(r"^[0-9a-f]{32}$")


def root() -> str:
    from services import web_jobs

    return os.path.join(web_jobs.RESULTS_DIR, "decks")


def _dir(job_id: str) -> str:
    if not _ID.match(str(job_id or "")):
        raise ValueError("noto'g'ri buyurtma raqami")
    return os.path.join(root(), job_id)


def lock(job_id: str) -> asyncio.Lock:
    """Bitta taqdimotni bir vaqtda bitta ish o'zgartiradi."""
    return _locks.setdefault(job_id, asyncio.Lock())


def exists(job_id: str) -> bool:
    try:
        return os.path.isfile(os.path.join(_dir(job_id), "deck.json"))
    except ValueError:
        return False


def load(job_id: str) -> Optional[dict]:
    try:
        with open(os.path.join(_dir(job_id), "deck.json"), encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def save(job_id: str, deck: dict) -> None:
    folder = _dir(job_id)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "deck.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(deck, handle, ensure_ascii=False)
    os.replace(tmp, path)


def preview_path(job_id: str, number: int) -> str:
    return os.path.join(_dir(job_id), f"p{int(number):02d}.jpg")


def _jpeg(png_path: str, out_path: str) -> None:
    from PIL import Image

    image = Image.open(png_path).convert("RGB")
    image = image.resize((PREVIEW_W, PREVIEW_H), Image.LANCZOS)
    tmp = out_path + ".tmp"
    image.save(tmp, "JPEG", quality=82, optimize=True)
    os.replace(tmp, out_path)


def store_shots(job_id: str, shots: Dict[int, str]) -> int:
    """`{sahifa indeksi (0 dan): png yo'li}` → `pNN.jpg`. Saqlangan suratlar soni."""
    os.makedirs(_dir(job_id), exist_ok=True)
    done = 0
    for index, path in shots.items():
        try:
            _jpeg(path, preview_path(job_id, index + 1))
            done += 1
        except Exception as exc:
            log.warning("%s: %d-sahifa surati saqlanmadi: %s", job_id, index + 1, exc)
    return done


def titles_of(pages: List[str]) -> List[str]:
    from services.premium_presentation import deck_logic, html_slides

    return [deck_logic.title_of(html_slides.source_of(page) or page) for page in pages]


def create(job_id: str, params: dict, data: dict) -> None:
    """Yangi yaratilgan taqdimotni saqlaydi (`data` — `pipeline.build_deck(deck_out=...)` natijasi)."""
    pages = list(data.get("pages") or [])
    if not pages:
        return
    shots = {}
    folder = data.get("shots_dir") or ""
    for index in range(len(pages)):
        path = os.path.join(folder, f"shot_{index + 1:02d}.png")
        if folder and os.path.exists(path):
            shots[index] = path
    deck = {
        "topic": params.get("topic", ""), "language": params.get("language", "uz"), "style": params.get("style", ""),
        "theme_key": data.get("theme_key", ""), "author": params.get("author", ""),
        "preferences": params.get("preferences", ""), "source_text": (params.get("source_text") or "")[:4000],
        "level": 2, "family": data.get("family", ""), "outline": data.get("outline") or [],
        "pages": pages, "titles": titles_of(pages), "version": 1, "history": [], "created": time.time()}
    store_shots(job_id, shots)
    save(job_id, deck)
    if folder:
        shutil.rmtree(folder, ignore_errors=True)


def count(deck: dict) -> int:
    return int(deck.get("count") or len(deck.get("pages") or []))


def public(job_id: str, deck: dict) -> dict:
    """Brauzerga beriladigan qisqa ko'rinish (sahifalar HTML isiz)."""
    count_ = count(deck)
    titles = list(deck.get("titles") or [])
    shown = [os.path.exists(preview_path(job_id, n + 1)) for n in range(count_)]
    return {"count": count_, "version": int(deck.get("version") or 1), "editable": not deck.get("view_only"),
            "slides": [{"n": n + 1, "title": titles[n] if n < len(titles) else "", "image": shown[n]}
                       for n in range(count_)],
            "history": list(deck.get("history") or [])[-30:]}


def _pptx_titles(pptx_path: str) -> List[str]:
    from pptx import Presentation

    titles = []
    for slide in Presentation(pptx_path).slides:
        text = ""
        if slide.shapes.title is not None and slide.shapes.title.has_text_frame:
            text = slide.shapes.title.text_frame.text
        if not text.strip():
            for shape in slide.shapes:
                if shape.has_text_frame and shape.text_frame.text.strip():
                    text = shape.text_frame.text
                    break
        titles.append(re.sub(r"\s+", " ", text).strip()[:80])
    return titles


def pptx_previews(pptx_path: str, out_dir: str) -> List[str]:
    """PPTX → PDF (LibreOffice) → har sahifa PNG. Qaytaradi: PNG yo'llari (tartib bilan)."""
    import subprocess

    import pymupdf

    os.makedirs(out_dir, exist_ok=True)
    subprocess.run(["soffice", f"-env:UserInstallation=file://{out_dir}/profile", "--headless", "--convert-to", "pdf",
                    "--outdir", out_dir, pptx_path], check=True, capture_output=True, timeout=240)
    pdf = os.path.join(out_dir, os.path.splitext(os.path.basename(pptx_path))[0] + ".pdf")
    paths = []
    with pymupdf.open(pdf) as doc:
        for number, page in enumerate(doc, 1):
            zoom = PREVIEW_W / max(page.rect.width, 1)
            path = os.path.join(out_dir, f"v{number:02d}.png")
            page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False).save(path)
            paths.append(path)
    return paths


def create_view(job_id: str, params: dict, pptx_path: str) -> int:
    """Oddiy (orqa fonli) taqdimot: faqat ko'rish. Sahifalarni LibreOffice chizadi; qayta yozish yo'q."""
    import tempfile

    work = tempfile.mkdtemp(prefix="deckview_")
    try:
        paths = pptx_previews(pptx_path, work)
        if not paths:
            return 0
        done = store_shots(job_id, {index: path for index, path in enumerate(paths)})
        titles = []
        try:
            titles = _pptx_titles(pptx_path)
        except Exception as exc:
            log.debug("Slayd sarlavhalari olinmadi: %s", exc)
        save(job_id, {"view_only": True, "topic": params.get("topic", ""), "count": len(paths), "pages": [],
                      "titles": (titles + [""] * len(paths))[:len(paths)], "version": 1, "history": [],
                      "created": time.time()})
        return done
    finally:
        shutil.rmtree(work, ignore_errors=True)


def drop(job_id: str) -> None:
    try:
        shutil.rmtree(_dir(job_id), ignore_errors=True)
    except ValueError:
        pass
    _locks.pop(job_id, None)


async def purge_orphans() -> int:
    """Buyurtmasi o'chirilgan (muddati o'tgan) taqdimot papkalarini o'chiradi."""
    from database import web_store

    base = root()
    if not os.path.isdir(base):
        return 0
    removed = 0
    for name in os.listdir(base):
        if not _ID.match(name):
            continue
        if await web_store.get_job(name) is None:
            drop(name)
            removed += 1
    return removed
