"""Saytda buyurtma qilinadigan xizmatlar (har biri `web_jobs.register` orqali ulanadi)."""
import asyncio
import logging
import re
import tempfile
from typing import Dict, Tuple

from services import uz_script, web_jobs
from services.web_jobs import JobError, Kind, Report, register

log = logging.getLogger(__name__)

LANGUAGES = ("uz", uz_script.UZ_CYRILLIC_LANG, "ru", "en", "kk")
MODERN_STYLES = ("toza", "jurnal", "blok", "kontur", "qorongu")


def _text(raw: Dict, key: str, limit: int) -> str:
    return re.sub(r"[ \t]+", " ", str(raw.get(key) or "")).strip()[:limit]


SOURCE_LIMIT = 60_000       # bot manbasi bilan bir xil (`project_work.source`)


def _long_text(raw: Dict, key: str, limit: int) -> str:
    """Qator uzilishlari saqlanadigan uzun matn (mijoz manbasi)."""
    text = str(raw.get(key) or "").replace("\r\n", "\n").replace("\x00", "")
    return re.sub(r"[ \t]+", " ", text).strip()[:limit]


def detect_language(topic: str) -> str:
    """Mavzuning tilidan taqdimot tili — botdagi qoida (`premium_presentation._detect_language`)."""
    from bot.handlers.premium_presentation import _detect_language

    language = _detect_language(topic)
    if language == "uz" and uz_script.has_cyrillic(topic):
        return uz_script.UZ_CYRILLIC_LANG
    return language


def _pick_language(raw: Dict, topic: str) -> str:
    language = raw.get("language")
    return language if language in LANGUAGES else detect_language(topic)


# ───────────────────────────────────────────────────────── zamonaviy (premium) taqdimot

def _premium_normalize(raw: Dict) -> Dict:
    from services.premium_presentation import pipeline

    topic = _text(raw, "topic", 300)
    if len(topic) < 3:
        raise JobError("Mavzu kamida 3 ta belgidan iborat bo'lsin.")
    try:
        count = int(raw.get("slide_count") or 10)
    except (TypeError, ValueError):
        count = 10
    style = raw.get("style") if raw.get("style") in MODERN_STYLES else "toza"
    # Rang alohida tanlanmaydi (mavzuga qarab); mijoz matn hajmini tanlaydi: ko'p yoki kam matnli.
    volume = str(raw.get("volume") or "").strip().lower()
    # Bepul sinov: varaq soni qat'iy (o'zgartirib bo'lmaydi), arzon model, rasmsiz.
    trial = raw.get("trial") is True
    if trial:
        from database import free_trial
        count = free_trial.SLIDES
    return {"topic": topic, "slide_count": max(pipeline.MIN_SLIDES, min(count, pipeline.MAX_SLIDES)), "trial": trial,
            "language": _pick_language(raw, topic), "style": style,
            "volume": "kop" if trial else (volume if volume in pipeline.VOLUMES else "kop"),
            "author": _text(raw, "author", 80), "preferences": _text(raw, "preferences", 1000),
            "source_text": _long_text(raw, "source_text", SOURCE_LIMIT),
            "source_label": _text(raw, "source_label", 120)}


def _premium_price(params: Dict) -> int:
    from services.premium_presentation import pipeline
    if params.get("trial"):
        return 0
    return pipeline.price_for(params["slide_count"])


