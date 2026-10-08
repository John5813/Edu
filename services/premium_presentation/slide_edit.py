"""Taqdimotning BITTA sahifasini mijoz ko'rsatmasi bo'yicha qayta yozish (saytdagi «Sahifani o'zgartirish»).

Tartib:
1. Reja: mijozning erkin yozgan iltimosi (masalan «doirasimon diagramma qilib ber») sahifa rejasiga
   aylanadi — joylashuv kategoriyasi, sarlavha, diagramma turi (AI, ishlamasa kalit so'zlar bo'yicha).
2. Diagramma kerak bo'lsa — tanlangan AI dan haqiqiy ma'lumot (taqdimot yaratishdagi qoida bilan bir xil).
3. Yozish: taqdimotning qolgan sahifalari ko'rsatib yoziladi — mavzu, ohang va til saqlanadi, boshqa
   sahifalarda aytilgan fikrlar takrorlanmaydi.
4. Qurish: ikonkalar, diagramma, rasm; so'ng sahifa brauzerda sig'dirilib, suratga olinadi.
5. Sarlavha o'zgarsa, reja sahifasi (2-sahifa) yangi sarlavhalardan qayta yig'iladi.
"""
import asyncio
import logging
import os
import re
import shutil
import tempfile
from typing import Callable, Dict, List, Optional

from . import chart_data, deck_logic, html_images, html_render, html_slides, llm_client, prompts, themes

log = logging.getLogger(__name__)

MAX_INSTRUCTION = 500
PLAN_INDEX = 1                       # 2-sahifa: reja — sarlavhalardan o'zi yig'iladi

Progress = Optional[Callable[[str, int], None]]


class SlideEditError(RuntimeError):
    """Sahifani qayta yozib bo'lmadi (mijozga ko'rsatiladi, pul qaytariladi)."""


# Kalit so'zlar: AI reja bermasa, iltimosdan kategoriya shu yerda aniqlanadi.
_KEYWORDS = (
    (r"doira|halqa|pie\b|donut|doughnut|кругов|кольц|круг", "diagramma", "halqa"),
    (r"ustunli|ustun diagramma|bar chart|column|столбч|гистограмм", "diagramma", "ustunli"),
    (r"chiziqli|trend|dinamik|line chart|линейн", "diagramma", "chiziqli"),
    (r"diagramm|grafik|chart|график|диаграмм", "diagramma", ""),
    (r"rasm|surat|foto|image|photo|picture|картин|фото|изображен", "matn_rasm", ""),
    (r"qadam|bosqich|jarayon|\bstep|process|этап|шаг", "jarayon", ""),
    (r"vaqt o|xronolog|timeline|хронолог", "vaqt_oqi", ""),
    (r"taqqos|qiyos|compar|versus|сравнен", "qiyoslash", ""),
    (r"kartochka|karta\b|kartalar|cards|карточ", "kartalar", ""),
    (r"raqam|ko'rsatkich|ko‘rsatkich|kpi|number|показател|цифр", "korsatkichlar", ""),
    (r"iqtibos|quote|цитат", "iqtibos", ""),
    (r"jadval|table|таблиц", "jadval", ""),
    (r"formula|формул", "formula", ""),
)
_CHART_KINDS = ("halqa", "ustunli", "chiziqli")


def guess(instruction: str) -> Dict[str, str]:
    """Iltimosdan kategoriya va diagramma turini kalit so'zlar bo'yicha taxmin qiladi."""
    text = (instruction or "").lower()
    for pattern, category, chart_kind in _KEYWORDS:
        if re.search(pattern, text):
            return {"category": category, "chart_kind": chart_kind}
    return {"category": "", "chart_kind": ""}


def _theme(deck: dict):
    chosen = themes.get(deck["theme_key"]) if deck.get("theme_key") else themes.suggest(deck.get("topic", ""))
    return themes.with_style(chosen, deck.get("style", ""))


def _source(deck: dict, index: int) -> str:
    page = deck["pages"][index]
    return html_slides.source_of(page) or page


