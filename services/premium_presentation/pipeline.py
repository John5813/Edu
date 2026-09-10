import logging

from pydantic import ValidationError

from services.project_work import variety

from . import config, infographics, llm_client, qa
from .models import Brief, Slide, ROLE_ORDER, VisualElement, grounding_check
from .renderer import build_presentation

log = logging.getLogger("pipeline")


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

    return True, ""


def ensure_chart_explanations(brief: Brief) -> Brief:
    """Diagramma izohsiz qolmasin, lekin AI yozgan izohni majburan almashtirmasin."""
    for slide in brief.slides:
        for element in slide.canvas.elements:
            if element.type != "chart" or (element.caption and element.caption.strip()):
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
    return brief


def canvas_validation_and_fix(
    brief: Brief, topic: str, max_attempts: int = 2, language: str = "uz"
) -> Brief:
    """Har slaydni tekshiradi, muammoli slaydlarni qayta loyihalaydi."""
    # Avval matn o'lchamlari va ustma-ustni tuzatamiz
    brief = ensure_visuals(brief, topic, language)
    brief = spread_chart_types(brief, topic)
    brief = expand_infographics(brief)
    brief = ensure_icons(brief)
    brief = fix_text_overlaps(brief)
    brief = enforce_min_text_size(brief)
    brief = ensure_chart_explanations(brief)

    for attempt in range(max_attempts):
        any_issue = False
        for i, slide in enumerate(brief.slides):
            ok, problem = canvas_check(slide)
            if not ok:
                any_issue = True
                log.warning("Kanvas muammo (slayd %s, urinish %s): %s", slide.index, attempt + 1, problem)
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
        fix_slide_overlaps(slide)
    return brief


def fix_slide_overlaps(slide: Slide) -> Slide:
    """Bitta slayd ichidagi matn bloklarini ustma-ustlikdan tozalaydi.

    Alohida funksiya, chunki vizual QA aynan bitta slaydni tuzatadi —
    uni `Brief` ichiga o'rash rol tartibi validatorini buzardi.
    """
    slide_w = 13.333
    slide_h = 7.5
    edge = 0.3

    if True:
        # locked — infografika presetlari hisoblab qo'ygan matnlar. Ularning
        # o'rni kartochkasiga bog'liq, mustaqil surilsa kompozitsiya buziladi.
        text_els = [e for e in slide.canvas.elements
                    if e.type == "text" and not e.locked]

        # Renderer elementlarni slayd ichiga qistiradi. QA esa renderdan oldingi
        # koordinatalar bilan ishlaydi, shuning uchun avval bir xil koordinata
        # tizimiga keltiramiz.
        for el in text_els:
            el_w = el.w or 5.0
            el_h = el.h or 1.0
            el.w = min(max(el_w, 0.5), slide_w - edge * 2)
            el.h = min(max(el_h, 0.2), slide_h - edge * 2)
            el.x = min(max(el.x, edge), slide_w - edge - el.w)
            el.y = min(max(el.y, edge), slide_h - edge - el.h)

        changed = True
        max_iter = max(10, len(text_els) * len(text_els))
        while changed and max_iter > 0:
            changed = False
            max_iter -= 1
            for i in range(len(text_els)):
                for j in range(i + 1, len(text_els)):
                    el1, el2 = text_els[i], text_els[j]
                    el1_w = el1.w or 5.0
                    el1_h = el1.h or 1.0
                    el2_w = el2.w or 5.0
                    el2_h = el2.h or 1.0

                    # Gorizontal va vertikal kesishishni tekshir
                    h_overlap = (el1.x < el2.x + el2_w) and (el2.x < el1.x + el1_w)
                    v_overlap = (el1.y < el2.y + el2_h) and (el2.y < el1.y + el1_h)

                    if h_overlap and v_overlap:
                        # Pastdagini biroz pastga tushir. Pastda joy qolmasa,
                        # yuqoridagi blokni ko'taramiz; eski kod bu holatda
                        # hech narsa qilmasdan chiqib ketardi.
                        if el1.y <= el2.y:
                            moving, anchor = el2, el1
                        else:
                            moving, anchor = el1, el2

                        moving_h = moving.h or 1.0
                        anchor_h = anchor.h or 1.0
                        below = anchor.y + anchor_h + 0.1
                        max_y = slide_h - edge - moving_h
                        if below <= max_y:
                            new_y = below
                        else:
                            above = anchor.y - moving_h - 0.1
                            new_y = max(edge, above)

                        if abs(moving.y - new_y) > 0.001:
                            moving.y = new_y
                            changed = True

        # A final clamp is important after several cascading moves.
        for el in text_els:
            el.x = min(max(el.x, edge), slide_w - edge - (el.w or 5.0))
            el.y = min(max(el.y, edge), slide_h - edge - (el.h or 1.0))
    return slide


