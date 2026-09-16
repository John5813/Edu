import hashlib
import logging
import os
import random
import re

from pydantic import ValidationError

from services.project_work import variety

from . import config, infographics, llm_client, qa
from .models import (Brief, INFOGRAPHIC_PRESETS, InfographicItem, Slide,
                     ROLE_ORDER, VisualElement, grounding_check)
from .renderer import build_presentation

log = logging.getLogger("pipeline")


# Bitta slaydda bitta instrument. Instrument — diagramma, rasm, infografika
# yoki ko'rsatkich kartochkalari qatori; oddiy matn hisobga olinmaydi.
#
# Ilgari ikkitasiga ruxsat berilardi va eng ko'p uchraydigan juftlik aynan
# "diagramma + rasm" edi: rasm diagramma ustiga tushib uni yopib qo'yardi,
# o'quvchi esa ikkalasini birdan o'qiy olmaydi. Bitta instrument qolsa, unga
# joy ham, izoh ham yetadi.
_INSTRUMENTS = {"image", "chart", "infographic", "kpi"}

# Qaysi biri qolishi kerak: diagramma raqam ko'rsatadi, rasm mavzuni ochadi,
# infografika bandlarni tartiblaydi, kartochkalar esa eng kam ma'lumot beradi.
_INSTRUMENT_RANK = {"chart": 0, "image": 1, "infographic": 2, "kpi": 3}

_INSTRUMENT_NAMES = {"image": "rasm", "chart": "diagramma",
                     "infographic": "infografika", "kpi": "ko'rsatkich kartochkalari"}


def _instrument_groups(slide: Slide) -> list:
    """Slayddagi instrumentlar: (daraja, tartib, tur, elementlar).

    Kartochkalar qatori bitta instrument sifatida sanaladi — yonma-yon
    turgan to'rtta kartochka to'rtta alohida instrument emas.
    """
    groups = []
    kpis = []
    for position, element in enumerate(slide.canvas.elements):
        if element.type == "kpi":
            kpis.append((position, element))
        elif element.type in _INSTRUMENTS:
            groups.append((_INSTRUMENT_RANK[element.type], position,
                           element.type, [element]))
    if kpis:
        groups.append((_INSTRUMENT_RANK["kpi"], kpis[0][0], "kpi",
                       [element for _, element in kpis]))
    groups.sort(key=lambda group: (group[0], group[1]))
    return groups


# ─────────────────────────────────────────── Kanvas validatsiyasi

def canvas_check(slide: Slide) -> tuple[bool, str]:
    """Slayd kanvasining professional sifat talablarini tekshiradi."""
    elements = slide.canvas.elements or []

    if not elements:
        return False, (
            f"Slayd {slide.index}: kanvas bo'sh. Kamida bitta vizual yoki matn elementi kerak."
        )

    text_elements = [e for e in elements if e.type == "text" and e.text and e.text.strip()]
    if not text_elements:
        return False, (
            f"Slayd {slide.index}: tushuntiruvchi matn yo'q. Kamida bitta matn elementi kerak."
        )

    tiny_texts = [e for e in text_elements if e.size and e.size < 10]
    if tiny_texts:
        return False, (
            f"Slayd {slide.index}: {len(tiny_texts)} ta matn elementi juda kichik "
            f"({min(e.size for e in tiny_texts):.0f}pt). Minimal o'lcham 11pt."
        )

    if not slide.title or not slide.title.strip():
        return False, f"Slayd {slide.index}: 'title' maydoni bo'sh."

    groups = _instrument_groups(slide)
    if len(groups) > 1:
        listed = ", ".join(_INSTRUMENT_NAMES.get(kind, kind) for _, _, kind, _ in groups)
        return False, (
            f"Slayd {slide.index}: bir varaqda {len(groups)} ta instrument bor "
            f"({listed}). Bir varaqqa BITTA instrument qo'yiladi — ular "
            "bir-birini yopadi va o'quvchi ikkalasini birdan o'qiy olmaydi. "
            "Slayd g'oyasini qaysi biri yaxshiroq ochsa o'shani qoldir, "
            "qolganini olib tashla. Qolgan instrumentni kattaroq qilib joylashtir "
            "va uni matn bilan to'liq izohla: nima ko'rsatilgan va undan qanday "
            "xulosa chiqadi."
        )

    return True, ""


def _repair_in_code(brief: Brief, slide: Slide) -> bool:
    """Kanvas nuqsonini modelsiz tuzatishga urinadi. Bir narsa o'zgarsa True.

    Slaydni qayta yozdirish uchun modelga murojaat qilish eng qimmat yo'l:
    butun kanvas JSON ketadi va butun kanvas JSON qaytadi. Quyidagi
    nuqsonlarga esa model kerak emas.
    """
    repaired = False

    # Juda kichik shrift — o'lchamni ko'tarish yetarli.
    for element in slide.canvas.elements:
        if element.type != "text" or not element.size or element.size >= 10:
            continue
        element.size = 20.0 if element.bold else _MIN_BODY_PT
        element.fitted = False
        repaired = True

    # Bo'sh sarlavha — slaydning o'z matnidan olinadi.
    if not (slide.title or "").strip():
        source = next((element.text for element in slide.canvas.elements
                       if element.type == "text" and element.bold
                       and (element.text or "").strip()), "")
        source = source or (slide.key_text or "")
        if source.strip():
            slide.title = " ".join(source.split())[:80]
            repaired = True

    # Ikkita instrument — kesmasdan, mazmunni saqlab bittaga tushiramiz.
    if _reduce_to_one(brief, slide):
        repaired = True

    return repaired


def ensure_chart_explanations(brief: Brief) -> Brief:
    """Har diagrammaga raqam va izoh beradi.

    Diagramma raqamsiz va izohsiz bo'lsa, uni himoyada tushuntirib bo'lmaydi:
    o'qituvchi "bu nima?" deb so'raganda javob slaydning o'zida turishi kerak.
    AI yozgan izoh saqlanadi, faqat oldiga raqam qo'shiladi.
    """
    number = 0
    for slide in brief.slides:
        for element in slide.canvas.elements:
            if element.type != "chart":
                continue
            number += 1
            if element.caption and element.caption.strip():
                element.caption = _numbered(element.caption, number)
                continue
            categories = element.categories or []
            series = element.series or []
            series_name = "Ko‘rsatkich"
            values = []
            if series and isinstance(series[0], dict):
                series_name = series[0].get("name") or series_name
                values = series[0].get("values") or []
            if values and categories:
                try:
                    peak = max(range(min(len(values), len(categories))),
                               key=lambda i: float(values[i]))
                    element.caption = (
                        f"{series_name} bo‘yicha eng yuqori ko‘rsatkich "
                        f"{categories[peak]} davrida kuzatiladi."
                    )
                except (TypeError, ValueError):
                    element.caption = f"{series_name} ko‘rsatkichlarining taqqoslanishi."
            else:
                element.caption = (
                    f"{element.chart_title or series_name}: diagrammadagi asosiy "
                    "ko‘rsatkichlar taqqoslanishi."
                )
            element.caption = _numbered(element.caption, number)
    return brief


def _numbered(caption: str, number: int) -> str:
    """Izoh oldiga "1-rasm." qo'yadi, allaqachon raqamlangan bo'lsa tegmaydi."""
    text = (caption or "").strip()
    if re.match(r"^\d+\s*-\s*rasm", text, re.IGNORECASE):
        return text
    return f"{number}-rasm. {text}"


def canvas_validation_and_fix(
    brief: Brief, topic: str, max_attempts: int = 2, language: str = "uz"
) -> Brief:
    """Har slaydni tekshiradi, muammoli slaydlarni qayta loyihalaydi."""
    # Avval matn o'lchamlari va ustma-ustni tuzatamiz
    brief = ensure_visuals(brief, topic, language)
    # Bitta slaydda bitta instrument — tanlovni model qiladi. Bu qadam
    # `limit_instruments` dan oldin turishi shart: kod kesib tashlagandan
    # keyin modelga tanlaydigan narsa qolmaydi.
    brief = ensure_single_instrument(brief, topic, language)
    brief = spread_chart_types(brief, topic)
    # Mavzu sahifasi presetlar taqsimlanishidan oldin quriladi: aks holda
    # birinchi slaydning bloki navbatdan joy olib, keyin tashlab yuborilardi.
    brief = build_title_slide(brief, topic)
    brief = spread_infographic_presets(brief, topic)
    # Ortiqcha instrumentlar infografika yoyilishidan OLDIN olib tashlanadi:
    # yoyilgandan keyin u o'nlab ibtidoiy elementga aylanadi va uni butun
    # holda qaytarib olish imkonsiz bo'lardi.
    brief = limit_instruments(brief)
    brief = expand_infographics(brief)
    brief = ensure_title_contrast(brief)
    brief = ensure_body_contrast(brief)
    brief = ensure_icons(brief)
    brief = fix_text_overlaps(brief)
    # Band chegarasi matn joylashuvidan KEYIN tekshiriladi: blok surilgandan
    # keyin bandan chiqib ketishi mumkin.
    brief = keep_text_inside_panels(brief)
    brief = enforce_min_text_size(brief)
    brief = ensure_chart_explanations(brief)

    for attempt in range(max_attempts):
        any_issue = False
        for i, slide in enumerate(brief.slides):
            ok, problem = canvas_check(slide)
            if ok:
                continue
            log.warning("Kanvas muammo (slayd %s, urinish %s): %s",
                        slide.index, attempt + 1, problem)

            # Avval kod bilan tuzatishga urinamiz. Nuqsonlarning ko'pi —
            # juda kichik shrift, bo'sh sarlavha, ikkita instrument —
            # modelsiz tuzatiladi, slaydni butunicha qayta yozdirish esa
            # eng qimmat yo'l va tayyor qismlarni ham o'zgartirib yuboradi.
            if _repair_in_code(brief, slide):
                fix_slide_overlaps(slide)
                ok, problem = canvas_check(slide)
                if ok:
                    log.info("Slayd %s kod bilan tuzatildi (model chaqirilmadi)",
                             slide.index)
                    continue

            any_issue = True
            try:
                fixed = llm_client.regenerate_slide(
                    topic, slide.model_dump(), problem, language=language
                )
                merged = {**slide.model_dump(), **fixed}
                brief.slides[i] = Slide.model_validate(merged)
                ok2, problem2 = canvas_check(brief.slides[i])
                if not ok2:
                    log.error("Tuzatishdan keyin ham muammo (slayd %s): %s", slide.index, problem2)
            except Exception as e:
                log.error("Kanvas tuzatishda xato (slayd %s): %s", slide.index, e)

        if not any_issue:
            log.info("Kanvas tekshiruv: hamma slayd to'liq (urinish %s)", attempt + 1)
            break

    # Qayta loyihalangan slaydlar yangi infografika qaytargan bo'lishi mumkin.
    brief = expand_infographics(brief)
    brief = ensure_icons(brief)
    return brief


