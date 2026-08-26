import logging

from pydantic import ValidationError

from . import config, llm_client, qa
from .models import Brief, Slide, ROLE_ORDER, grounding_check
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

    return brief


# ─────────────────────────────────────────── Matn sifatini tuzatish (programmatik)

def fix_text_overlaps(brief: Brief) -> Brief:
    """Slayddagi matn bloklari bir-birining ustiga chiqmasligini ta'minlaydi."""
    slide_w = 13.333
    slide_h = 7.5
    edge = 0.3

    for slide in brief.slides:
        text_els = [e for e in slide.canvas.elements if e.type == "text"]

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
    return brief


def enforce_min_text_size(brief: Brief, min_body_pt: float = 13.0) -> Brief:
    """Sarlavha bo'lmagan matn elementlari uchun minimal 13pt ta'minlaydi."""
    for slide in brief.slides:
        for el in slide.canvas.elements:
            if el.type == "text" and not el.bold:
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


# ─────────────────────────────────────────── Vizual QA

def run_visual_qa_and_fix(
    pptx_path: str, brief: Brief, topic: str, language: str = "uz"
) -> str:
    """Slaydlarni rasmga aylantirib, vision model tekshiradi.
    Muammo topilsa tegishli slaydni qayta loyihalaydi yoki elementni olib tashlaydi."""
    current_path = pptx_path
    current_brief = brief

    for round_no in range(config.MAX_QA_RETRIES):
        try:
            images = qa.pptx_to_images(current_path)
        except Exception as e:
            log.error("QA rasmga aylantirishda xato (LibreOffice/poppler o'rnatilganmi?): %s", e)
            break

        if not images or len(images) != len(current_brief.slides):
            log.warning("QA rasm soni slayd soniga mos kelmadi (%s vs %s), QA bekor",
                        len(images or []), len(current_brief.slides))
            break

        any_issue = False
        for slide_pos, (img_path, slide) in enumerate(zip(images, current_brief.slides)):
            context = (
                f"role={slide.role}, title={slide.title}, "
                f"elements={len(slide.canvas.elements)}"
            )
            result = qa.check_slide_image(img_path, context)
            if not result.get("ok", True):
                any_issue = True
                issue = result.get("issue", "aniqlanmagan muammo")
                remove_type = result.get("remove")
                log.info("Vizual QA muammo (slayd %s): %s | remove=%s",
                         slide.index, issue, remove_type)
                try:
                    if remove_type:
                        slide_data = slide.model_dump()
                        before = len(slide_data["canvas"]["elements"])
                        slide_data["canvas"]["elements"] = [
                            e for e in slide_data["canvas"]["elements"]
                            if e.get("type") != remove_type
                        ]
                        removed = before - len(slide_data["canvas"]["elements"])
                        log.info("QA: %d ta '%s' olib tashlandi (slayd %s)",
                                 removed, remove_type, slide.index)
                        merged = {**slide.model_dump(), **slide_data}
                        current_brief.slides[slide_pos] = Slide.model_validate(merged)
                    else:
                        fixed = llm_client.regenerate_slide(
                            topic, slide.model_dump(), issue, language=language
                        )
                        merged = {**slide.model_dump(), **fixed}
                        current_brief.slides[slide_pos] = Slide.model_validate(merged)
                        ok2, problem2 = canvas_check(current_brief.slides[slide_pos])
                        if not ok2:
                            log.warning("Vizual tuzatishdan keyin kanvas muammo: %s", problem2)
                except Exception as e:
                    log.error("Slayd qayta loyihalashda xato: %s", e)

        if not any_issue:
            log.info("Vizual QA: barcha slayd qabul qilindi (round %s)", round_no + 1)
            break

        # Har qanday QA tuzatishidan keyin brief ham, PPTX ham yangilanadi.
        # Ayniqsa oxirgi raundda render qilmaslik eski faylni qaytarib yuborardi.
        current_brief = fix_text_overlaps(current_brief)
        current_path = build_presentation(current_brief)

    return current_path
