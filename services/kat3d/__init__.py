"""3D taqdimot (umumiy katalog): mavzu → katalogdan mos 3D modellar → AI reja → PowerPoint (Morph).

Oqim (bot): mijoz "3D taqdimot" bo'limiga kiradi va mavzu yozadi. Mavzu tana tuzilishiga oid bo'lsa —
3D Anatomiya (`services.med3d`). Aks holda `qidiruv.top()` katalogdan (`services.katalog3d`, keyinroq NASA
ham) mos modellarni topadi; topilsa — mijozga to'lovdan OLDIN ko'rsatiladi va taqdimot aynan shu modellar
bilan yasaladi (`build_deck`). Topilmasa — 3D taklif qilinmaydi.

- `qidiruv` — AI kalit so'zlar → katalogdan nomzodlar → AI mosini tanlaydi;
- `reja` — AI slaydlar rejasi (kompozitsiya, matn, raqamlar, qaysi slaydda qaysi model);
- `deck` — PowerPoint: uslub, fon bezaklari, 3D modellar, Morph (model slayddan slaydga aylanib suzadi);
- `yukla` — modellar serverga o'zi yuklanadi (3D Anatomiya atlasi kabi): topilishi bilan fonda, kerak bo'lsa
  taqdimotdan oldin kutib.
"""
import asyncio
import logging
import os
import tempfile
from typing import Callable, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

SLIDE_OPTIONS = (5, 8, 10, 12, 15)
MIN_SLIDES, MAX_SLIDES = 4, 15


MIX_DISCOUNT = 0.40                     # aralash taqdimot (3D + diagramma + rasm) — 40% arzon


def price_for(slide_count: int, mode: str = "full") -> int:
    """Narx — 3D Anatomiya bilan bir xil (ikkalasi ham haqiqiy 3D modellar va Morph); aralash — 40% arzon."""
    from services.med3d import auto as med3d_auto

    price = med3d_auto.price_for(slide_count)
    if mode == "mix":
        price = int(round(price * (1 - MIX_DISCOUNT) / 100.0)) * 100
    return price


# Aralash taqdimotdagi rasmlarni sifatli (pullik) AI modeli chizadi — internet fotosidan ko'ra mavzuga aniq mos keladi.
# Admin tanlagan arzon model emas, shu ro'yxat ishlatiladi (`KAT3D_IMAGE_MODELS` bilan almashtiriladi).
AI_IMAGE_MODELS = tuple(m.strip() for m in (os.getenv("KAT3D_IMAGE_MODELS") or
                                            "black-forest-labs/FLUX.2-pro,black-forest-labs/FLUX.1.1-pro").split(",")
                        if m.strip())


def _ai_prompt(topic: str, slide: dict) -> str:
    scene = (slide.get("photo") or slide.get("title") or topic).strip()
    return (f"{scene}. Related to: {topic}. Realistic high-quality editorial photograph, natural light, "
            "detailed, sharp focus, no text, no letters, no captions, no diagrams")


async def _ai_pictures(topic: str, slides: list) -> list:
    """Har rasmli slayd uchun AI chizgan rasm yo'li yoki None (chizilmasa — internet fotosiga o'tiladi)."""
    from services.premium_presentation import html_images

    if not html_images.photos_enabled():
        return [None] * len(slides)
    try:
        from services.together_service import get_together_service

        together = get_together_service()
    except Exception as exc:                  # noqa: BLE001
        log.warning("3D katalog: AI rasm xizmati yo'q (%s)", exc)
        return [None] * len(slides)
    gate = asyncio.Semaphore(3)

    async def one(slide):
        async with gate:
            try:
                return await together.generate_with_models(_ai_prompt(topic, slide), list(AI_IMAGE_MODELS),
                                                           stem="kat3d_ai")
            except Exception as exc:          # noqa: BLE001
                log.warning("3D katalog: AI rasm chizilmadi (%s): %s", slide.get("title", "")[:40], exc)
                return None

    return list(await asyncio.gather(*(one(s) for s in slides)))


async def _photos(topic: str, plan: dict, stage) -> None:
    """Aralash taqdimotdagi «rasm» slaydlari: avval sifatli AI rasm; chizilmaganiga internetdan haqiqiy foto.
    Ikkalasi ham bo'lmasa slayd matnli bo'lib qoladi."""
    slides = [s for s in plan["slides"] if s["layout"] == "rasm"]
    if not slides:
        return
    stage("photos", total=len(slides))
    paths = await _ai_pictures(topic, slides)
    missing = [(s, k) for k, (s, p) in enumerate(zip(slides, paths)) if not p]
    if missing:
        try:
            from services import photo_search

            found = await asyncio.wait_for(
                photo_search.find_photos(topic, [s["photo"] or s["title"] for s, _ in missing]), 150)
            for (s, k), path in zip(missing, found):
                paths[k] = path
        except Exception as exc:              # noqa: BLE001
            log.warning("3D katalog: internetdan rasm topilmadi (%s)", exc)
    for s, path in zip(slides, paths):
        if path:
            s["photo_path"] = path


class NoModels(RuntimeError):
    """Mavzuga mos 3D model qolmadi (masalan serverdan o'chirilgan) — pul qaytariladi."""


async def build_deck(topic: str, slide_count: int, model_ids: List[str], *, language: str = "uz",
                     level: int = 2, preferences: str = "", style: Optional[str] = None,
                     stage_cb: Optional[Callable[[str, Dict], None]] = None, mode: str = "full",
                     author: str = "") -> Tuple[str, int]:
    """Bot uchun: (PPTX yo'li, slaydlar soni). `model_ids` — mavzu tekshiruvida mijozga ko'rsatilgan (aralash
    rejimda — mijoz o'zi tanlagan) modellar. `mode="mix"` — qolgan slaydlar 3D'siz: diagramma, rasm, matn."""
    from . import deck, reja, yukla

    def stage(name: str, **info) -> None:
        if stage_cb:
            try:
                stage_cb(name, info)
            except Exception:                     # noqa: BLE001
                log.debug("stage_cb xatosi", exc_info=True)

    loop = asyncio.get_running_loop()
    stage("download", total=len(model_ids))
    ids = await loop.run_in_executor(None, yukla.ensure, list(model_ids), 600.0)   # odatda to'lovgacha tayyor
    if not ids:
        raise NoModels("3D modellar serverga yuklanmadi")
    count = max(MIN_SLIDES, min(MAX_SLIDES, int(slide_count or 8)))
    stage("plan")
    mix = mode == "mix"
    plan = await asyncio.wait_for(loop.run_in_executor(
        None, lambda: reja.plan(topic, count, ids, language, level, preferences, style, mix)), 6 * 60)
    plan["author"] = (author or "").strip()
    if mix:
        await _photos(topic, plan, stage)
    stage("models", slides=len(plan["slides"]))
    out_dir = tempfile.mkdtemp(prefix="kat3d_")
    from services import heavy_gate

    # Modellarni PowerPoint'ga yig'ish — og'ir ishlar navbatida (kutish vaqt chegarasiga kirmaydi).
    async with heavy_gate.aslot("3D taqdimot yig'ish", heavy_gate.DECK3D_MB):
        path = await asyncio.wait_for(loop.run_in_executor(
            None, lambda: deck.build(plan, os.path.join(out_dir, "3D.pptx"))), 5 * 60)
    return path, len(plan["slides"])
