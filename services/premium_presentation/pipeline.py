"""Zamonaviy (premium) taqdimotni yaratishning yagona yo'li — bot ham, sayt ham shuni chaqiradi.

Ilgari bu ketma-ketlik faqat bot handleri ichida edi. Sayt qo'shilgach nusxa ko'chirish o'rniga
shu modulga ajratildi: slaydlarni yozish → rasmlar → muqova → PPTX.
"""
import asyncio
import contextvars
import logging
from typing import Callable, Optional, Tuple

log = logging.getLogger(__name__)

MIN_SLIDES = 5
MAX_SLIDES = 30
MIN_PRICE = 3000

# Matn hajmi: "kop" — ko'p matnli (fikr batafsil, har 10 slaydda 4 ta rasm), "kam" — kam matnli
# (qisqa aniq fikrlar, kompozitsiyalar, rasm ko'proq). Rang mijozdan so'ralmaydi — mavzuga qarab.
VOLUMES = ("kop", "kam")

# Og'ir bosqichlar chegaralangan vaqt ichida bajariladi.
STEP_TIMEOUTS = {"brief": 15 * 60, "render": 8 * 60}


def price_for(slide_count: int) -> int:
    """Varaq soniga qarab narx (so'm) — oddiy taqdimot narxlari bilan mos.

    10 varaq — 5 000, 15 — 7 000, 20 — 10 000 (config.PRESENTATION_PRICES). Oraliq sonlar
    shu nuqtalar orasida chiziqli hisoblanib 500 so'mgacha yaxlitlanadi.
    """
    from config import PRESENTATION_PRICES

    try:
        count = int(slide_count or 0)
    except (TypeError, ValueError):
        count = MIN_SLIDES
    count = max(MIN_SLIDES, min(count, MAX_SLIDES))
    if count in PRESENTATION_PRICES:
        return int(PRESENTATION_PRICES[count])
    points = sorted((int(k), int(v)) for k, v in PRESENTATION_PRICES.items())
    if count < points[0][0]:
        value = points[0][1] / points[0][0] * count
    elif count > points[-1][0]:
        (x1, y1), (x2, y2) = points[-2], points[-1]
        value = y2 + (y2 - y1) / (x2 - x1) * (count - x2)
    else:
        (x1, y1), (x2, y2) = next((a, b) for a, b in zip(points, points[1:]) if a[0] <= count <= b[0])
        value = y1 + (y2 - y1) / (x2 - x1) * (count - x1)
    return max(MIN_PRICE, int(value / 500 + 0.5) * 500)


async def run_step(loop, func, *, step: str, label: str):
    """Og'ir bosqichni chegaralangan vaqt ichida bajaradi."""
    timeout = STEP_TIMEOUTS[step]
    # Oqimga joriy kontekst (masalan, bepul sinovning matn modeli) ham o'tadi — `run_in_executor` uni o'zi o'tkazmaydi.
    context = contextvars.copy_context()
    try:
        return await asyncio.wait_for(loop.run_in_executor(None, context.run, func), timeout)
    except (asyncio.TimeoutError, TimeoutError):
        raise RuntimeError(f"{label} {int(timeout // 60)} daqiqada tugamadi — "
                           f"tashqi xizmat javob bermadi") from None