# ─────────────────────────────────────────── Matn sifatini tuzatish (programmatik)

def fix_text_overlaps(brief: Brief) -> Brief:
    """Slayddagi matn bloklari bir-birining ustiga chiqmasligini ta'minlaydi."""
    for slide in brief.slides:
        lift_text_off_blockers(slide)
        fix_slide_overlaps(slide)
    return brief


# Ikki matn oralig'idagi eng kichik bo'shliq.
_GAP = 0.1
# Gorizontal kesishish shu ulushdan kam bo'lsa — bloklar yonma-yon ustunlarda
# turibdi. Ularni vertikal ajratish kompozitsiyani buzadi, chunki ular
# allaqachon bir-biriga xalaqit qilmaydi.
_COLUMN_SHARE = 0.3
# Qisqartirilgan matn blokining eng kichik balandligi.
_MIN_TEXT_H = 0.45
# Tana matnining odatdagi pastki chegarasi.
_MIN_BODY_PT = 13.0
# Model belgilangan hajmdan oshib ketgan slaydda oxirgi chora. 11pt kichik,
# lekin ustma-ust tushgan matndan o'qish osonroq — shuning uchun faqat
# 13pt da ham sig'magan holatda ishlatiladi. 9pt esa juda kam uchraydigan
# holat uchun: matn hajmi chegaradan ikki baravar oshib ketganda.
_HARD_MIN_PT = 11.0
_LAST_RESORT_PT = 9.0
def _reading_key(element, index: int) -> tuple:
    """Elementning o'qilish tartibidagi o'rni.

    Sarlavha har doim birinchi: tuzatish jarayonida uning `y` qiymati
    o'zgarsa ham u matn ostiga tushib qolmasligi kerak.
    """
    is_title = bool(element.bold) and (element.size or 0) >= _TITLE_MIN_SIZE
    return (0 if is_title else 1, round(element.y, 2), round(element.x, 2), index)


def _horizontal_share(first: tuple, second: tuple) -> float:
    """Ikki maydon gorizontal bo'yicha qanchalik ustma-ust tushishini qaytaradi."""
    ax, _, aw, _ = first
    bx, _, bw, _ = second
    overlap = min(ax + aw, bx + bw) - max(ax, bx)
    if overlap <= 0 or aw <= 0 or bw <= 0:
        return 0.0
    return overlap / min(aw, bw)


def _is_title(element) -> bool:
    return bool(element.bold) and (element.size or 0) >= _TITLE_MIN_SIZE


def _ceiling(element, placed: list) -> float:
    """Element joylasha oladigan eng yuqori nuqta.

    Faqat undan oldin o'qiladigan va gorizontal kesishadigan bloklar to'sadi;
    yonma-yon ustundagi blok halaqit qilmaydi.
    """
    ex, _, ew, _ = _box(element)
    top = _EDGE
    for other in placed:
        ox, oy, ow, oh = _box(other)
        if min(ex + ew, ox + ow) - max(ex, ox) <= 0:
            continue
        if _horizontal_share(_box(element), _box(other)) < _COLUMN_SHARE:
            continue
        top = max(top, oy + oh + _GAP)
    return top


def _flow(ordered: list, compact: bool) -> bool:
    """Bloklarni o'qilish tartibida yuqoridan pastga joylaydi.

    Har blok o'zidan oldingilarning ostiga tushadi, shuning uchun tartib
    hech qachon teskari bo'lmaydi. `compact` rejimida bloklar imkon qadar
    yuqoriga tortiladi — bu faqat slaydga sig'may qolganda ishlatiladi,
    chunki u dizayn qo'ygan bo'shliqlarni yeb qo'yadi. Sarlavha esa
    ko'tarilmaydi: u o'zining bezak bandi ichida turishi kerak.
    """
    fits = True
    placed = []
    for element in ordered:
        top = _ceiling(element, placed)
        if element.y < top - _TOLERANCE or (compact and not _is_title(element)):
            element.y = top
        _, _, _, height = _box(element)
        if element.y + height > SLIDE_H - _EDGE + _TOLERANCE:
            fits = False
        placed.append(element)
    return fits


def _shrink_overflow(ordered: list, floor: float = _MIN_BODY_PT) -> None:
    """Slayddan toshib ketgan matnni qisqartiradi.

    Tartibni buzib blokni yuqoriga ko'tarishdan ko'ra matnni kichraytirgan
    ma'qul. Qisqartirish faqat oxirgi blokdan emas, hamma moslashuvchan
    bloklardan ulushiga qarab olinadi: aks holda oxirgisi yolg'iz o'zi
    o'qib bo'lmas darajada siqilardi. Sarlavhaga tegilmaydi.
    """
    bottom = max((element.y + _box(element)[3]) for element in ordered)
    overflow = bottom - (SLIDE_H - _EDGE)
    if overflow <= _TOLERANCE:
        return

    flexible = [e for e in ordered
                if not _is_title(e) and _box(e)[3] > _MIN_TEXT_H + _TOLERANCE]
    slack = sum(_box(e)[3] - _MIN_TEXT_H for e in flexible)
    if slack <= _TOLERANCE:
        return

    ratio = min(1.0, overflow / slack)
    for element in flexible:
        height = _box(element)[3]
        new_height = height - (height - _MIN_TEXT_H) * ratio
        if element.size:
            reduced = max(floor, element.size * max(new_height / height, 0.7))
            if reduced < element.size:
                # `enforce_min_text_size` shriftni qaytarib kattalashtirmasin:
                # aks holda matn yana qutidan toshib, quyidagi blok ustiga
                # minib qolardi.
                element.fitted = reduced < _MIN_BODY_PT
                element.size = reduced
        element.h = new_height


def fix_slide_overlaps(slide: Slide) -> Slide:
    """Bitta slayd ichidagi matn bloklarini ustma-ustlikdan tozalaydi.

    Alohida funksiya, chunki vizual QA aynan bitta slaydni tuzatadi —
    uni `Brief` ichiga o'rash rol tartibi validatorini buzardi.
    """
    edge = _EDGE
    # locked — infografika presetlari hisoblab qo'ygan matnlar. Ularning
    # o'rni kartochkasiga bog'liq, mustaqil surilsa kompozitsiya buziladi.
    texts = [e for e in slide.canvas.elements if e.type == "text" and not e.locked]
    if not texts:
        return slide

    # Renderer elementlarni slayd ichiga qistiradi. QA esa renderdan oldingi
    # koordinatalar bilan ishlaydi, shuning uchun avval bir xil koordinata
    # tizimiga keltiramiz.
    for element in texts:
        width = min(max(element.w or 5.0, 0.5), SLIDE_W - edge * 2)
        height = min(max(element.h or 1.0, 0.2), SLIDE_H - edge * 2)
        element.w, element.h = width, height
        element.x = min(max(element.x, edge), SLIDE_W - edge - width)
        element.y = min(max(element.y, edge), SLIDE_H - edge - height)

    # O'qilish tartibi bir marta, kirish holatidan olinadi va keyin
    # o'zgarmaydi. Ilgari "qaysi biri pastroq turibdi" degan savolga har
    # iteratsiyada qayta javob berilardi: bir marta surilgan blok keyingi
    # aylanishda anchorga aylanib, sarlavhani o'zidan pastga itarib
    # yuborardi va slayd teskari o'qiladigan bo'lib qolardi.
    # `texts.index(...)` ishlatilmaydi: pydantic modellari qiymat bo'yicha
    # taqqoslanadi, ya'ni bir xil ikki matn bitta indeksni qaytarardi.
    ordered = [element for _, element in sorted(
        ((_reading_key(element, position), element)
         for position, element in enumerate(texts)),
        key=lambda pair: pair[0],
    )]

    if not _flow(ordered, compact=False):
        # Har qadamda shrift pastki chegarasi tushadi. Birinchi qadam —
        # avvalgi xatti-harakat (13pt). Model belgilangan matn hajmidan
        # oshib ketgan slaydda 13pt da hech narsa sig'maydi va tanlov
        # ikkita bo'lib qoladi: o'qib bo'lmaydigan ustma-ustlik yoki
        # kichikroq shrift. Ikkinchisi afzal.
        for floor in (_MIN_BODY_PT, _HARD_MIN_PT, _LAST_RESORT_PT):
            _flow(ordered, compact=True)
            _shrink_overflow(ordered, floor=floor)
            if _flow(ordered, compact=True):
                break

    # Yakuniy chegara tekshiruvi HAM o'lchangan balandlik bilan bajariladi.
    # Ilgari bu yerda modelning e'lon qilgan `h` qiymati ishlatilardi:
    # oxirgi blok "sig'yapti" deb hisoblanib yuqoriga tortilar va endigina
    # ajratilgan qo'shni blok ustiga qaytib minib qolardi — ya'ni
    # ustma-ustlikni tuzatuvchining o'zi tiklab qo'yardi.
    for element in texts:
        _, _, width, height = _box(element)
        element.x = min(max(element.x, edge), SLIDE_W - edge - width)
        element.y = min(max(element.y, edge), SLIDE_H - edge - height)
    return slide


def enforce_min_text_size(brief: Brief, min_body_pt: float = _MIN_BODY_PT) -> Brief:
    """Sarlavha bo'lmagan matn elementlari uchun minimal 13pt ta'minlaydi.

    `fitted` belgisi qo'yilgan bloklar chetlab o'tiladi: ularning shrifti
    matnni qutiga sig'dirish uchun ataylab kichraytirilgan va uni qaytarib
    kattalashtirish ustma-ustlikni tiklab qo'yardi.
    """
    for slide in brief.slides:
        for el in slide.canvas.elements:
            if el.type == "text" and not el.bold and not el.locked and not el.fitted:
                if el.size < min_body_pt:
                    el.size = min_body_pt
    return brief


# ─────────────────────────────────────────── Brief generatsiyasi (to'liq)