async def _premium_run(params: Dict, report: Report) -> Tuple[str, str]:
    import contextlib

    from database import free_trial
    from services.premium_presentation import llm_client, pipeline

    trial = bool(params.get("trial"))
    if not trial:       # bepul sinov admin tanlagan modelga tegmaydi (u faqat shu buyurtmaga arzon model oladi)
        try:
            from config import AI_MODELS
            from database.database import Database
            key = await Database.get_premium_ai_model()
            if key in AI_MODELS:
                llm_client.set_text_model(AI_MODELS[key]["id"])
        except Exception:
            pass
    llm_client.reset_usage()

    topic = params["topic"]
    job_id = params.get("_job_id") or ""

    def on_progress(done: int, total: int) -> None:
        report("writing", 5 + int(70 * done / max(total, 1)))
        web_jobs.note(job_id, done=done, total=total)

    def on_stage(name: str, info: dict) -> None:
        if name == "plan":      # reja tayyor: kutish animatsiyasi haqiqiy sarlavhalarni ko'rsatadi
            web_jobs.note(job_id, plan=[{"title": o["title"][:90], "category": o["category"]}
                                        for o in info.get("outline", [])][:40])
            return
        if name in ("images", "render"):
            web_jobs.note(job_id, done=web_jobs.LIVE.get(job_id, {}).get("total", 0))
        report(name, {"writing": 5, "images": 78, "render": 90}.get(name, 5))
    # Taqdimot saytda varaqlanadi va sahifalari qayta yozdiriladi: yakuniy sahifalar va suratlar saqlanadi.
    deck_out: dict = {"shots_dir": tempfile.mkdtemp(prefix="deckshots_")} if job_id else {}
    with (llm_client.text_model(free_trial.MODEL) if trial else contextlib.nullcontext()):
        path, _slides, _photos = await pipeline.build_deck(
            topic, params["slide_count"], language=params["language"], preferences=params["preferences"],
            author=params["author"], style=params["style"], volume=params.get("volume") or "kop", photos=not trial,
            source_text=params.get("source_text", ""), progress_cb=on_progress, stage_cb=on_stage,
            deck_out=deck_out if job_id else None)
    if job_id and deck_out.get("pages"):
        try:
            from services import web_decks
            await asyncio.to_thread(web_decks.create, job_id, params, deck_out)
        except Exception as exc:        # ko'rib chiqish ishlamasa ham fayl mijozga yetadi
            log.warning("Taqdimot nusxasi saqlanmadi (%s): %s", job_id, exc)
    stem = re.sub(r"[^\w-]+", "_", topic)[:30].strip("_") or "fayl"
    return path, f"Taqdimot_{stem}.pptx"


register(Kind(key="premium_presentation", label="Zamonaviy taqdimot", normalize=_premium_normalize,
              price=_premium_price, title=lambda p: p["topic"], run=_premium_run,
              publish_as="premium_taqdimot", options={"form": "presentation", "eta_minutes": 5}))


# ──────────────────────────────────────────────────────────────── hujjatlar (docx)
#
# Botdagi bilan bir xil ikki chaqiruv: AI matn yozadi (`ai_service`), so'ng `document_service`
# Word faylini yig'adi. Narxlar va hajmlar `config` dagi jadvallardan olinadi, shuning uchun bot
# va sayt narxi hech qachon farq qilmaydi.

DOC_LANGUAGES = ("uz", "ru", "en")
EXTRAS_LABELS = {"formulas": "Formulalar", "images": "Rasmlar", "scheme": "Sxemalar", "tables": "Jadvallar",
                 "glossary": "Glossariy", "statistics": "Statistika"}
PLAN_STYLES = {"oddiy": "Oddiy (savollar bilan)", "murakkab": "Murakkab (boblar bilan)"}


def _size_label(key: str, with_chapters: bool) -> str:
    parts = key.split("_")
    text = f"{parts[0]}–{parts[1]} varoq"
    return text + (f" · {parts[2]} bob" if with_chapters and len(parts) > 2 else "")


def _doc_spec(key: str):
    from config import (ARTICLE_PRICES, COURSE_WORK_PRICES, DIPLOMA_WORK_PRICES, DISSERTATION_PRICES,
                        DOCUMENT_PRICES, GRADUATION_WORK_PRICES)
    simple = {k: v for k, v in DOCUMENT_PRICES.items() if k != "tezis"}
    return {
        "independent_work": dict(label="Mustaqil ish", prices=simple, extras=True, free_extras=True, store="mustaqil_ish",
                                 eta=150, emoji="🎓"),
        "referat": dict(label="Referat", prices=simple, extras=True, free_extras=False, store="referat", eta=150),
        "article": dict(label="Maqola (IMRAD)", prices=dict(ARTICLE_PRICES), extras=False, store="maqola", eta=120),
        "course_work": dict(label="Kurs ishi", prices=dict(COURSE_WORK_PRICES), extras=True, free_extras=False,
                            store="kurs_ishi", heavy=True, eta=360, plan_style=True),
        "diploma_work": dict(label="Diplom ishi", prices=dict(DIPLOMA_WORK_PRICES), extras=True, free_extras=False,
                             store="diplom_ishi", heavy=True, eta=540),
        "bitiruv_ishi": dict(label="Bitiruv malakaviy ishi", prices=dict(GRADUATION_WORK_PRICES), extras=True,
                             free_extras=False, store="bitiruv_ishi", heavy=True, eta=480),
        "dissertatsiya": dict(label="Magistrlik dissertatsiyasi", prices=dict(DISSERTATION_PRICES), extras=True,
                              free_extras=False, store="dissertatsiya", heavy=True, eta=720),
    }[key]


