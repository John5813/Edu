"""3D taqdimot (umumiy katalog): mavzu → katalogdan mos 3D modellar → AI reja → PowerPoint (Morph).

Oqim (bot): mijoz "3D taqdimot" bo'limiga kiradi va mavzu yozadi. Mavzu tana tuzilishiga oid bo'lsa —
3D Anatomiya (`services.med3d`). Aks holda `qidiruv.top()` katalogdan (`services.katalog3d`, keyinroq NASA
ham) mos modellarni topadi; topilsa — mijozga to'lovdan OLDIN ko'rsatiladi va taqdimot aynan shu modellar
bilan yasaladi (`build_deck`). Topilmasa — 3D taklif qilinmaydi.

- `qidiruv` — AI kalit so'zlar → katalogdan nomzodlar → AI mosini tanlaydi;
- `reja` — AI slaydlar rejasi (kompozitsiya, matn, raqamlar, qaysi slaydda qaysi model);
- `deck` — PowerPoint: uslub, fon bezaklari, 3D modellar, Morph (model slayddan slaydga aylanib suzadi).
"""
import asyncio
import logging
import os
import tempfile
from typing import Callable, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

SLIDE_OPTIONS = (5, 8, 10, 12, 15)
MIN_SLIDES, MAX_SLIDES = 4, 15


def price_for(slide_count: int) -> int:
    """Narx — 3D Anatomiya bilan bir xil (ikkalasi ham haqiqiy 3D modellar va Morph)."""
    from services.med3d import auto as med3d_auto

    return med3d_auto.price_for(slide_count)


class NoModels(RuntimeError):
    """Mavzuga mos 3D model qolmadi (masalan serverdan o'chirilgan) — pul qaytariladi."""


async def build_deck(topic: str, slide_count: int, model_ids: List[str], *, language: str = "uz",
                     level: int = 2, preferences: str = "", style: Optional[str] = None,
                     stage_cb: Optional[Callable[[str, Dict], None]] = None) -> Tuple[str, int]:
    """Bot uchun: (PPTX yo'li, slaydlar soni). `model_ids` — mavzu tekshiruvida mijozga ko'rsatilgan modellar."""
    from services import katalog3d

    from . import deck, reja

    def stage(name: str, **info) -> None:
        if stage_cb:
            try:
                stage_cb(name, info)
            except Exception:                     # noqa: BLE001
                log.debug("stage_cb xatosi", exc_info=True)

    have = katalog3d.mavjud(ttl=0)
    ids = [i for i in model_ids if i in have]
    if not ids:
        raise NoModels("3D modellar serverda topilmadi")
    count = max(MIN_SLIDES, min(MAX_SLIDES, int(slide_count or 8)))
    loop = asyncio.get_running_loop()
    stage("plan")
    plan = await asyncio.wait_for(loop.run_in_executor(
        None, lambda: reja.plan(topic, count, ids, language, level, preferences, style)), 6 * 60)
    stage("models", slides=len(plan["slides"]))
    out_dir = tempfile.mkdtemp(prefix="kat3d_")
    path = await asyncio.wait_for(loop.run_in_executor(
        None, lambda: deck.build(plan, os.path.join(out_dir, "3D.pptx"))), 5 * 60)
    return path, len(plan["slides"])