def _outline(deck: dict) -> List[Dict]:
    """Taqdimot rejasi: saqlangani, yo'q bo'lsa sahifalardan tiklanadi."""
    saved = list(deck.get("outline") or [])
    count = len(deck["pages"])
    result = []
    for index in range(count):
        item = dict(saved[index]) if index < len(saved) and isinstance(saved[index], dict) else {}
        body = _source(deck, index)
        item["title"] = deck_logic.title_of(body) or item.get("title", "")
        item.setdefault("brief", deck_logic.short_note(deck_logic.plain(body), 120))
        item.setdefault("category", "")
        result.append(item)
    return result


def _shape(deck: dict, index: int) -> str:
    return html_slides._shape_label(html_slides.shape_signature(_source(deck, index)), deck.get("language", "uz"))


# ─────────────────────────────────────────────────────────────── 1. reja

def plan_edit(deck: dict, index: int, instruction: str) -> Dict[str, str]:
    """Sahifaning yangi rejasi: {category, title, brief, chart_kind}."""
    total = len(deck["pages"])
    language = deck.get("language", "uz")
    outline = _outline(deck)
    current = outline[index]
    lines = "\n".join(f"  {i + 1}. «{item['title']}» — {_shape(deck, i)}" for i, item in enumerate(outline))
    E = prompts.get(language).EDIT
    prompt = prompts.fill(E["plan"], topic=deck.get("topic", ""), total=total, lines=lines, n=index + 1,
                          title=current["title"], shape=_shape(deck, index), instruction=instruction,
                          categories=html_slides.catalogue_text(language), target=prompts.target(language))
    plan: Dict[str, str] = {}
    try:
        with prompts.use(language):
            data = llm_client._call_openrouter(E["system"], prompt, temperature=0.3, max_tokens=500)
        if isinstance(data, dict):
            plan = {key: str(data.get(key) or "").strip() for key in ("category", "title", "brief", "chart_kind")}
    except llm_client.NoCredits:
        raise
    except Exception as exc:
        log.warning("Sahifa rejasi AI dan olinmadi, kalit so'zlardan olinadi: %s", exc)

    hint = guess(instruction)
    category = plan.get("category", "").lower()
    if category not in html_slides.CATEGORY_KEYS:
        category = hint["category"]
    # Kalit so'z aniq diagramma/rasm desa — AI adashgan bo'lsa ham mijoz so'ragani bo'ladi.
    if hint["category"] in ("diagramma", "matn_rasm") and category != hint["category"]:
        category = hint["category"]
    if index == 0:
        category = "muqova"
    elif category in ("muqova", "reja") or not category:
        category = hint["category"] or _current_category(deck, index)
    chart_kind = plan.get("chart_kind", "").lower()
    if chart_kind not in _CHART_KINDS:
        chart_kind = hint["chart_kind"]
    if category == "diagramma" and not chart_kind:
        chart_kind = deck_logic.chart_kind_for(f"{current['title']} {instruction}", index)
    title = deck_logic.short_title(plan.get("title", "")) or current["title"]
    brief = plan.get("brief") or current.get("brief") or current["title"]
    return {"category": category, "title": title, "brief": brief,
            "chart_kind": chart_kind if category == "diagramma" else ""}


def _current_category(deck: dict, index: int) -> str:
    saved = (_outline(deck)[index].get("category") or "").strip()
    return saved if saved in html_slides.CATEGORY_KEYS and saved not in ("muqova", "reja") else "kartalar"


# ────────────────────────────────────────────────────────────── 2-3. yozish