def enforce_min_text_size(brief: Brief, min_body_pt: float = 13.0) -> Brief:
    """Sarlavha bo'lmagan matn elementlari uchun minimal 13pt ta'minlaydi."""
    for slide in brief.slides:
        for el in slide.canvas.elements:
            if el.type == "text" and not el.bold and not el.locked:
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


def generate_brief_chunked(topic: str, target_count: int, progress_cb=None, level: int = 2,
                           preferences: str = "", language: str = "uz") -> Brief:
    """Katta taqdimotni har 5 varoqlik bo'laklarda generatsiya qiladi.
    Har bo'lak avvalgi bo'lak xulosasi bilan mantiqiy bog'liq bo'ladi.
    """
    CHUNK_SIZE = 5

    if target_count <= 7:
        # Kichik taqdimot — yagona prompt
        return generate_brief_with_validation(topic, target_count, level=level,
                                              preferences=preferences, language=language)

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
                                   preferences: str = "", language: str = "uz") -> Brief:
    """LLM'dan JSON so'raydi, pydantic orqali qat'iy tekshiradi. Silent fallback YO'Q."""
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            raw = llm_client.generate_brief(topic, slide_count, level=level,
                                            preferences=preferences, language=language)
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

MIN_IMAGES = 2
MIN_CHARTS = 2
MIN_INFOGRAPHICS = 2


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
    """
    if not brief.slides:
        return brief

    # 1. Birinchi slaydda rasm — mijoz uchun majburiy talab.
    if not _has(brief.slides[0], "image"):
        brief.slides[0] = _redesign(
            brief.slides[0], topic, language,
            "Bu slaydda rasm yo'q. Chap yarmiga matn, o'ng yarmiga (x=7.0, w=5.9, "
            "y=0.9, h=5.7) image elementi qo'y. Rasm prompti ingliz tilida, "
            "mavzuni ko'rsatuvchi, matnsiz tasvir bo'lsin.",
        )
        if not _has(brief.slides[0], "image"):
            _force_image(brief.slides[0], topic)

    # 2. Umumiy minimum — qaysi slaydga qo'shishni mazmuniga qarab tanlaymiz.
    for element_type, minimum, instruction in (
        ("image", MIN_IMAGES,
         "Bu slaydga image elementi qo'sh (matnni siqib, o'ng yoki past qismga "
         "joyla). Rasm prompti ingliz tilida, matnsiz tasvir."),
        ("chart", MIN_CHARTS,
         "Bu slaydga chart elementi qo'sh — mavzuga oid haqiqiy raqamlar bilan "
         "(sanalar, ulushlar, bosqichlar, taqqoslash). Kategoriya va qiymatlar "
         "o'ylab topilgan emas, mavzuga tegishli bo'lsin. caption ni to'ldir."),
        ("infographic", MIN_INFOGRAPHICS,
         "Bu slaydning ro'yxat yoki bosqichli matnini infographic elementiga "
         "aylantir: {\"type\":\"infographic\",\"x\":0.6,\"y\":1.9,\"w\":12.1,"
         "\"h\":4.4,\"preset\":\"cards|steps|timeline|cycle|pyramid\","
         "\"items\":[{\"title\":\"...\",\"text\":\"...\",\"icon\":\"<ikonka nomi>\"}]}. "
         "3-5 band bo'lsin, har bandda icon nomi bo'lsin. Eski matn elementlarini olib tashla."),
    ):
        for slide_index in _candidates(brief, element_type):
            if _count(brief, element_type) >= minimum:
                break
            brief.slides[slide_index] = _redesign(
                brief.slides[slide_index], topic, language, instruction
            )

    log.info("Vizual kafolat: %s rasm, %s diagramma, %s infografika",
             _count(brief, "image"), _count(brief, "chart"), _count(brief, "infographic"))
    return brief


def _candidates(brief: Brief, element_type: str) -> list:
    """Qaysi slaydlarga qo'shish mumkin — o'rtadagi, hali bandi bo'lmaganlari."""
    middle = range(1, max(len(brief.slides) - 1, 1))
    return [i for i in middle if not _has(brief.slides[i], element_type)]