def _enforce_role_order(slides_raw: list) -> list:
    """Slaydlar rollarini kamaymaslik tartibida tuzatadi."""
    if not slides_raw:
        return slides_raw
    slides_raw[0]["role"] = "hook"
    slides_raw[-1]["role"] = "synthesis"

    last_rank = 0
    for i, s in enumerate(slides_raw[1:-1], start=1):
        role = s.get("role", "detail")
        if role not in ROLE_ORDER:
            role = "detail"
        rank = ROLE_ORDER.index(role)
        if rank < last_rank:
            rank = last_rank
        if rank >= len(ROLE_ORDER) - 1:
            rank = len(ROLE_ORDER) - 2  # synthesis faqat oxirgi uchun
        s["role"] = ROLE_ORDER[rank]
        last_rank = rank

    return slides_raw


# Mijoz bergan hujjat promptga to'liq sig'maydi va har bo'lakka qayta-qayta
# yuborilsa qimmatga tushadi. Shundan uzuni bir marta siqiladi.
_SOURCE_INLINE_LIMIT = 3_500


def condense_source(source_text: str, topic: str) -> str:
    """Mijoz bergan materialni har bo'lak promptiga sig'adigan holga keltiradi.

    Qisqa material o'z holicha ketadi. Uzuni bir marta xulosalanadi: aks
    holda o'nta slaydlik taqdimotda 60 000 belgilik qo'llanma sakkiz marta
    yuborilardi.
    """
    text = (source_text or "").strip()
    if len(text) <= _SOURCE_INLINE_LIMIT:
        return text
    try:
        return llm_client.condense_source(text, topic)
    except Exception as e:
        log.error("Manbani siqib bo'lmadi, boshi ishlatiladi: %s", e)
        return text[:_SOURCE_INLINE_LIMIT]


def generate_brief_chunked(topic: str, target_count: int, progress_cb=None, level: int = 2,
                           preferences: str = "", language: str = "uz",
                           source_text: str = "") -> Brief:
    """Katta taqdimotni har 5 varoqlik bo'laklarda generatsiya qiladi.
    Har bo'lak avvalgi bo'lak xulosasi bilan mantiqiy bog'liq bo'ladi.
    """
    CHUNK_SIZE = 5
    source = condense_source(source_text, topic)

    if target_count <= 7:
        # Kichik taqdimot — yagona prompt
        return generate_brief_with_validation(topic, target_count, level=level,
                                              preferences=preferences, language=language,
                                              source=source)

    total_chunks = (target_count + CHUNK_SIZE - 1) // CHUNK_SIZE
    all_slides_raw: list = []
    first_theme = None
    prev_summary: str | None = None
    remaining = target_count

    for chunk_num in range(total_chunks):
        chunk_size = min(CHUNK_SIZE, remaining)
        is_first = chunk_num == 0
        is_last = remaining <= CHUNK_SIZE

        log.info("Bo'lak %s/%s generatsiya: %s slayd (daraja=%s)", chunk_num + 1, total_chunks, chunk_size, level)
        if progress_cb:
            progress_cb(chunk_num + 1, total_chunks)

        last_err = None
        for attempt in range(3):
            try:
                raw = llm_client.generate_brief_chunk(
                    topic=topic,
                    chunk_size=chunk_size,
                    chunk_num=chunk_num,
                    total_chunks=total_chunks,
                    is_first=is_first,
                    is_last=is_last,
                    prev_summary=prev_summary,
                    level=level,
                    preferences=preferences,
                    source=source,
                    language=language,
                )
                slides_raw = raw.get("slides", [])
                if not slides_raw:
                    raise ValueError("Bo'sh slides ro'yxati qaytdi")

                if first_theme is None:
                    first_theme = raw.get("theme")

                # Reindex
                base_idx = len(all_slides_raw)
                for k, s in enumerate(slides_raw):
                    s["index"] = base_idx + k + 1

                all_slides_raw.extend(slides_raw)
                prev_summary = llm_client.get_chunk_summary(slides_raw)
                break

            except Exception as e:
                last_err = e
                log.error("Bo'lak %s/%s xato (urinish %s): %s",
                          chunk_num + 1, total_chunks, attempt + 1, e)
                if attempt == 2:
                    raise RuntimeError(
                        f"Bo'lak {chunk_num+1}/{total_chunks} 3 urinishda ham muvaffaqiyatsiz: {last_err}"
                    )

        remaining -= chunk_size

    # Role tartibini tuzat va validate
    if all_slides_raw:
        _enforce_role_order(all_slides_raw)

    default_theme = {
        "primary": "1B2A4A", "accent": "E8A020", "light": "F4F6F9",
        "heading_font": "Calibri", "body_font": "Calibri",
    }
    brief_dict = {
        "topic": topic,
        "theme": first_theme or default_theme,
        "slides": all_slides_raw,
    }

    try:
        return ensure_chart_explanations(Brief.model_validate(brief_dict))
    except Exception as e:
        log.error("Chunked brief validate xatosi, role-order qayta tuzatilmoqda: %s", e)
        # Ikkinchi urinish — role-orderni qattiqroq tuzatib qayta validate
        _enforce_role_order(all_slides_raw)
        # Oxirgi 2 ta slayd synthesis bo'lishi mumkin — birini application qilish
        for s in all_slides_raw[1:-1]:
            if s.get("role") == "synthesis":
                s["role"] = "application"
        brief_dict["slides"] = all_slides_raw
        return ensure_chart_explanations(Brief.model_validate(brief_dict))


def generate_brief_with_validation(topic: str, slide_count: int = 8,
                                   max_attempts: int = 3, level: int = 2,
                                   preferences: str = "", language: str = "uz",
                                   source: str = "") -> Brief:
    """LLM'dan JSON so'raydi, pydantic orqali qat'iy tekshiradi. Silent fallback YO'Q."""
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            raw = llm_client.generate_brief(topic, slide_count, level=level,
                                            preferences=preferences, language=language,
                                            source=source)
            brief = Brief.model_validate(raw)

            for i, s in enumerate(brief.slides):
                if not grounding_check(s):
                    log.warning("Grounding-check muvaffaqiyatsiz: slayd %s, qayta yozilmoqda", s.index)
                    fixed = llm_client.regenerate_slide(
                        topic, s.model_dump(),
                        "Bu slaydda aniq raqam, sana yoki atoqli ot yo'q. "
                        "Aniq fakt/misol qo'shib, vizual kompozitsiyani ham yangilab qayta yoz.",
                        language=language,
                    )
                    merged = {**s.model_dump(), **fixed}
                    brief.slides[i] = Slide.model_validate(merged)

            return ensure_chart_explanations(brief)

        except ValidationError as e:
            last_error = e
            log.error("Brief validatsiya xatosi (urinish %s/%s): %s", attempt, max_attempts, e)
        except Exception as e:
            last_error = e
            log.error("Brief generatsiyasida xato (urinish %s/%s): %s", attempt, max_attempts, e)

    raise RuntimeError(
        f"Brief generatsiya {max_attempts} urinishdan keyin muvaffaqiyatsiz: {last_error}"
    )



# ─────────────────────────────────────────── Infografika va ikonkalar

def spread_chart_types(brief: Brief, topic: str) -> Brief:
    """Bitta taqdimotda bir xil diagramma turi takrorlanmasin.

    Model odatda hamma slaydga ustunli diagramma qo'yadi. Almashtirish
    faqat bir xil ma'lumotni ko'rsata oladigan turlar orasida bo'ladi,
    shuning uchun mazmun buzilmaydi.
    """
    charts = [
        element
        for slide in brief.slides
        for element in slide.canvas.elements
        if element.type == "chart"
    ]
    if len(charts) < 2:
        return brief

    current = [element.chart_type or "column" for element in charts]
    spread = variety.spread_chart_types(current, (topic, brief.topic))
    for element, chart_type in zip(charts, spread):
        element.chart_type = chart_type
    if spread != current:
        log.info("Diagramma turlari yoyildi: %s → %s", current, spread)
    return brief


def spread_infographic_presets(brief: Brief, topic: str) -> Brief:
    """Bir xil kartochka to'ri hamma slaydga tushib qolmasin.

    Yetkazilgan taqdimotda 11 slaydning 8 tasi bir xil tuzilishda edi:
    to'rtta kartochka, to'rtta doira, to'rtta ikonka. Model eng oson
    presetni tanlab, uni takrorlayverardi. Bu yerda presetlar bandlar
    soniga mos keladiganlari orasida almashtiriladi.
    """
    blocks = [
        element
        for slide in brief.slides
        for element in slide.canvas.elements
        if element.type == "infographic"
    ]
    if len(blocks) < 2:
        return brief

    seed = f"{topic}|{brief.topic}"
    rng = random.Random(hashlib.sha256(seed.encode("utf-8")).hexdigest())

    # Ketma-ket ikkitadan ortiq takrorlanmasin va umuman bir xili ko'p
    # bo'lmasin — shuning uchun har preset nechta ishlatilgani sanaladi.
    used: dict = {}
    previous = None
    current = [element.preset or "cards" for element in blocks]

    for element in blocks:
        items = len(element.items or [])
        options = [preset for preset in infographics.PRESET_FITS
                   if infographics.fits(preset, items)]
        if not options:
            continue
        fewest = min(used.get(option, 0) for option in options)
        fresh = [option for option in options
                 if used.get(option, 0) == fewest and option != previous]
        pick = rng.choice(fresh or [o for o in options if o != previous] or options)
        element.preset = pick
        used[pick] = used.get(pick, 0) + 1
        previous = pick

    spread = [element.preset for element in blocks]
    if spread != current:
        log.info("Infografika presetlari yoyildi: %s → %s", current, spread)
    return brief


def _describe(kind: str, elements: list) -> str:
    """Instrumentni bir satrda tasvirlaydi — modelga qaror uchun shu yetadi."""
    element = elements[0]
    if kind == "chart":
        what = element.chart_title or element.caption or ""
        cats = ", ".join(str(c) for c in (element.categories or [])[:4])
        return f"{what} ({element.chart_type}; {cats})".strip()
    if kind == "image":
        return (element.prompt or "")[:120]
    if kind == "infographic":
        titles = ", ".join((item.title or item.text or "")[:24]
                           for item in (element.items or [])[:4])
        return f"{element.preset}: {titles}"
    return " · ".join(f"{e.value} {e.label}".strip() for e in elements[:4])


def _ask_which_instrument(topic: str, slide: Slide, groups: list,
                          language: str) -> tuple:
    """Modeldan faqat bitta qarorni so'raydi: qaysi instrument qolsin.

    Butun slaydni qayta yozdirish o'rniga shu: so'rovga slaydning JSON'i
    emas, sarlavhasi va variantlar ro'yxati ketadi, javob esa bir necha
    o'nlab token. Slaydning yaxshi qismlari ham o'z joyida qoladi.
    """
    options = [{"kind": kind, "what": _describe(kind, elements)}
               for _, _, kind, elements in groups]
    try:
        answer = llm_client.choose_instrument(
            topic, slide.title or "", slide.key_text or "", options, language)
    except Exception as e:
        log.error("Instrument tanlashda xato (slayd %s): %s", slide.index, e)
        return "", ""
    keep = str(answer.get("keep") or "").strip().lower()
    if keep not in {kind for _, _, kind, _ in groups}:
        log.warning("Slayd %s: model noma'lum instrument nomini qaytardi (%r)",
                    slide.index, keep)
        keep = ""
    return keep, str(answer.get("note") or "").strip()


