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


async def _photos(topic: str, plan: dict, stage) -> None:
    """Aralash taqdimotdagi «rasm» slaydlariga internetdan haqiqiy foto. Topilmasa slayd matnli bo'lib qoladi."""
    slides = [s for s in plan["slides"] if s["layout"] == "rasm"]
    if not slides:
        return
    stage("photos", total=len(slides))
    try:
        from services import photo_search

        paths = await asyncio.wait_for(photo_search.find_photos(topic, [s["photo"] or s["title"] for s in slides]), 150)
    except Exception as exc:                  # noqa: BLE001
        log.warning("3D katalog: rasmlar topilmadi (%s) — matnli slaydlar", exc)
        return
    for s, path in zip(slides, paths):
        s["photo_path"] = path


class NoModels(RuntimeError):
    """Mavzuga mos 3D model qolmadi (masalan serverdan o'chirilgan) — pul qaytariladi."""


async def build_deck(topic: str, slide_count: int, model_ids: List[str], *, language: str = "uz",
                     level: int = 2, preferences: str = "", style: Optional[str] = None,
                     stage_cb: Optional[Callable[[str, Dict], None]] = None, mode: str = "full") -> Tuple[str, int]:
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
    ids = await loop.run_in_executor(None, yukla.ensure, list(model_ids), 240.0)   # odatda to'lovgacha tayyor
    if not ids:
        raise NoModels("3D modellar serverga yuklanmadi")
    count = max(MIN_SLIDES, min(MAX_SLIDES, int(slide_count or 8)))
    stage("plan")
    mix = mode == "mix"
    plan = await asyncio.wait_for(loop.run_in_executor(
        None, lambda: reja.plan(topic, count, ids, language, level, preferences, style, mix)), 6 * 60)
    if mix:
        await _photos(topic, plan, stage)
    stage("models", slides=len(plan["slides"]))
    out_dir = tempfile.mkdtemp(prefix="kat3d_")
    path = await asyncio.wait_for(loop.run_in_executor(
        None, lambda: deck.build(plan, os.path.join(out_dir, "3D.pptx"))), 5 * 60)
    return path, len(plan["slides"])