def _doc_normalize(key: str):
    spec = _doc_spec(key)

    def normalize(raw: Dict) -> Dict:
        topic = _text(raw, "topic", 300)
        if len(topic) < 3:
            raise JobError("Mavzu kamida 3 ta belgidan iborat bo'lsin.")
        size = str(raw.get("size") or "")
        if size not in spec["prices"]:
            size = next(iter(spec["prices"]))
        language = raw.get("language") if raw.get("language") in DOC_LANGUAGES else "uz"
        extras = []
        if spec["extras"]:
            extras = [k for k in (raw.get("extras") or []) if k in EXTRAS_LABELS and k not in extras] \
                if isinstance(raw.get("extras"), list) else []
            extras = list(dict.fromkeys(extras))
        parts = [int(x) for x in size.split("_")]
        params = {"topic": topic, "size": size, "language": language, "extras": extras,
                  "author": _text(raw, "author", 80) or _text(raw, "_default_author", 80),
                  "min_pages": parts[0], "max_pages": parts[1], "chapters": parts[2] if len(parts) > 2 else 0}
        if spec.get("plan_style"):
            params["plan_style"] = raw.get("plan_style") if raw.get("plan_style") in PLAN_STYLES else "murakkab"
        return params
    return normalize


def _doc_price(key: str):
    spec = _doc_spec(key)
    from config import EXTRAS_PRICES

    def price(params: Dict) -> int:
        base = int(spec["prices"][params["size"]])
        if spec["extras"] and not spec.get("free_extras"):
            base += sum(EXTRAS_PRICES.get(k, 0) for k in params["extras"])
        return base
    return price


async def _ticker(report: Report, seconds: int, start: int = 8, end: int = 88) -> None:
    """Hujjat uzoq yoziladi va ichki bosqichlar ko'rinmaydi: ko'rsatkich taxminiy vaqt bo'yicha yuradi."""
    import asyncio
    steps = 40
    for i in range(steps):
        await asyncio.sleep(max(seconds / steps, 0.05))
        report("writing" if i < steps * 0.8 else "render", start + int((end - start) * (i + 1) / steps))


def _doc_runner(key: str):
    spec = _doc_spec(key)

    async def run(params: Dict, report: Report) -> Tuple[str, str]:
        import asyncio
        import os

        from services.ai_service import get_ai_service
        from services.document_service import get_document_service

        topic, lang = params["topic"], params["language"]
        extras = params["extras"] or None
        ai, docs = get_ai_service(), get_document_service()
        ticker = asyncio.ensure_future(_ticker(report, spec["eta"]))
        try:
            if key in ("independent_work", "referat"):
                mx = params["max_pages"]
                sections = 6 if mx <= 15 else 9 if mx <= 20 else 12 if mx <= 25 else 15
                content = await ai.generate_document_content(topic, sections, key, lang,
                                                             min_pages=params["min_pages"], max_pages=mx)
                content["language"], content["author_name"] = lang, params["author"]
                make = docs.create_independent_work if key == "independent_work" else docs.create_referat
                path = await make(topic, content, extras=extras)
            elif key == "article":
                content = await ai.generate_article_content(topic, params["min_pages"], params["max_pages"], lang)
                path = await docs.create_article(topic, content, params["author"], lang)
            else:
                ai_method = {"course_work": "generate_course_work_content",
                             "diploma_work": "generate_diploma_work_content",
                             "bitiruv_ishi": "generate_graduation_work_content",
                             "dissertatsiya": "generate_dissertation_content"}[key]
                doc_method = {"course_work": "create_course_work", "diploma_work": "create_diploma_work",
                              "bitiruv_ishi": "create_graduation_work", "dissertatsiya": "create_dissertation"}[key]
                kwargs = {"min_pages": params["min_pages"], "max_pages": params["max_pages"]}
                if key == "course_work":
                    kwargs.update(manual_plan=None, plan_style=params.get("plan_style", ""))
                elif key == "bitiruv_ishi":
                    kwargs.update(manual_plan=None)
                content = await getattr(ai, ai_method)(topic, params["chapters"], lang, **kwargs)
                path = await getattr(docs, doc_method)(topic, content, params["author"], lang, extras=extras)
        finally:
            ticker.cancel()
        if not path or not os.path.exists(path):
            raise RuntimeError("Fayl yaratilmadi")
        stem = re.sub(r"[^\w-]+", "_", topic)[:30].strip("_") or "fayl"
        return path, f"{spec['label'].split(' (')[0].replace(' ', '_')}_{stem}.docx"
    return run