def _write(deck: dict, index: int, plan: Dict, instruction: str, retry: str = "") -> str:
    theme = _theme(deck)
    language = deck.get("language", "uz")
    total = len(deck["pages"])
    outline = _outline(deck)
    item = dict(outline[index])
    item.update(title=plan["title"], brief=plan["brief"], category=plan["category"])
    if plan.get("chart"):
        item["chart"], item["chart_note"] = plan["chart"], plan.get("chart_note", "")
    if plan.get("chart_fallback"):
        item["chart_fallback"], item["chart_note"] = True, plan.get("chart_note", "")
    outline[index] = item

    others = [i for i in range(total) if i != index]
    system = html_slides.shell_rules(theme, language)
    user = html_slides._user_prompt(
        deck.get("topic", ""), index + 1, 1, total, outline,
        [outline[i].get("brief", "") for i in others][:8], int(deck.get("level") or 2),
        deck.get("source_text", ""), deck.get("preferences", ""), deck.get("author", ""),
        deck.get("family", "umumiy") or "umumiy",
        shapes=[html_slides.shape_signature(_source(deck, i)) for i in others],
        written=[outline[i]["title"] for i in others], language=language)
    previous = outline[index - 1]["title"] if index > 0 else ""
    following = outline[index + 1]["title"] if index + 1 < total else ""
    P = prompts.get(language)
    E = P.EDIT
    parts = [
        prompts.fill(E["request"], instruction=instruction),
        prompts.fill(E["redo"], n=index + 1, total=total, category=plan["category"],
                     note=P.CATEGORIES.get(plan["category"], "")),
        prompts.fill(E["neighbours"], previous=previous, next=following)]
    if plan["category"] == "matn_rasm":
        parts.append(E["photo"])
    if retry:
        parts.append(retry)
    chunk = html_slides._write_chunk(system, user + "\n\n" + "\n".join(parts), 1)
    return chunk[0] if chunk else ""


def _finish(deck: dict, index: int, body: str, item: Dict) -> str:
    """Yozilgan sahifaga taqdimot yaratishdagi barcha tuzatishlar (muqova, xulosa, diagramma, sarlavha)."""
    theme, language = _theme(deck), deck.get("language", "uz")
    total = len(deck["pages"])
    system = html_slides.shell_rules(theme, language)
    if index == 0:
        body = html_slides._cover_credit(body, deck.get("author", ""), language)
    if index == total - 1:
        body = html_slides._drop_thanks(body)
    body = chart_data.enforce(body, item, language)
    if index >= 1 and html_slides._thin(body):
        body = html_slides._thicken(body, system, theme)
    if index == total - 1:
        body = html_slides._no_photo(body)
    body = deck_logic.strip_numbering(body)
    if index != 0:
        body = deck_logic.flow_photo_text(deck_logic.fix_columns(deck_logic.fix_title_case(body)))
    return body


# ───────────────────────────────────────────────────────────── 4. qurish

def _settle(pages: List[str], theme, language: str, shots_dir: str) -> List[str]:
    """Sahifalarni brauzerda sig'dirib, yakuniy HTML ni qaytaradi (suratlar `shots_dir` ga tushadi)."""
    final: List[str] = []
    work = tempfile.mkdtemp(prefix="edit_")
    try:
        path = html_render.render(
            pages, out_dir=work, name="sahifa",
            repair=lambda page, problems: html_slides.fix_slide(page, problems, theme, language),
            explain=lambda page, area: html_slides.fill_gap(page, area, theme, language),
            collect=final, shots_dir=shots_dir)
        try:
            os.remove(path)
        except OSError:
            pass
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if len(final) != len(pages):
        raise SlideEditError("Sahifa chizilmadi")
    return final


def build_pptx(pages: List[str], out_dir: str) -> str:
    """Taqdimotning yakuniy sahifalaridan tahrirlanadigan PPTX (tuzatishsiz: sahifalar allaqachon yakuniy)."""
    return html_render.render(pages, out_dir=out_dir, name="taqdimot")


async def rewrite(deck: dict, index: int, instruction: str, shots_dir: str,
                  progress: Progress = None) -> Dict:
    """Sahifani qayta yozadi. Qaytaradi: {pages: {indeks: html}, shots: {indeks: png}, outline: {indeks: {...}}}.

    `deck` o'zgartirilmaydi; natijani chaqiruvchi saqlaydi. Promptlar taqdimot tilida (prompts/*.py).
    """
    with prompts.use(deck.get("language", "uz")):
        return await _rewrite(deck, index, instruction, shots_dir, progress)