def _redesign(slide: Slide, topic: str, language: str, instruction: str) -> Slide:
    try:
        fixed = llm_client.regenerate_slide(topic, slide.model_dump(), instruction, language=language)
        merged = {**slide.model_dump(), **fixed}
        return Slide.model_validate(merged)
    except Exception as e:
        log.error("Slaydni qayta loyihalashda xato (slayd %s): %s", slide.index, e)
        return slide


def _force_image(slide: Slide, topic: str) -> None:
    """Oxirgi chora: matnni chap yarmiga siqib, o'ngga rasm qo'yadi."""
    for element in slide.canvas.elements:
        if element.type == "text":
            element.w = min(element.w or 6.0, 6.4)
            element.x = min(element.x, 0.7)
    slide.canvas.elements.append(
        VisualElement(
            type="image", x=7.1, y=0.9, w=5.8, h=5.7,
            prompt=(
                f"professional photorealistic image representing {topic}, "
                "clean composition, natural lighting, high detail"
            ),
        )
    )
    log.info("Birinchi slaydga rasm majburan qo'yildi")

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

# Matn ustiga tushib qolsa o'qilmay qoladigan elementlar. `rect` faqat
# to'ldirilgan bo'lsa hisobga olinadi — fonsiz to'rtburchak xalaqit bermaydi.
_OPAQUE_TYPES = {"image", "chart", "kpi", "circle", "infographic"}


def _box(element) -> tuple:
    width = element.w or element.d or (5.0 if element.type == "text" else 1.0)
    height = element.h or element.d or (1.0 if element.type == "text" else 1.0)
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
    if element.type in _OPAQUE_TYPES:
        return True
    return element.type == "rect" and bool(element.fill)


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
            if _shift_clear(text, blocker_box):
                moved += 1
                break
    return moved


def _shift_clear(text, blocker: tuple) -> bool:
    """Matnni to'suvchi elementdan chetga suradi — eng kam siljish tomoniga."""
    tx, ty, tw, th = _box(text)
    bx, by, bw, bh = blocker

    candidates = [
        ("chapga", bx - tw - 0.12, ty),
        ("o'ngga", bx + bw + 0.12, ty),
        ("yuqoriga", tx, by - th - 0.12),
        ("pastga", tx, by + bh + 0.12),
    ]
    best = None
    for _, new_x, new_y in candidates:
        if new_x < _EDGE - _TOLERANCE or new_x + tw > SLIDE_W - _EDGE + _TOLERANCE:
            continue
        if new_y < _EDGE - _TOLERANCE or new_y + th > SLIDE_H - _EDGE + _TOLERANCE:
            continue
        distance = abs(new_x - tx) + abs(new_y - ty)
        if best is None or distance < best[0]:
            best = (distance, new_x, new_y)

    if best is None:
        return False
    text.x, text.y = best[1], best[2]
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
            else:
                log.warning("QA slaydlarni rasmga aylantira olmadi — serverda "
                            "LibreOffice o'rnatilganini tekshiring")
            # Ko'z bilan tekshirib bo'lmasa ham, geometriyani kod tekshira
            # oladi: ustma-ustlik va chetdan chiqish shu yerda hal bo'ladi.
            return _geometry_only_pass(current_brief, current_path)

        repaired = set()
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

        to_check = repaired
        if not repaired:
            log.info("Vizual QA: barcha slayd qabul qilindi (raund %s)", round_no + 1)
            break

        # Tuzatishdan keyin brief ham, PPTX ham yangilanadi. Ayniqsa oxirgi
        # raundda render qilmaslik eski faylni qaytarib yuborardi.
        current_brief = expand_infographics(current_brief)
        current_brief = fix_text_overlaps(current_brief)
        current_path = build_presentation(current_brief)

    return current_path


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