async def build_deck(topic: str, slide_count: int, *, language: str = "uz", level: int = 2,
                     preferences: str = "", source_text: str = "", author: str = "",
                     theme_key: str = "", style: str = "", volume: str = "kop", photos: bool = True,
                     progress_cb: Optional[Callable[[int, int], None]] = None,
                     stage_cb: Optional[Callable[[str, dict], None]] = None,
                     deck_out: Optional[dict] = None) -> Tuple[str, int, int]:
    """Taqdimotni yaratadi va PPTX yo'lini qaytaradi: (yo'l, slaydlar soni, rasmlar soni).

    `progress_cb(tayyor_bo'lak, jami)` — kontent yozilayotganda (boshqa oqimdan chaqirilishi mumkin);
    `stage_cb(nom, ma'lumot)` — bosqich almashganda: "writing", "plan" (reja tayyor: `outline`),
    "images", "render".
    Xatoda istisno ko'tariladi; pulni qaytarish chaqiruvchining ishi.

    `deck_out` berilsa (sayt): unga taqdimotning yakuniy sahifalari (`pages`), rang kaliti, reja va
    sahifa suratlari papkasi (`shots_dir`, agar berilgan bo'lsa) yoziladi — taqdimotni saytda
    varaqlash va bitta sahifani qayta yozish uchun.

    `photos=False` (bepul sinov): rasm chizdirilmaydi — rasm o'rnida qo'shimcha matn qoladi, muqova rasmsiz.
    `volume` — matn hajmi (`VOLUMES`); `theme_key` faqat saqlangan taqdimotni qayta yig'ish uchun (bo'sh —
    rang mavzuga qarab).
    """
    from services.premium_presentation import prompts

    # Hamma so'rovlardagi umumiy qoidalar (bugungi sana va h.k.) ham taqdimot tilida — oqimlarga ham o'tadi.
    with prompts.use(language):
        return await _build_deck(topic, slide_count, language=language, level=level, preferences=preferences,
                                 source_text=source_text, author=author, theme_key=theme_key, style=style,
                                 volume=volume if volume in VOLUMES else "kop", photos=photos, progress_cb=progress_cb, stage_cb=stage_cb, deck_out=deck_out)


async def _build_deck(topic, slide_count, *, language, level, preferences, source_text, author, theme_key,
                      style, volume, photos, progress_cb, stage_cb, deck_out) -> Tuple[str, int, int]:
    from services.premium_presentation import html_images, html_render, html_slides, themes

    loop = asyncio.get_running_loop()

    def stage(name: str, **info) -> None:
        if stage_cb:
            try:
                stage_cb(name, info)
            except Exception:  # holat yangilanmasa ham yaratish to'xtamasin
                log.debug("stage_cb xatosi", exc_info=True)

    theme = themes.for_deck(topic, style, volume, theme_key)

    stage("writing")
    outline_out: dict = {}
    pages = await run_step(
        loop,
        lambda: html_slides.write_slides(
            topic, slide_count, theme, language=language, level=level, preferences=preferences,
            source_text=source_text, author=author, progress_cb=progress_cb, outline_out=outline_out,
            plan_cb=lambda outline: stage("plan", outline=outline)),
        step="brief", label="Slaydlarni yozish")

    stage("images", slides=len(pages))
    placed = 0
    if photos:
        try:
            pages, placed = await html_images.fill_photos(pages, limit=html_images.photo_limit(slide_count, volume))
        except Exception as exc:
            log.warning("Rasmlar qo'yilmadi: %s", exc)
        try:
            pages, cover_done = await html_images.fill_cover(pages, topic)
            placed += 1 if cover_done else 0
        except Exception as exc:
            log.warning("Muqova rasmi qo'yilmadi: %s", exc)

    stage("render", slides=len(pages), photos=placed)
    final: list = []
    shots = (deck_out or {}).get("shots_dir")
    path = await run_step(
        loop,
        lambda: html_render.render(
            pages,
            repair=lambda page, problems: html_slides.fix_slide(page, problems, theme, language),
            # Kam matnli kompozitsiyalarda bo'sh joy ataylab qoldirilgan — u matn bilan to'ldirilmaydi.
            explain=None if volume == "kam" else (lambda page, area: html_slides.fill_gap(page, area, theme, language)),
            collect=final if deck_out is not None else None, shots_dir=shots),
        step="render", label="Slaydlarni suratga olish")
    if deck_out is not None:
        deck_out.update(pages=final if len(final) == len(pages) else pages, theme_key=theme.key, volume=volume,
                        family=outline_out.get("family", ""), outline=outline_out.get("outline", []))
    return path, len(pages), placed
