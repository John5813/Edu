"""3D Pro taqdimot: har slaydda fonsiz 3D obyekt, yorliq-chiziqlar va PowerPoint Morph o'tishlari.

Bosqichlar: AI reja tuzadi (`content`) → Together modeli obyektlarni chizadi va fon serverda olib
tashlanadi (`images`, `cutout`) → vision modeli yorliq chiziqlari uchun nuqtalarni topadi → taqdimot
PowerPoint'ning haqiqiy shakllari bilan yig'iladi (`build`).
"""
import asyncio
import datetime
import logging
import os
from typing import Callable, Dict, Optional, Tuple

log = logging.getLogger(__name__)

MIN_SLIDES, MAX_SLIDES = 5, 20
SLIDE_OPTIONS = (5, 8, 10, 12, 15, 20)
# Rasm modeli qimmat va har slaydga alohida obyekt chiziladi — narx zamonaviy taqdimotnikidan yuqori.
PRICE_FACTOR = float(os.getenv("PRO3D_PRICE_FACTOR") or 3)
# Obyektlarning shuncha qismidan kami chizilsa taqdimot "3D" bo'lmaydi — xato, pul qaytariladi.
MIN_PICTURE_SHARE = 0.5


def price_for(slide_count: int) -> int:
    from services.premium_presentation import pipeline

    return int(round(pipeline.price_for(slide_count) * PRICE_FACTOR / 500.0)) * 500


async def build_deck(topic: str, slide_count: int, *, language: str = "uz", level: int = 2,
                     preferences: str = "", source_text: str = "", author: str = "",
                     stage_cb: Optional[Callable[[str, Dict], None]] = None) -> Tuple[str, int, int]:
    """Taqdimotni yaratadi: (PPTX yo'li, slaydlar soni, chizilgan obyektlar soni). Xatoda istisno."""
    from services.premium_presentation import prompts

    from . import build, content, images

    def stage(name: str, **info) -> None:
        if stage_cb:
            try:
                stage_cb(name, info)
            except Exception:
                log.debug("stage_cb xatosi", exc_info=True)

    loop = asyncio.get_running_loop()
    count = max(MIN_SLIDES, min(MAX_SLIDES, int(slide_count or 8)))

    stage("plan")
    with prompts.use(language):
        deck = await asyncio.wait_for(loop.run_in_executor(
            None, lambda: content.plan(topic, count, language, level, preferences, source_text)), 8 * 60)
    objects = content.objects(deck)
    log.info("3D Pro reja: %d slayd, %d obyekt, palitra %s, uslub %s",
             len(deck["slides"]), len(objects), deck["palette"], deck["style"])

    stage("images", total=len(objects))
    pictures = await asyncio.wait_for(
        images.draw(objects, deck["style"], progress=lambda done, total: stage("image", done=done, total=total)),
        15 * 60)
    if len(pictures) < max(1, int(len(objects) * MIN_PICTURE_SHARE + 0.5)):
        raise RuntimeError(f"3D obyektlar chizilmadi ({len(pictures)}/{len(objects)}) — rasm xizmati javob bermadi")

    stage("anchors")
    jobs = [(i, s) for i, s in enumerate(deck["slides"])
            if s["layout"] == "callouts" and s["object"]["id"] in pictures]

    def locate(i, s):
        picture = pictures[s["object"]["id"]]
        return i, images.locate(picture, s["object"]["prompt"], [c["part"] for c in s["callouts"]])

    anchors: Dict[int, list] = {}
    if jobs:
        results = await asyncio.gather(*(loop.run_in_executor(None, locate, i, s) for i, s in jobs),
                                       return_exceptions=True)
        for item in results:
            if isinstance(item, Exception):
                log.warning("Yorliq nuqtalari topilmadi: %s", item)
                continue
            anchors[item[0]] = item[1]

    stage("render", slides=len(deck["slides"]), photos=len(pictures))
    year = str(datetime.date.today().year)
    path = await loop.run_in_executor(None, lambda: build.build(deck, pictures, anchors, author=author, year=year))
    for picture in pictures.values():
        try:
            os.remove(picture.path)
        except OSError:
            pass
    return path, len(deck["slides"]), len(pictures)