async def _rewrite(deck: dict, index: int, instruction: str, shots_dir: str,
                   progress: Progress = None) -> Dict:
    def report(stage: str, value: int) -> None:
        if progress:
            try:
                progress(stage, value)
            except Exception:
                pass

    instruction = re.sub(r"\s+", " ", str(instruction or "")).strip()[:MAX_INSTRUCTION]
    total = len(deck.get("pages") or [])
    if not 0 <= index < total:
        raise SlideEditError("Bunday sahifa yo'q")
    if index == PLAN_INDEX and total > 3:
        raise SlideEditError("Reja sahifasi boshqa sahifalar sarlavhalaridan o'zi yig'iladi: "
                             "uni emas, kerakli sahifani o'zgartiring.")
    if len(instruction) < 3:
        raise SlideEditError("Sahifa qanday bo'lishini yozing.")

    theme, language = _theme(deck), deck.get("language", "uz")

    report("writing", 8)
    plan = await asyncio.to_thread(plan_edit, deck, index, instruction)
    log.info("%d-sahifa rejasi: %s", index + 1, plan)

    item = {"title": plan["title"], "brief": plan["brief"], "category": plan["category"],
            "chart_kind": plan["chart_kind"]}
    if plan["category"] == "diagramma":
        report("writing", 18)
        await asyncio.to_thread(chart_data.ground, [item], deck.get("topic", ""), language,
                                int(deck.get("level") or 2))
        plan.update({k: item[k] for k in ("chart", "chart_note", "chart_fallback") if k in item})

    report("writing", 32)
    body = await asyncio.to_thread(_write, deck, index, plan, instruction)
    wanted = {"diagramma": deck_logic.has_chart, "matn_rasm": deck_logic.has_photo}.get(plan["category"])

    def acceptable(text: str) -> bool:
        if not text:
            return False
        probe = chart_data.enforce(text, item, language) if plan["category"] == "diagramma" else text
        return wanted is None or wanted(probe)

    if not acceptable(body):
        log.info("%d-sahifa: so'ralgan ko'rinish chiqmadi, qayta so'raladi", index + 1)
        report("writing", 44)
        E = prompts.get(language).EDIT
        retry = E["chart_retry"] if plan["category"] == "diagramma" else E["photo"]
        body = await asyncio.to_thread(_write, deck, index, plan, instruction, retry)
    if not acceptable(body):
        raise SlideEditError("AI so'ralgan ko'rinishdagi sahifani yarata olmadi. Iltimosni boshqacha yozib ko'ring.")

    body = await asyncio.to_thread(_finish, deck, index, body, item)
    page = (await asyncio.to_thread(html_slides.build_pages, [body], theme, language))[0]

    report("images", 55)
    try:
        pages, _ = await html_images.fill_photos([page], limit=2)
        page = pages[0]
        if index == 0:
            pages, _ = await html_images.fill_cover([page], deck.get("topic", ""))
            page = pages[0]
    except Exception as exc:
        log.warning("Sahifa rasmlari qo'yilmadi: %s", exc)

    outline = _outline(deck)
    old_title = outline[index]["title"]
    new_title = deck_logic.title_of(body) or plan["title"]
    updates = {index: {"title": new_title, "brief": plan["brief"], "category": plan["category"]}}

    targets = [(index, page)]
    if new_title != old_title and total > 3:
        merged = [dict(o) for o in outline]
        merged[index] = updates[index]
        items = [(merged[i]["title"], merged[i].get("brief", "")) for i in range(2, total - 1)
                 if merged[i].get("title")]
        if items:
            plan_body = deck_logic.plan_slide(items, language)
            plan_page = (await asyncio.to_thread(html_slides.build_pages, [plan_body], theme, language))[0]
            targets.append((PLAN_INDEX, plan_page))

    report("render", 70)
    final = await asyncio.to_thread(_settle, [html for _, html in targets], theme, language, shots_dir)
    shots = {}
    for position, (target, _) in enumerate(targets):
        path = os.path.join(shots_dir, f"shot_{position + 1:02d}.png")
        if os.path.exists(path):
            shots[target] = path
    return {"pages": {target: final[position] for position, (target, _) in enumerate(targets)},
            "shots": shots, "outline": updates, "title": new_title, "category": plan["category"]}