def ensure_single_instrument(brief: Brief, topic: str, language: str = "uz") -> Brief:
    """Bir slaydda bitta instrument qolishini ta'minlaydi.

    Tanlovni MODEL qiladi, o'zgartirishni KOD bajaradi. Ilgari bu yerda
    butun slayd qayta yozdirilardi — bitta qaror uchun ming-ming token
    ketardi va slaydning butun qismlari ham qaytadan yozilib, yaxshi
    joylari yo'qolardi.

    Mazmun yo'qotilmaydi: infografika matnga aylanadi, kartochka raqamlari
    matn satriga ko'chadi, ortiqcha rasm yoki diagramma esa instrumenti
    yo'q boshqa slaydga o'tadi.
    """
    for slide in brief.slides:
        groups = _instrument_groups(slide)
        if len(groups) <= 1:
            continue
        keep, note = _ask_which_instrument(topic, slide, groups, language)
        _reduce_to_one(brief, slide, keep, grow=False)
        if note:
            _explain_instrument(slide, note)
        _grow_into_free_space_any(slide)
    return brief


def limit_instruments(brief: Brief) -> Brief:
    """Kafolat: yetkazilayotgan slaydda bitta instrument qoladi.

    Tanlovni model qilishi kerak edi (`ensure_single_instrument`); bu yer
    so'rov xato bilan tugagan yoki keyingi qadamlar yana ikkinchisini
    qo'shib qo'ygan holat uchun.
    """
    for slide in brief.slides:
        _reduce_to_one(brief, slide)
    return brief


def _reduce_to_one(brief: Brief, slide: Slide, keep: str = "",
                   grow: bool = True) -> bool:
    """Slaydda bitta instrument qoldiradi. Qaysi biri — `keep` aytadi.

    `keep` bo'sh bo'lsa tartib bo'yicha eng yuqorisi qoladi. Ortiqchasi
    o'chirilmaydi: iloji boricha mazmuni saqlanadi.
    """
    groups = _instrument_groups(slide)
    if len(groups) <= 1:
        return False
    if keep:
        groups.sort(key=lambda group: (group[2] != keep, group[0], group[1]))

    for _, _, kind, elements in groups[1:]:
        log.info("Slayd %s: ortiqcha %s olib tashlandi (%s ta instrument edi, "
                 "qoladigani %s)", slide.index, kind, len(groups), groups[0][2])
        if kind == "infographic":
            _infographic_to_text(elements[0], slide)
        elif kind == "kpi":
            _kpis_to_text(elements, slide)
        elif kind in ("image", "chart") and _relocate_visual(brief, slide, elements[0]):
            continue
        else:
            for element in elements:
                if element in slide.canvas.elements:
                    slide.canvas.elements.remove(element)
    if grow:
        _grow_into_free_space_any(slide)
    return True


def _explain_instrument(slide: Slide, note: str) -> None:
    """Qolgan instrumentga izoh qo'yadi.

    Bitta instrument qoldirish uni yaxshiroq yoritish uchun qilinadi,
    shuning uchun "nima ko'rsatilgani" slaydda yozilib turishi kerak.
    Diagrammada bu `caption`, boshqalarida — ostidagi kichik matn.
    """
    groups = _instrument_groups(slide)
    if len(groups) != 1:
        return
    kind, elements = groups[0][2], groups[0][3]
    element = elements[0]
    if kind == "chart":
        if not (element.caption or "").strip():
            element.caption = note
        return

    x, y, width, height = _box(element)
    top = y + height + 0.08
    floor = SLIDE_H - _EDGE
    for other in slide.canvas.elements:
        if other is element or other.type == "rect":
            continue
        ox, oy, ow, oh = _box(other)
        if min(x + width, ox + ow) - max(x, ox) <= 0.1 or oy < top:
            continue
        floor = min(floor, oy - _GAP)
    room = floor - top
    if room < 0.4:
        return
    size = infographics.fit_size(note, width, room, start=12.0, minimum=10.0)
    slide.canvas.elements.append(VisualElement(
        type="text", x=x, y=top, w=width,
        h=min(room, infographics.height_of(note, width, size)),
        text=note, size=size, italic=True, align="center", color="52514E",
        fitted=True,
    ))


def _kpis_to_text(elements: list, slide: Slide) -> None:
    """Kartochkalar qatorini bitta matn satriga aylantiradi.

    Kartochkalarni o'chirish raqamlarni yo'qotardi — aynan ular slaydning
    eng qimmatli qismi. Matn ularni saqlaydi, joyni esa bo'shatadi.
    """
    parts = []
    for element in elements:
        value = (element.value or "").strip()
        label = (element.label or "").strip()
        if value and label:
            parts.append(f"{value} — {label}")
        elif value or label:
            parts.append(value or label)
    box = [(element.x, element.y, element.w or 3.0, element.h or 1.8)
           for element in elements]
    for element in elements:
        if element in slide.canvas.elements:
            slide.canvas.elements.remove(element)
    if not parts:
        return
    left = min(x for x, _, _, _ in box)
    top = min(y for _, y, _, _ in box)
    right = max(x + w for x, _, w, _ in box)
    text = " · ".join(parts)
    width = max(right - left, 2.0)
    slide.canvas.elements.append(VisualElement(
        type="text", x=left, y=top, w=width,
        h=infographics.height_of(text, width, 13.0),
        text=text, size=13.0, align="left", color="1B2A4A",
    ))


def _relocate_visual(brief: Brief, source: Slide, element) -> bool:
    """Ortiqcha rasm yoki diagrammani instrumenti yo'q slaydga ko'chiradi.

    O'chirish taqdimotdagi rasmlar sonini kamaytirardi — `ensure_visuals`
    esa aynan shu sonni kafolatlaydi, ya'ni ikkita qoida bir-biri bilan
    kurashardi. Ko'chirishda rasm ham qoladi, kafolat ham buzilmaydi.
    """
    for slide in brief.slides[1:-1]:
        if slide is source or _instrument_groups(slide):
            continue
        source.canvas.elements.remove(element)
        # Qabul qiluvchi slaydning matni chap yarmiga siqiladi, rasm o'ng
        # yarmini egallaydi — `_add_image` dagi bilan bir xil sxema.
        for text in slide.canvas.elements:
            if text.type == "text" and not text.locked:
                text.w = min(text.w or 6.0, 6.4)
                text.x = min(text.x, 0.7)
        element.x, element.y, element.w, element.h = 7.1, 0.9, 5.8, 5.7
        slide.canvas.elements.append(element)
        log.info("Slayd %s dagi ortiqcha %s %s-slaydga ko'chirildi",
                 source.index, element.type, slide.index)
        return True
    return False


def _grow_into_free_space_any(slide: Slide) -> None:
    """Yolg'iz qolgan instrumentni bo'shagan joy hisobiga kattalashtiradi.

    Ikkinchi instrument ketgach uning o'rni bo'sh qoladi. Bitta instrument
    qoldi degani uni kichik qoldirish degani emas — mijoz to'lagan slayd
    yarim bo'sh ko'rinmasligi kerak.
    """
    groups = _instrument_groups(slide)
    if len(groups) != 1:
        return
    kind, elements = groups[0][2], groups[0][3]
    if kind == "kpi" or len(elements) != 1:
        return
    _grow_into_free_space(elements[0], slide)


def _infographic_to_text(element, slide: Slide) -> None:
    """Infografikani o'z qutisidagi oddiy ro'yxatga aylantiradi."""
    lines = []
    for item in (element.items or []):
        head = (item.title or item.value or "").strip()
        body = (item.text or "").strip()
        if head and body:
            lines.append(f"• {head} — {body}")
        elif head or body:
            lines.append(f"• {head or body}")
    position = slide.canvas.elements.index(element)
    slide.canvas.elements.remove(element)
    if not lines:
        return

    width = max(element.w or 6.0, 2.0)
    height = max(element.h or 3.0, 0.6)
    text = "\n".join(lines)
    size = infographics._fit(text, width, height, start=14.0, minimum=11.0)
    slide.canvas.elements.insert(position, VisualElement(
        type="text", x=element.x, y=element.y, w=width, h=height,
        text=text, size=size, align="left", color="1B2A4A",
    ))


def _grow_into_free_space(element, slide: Slide) -> None:
    """Infografika blokini ostidagi bo'sh joy hisobiga kengaytiradi.

    Blok past bo'lsa kartochkadagi izoh matni sig'may "…" bilan kesilardi.
    Balandlikni oshirish eng arzon yechim, lekin faqat haqiqatan bo'sh joyga:
    pastda boshqa element tursa, uning tepasida to'xtaymiz.
    """
    left = element.x
    right = element.x + (element.w or 6.0)
    bottom = element.y + (element.h or 3.0)
    floor = SLIDE_H - _EDGE

    for other in slide.canvas.elements:
        if other is element:
            continue
        other_left, other_top, other_w, other_h = _box(other)
        if min(right, other_left + other_w) - max(left, other_left) <= 0.1:
            continue          # yonma-yon turibdi, xalaqit qilmaydi
        if other_top + other_h <= element.y + 0.1:
            continue          # tepada turibdi
        if other_top < bottom - 0.1:
            continue          # allaqachon kesishyapti — o'sish mumkin emas
        floor = min(floor, other_top - _GAP)

    room = floor - element.y
    if room > (element.h or 0) + 0.1:
        element.h = round(room, 2)


def expand_infographics(brief: Brief) -> Brief:
    """`infographic` elementlarini ibtidoiy shakllarga yoyadi.

    AI faqat mazmun beradi (3-6 band), koordinata va ranglarni kod hisoblaydi —
    shu sababli kompozitsiya har doim tekis chiqadi.
    """
    total = 0
    for slide in brief.slides:
        expanded = []
        for element in slide.canvas.elements:
            if element.type != "infographic":
                expanded.append(element)
                continue
            _grow_into_free_space(element, slide)
            parts = infographics.expand(element, brief.theme)
            if parts:
                expanded.extend(parts)
                total += 1
            else:
                log.warning("Slayd %s: infografika yoyilmadi, element tashlandi", slide.index)
        slide.canvas.elements = expanded
    if total:
        log.info("Infografika: %s ta blok yoyildi", total)
    return brief