def _doc_options(key: str) -> Dict:
    from config import EXTRAS_PRICES
    spec = _doc_spec(key)
    chapters = key in ("course_work", "diploma_work", "bitiruv_ishi", "dissertatsiya")
    options = {"form": "document", "languages": list(DOC_LANGUAGES),
               "sizes": [{"key": k, "label": _size_label(k, chapters), "price": int(v)} for k, v in spec["prices"].items()],
               "extras": [{"key": k, "label": EXTRAS_LABELS[k], "price": 0 if spec.get("free_extras") else EXTRAS_PRICES.get(k, 0)}
                          for k in EXTRAS_LABELS] if spec["extras"] else [],
               "eta_minutes": max(1, round(spec["eta"] / 60))}
    if spec.get("plan_style"):
        options["plan_styles"] = [{"key": k, "label": v} for k, v in PLAN_STYLES.items()]
    return options


for _key in ("independent_work", "referat", "article", "course_work", "diploma_work", "bitiruv_ishi", "dissertatsiya"):
    _spec = _doc_spec(_key)
    register(Kind(key=_key, label=_spec["label"], normalize=_doc_normalize(_key), price=_doc_price(_key),
                  title=lambda p: p["topic"], run=_doc_runner(_key), publish_as=_spec["store"],
                  heavy=bool(_spec.get("heavy")), options=_doc_options(_key)))


# ───────────────────────────────────────────────────────────────────────── tezis

def _thesis_normalize(raw: Dict) -> Dict:
    topic = _text(raw, "topic", 300)
    if len(topic) < 3:
        raise JobError("Mavzu kamida 3 ta belgidan iborat bo'lsin.")
    author = _text(raw, "author", 80) or _text(raw, "_default_author", 80)
    university = _text(raw, "university", 120)
    if not university:
        raise JobError("Universitet nomini kiriting.")
    return {"topic": topic, "language": raw.get("language") if raw.get("language") in DOC_LANGUAGES else "uz",
            "author": author, "university": university, "faculty": _text(raw, "faculty", 120),
            "group": _text(raw, "group", 40)}


async def _thesis_run(params: Dict, report: Report) -> Tuple[str, str]:
    import asyncio
    import os

    from services.ai_service import get_ai_service
    from services.document_service import get_document_service

    ticker = asyncio.ensure_future(_ticker(report, 60))
    try:
        content = await get_ai_service().generate_thesis_content(params["topic"], params["language"])
        path = await get_document_service().create_thesis(
            params["topic"], content, params["author"], params["university"], params["language"],
            faculty=params["faculty"], group=params["group"])
    finally:
        ticker.cancel()
    if not path or not os.path.exists(path):
        raise RuntimeError("Fayl yaratilmadi")
    stem = re.sub(r"[^\w-]+", "_", params["topic"])[:30].strip("_") or "fayl"
    return path, f"Tezis_{stem}.docx"


def _thesis_price(_params: Dict) -> int:
    from config import DOCUMENT_PRICES
    return int(DOCUMENT_PRICES["tezis"])


register(Kind(key="thesis", label="Tezis", normalize=_thesis_normalize, price=_thesis_price,
              title=lambda p: p["topic"], run=_thesis_run, publish_as="tezis",
              options={"form": "thesis", "languages": list(DOC_LANGUAGES), "price": _thesis_price({}),
                       "eta_minutes": 1}))
KINDS_ORDER = ("premium_presentation", "independent_work", "referat", "article", "thesis", "course_work",
               "diploma_work", "bitiruv_ishi", "dissertatsiya")


# ─────────────────────────────────────────── oddiy taqdimot (chiroyli orqa fonlar)

def _simple_templates():
    from services.template_service import TemplateService
    return TemplateService().templates


