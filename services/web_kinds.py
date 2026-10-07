"""Saytda buyurtma qilinadigan xizmatlar (har biri `web_jobs.register` orqali ulanadi)."""
import re
from typing import Dict, Tuple

from services import uz_script
from services.web_jobs import JobError, Kind, Report, register

LANGUAGES = ("uz", uz_script.UZ_CYRILLIC_LANG, "ru", "en", "kk")
MODERN_STYLES = ("toza", "jurnal", "blok", "kontur", "qorongu")


def _text(raw: Dict, key: str, limit: int) -> str:
    return re.sub(r"[ \t]+", " ", str(raw.get(key) or "")).strip()[:limit]


# ───────────────────────────────────────────────────────── zamonaviy (premium) taqdimot

def _premium_normalize(raw: Dict) -> Dict:
    from services.premium_presentation import pipeline, themes

    topic = _text(raw, "topic", 300)
    if len(topic) < 3:
        raise JobError("Mavzu kamida 3 ta belgidan iborat bo'lsin.")
    try:
        count = int(raw.get("slide_count") or 10)
    except (TypeError, ValueError):
        count = 10
    language = raw.get("language") if raw.get("language") in LANGUAGES else "uz"
    style = raw.get("style") if raw.get("style") in MODERN_STYLES else "toza"
    theme = str(raw.get("theme") or "").strip().lower()
    return {"topic": topic, "slide_count": max(pipeline.MIN_SLIDES, min(count, pipeline.MAX_SLIDES)),
            "language": language, "style": style, "theme": theme if theme in themes.THEMES else "",
            "author": _text(raw, "author", 80), "preferences": _text(raw, "preferences", 1000)}


def _premium_price(params: Dict) -> int:
    from services.premium_presentation import pipeline
    return pipeline.price_for(params["slide_count"])


async def _premium_run(params: Dict, report: Report) -> Tuple[str, str]:
    from services.premium_presentation import llm_client, pipeline

    try:
        from config import AI_MODELS
        from database.database import Database
        key = await Database.get_premium_ai_model()
        if key in AI_MODELS:
            llm_client.set_text_model(AI_MODELS[key]["id"])
    except Exception:
        pass
    llm_client.reset_usage()

    def on_progress(done: int, total: int) -> None:
        report("writing", 5 + int(70 * done / max(total, 1)))

    def on_stage(name: str, info: dict) -> None:
        report(name, {"writing": 5, "images": 78, "render": 90}.get(name, 5))

    topic = params["topic"]
    path, _slides, _photos = await pipeline.build_deck(
        topic, params["slide_count"], language=params["language"], preferences=params["preferences"],
        author=params["author"], theme_key=params["theme"], style=params["style"],
        progress_cb=on_progress, stage_cb=on_stage)
    stem = re.sub(r"[^\w-]+", "_", topic)[:30].strip("_") or "fayl"
    return path, f"Taqdimot_{stem}.pptx"


register(Kind(key="premium_presentation", label="Zamonaviy taqdimot", normalize=_premium_normalize,
              price=_premium_price, title=lambda p: p["topic"], run=_premium_run,
              publish_as="premium_taqdimot"))