def _title_icon(slide: Slide, brief: Brief) -> VisualElement | None:
    """Sarlavha yoniga kichik ikonka qo'yadi, kerak bo'lsa sarlavhani suradi.

    Sarlavhalar odatda x=0.7 da turadi, ya'ni chapda ikonkaga joy yo'q. Shu
    sababli joy topilmasa sarlavhaning o'zi o'ngga suriladi — ikonka slayddan
    tashqariga chiqib ketmasin.
    """
    title_elements = [
        e for e in slide.canvas.elements
        if e.type == "text" and e.bold and e.text and e.size >= 20
    ]
    if not title_elements:
        return None
    title = min(title_elements, key=lambda e: (e.y, e.x))

    d = 0.46
    needed = d + 0.22
    icon_x = title.x - needed
    if icon_x < 0.25:
        # Chapda joy yo'q: sarlavhani o'ngga surib, bo'shagan joyga qo'yamiz.
        icon_x = max(title.x, 0.25)
        title.x = icon_x + needed
        title.w = max((title.w or 5.0) - needed, 2.0)
        if title.x + title.w > 13.03:
            title.w = 13.03 - title.x
        if title.w < 2.0:
            return None

    accent = (brief.theme.accent if brief.theme else "E8A020").lstrip("#")
    return VisualElement(
        type="icon", x=icon_x, y=title.y + 0.06, w=d, h=d,
        text=f"{slide.title} {title.text}", color=accent, shape="none", locked=True,
    )


# Bezak bandi ichidagi matn uchun chekinish.
_PANEL_PAD = 0.12
# Matn bandga "tegishli" hisoblanishi uchun kerakli gorizontal ustma-ustlik.
_PANEL_SHARE = 0.6
# Ingichka aksent chiziqlari band emas.
_MIN_PANEL_H = 0.5


def _host_panel_of(element, panels) -> object:
    """Matn qaysi rangli band ICHIDA boshlanganini aniqlaydi.

    Maydon ulushi bilan aniqlab bo'lmaydi: aynan nuqsonli holatda matnning
    ko'p qismi banddan TASHQARIDA bo'ladi (u bandan chiqib ketgan), ya'ni
    ulush kichik chiqadi. Shu sababli matnning boshlanish nuqtasi qaralaadi.
    """
    ex, ey, ew, eh = _box(element)
    best, best_top = None, -1.0
    for panel in panels:
        px, py, pw, ph = _box(panel)
        if ph < _MIN_PANEL_H:
            continue
        # Butun slaydni qoplagan band — bu fon, chegara emas.
        if pw >= SLIDE_W - 0.4 and ph >= SLIDE_H - 0.4:
            continue
        if not (py - _TOLERANCE <= ey < py + ph):
            continue
        overlap = min(ex + ew, px + pw) - max(ex, px)
        if ew <= 0 or overlap / ew < _PANEL_SHARE:
            continue
        # Bir nechta band mos kelsa — eng ichkarisi, ya'ni eng pastdan
        # boshlanadigani.
        if py > best_top:
            best, best_top = panel, py
    return best


def _grow_panel(panel, slide: Slide, guests: list) -> None:
    """Bandni pastdagi bo'sh joy hisobiga uzaytiradi.

    `guests` — bandning o'z matnlari. Ular band bilan kesishgani tabiiy,
    shuning uchun to'siq deb hisoblanmaydi.
    """
    px, py, pw, ph = _box(panel)
    floor = SLIDE_H - _EDGE
    for other in slide.canvas.elements:
        if other is panel or any(other is guest for guest in guests):
            continue
        if other.type == "rect":
            continue                      # band bandni to'smaydi
        ox, oy, ow, oh = _box(other)
        if min(px + pw, ox + ow) - max(px, ox) <= 0.1:
            continue                      # yonma-yon turibdi
        if oy + oh <= py + 0.1:
            continue                      # tepada
        # Qolgan hamma narsa chegara: band o'sib begona matnni bosib qolsa,
        # o'sha matn rangi endi mos kelmay qoladi (oq fon uchun tanlangan
        # to'q harflar to'q band ustiga tushib, o'qilmay qoladi).
        floor = min(floor, oy - _GAP)
    if floor - py > ph + 0.1:
        panel.h = round(floor - py, 2)


def keep_text_inside_panels(brief: Brief) -> Brief:
    """Rangli band ustidagi matn bandning ichida qolishini ta'minlaydi.

    Ustma-ustlik tuzatuvchisi to'ldirilgan `rect` ni ataylab to'siq deb
    bilmaydi: band aynan matn ORTIDA turishi uchun chiziladi. Lekin hech
    kim matn bandning pastidan chiqib ketmasligini tekshirmasdi — matn
    to'q bandan chiqib, oq fonda oq harflar bilan davom etar va o'sha
    yerdan o'qilmay qolardi.

    Avval shrift kichraytiriladi; u yetmasa band pastdagi bo'sh joy
    hisobiga uzaytiriladi.
    """
    for slide in brief.slides:
        panels = _panels(slide)
        if not panels:
            continue

        hosted = {}
        for element in slide.canvas.elements:
            if element.type != "text" or not (element.text or "").strip():
                continue
            if element.locked:
                continue                 # preset hisoblab qo'ygan matn
            panel = _host_panel_of(element, panels)
            if panel is None:
                continue
            hosted.setdefault(id(panel), (panel, []))[1].append(element)

        for panel, guests in hosted.values():
            px, py, pw, ph = _box(panel)
            over = max((_box(e)[1] + _box(e)[3] for e in guests), default=0.0)
            # Avval bandni uzaytirishga urinamiz: pastda bo'sh joy tursa,
            # matnni kichraytirgandan ko'ra bandni cho'zgan ma'qul.
            if over > py + ph - _PANEL_PAD + _TOLERANCE:
                _grow_panel(panel, slide, guests)
                px, py, pw, ph = _box(panel)
            bottom = py + ph - _PANEL_PAD
            for element in guests:
                ex, ey, ew, eh = _box(element)
                room = bottom - ey
                if eh <= room + _TOLERANCE:
                    continue
                size = infographics.fit_size(
                    element.text, ew, max(room, 0.2),
                    start=element.size or 14.0, minimum=_LAST_RESORT_PT)
                if size < (element.size or 14.0):
                    element.fitted = size < _MIN_BODY_PT
                    element.size = size
                    log.info("Slayd %s: matn banddan chiqib ketgan edi, "
                             "shrift %.1f pt ga tushirildi", slide.index, size)
                # E'lon qilingan balandlik ham qisqartiriladi: matn
                # kichraygan bo'lsa ham, model qo'ygan katta `h` qiymati
                # blokni banddan chiqarib turaverardi.
                fitted_h = infographics.height_of(element.text, ew, element.size or 14.0)
                element.h = max(min(element.h or eh, room), fitted_h)
    return brief


def ensure_icons(brief: Brief) -> Brief:
    """Har slaydda kamida bitta ikonka bo'lishini ta'minlaydi.

    Promptda so'rash yetarli emasligini rasm va diagramma tajribasi ko'rsatdi:
    model cheklovni ko'rib eng xavfsiz yo'lni — hech narsa qo'ymaslikni —
    tanlaydi. Shuning uchun kafolat kodda.
    """
    added = 0
    for slide in brief.slides:
        if _has(slide, "icon"):
            continue
        icon = _title_icon(slide, brief)
        if icon:
            slide.canvas.elements.append(icon)
            added += 1
    if added:
        log.info("Ikonka kafolati: %s slaydga sarlavha ikonkasi qo'shildi", added)
    return brief


# ─────────────────────────────────────────── Vizual kafolat

# Sobit ikkita rasm 11 slaydlik taqdimotda juda kam edi — kafolat aynan
# minimumda to'xtab, qolgan hamma slayd matn va kartochka bo'lib qolardi.
MIN_IMAGES = 2
MIN_CHARTS = 2
MIN_INFOGRAPHICS = 2


def _image_target(brief: Brief) -> int:
    """Har uch slaydga kamida bitta rasm, lekin ikkitadan kam emas."""
    return max(MIN_IMAGES, round(len(brief.slides) / 3))


def _count(brief: Brief, element_type: str) -> int:
    return sum(
        1 for slide in brief.slides
        for element in slide.canvas.elements
        if element.type == element_type
    )


def _has(slide: Slide, element_type: str) -> bool:
    return any(element.type == element_type for element in slide.canvas.elements)


def ensure_visuals(brief: Brief, topic: str, language: str = "uz") -> Brief:
    """Taqdimot rasmsiz va diagrammasiz chiqib ketmasligini kafolatlaydi.

    Promptda "majburiy" deyish yetarli emas edi: yetkazilgan taqdimotda 39 ta
    shakl bor edi va ularning hammasi matn qutisi bo'lib chiqdi. Model
    cheklovlarni ko'rib eng xavfsiz yo'lni — hech narsa qo'ymaslikni —
    tanlagan. Shuning uchun tekshiruv shu yerda, kodda.

    Yetishmagan element ham shu yerda QO'SHILADI, slaydni qayta yozdirib
    emas: rasm uchun model umuman chaqirilmaydi (prompt mavzudan quriladi),
    diagramma va infografika uchun esa faqat o'sha elementning o'zi
    so'raladi. Ilgari har bir yetishmovchilik butun slaydni qaytadan
    yozdirardi — eng qimmat yo'l va slaydning tayyor qismlari ham
    o'zgarardi.
    """
    if not brief.slides:
        return brief

    # 1. Birinchi slaydda rasm — mijoz uchun majburiy talab.
    if not _has(brief.slides[0], "image"):
        _add_image(brief.slides[0], topic)

    # 2. Umumiy minimum — qaysi slaydga qo'shishni mazmuniga qarab tanlaymiz.
    for element_type, minimum in (("image", _image_target(brief)),
                                  ("chart", MIN_CHARTS),
                                  ("infographic", MIN_INFOGRAPHICS)):
        for slide_index in _candidates(brief, element_type):
            if _count(brief, element_type) >= minimum:
                break
            slide = brief.slides[slide_index]
            added = False
            if element_type == "image":
                added = _add_image(slide, topic)
            elif element_type == "chart":
                added = _add_chart(slide, topic, language)
            else:
                added = _add_infographic(slide, topic, language)
            if added:
                fix_slide_overlaps(slide)

    log.info("Vizual kafolat: %s rasm, %s diagramma, %s infografika",
             _count(brief, "image"), _count(brief, "chart"), _count(brief, "infographic"))
    return brief