def _simple_normalize(raw: Dict) -> Dict:
    from config import PRESENTATION_PRICES

    topic = _text(raw, "topic", 300)
    if len(topic) < 3:
        raise JobError("Mavzu kamida 3 ta belgidan iborat bo'lsin.")
    try:
        count = int(raw.get("slide_count") or 10)
    except (TypeError, ValueError):
        count = 10
    if count not in PRESENTATION_PRICES:
        count = min(PRESENTATION_PRICES, key=lambda n: abs(n - count))
    template = raw.get("template") if raw.get("template") in _simple_templates() else "template_20"
    return {"topic": topic, "slide_count": count, "template": template,
            "language": _pick_language(raw, topic),
            "author": _text(raw, "author", 80) or _text(raw, "_default_author", 80),
            "icons": raw.get("icons") is not False, "plan_slide": bool(raw.get("plan_slide")),
            "preferences": _text(raw, "preferences", 1000),
            "source_text": _long_text(raw, "source_text", SOURCE_LIMIT),
            "source_label": _text(raw, "source_label", 120)}


def _simple_price(params: Dict) -> int:
    from config import PRESENTATION_PRICES
    return int(PRESENTATION_PRICES[params["slide_count"]])


async def _simple_run(params: Dict, report: Report) -> Tuple[str, str]:
    import asyncio
    import os

    from services.ai_service import get_ai_service
    from services.document_service import get_document_service
    from services.template_service import TemplateService

    topic, language = params["topic"], params["language"]
    # Botdagi qoida: o'zbekcha taqdimotda yozuv (lotin/kirill) tanlanadi, ikkisi aralashmaydi.
    script = uz_script.script_of_language(language)
    lang = "uz" if script else language
    token = None
    ai_topic = topic
    if params.get("source_text"):
        from bot.handlers.documents import _build_book_topic
        ai_topic = _build_book_topic(topic, params["source_text"], lang)
    if params.get("preferences"):
        ai_topic = f"{ai_topic}\n\nClient wishes for this presentation: {params['preferences']}"
    if script:
        token = uz_script.use(script)
        if script == uz_script.LATIN:
            topic = uz_script.to_latin(topic)
            ai_topic = uz_script.to_latin(ai_topic)
    ticker = asyncio.ensure_future(_ticker(report, 100))
    try:
        ai = get_ai_service()
        content = await ai.generate_presentation_in_batches(ai_topic, params["slide_count"], lang)
        if not content or not content.get("slides"):
            content = await ai.generate_presentation_in_batches(ai_topic, params["slide_count"], lang)
        if not content or not content.get("slides"):
            raise RuntimeError("AI taqdimot mazmunini qaytarmadi")
        content["slides"] = [x for x in content["slides"] if x.get("layout") != "references"]
        plan_items = await ai.generate_plan_items(ai_topic, lang) if params["plan_slide"] else []
        docs = get_document_service()
        docs.use_icons = params["icons"]
        path = await docs.create_presentation_with_template_background(
            topic, content, params["author"], params["template"], TemplateService(), lang, [], plan_items)
        if path and script:
            await asyncio.to_thread(uz_script.normalize_pptx, path, script)
    finally:
        ticker.cancel()
        if token is not None:
            uz_script.reset(token)
    if not path or not os.path.exists(path):
        raise RuntimeError("Fayl yaratilmadi")
    job_id = params.get("_job_id") or ""
    if job_id:      # saytda ochib ko'rish uchun (xato bo'lsa ham fayl mijozga yetadi)
        try:
            from services import web_decks
            await asyncio.to_thread(web_decks.create_view, job_id, params, path)
        except Exception as exc:
            log.warning("Taqdimot ko'rinishi tayyorlanmadi (%s): %s", job_id, exc)
    stem = re.sub(r"[^\w-]+", "_", topic)[:30].strip("_") or "fayl"
    return path, f"Taqdimot_{stem}.pptx"


def _simple_options() -> Dict:
    from config import PRESENTATION_PRICES
    return {"form": "simple_presentation", "languages": list(DOC_LANGUAGES), "eta_minutes": 2,
            "sizes": [{"key": str(n), "label": f"{n} slayd", "price": int(p)} for n, p in sorted(PRESENTATION_PRICES.items())]}


register(Kind(key="simple_presentation", label="Taqdimot (chiroyli orqa fonlar)", normalize=_simple_normalize,
              price=_simple_price, title=lambda p: p["topic"], run=_simple_run, publish_as="taqdimot",
              options=_simple_options()))