# Instrument o'ng yarmda, matn chap yarmda — eng ishonchli va eng ko'p
# ishlatiladigan sxema.
_VISUAL_BOX = (7.1, 0.9, 5.8, 5.7)
_TEXT_HALF = 6.4


def _clear_left(slide: Slide) -> None:
    """Matnni chap yarimga siqadi — o'ng yarim instrument uchun bo'shaydi."""
    for element in slide.canvas.elements:
        if element.type == "text" and not element.locked:
            element.w = min(element.w or 6.0, _TEXT_HALF)
            element.x = min(element.x, 0.7)


def _add_image(slide: Slide, topic: str) -> bool:
    """Slaydga rasm qo'yadi — model chaqirilmaydi.

    Rasm prompti mavzu va slayd sarlavhasidan quriladi; rasmni baribir
    tasvir modeli chizadi, matn modelidan bu yerda hech narsa so'rash
    shart emas.
    """
    _clear_left(slide)
    x, y, width, height = _VISUAL_BOX
    subject = " — ".join(part for part in (topic, (slide.title or "").strip()) if part)
    slide.canvas.elements.append(VisualElement(
        type="image", x=x, y=y, w=width, h=height,
        prompt=(f"professional photorealistic image representing {subject}, "
                "clean composition, natural lighting, high detail, no text"),
    ))
    log.info("Slayd %s: rasm qo'shildi (modelsiz)", slide.index)
    return True


def _add_chart(slide: Slide, topic: str, language: str) -> bool:
    """Slaydga diagramma qo'yadi — modeldan faqat raqamlar so'raladi."""
    try:
        data = llm_client.make_chart(topic, slide.title or "",
                                     slide.key_text or "", language)
    except Exception as e:
        log.error("Diagramma ma'lumoti olinmadi (slayd %s): %s", slide.index, e)
        return False
    categories = [str(c) for c in (data.get("categories") or [])]
    series = [item for item in (data.get("series") or []) if isinstance(item, dict)]
    if not categories or not series:
        log.warning("Slayd %s: diagramma ma'lumoti bo'sh qaytdi", slide.index)
        return False

    _clear_left(slide)
    x, y, width, height = _VISUAL_BOX
    slide.canvas.elements.append(VisualElement(
        type="chart", x=x, y=y + 0.3, w=width, h=height - 1.0,
        chart_type=str(data.get("chart_type") or "column"),
        chart_title=str(data.get("chart_title") or "")[:80],
        caption=str(data.get("caption") or "")[:200],
        categories=categories, series=series,
    ))
    log.info("Slayd %s: diagramma qo'shildi", slide.index)
    return True


def _add_infographic(slide: Slide, topic: str, language: str) -> bool:
    """Slaydning eng uzun matnini infografikaga aylantiradi.

    Joylashuvni infografika presetlari o'zi hisoblaydi, shuning uchun
    modeldan faqat bandlar so'raladi.
    """
    try:
        data = llm_client.make_infographic(topic, slide.title or "",
                                           slide.key_text or "",
                                           llm_client.ICON_NAMES, language)
    except Exception as e:
        log.error("Infografika bandlari olinmadi (slayd %s): %s", slide.index, e)
        return False
    items = [item for item in (data.get("items") or []) if isinstance(item, dict)][:5]
    if len(items) < 2:
        log.warning("Slayd %s: infografika bandlari yetarli emas", slide.index)
        return False

    bodies = [element for element in slide.canvas.elements
              if element.type == "text" and not element.locked and not element.bold
              and (element.text or "").strip()]
    if bodies:
        longest = max(bodies, key=lambda e: len(e.text or ""))
        top = max(_box(longest)[1], 1.6)
        slide.canvas.elements.remove(longest)
    else:
        top = 1.9

    preset = str(data.get("preset") or "cards")
    if preset not in INFOGRAPHIC_PRESETS:
        preset = "cards"
    slide.canvas.elements.append(VisualElement(
        type="infographic", x=0.6, y=top, w=12.1,
        h=max(SLIDE_H - _EDGE - top, 2.6), preset=preset,
        items=[InfographicItem(
            title=str(item.get("title") or "")[:60],
            text=str(item.get("text") or "")[:160],
            icon=str(item.get("icon") or "") or None,
            value=str(item.get("value") or "") or None,
        ) for item in items],
    ))
    log.info("Slayd %s: infografika qo'shildi (%s ta band)", slide.index, len(items))
    return True


def _candidates(brief: Brief, element_type: str) -> list:
    """Qaysi slaydlarga qo'shish mumkin — o'rtadagi, hali bo'sh turganlari.

    Instrument faqat instrumenti YO'Q slaydga qo'shiladi. Ilgari tekshiruv
    "shu turdagi element bormi" degan savolga qarardi, shuning uchun kafolat
    diagrammasi bor slaydga rasm qo'yib yuborardi — ya'ni ustma-ustlikni
    aynan tuzatuvchining o'zi yaratardi.
    """
    middle = range(1, max(len(brief.slides) - 1, 1))
    if element_type in _INSTRUMENTS:
        return [i for i in middle if not _instrument_groups(brief.slides[i])]
    return [i for i in middle if not _has(brief.slides[i], element_type)]


def _redesign(slide: Slide, topic: str, language: str, instruction: str) -> Slide:
    try:
        fixed = llm_client.regenerate_slide(topic, slide.model_dump(), instruction, language=language)
        merged = {**slide.model_dump(), **fixed}
        return Slide.model_validate(merged)
    except Exception as e:
        log.error("Slaydni qayta loyihalashda xato (slayd %s): %s", slide.index, e)
        return slide


def build_title_slide(brief: Brief, topic: str) -> Brief:
    """Birinchi slaydni toza mavzu sahifasiga aylantiradi.

    Yetkazilgan taqdimotda birinchi slayd oddiy kontent sahifasi edi:
    sarlavha o'rtada emas, yonida statistika kartochkalari va cho'zilgan
    rasm. Mavzu sahifasi bitta ish qiladi — mavzuni e'lon qiladi, shuning
    uchun u shu yerda qo'lda quriladi, model ixtiyoriga qoldirilmaydi.
    """
    if not brief.slides:
        return brief

    slide = brief.slides[0]
    theme = brief.theme
    primary = (theme.primary if theme else "1B2A4A").lstrip("#")
    accent = (theme.accent if theme else "E8A020").lstrip("#")

    # Mavjud matnlardan sarlavha va tagsarlavhani ajratib olamiz.
    texts = [e for e in slide.canvas.elements
             if e.type == "text" and (e.text or "").strip()]
    title_text = (slide.title or topic).strip()
    subtitle = ""
    for element in sorted(texts, key=lambda e: -(e.size or 0)):
        candidate = " ".join((element.text or "").split())
        if candidate and candidate != title_text and len(candidate) > 25:
            subtitle = candidate[:200]
            break
    if not subtitle:
        subtitle = " ".join((slide.key_text or "").split())[:200]

    # Rasm promptini saqlab qolamiz — u mavzuga moslab yozilgan.
    image = next((e for e in slide.canvas.elements if e.type == "image" and e.prompt), None)
    prompt = image.prompt if image else (
        f"professional photorealistic image representing {topic}, "
        "clean composition, natural lighting, high detail"
    )

    slide.canvas.background = "FFFFFF"
    slide.canvas.elements = [
        # Chap yarmi — to'q panel, sarlavha shu yerda turadi.
        VisualElement(type="rect", x=0.0, y=0.0, w=7.2, h=7.5, fill=primary),
        VisualElement(type="rect", x=0.9, y=2.35, w=1.5, h=0.09, fill=accent),
        VisualElement(type="text", x=0.9, y=2.75, w=5.7, h=2.2,
                      text=title_text, size=34, bold=True,
                      color="FFFFFF", align="left"),
        VisualElement(type="image", x=7.6, y=0.0, w=5.733, h=7.5, prompt=prompt),
    ]
    if subtitle:
        slide.canvas.elements.insert(3, VisualElement(
            type="text", x=0.9, y=5.15, w=5.7, h=1.4,
            text=subtitle, size=14, color="D6DAE2", align="left"))

    log.info("Birinchi slayd mavzu sahifasi qilib qayta qurildi")
    return brief


# ─────────────────────────────────────────── Sarlavha ko'rinishi
#
# Yetkazilgan taqdimotda 11 slaydning 11 tasida ham sarlavha oq rangda,
# lekin oq fon ustida turardi — kontrast 1.00, ya'ni umuman ko'rinmasdi.
# Model to'q ko'k bezak bandini chizib, sarlavhani oq qilardi, lekin uni
# band ichiga qo'ymasdi. Buni promptda so'rash yordam bermadi, shuning
# uchun kafolat shu yerda.

_TITLE_MIN_SIZE = 20.0
_MIN_CONTRAST = 4.5


def _luminance(hex_colour: str) -> float:
    h = (hex_colour or "").lstrip("#")
    if len(h) == 3:
        h = h[0] * 2 + h[1] * 2 + h[2] * 2
    if len(h) != 6:
        return 1.0
    try:
        channels = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    except ValueError:
        return 1.0
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(first: str, second: str) -> float:
    a, b = _luminance(first), _luminance(second)
    high, low = max(a, b), min(a, b)
    return (high + 0.05) / (low + 0.05)


def readable_on(background: str) -> str:
    """Fon ustida o'qiladigan matn rangi."""
    return "1B2A4A" if _luminance(background) > 0.4 else "FFFFFF"


def _titles(slide: Slide) -> list:
    return [
        element for element in slide.canvas.elements
        if element.type == "text" and (element.text or "").strip()
        and element.bold and (element.size or 0) >= _TITLE_MIN_SIZE
    ]


def _panels(slide: Slide) -> list:
    """To'ldirilgan bloklar — sarlavha ular ustida turishi mumkin."""
    return [
        element for element in slide.canvas.elements
        if element.type == "rect" and element.fill
    ]


def _covering_fill(element, panels, background: str) -> str:
    """Element ostidagi KO'RINADIGAN fon rangini aniqlaydi.

    Elementlar ro'yxat tartibida chiziladi, ya'ni keyingisi oldingisining
    ustiga tushadi. Shuning uchun qidiruv teskari tartibda boradi: bosqich
    raqami och kartochka VA uning ustidagi rangli band bilan qoplangan
    bo'lsa, ko'rinadigani — band.
    """
    box = _box(element)
    for panel in reversed(panels):
        if _overlap_share(box, _box(panel)) > 0.6:
            return panel.fill

    best, best_share = background, 0.0
    for panel in reversed(panels):
        share = _overlap_share(box, _box(panel))
        if share > best_share:
            best, best_share = panel.fill, share
    return best if best_share > 0.5 else background


def _host_panel(title, panels, slide: Slide):
    """Sarlavhani sig'dira oladigan BO'SH bezak bandini topadi.

    Eng yaqin panelni olish xato edi: piramida qatori sarlavhaga bandan
    ko'ra yaqinroq bo'lib chiqib, sarlavha kontent ustida qolib ketardi.
    Endi faqat matnsiz panellar ko'riladi va ular orasidan eng yuqoridagisi
    tanlanadi — bezak bandi odatda slayd tepasida turadi.
    """
    tx, ty, tw, th = _box(title)
    candidates = []
    for panel in panels:
        px, py, pw, ph = _box(panel)
        if pw < tw * 0.7 or ph < th + 0.1:
            continue
        if not _panel_is_free(panel, slide):
            continue
        candidates.append((py, panel))
    if not candidates:
        return None
    return min(candidates, key=lambda pair: pair[0])[1]


def _panel_is_free(panel, slide: Slide) -> bool:
    panel_box = _box(panel)
    for element in slide.canvas.elements:
        if element.type != "text" or not (element.text or "").strip():
            continue
        if _overlap_share(_box(element), panel_box) > 0.5:
            return False
    return True


def ensure_title_contrast(brief: Brief) -> Brief:
    """Har slayd sarlavhasi o'qiladigan bo'lishini kafolatlaydi.

    Ikki yo'l bor va arzonrog'i tanlanadi: sarlavhani o'zi uchun chizilgan
    bo'sh bandga ko'chirish, yoki rangini fonga moslash. Birinchisi afzal,
    chunki model bandni ataylab chizgan.
    """
    moved = recoloured = 0
    for slide in brief.slides:
        background = slide.canvas.background or "FFFFFF"
        panels = _panels(slide)
        for title in _titles(slide):
            colour = title.color or "1B2A4A"
            under = _covering_fill(title, panels, background)
            if contrast_ratio(colour, under) >= _MIN_CONTRAST:
                continue

            host = _host_panel(title, panels, slide)
            if host is not None:
                hx, hy, hw, hh = _box(host)
                tw = min(title.w or hw, hw - 0.5)
                title.x = hx + 0.35
                title.w = max(tw, 1.5)
                title.y = hy + max((hh - (title.h or 0.9)) / 2, 0.1)
                title.color = readable_on(host.fill)
                moved += 1
                continue

            title.color = readable_on(under)
            recoloured += 1

    if moved or recoloured:
        log.info("Sarlavha ko'rinishi: %s ta bandga ko'chirildi, %s ta rangi o'zgartirildi",
                 moved, recoloured)
    return brief


def ensure_body_contrast(brief: Brief) -> Brief:
    """Tana matni ham fon bilan qo'shilib ketmasin.

    Yetkazilgan taqdimotda to'q ko'k panel ustida to'q ko'k ro'yxat bor
    edi — butun bir bo'lim ko'rinmasdi.
    """
    fixed = 0
    for slide in brief.slides:
        background = slide.canvas.background or "FFFFFF"
        panels = _panels(slide)
        for element in slide.canvas.elements:
            if element.type != "text" or not (element.text or "").strip():
                continue
            if element.locked:
                continue   # infografika ranglarini o'zi hisoblaydi
            colour = element.color or "1B2A4A"
            under = _covering_fill(element, panels, background)
            if contrast_ratio(colour, under) < 3.0:
                element.color = readable_on(under)
                fixed += 1
    if fixed:
        log.info("Matn kontrasti: %s ta blok rangi tuzatildi", fixed)
    return brief


# ─────────────────────────────────────────── Vizual tuzatish darajalari
#
# Vision faqat "yomon" deb aytsa, yagona chora slaydni qaytadan yozish edi —
# eng qimmat va eng xavfli yo'l, chunki yaxshi qismlar ham yo'qolardi. Endi
# uch daraja bor va har biri o'zidan qimmatrog'iga faqat kerak bo'lganda
# o'tadi.

SLIDE_W = 13.333
SLIDE_H = 7.5
_EDGE = 0.3
# Suzuvchi nuqta xatosi uchun bo'shashish: 5.800000000000001 + 1.4 qiymati
# 7.2 dan katta chiqib, mutlaqo joyiga tushadigan variant rad etilardi.
_TOLERANCE = 0.02
# Sarlavha bezak panelining burchagiga ozgina tegib turishi — dizaynda
# odatiy hol. Faqat matnning sezilarli qismi yopilgandagina suramiz.
_MIN_OVERLAP_SHARE = 0.15

# Matn ustiga tushib qolsa o'qilmay qoladigan elementlar.
_OPAQUE_TYPES = {"image", "chart", "kpi", "circle", "infographic"}


def _box(element) -> tuple:
    width = element.w or element.d or (5.0 if element.type == "text" else 1.0)
    height = element.h or element.d or (1.0 if element.type == "text" else 1.0)
    if element.type == "text" and (element.text or "").strip():
        # E'lon qilingan balandlik — modelning taxmini, o'lchov emas.
        # PowerPoint sig'magan matnni qutidan pastga chiqarib yuboradi,
        # shuning uchun quyidagi blok "bo'sh joy" deb hisoblangan yerga
        # qo'yilar va matn ustma-ust tushardi. Endi haqiqiy balandlik
        # o'lchanadi; kattasi olinadi, ya'ni model ataylab qoldirgan
        # bo'shliq ham saqlanadi.
        height = max(height, infographics.height_of(
            element.text, width, element.size or 14.0))
    return element.x, element.y, width, height


def _overlaps(first: tuple, second: tuple, pad: float = 0.0) -> bool:
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    return (ax < bx + bw - pad and bx < ax + aw - pad
            and ay < by + bh - pad and by < ay + ah - pad)


def _overlap_share(text_box: tuple, blocker_box: tuple) -> float:
    """Matn maydonining qancha ulushi to'suvchi ostida qolganini qaytaradi."""
    tx, ty, tw, th = text_box
    bx, by, bw, bh = blocker_box
    width = min(tx + tw, bx + bw) - max(tx, bx)
    height = min(ty + th, by + bh) - max(ty, by)
    if width <= 0 or height <= 0 or tw <= 0 or th <= 0:
        return 0.0
    return (width * height) / (tw * th)


def _is_opaque(element) -> bool:
    """Matnni yeb qo'yadigan element — rasm, diagramma, ikonka doirasi.

    To'ldirilgan `rect` bu ro'yxatda emas: bezak bandi ham, kartochka ham
    aynan matn ORTIDA turishi uchun chiziladi. Ilgari u ham to'suvchi
    sanalardi va sarlavha o'z bandidan surib chiqarilardi — band bo'sh
    qolib, sarlavha kontent ustiga tushardi. O'qilishini `ensure_title_contrast`
    va `ensure_body_contrast` ta'minlaydi.
    """
    return element.type in _OPAQUE_TYPES


def pull_inside(slide: Slide) -> int:
    """Chegaradan chiqqan elementlarni slayd ichiga tortadi."""
    moved = 0
    for element in slide.canvas.elements:
        if element.locked:
            continue
        x, y, width, height = _box(element)
        width = min(width, SLIDE_W - 2 * _EDGE)
        height = min(height, SLIDE_H - 2 * _EDGE)
        new_x = min(max(x, _EDGE), SLIDE_W - _EDGE - width)
        new_y = min(max(y, _EDGE), SLIDE_H - _EDGE - height)
        if abs(new_x - x) > 0.01 or abs(new_y - y) > 0.01:
            element.x, element.y = new_x, new_y
            if element.w:
                element.w = width
            if element.h:
                element.h = height
            moved += 1
    return moved


def lift_text_off_blockers(slide: Slide) -> int:
    """Matnni rasm, diagramma yoki to'ldirilgan blok ustidan olib ketadi.

    `fix_text_overlaps` faqat matnni matn bilan solishtiradi, shuning uchun
    rasm ustiga tushgan sarlavhani ko'rmasdi — vision aynan shuni topardi.
    """
    texts = [e for e in slide.canvas.elements
             if e.type == "text" and e.text and not e.locked]
    blockers = [e for e in slide.canvas.elements if _is_opaque(e) and not e.locked]
    if not texts or not blockers:
        return 0

    moved = 0
    for text in texts:
        for blocker in blockers:
            text_box = _box(text)
            blocker_box = _box(blocker)
            if not _overlaps(text_box, blocker_box, pad=0.06):
                continue
            if _overlap_share(text_box, blocker_box) < _MIN_OVERLAP_SHARE:
                continue
            is_title = bool(text.bold) and (text.size or 0) >= _TITLE_MIN_SIZE
            if _shift_clear(text, blocker_box, prefer_up=is_title):
                moved += 1
                break
    return moved


def _shift_clear(text, blocker: tuple, prefer_up: bool = False) -> bool:
    """Matnni to'suvchi elementdan chetga suradi — eng kam siljish tomoniga.

    `prefer_up` sarlavha uchun: uni pastga surish slaydni boshsiz qoldiradi,
    shuning uchun avval yuqoriga (va yon tomonlarga) qaraladi va pastga
    tushirish faqat boshqa iloj qolmaganda bo'ladi.
    """
    tx, ty, tw, th = _box(text)
    bx, by, bw, bh = blocker

    candidates = [
        ("chapga", bx - tw - 0.12, ty),
        ("o'ngga", bx + bw + 0.12, ty),
        ("yuqoriga", tx, by - th - 0.12),
        ("pastga", tx, by + bh + 0.12),
    ]
    best = None
    for name, new_x, new_y in candidates:
        if new_x < _EDGE - _TOLERANCE or new_x + tw > SLIDE_W - _EDGE + _TOLERANCE:
            continue
        if new_y < _EDGE - _TOLERANCE or new_y + th > SLIDE_H - _EDGE + _TOLERANCE:
            continue
        distance = abs(new_x - tx) + abs(new_y - ty)
        # Sarlavha uchun pastga tushish eng oxirgi chora.
        rank = 1 if (prefer_up and name == "pastga") else 0
        if best is None or (rank, distance) < (best[0], best[1]):
            best = (rank, distance, new_x, new_y)

    if best is None:
        return False
    text.x, text.y = best[2], best[3]
    return True