# Oddiy taqdimot (chiroyli orqa fonlar) saytda ko'rsatilmaydi: «Taqdimot» faqat zamonaviy tizim orqali
# ishlaydi. Xizmat ro'yxatda qoladi — ilgari berilgan buyurtmalar va API mos bo'lib qoladi.


# ───────────────────────────────────── taqdimotning bitta sahifasini AI ga qayta yozdirish

def _rewrite_normalize(raw: Dict) -> Dict:
    parent = str(raw.get("parent") or "")
    if not re.fullmatch(r"[0-9a-f]{32}", parent):
        raise JobError("Taqdimot topilmadi.")
    try:
        index = int(raw.get("index"))
    except (TypeError, ValueError):
        raise JobError("Sahifani tanlang.")
    instruction = re.sub(r"\s+", " ", str(raw.get("instruction") or "")).strip()[:500]
    if len(instruction) < 3:
        raise JobError("Sahifa qanday bo'lishini yozing.")
    return {"parent": parent, "index": index, "instruction": instruction,
            "owner": int(raw.get("_telegram_id") or 0)}


def _rewrite_price(_params: Dict) -> int:
    from config import SLIDE_REWRITE_PRICE
    return int(SLIDE_REWRITE_PRICE)


async def _rewrite_run(params: Dict, report: Report) -> Tuple[str, str]:
    import os
    import shutil

    from database import web_store
    from services import web_decks
    from services.premium_presentation import llm_client, slide_edit

    parent = params["parent"]
    index = params["index"]
    job = await web_store.get_job(parent, params.get("owner") or None)
    if not job or job["kind"] != "premium_presentation" or job["status"] != "done" or not job.get("result_path"):
        raise RuntimeError("Taqdimot topilmadi yoki muddati o'tgan")
    try:
        from config import AI_MODELS
        from database.database import Database
        key = await Database.get_premium_ai_model()
        if key in AI_MODELS:
            llm_client.set_text_model(AI_MODELS[key]["id"])
    except Exception:
        pass
    llm_client.reset_usage()

    shots = tempfile.mkdtemp(prefix="editshots_")
    work = tempfile.mkdtemp(prefix="editdeck_")
    try:
        async with web_decks.lock(parent):
            deck = web_decks.load(parent)
            if not deck:
                raise RuntimeError("Taqdimot nusxasi topilmadi")
            try:
                result = await slide_edit.rewrite(deck, index, params["instruction"], shots, progress=report)
            except slide_edit.SlideEditError as exc:
                raise RuntimeError(str(exc)) from None
            pages = list(deck["pages"])
            for number, html in result["pages"].items():
                pages[number] = html
            report("render", 84)
            pptx = await asyncio.to_thread(slide_edit.build_pptx, pages, work)

            outline = list(deck.get("outline") or [])
            while len(outline) < len(pages):
                outline.append({"title": "", "brief": "", "category": ""})
            for number, item in result["outline"].items():
                outline[number] = item
            deck.update(pages=pages, outline=outline, titles=web_decks.titles_of(pages),
                        version=int(deck.get("version") or 1) + 1, pptx_stale=False)   # PPTX shu yerda yig'ildi
            deck.setdefault("history", []).append(
                {"index": index + 1, "instruction": params["instruction"], "title": result["title"],
                 "at": __import__("time").time()})
            await asyncio.to_thread(web_decks.store_shots, parent, result["shots"])
            web_decks.save(parent, deck)

            # Mijoz "Yuklab olish" bosganda endi o'zgartirilgan taqdimotni oladi.
            target = job["result_path"]
            tmp = target + ".new"
            shutil.copyfile(pptx, tmp)
            os.replace(tmp, target)
            handle, final = tempfile.mkstemp(prefix="yangi_", suffix=".pptx")
            os.close(handle)
            shutil.copyfile(pptx, final)
    finally:
        shutil.rmtree(shots, ignore_errors=True)
        shutil.rmtree(work, ignore_errors=True)
    return final, job.get("result_name") or "Taqdimot.pptx"


register(Kind(key="slide_rewrite", label="Sahifani o'zgartirish", normalize=_rewrite_normalize,
              price=_rewrite_price, title=lambda p: f"{p['index'] + 1}-sahifa: {p['instruction'][:40]}",
              run=_rewrite_run, quiet=True))