def repair_regions(slide: Slide, regions: list) -> int:
    """1-daraja: vision belgilagan joylarni kod bilan tuzatadi.

    Model chaqirilmaydi, shuning uchun bu tuzatish bepul va bir zumda.
    """
    kinds = {region.get("kind") for region in (regions or [])}
    changed = 0

    if "offscreen" in kinds or not kinds:
        changed += pull_inside(slide)

    if "overlap" in kinds or "clutter" in kinds or not kinds:
        changed += lift_text_off_blockers(slide)
        before = [(e.x, e.y) for e in slide.canvas.elements]
        fix_slide_overlaps(slide)
        changed += sum(
            1 for old, element in zip(before, slide.canvas.elements)
            if abs(old[0] - element.x) > 0.01 or abs(old[1] - element.y) > 0.01
        )

    # Ustma-ustlik tuzatuvchisi elementni pastga surib chegaradan chiqarishi
    # mumkin, shuning uchun oxirida yana ichkariga tortamiz.
    changed += pull_inside(slide)
    return changed


def simplify_slide(slide: Slide, remove_type: str | None) -> str:
    """2-daraja: slayddan bitta ortiqcha narsani olib tashlaydi.

    Butun slaydni qayta yozishdan arzon va xavfsiz: qolgan mazmun joyida
    qoladi, faqat xalaqit berayotgani ketadi.
    """
    elements = slide.canvas.elements

    if remove_type:
        kept = [e for e in elements if e.type != remove_type]
        if len(kept) < len(elements) and any(e.type == "text" for e in kept):
            slide.canvas.elements = kept
            return f"'{remove_type}' olib tashlandi"

    # Model nimani olib tashlashni aytmagan: eng ko'p joy egallagan, lekin
    # mazmun tashimaydigan bezakni tanlaymiz.
    decorations = [e for e in elements
                   if e.type in ("circle", "rect") and not e.locked]
    if decorations:
        biggest = max(decorations, key=lambda e: (e.w or e.d or 0) * (e.h or e.d or 0))
        elements.remove(biggest)
        return "bezak bloki olib tashlandi"

    # Bezak yo'q — eng uzun matnni qisqartiramiz.
    texts = [e for e in elements if e.type == "text" and e.text and not e.locked]
    if texts:
        longest = max(texts, key=lambda e: len(e.text or ""))
        if len(longest.text) > 120:
            longest.text = _trim_sentence(longest.text, int(len(longest.text) * 0.6))
            return "eng uzun matn qisqartirildi"

    charts = [e for e in elements if e.type in ("chart", "image")]
    if charts and sum(1 for e in elements if e.type == "text") >= 1:
        elements.remove(charts[-1])
        return f"'{charts[-1].type}' olib tashlandi"

    return ""


def _trim_sentence(text: str, limit: int) -> str:
    """Matnni oxirgi tugagan jumlada kesadi."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for mark in (". ", "! ", "? ", "\n"):
        index = cut.rfind(mark)
        if index > limit * 0.4:
            return cut[:index + 1].strip()
    space = cut.rfind(" ")
    return (cut[:space] if space > limit * 0.5 else cut).rstrip(" ,;:") + "."


# ─────────────────────────────────────────── Vizual QA

def run_visual_qa_and_fix(
    pptx_path: str, brief: Brief, topic: str, language: str = "uz"
) -> str:
    """Slaydlarni rasmga aylantirib, vision model tekshiradi va TUZATADI.

    Vision faqat baho bermaydi — u muammoli joyni belgilaydi va tuzatish
    darajasini aytadi. Daraja qanchalik past bo'lsa, tuzatish shunchalik
    arzon va xavfsiz:

      1 — joyini surish (kod hal qiladi, model chaqirilmaydi)
      2 — bitta ortiqcha elementni olib tashlash
      3 — slaydni soddaroq qilib qayta yozish

    Arzonrog'i yordam bermasa, keyingi raundda daraja ko'tariladi. Butun
    taqdimot emas, faqat muammoli slayd qayta yoziladi.
    """
    if not config.VISUAL_QA_ENABLED:
        log.info("Vizual QA o'chirilgan (PREMIUM_VISUAL_QA=0)")
        return pptx_path

    current_path = pptx_path
    current_brief = brief
    # Qaysi slaydga qaysi daraja qo'llanganini eslab qolamiz: bir xil
    # muammo takrorlansa, o'sha darajada tiqilib qolmasdan yuqoriga chiqamiz.
    applied: dict[int, int] = {}
    # Birinchi raundda hamma slayd tekshiriladi; keyingilarida faqat
    # tuzatilganlar — o'tgan slaydni qayta so'rash bekorga pul sarflashdir.
    to_check: set | None = None

    for round_no in range(config.MAX_QA_RETRIES):
        try:
            images = qa.pptx_to_images(current_path)
        except Exception as e:
            log.error("QA rasmga aylantirishda xato (LibreOffice/poppler o'rnatilganmi?): %s", e)
            break

        if not images or len(images) != len(current_brief.slides):
            if images:
                log.warning("QA rasm soni slayd soniga mos kelmadi (%s vs %s)",
                            len(images), len(current_brief.slides))
                qa.discard_images(images)
            else:
                log.warning("QA slaydlarni rasmga aylantira olmadi — serverda "
                            "LibreOffice o'rnatilganini tekshiring")
            # Ko'z bilan tekshirib bo'lmasa ham, geometriyani kod tekshira
            # oladi: ustma-ustlik va chetdan chiqish shu yerda hal bo'ladi.
            return _geometry_only_pass(current_brief, current_path)

        repaired = set()
        try:
            repaired = _inspect_and_repair(images, current_brief, topic, language,
                                           applied, to_check, round_no)
        finally:
            # Skrinshotlar faqat shu raund uchun kerak edi.
            qa.discard_images(images)

        to_check = repaired
        if not repaired:
            log.info("Vizual QA: barcha slayd qabul qilindi (raund %s)", round_no + 1)
            break

        # Tuzatishdan keyin brief ham, PPTX ham yangilanadi. Ayniqsa oxirgi
        # raundda render qilmaslik eski faylni qaytarib yuborardi.
        current_brief = expand_infographics(current_brief)
        current_brief = fix_text_overlaps(current_brief)
        current_brief = keep_text_inside_panels(current_brief)
        previous_path = current_path
        current_path = build_presentation(current_brief)
        # Almashtirilgan oraliq fayl kerak emas; asl fayl chaqiruvchiniki,
        # shuning uchun unga tegilmaydi.
        if previous_path != pptx_path:
            try:
                os.remove(previous_path)
            except OSError:
                pass

    return current_path


def _inspect_and_repair(images, current_brief, topic, language,
                        applied: dict, to_check, round_no: int) -> set:
    """Bir raundni yuradi: har slaydni tekshiradi va tuzatadi."""
    repaired: set = set()
    for slide_pos, (img_path, slide) in enumerate(zip(images, current_brief.slides)):
            if to_check is not None and slide.index not in to_check:
                continue
            context = (
                f"role={slide.role}, title={slide.title}, "
                f"elements={len(slide.canvas.elements)}"
            )
            result = qa.check_slide_image(img_path, context)
            level = int(result.get("level", qa.LEVEL_OK))
            if level == qa.LEVEL_OK:
                continue

            # Shu slaydda o'sha daraja allaqachon sinalgan bo'lsa, keyingisiga.
            level = max(level, applied.get(slide.index, 0) + 1)
            if level > qa.LEVEL_REBUILD:
                log.warning("Slayd %s: uchala daraja ham yordam bermadi, qoldirildi",
                            slide.index)
                continue

            issue = result.get("issue") or "aniqlanmagan muammo"
            log.info("Vizual QA (raund %s, slayd %s): %s-daraja | %s",
                     round_no + 1, slide.index, level, issue[:120])

            try:
                done = _apply_level(current_brief, slide_pos, level, result,
                                    topic, language)
            except Exception as e:
                log.error("Tuzatishda xato (slayd %s, %s-daraja): %s",
                          slide.index, level, e)
                continue

            if done:
                applied[slide.index] = level
                repaired.add(slide.index)
                log.info("Slayd %s tuzatildi (%s-daraja): %s", slide.index, level, done)
    return repaired


def _geometry_only_pass(brief: Brief, current_path: str) -> str:
    """Vision ishlamaganda ham 1-darajali tuzatishni qo'llaydi.

    Rasterizatsiya serverga bog'liq va har doim ham ishlamaydi. Shunday
    holatda QA ni butunlay tashlab ketish mijozga eng ko'p uchraydigan
    nuqsonlar bilan hujjat berish demakdir, holbuki ularning aksari
    koordinatalardan ham ko'rinadi.
    """
    repaired = 0
    for slide in brief.slides:
        repaired += repair_regions(slide, [])
    if not repaired:
        return current_path

    log.info("Vizual QA ko'zsiz o'tdi: %s ta element joyiga qo'yildi", repaired)
    brief = expand_infographics(brief)
    brief = keep_text_inside_panels(brief)
    return build_presentation(brief)


def _apply_level(brief: Brief, slide_pos: int, level: int, result: dict,
                 topic: str, language: str) -> str:
    """Berilgan darajadagi tuzatishni qo'llaydi va nima qilinganini qaytaradi."""
    slide = brief.slides[slide_pos]

    if level == qa.LEVEL_NUDGE:
        moved = repair_regions(slide, result.get("regions") or [])
        return f"{moved} ta element surildi" if moved else ""

    if level == qa.LEVEL_SIMPLIFY:
        what = simplify_slide(slide, result.get("remove"))
        # Element olib tashlanishi joylashuvni o'zgartiradi, shuning uchun
        # qolganlarini yana joyiga qo'yamiz.
        repair_regions(slide, [])
        return what

    # 3-daraja: faqat shu slayd qayta yoziladi, boshqalariga tegilmaydi.
    instruction = (
        f"Bu slaydda quyidagi muammo bor: {result.get('issue') or 'bloklar bir-biriga xalaqit beradi'}. "
        "Slaydni SODDAROQ qilib qayta loyihala: elementlar soni kamaysin, "
        "har blok o'z joyida tursin, hech biri ikkinchisining ustiga chiqmasin "
        "va hech nima slayd chetidan chiqmasin. Mazmunni saqlab qol, faqat "
        "joylashuvni va blok sonini soddalashtir."
    )
    before = slide.model_dump()
    rebuilt = _redesign(slide, topic, language, instruction)
    brief.slides[slide_pos] = rebuilt
    moved = repair_regions(rebuilt, [])

    if rebuilt.model_dump() == before:
        # Model chaqiruvi yiqildi yoki hech nima o'zgartirmadi. Buni
        # "tuzatildi" deb ko'rsatish yolg'on bo'lardi.
        return f"qayta loyihalash ishlamadi, {moved} ta element surildi" if moved else ""
    return "slayd qayta loyihalandi"
