"""Infografika presetlari — kompozitsiyani kod hisoblaydi, AI faqat mazmun beradi.

AI dan har bir doiraning koordinatasini so'rash ishonchsiz: bloklar qiyshiq
chiqadi, ustma-ust tushadi, ranglar to'qnashadi. Shu sababli bu yerda beshta
tayyor kompozitsiya bor. AI `{"type":"infographic","preset":"cards","items":[...]}`
yuboradi, qolgan hamma narsani — koordinata, rang, bog'lovchi chiziq, raqam —
shu modul hisoblaydi.
"""
import logging
import math

from .models import VisualElement

log = logging.getLogger("infographics")

# dataviz validatoridan o'tgan kategorik palitra (light rejim, qo'shni juftlar):
# eng yomon CVD ΔE 9.1, normal ko'rish ΔE 19.6 — ikkalasi ham chegaradan yuqori.
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#4a3aa7"]

SLIDE_W = 13.333
SLIDE_H = 7.5

MIN_BODY_PT = 11.0
MAX_ITEMS = 6

# Har preset nechta bandni ko'tara oladi. Halqa uchtadan kam va to'rttadan
# ko'p bandni ko'tara olmaydi (yassi ellipsda bandlar bir-birining ustiga
# tushadi), piramida esa beshtadan ko'pini.
PRESET_FITS = {
    "cards": (2, 6),
    "steps": (2, 6),
    "timeline": (2, 6),
    "cycle": (3, 4),
    "pyramid": (2, 5),
}


def fits(preset: str, items: int) -> bool:
    low, high = PRESET_FITS.get(preset, (2, MAX_ITEMS))
    return low <= items <= high


def expand(el: VisualElement, theme=None) -> list[VisualElement]:
    """Infografika elementini ibtidoiy elementlar ro'yxatiga aylantiradi."""
    items = [i for i in (el.items or []) if (i.title or i.text or i.value)][:MAX_ITEMS]
    if len(items) < 2:
        log.warning("Infografika bandlari yetarli emas (%s ta) — o'tkazib yuborildi", len(items))
        return []

    x = _clamp(el.x, 0.3, SLIDE_W - 2.0)
    y = _clamp(el.y, 0.3, SLIDE_H - 1.5)
    w = _clamp(el.w or (SLIDE_W - 2 * x), 3.0, SLIDE_W - x - 0.3)
    h = _clamp(el.h or 4.2, 1.5, SLIDE_H - y - 0.25)

    preset = el.preset or "cards"
    # Halqa 4 tadan ortiq bandni ko'tara olmaydi: slayd keng va past bo'lgani
    # uchun ellips yassilashib, yon bandlar bir-birining ustiga tushadi.
    if preset == "cycle" and len(items) > 4:
        log.info("cycle preseti %s band uchun tor — cards ga o'tkazildi", len(items))
        preset = "cards"

    builder = {
        "cards": _cards,
        "steps": _steps,
        "timeline": _timeline,
        "cycle": _cycle,
        "pyramid": _pyramid,
    }.get(preset, _cards)

    colors = _colors(el, theme)
    low = PRESET_FITS.get(preset, (2, MAX_ITEMS))[0]

    def _build(chosen):
        out = builder(chosen, x, y, w, h, colors)
        if not out and builder is not _cards:
            # Preset bu mazmun uchun geometrik jihatdan imkonsiz — har doim
            # ishlaydigan kartochkalarga o'tamiz, bo'sh slayd qoldirmaymiz.
            log.info("'%s' preseti bu mazmunga sig'madi — cards ishlatildi", preset)
            out = _cards(chosen, x, y, w, h, colors)
        return out

    try:
        # Bandlar ko'p yoki blok past bo'lsa matn "…" bilan kesilardi — mijoz
        # kesilgan gapni haqli ravishda kamchilik deb biladi. Endi kesilish
        # bo'lsa mazmun bosqichma-bosqich siyraklashtiriladi, lekin hech
        # qachon so'z o'rtasidan kesilmaydi:
        #   1) hamma band, to'liq matn
        #   2) kamroq band, to'liq matn  — to'rtta to'liq kartochka beshta
        #      chala kartochkadan yaxshiroq
        #   3) hamma band, faqat sarlavhalar — izoh yo'qoladi, lekin qolgani
        #      butun bo'ladi
        #   4) kamroq band, faqat sarlavhalar
        out = None
        for titles_only in (False, True):
            source = items if not titles_only else [_without_text(i) for i in items]
            for count in range(len(source), max(low, 2) - 1, -1):
                candidate = _build(source[:count])
                if out is None:
                    out = candidate
                if candidate and not _is_truncated(candidate, source[:count]):
                    if titles_only or count < len(items):
                        log.info("Infografika sig'madi — %s band%s bilan qurildi",
                                 count, ", izohsiz" if titles_only else "")
                    out = candidate
                    break
            else:
                continue
            break
    except Exception as exc:
        log.error("Infografika qurishda xato (preset=%s): %s", el.preset, exc)
        return []
    if not out:
        return []

    if _is_truncated(out, items):
        # Hech bir ko'rinishda sig'madi. Kesilgan gap qoldirgandan ko'ra
        # oddiy ro'yxat: u tabiiy o'raladi va shrifti joyga moslashadi.
        log.info("Infografika bu joyga sig'madi — ro'yxat matniga aylantirildi")
        return _as_list(items, x, y, w, h)

    for e in out:
        e.locked = True
    return out


def _as_list(items, x, y, w, h) -> list[VisualElement]:
    """Bandlarni bitta oddiy ro'yxat blokiga aylantiradi."""
    lines = []
    for item in items:
        head = (item.title or item.value or "").strip()
        body = (item.text or "").strip()
        if head and body:
            lines.append(f"• {head} — {body}")
        elif head or body:
            lines.append(f"• {head or body}")
    if not lines:
        return []
    text = "\n".join(lines)
    size = _fit(text, w, h, start=14.0, minimum=MIN_BODY_PT)
    return [VisualElement(type="text", x=x, y=y, w=w, h=h,
                          text=text, size=size, align="left", color="1B2A4A")]


# ─────────────────────────────────────────────────────── presetlar

def _cards(items, x, y, w, h, colors):
    """Ikonkali kartochkalar qatori — ikonka doirasi kartochka tepasida turadi."""
    n = len(items)
    gap = 0.3 if n <= 4 else 0.2
    col_w = (w - gap * (n - 1)) / n
    icon_d = min(1.15, col_w * 0.62, h * 0.3)
    text_w = col_w - 0.32

    # Kartochka balandligi mazmunga qarab hisoblanadi — aks holda uzun bo'sh
    # quyi qism qoladi va slayd tugallanmagandek ko'rinadi.
    title_box = _uniform_title(items, text_w)
    need = max(_natural_height(item, text_w, title_box=title_box) for item in items)
    card_h = _clamp(icon_d / 2 + 0.24 + need + 0.32, 1.5, h - icon_d / 2)
    top = y + max((h - (icon_d / 2 + card_h)) * 0.35, 0)
    card_y = top + icon_d / 2

    out = []
    for i, item in enumerate(items):
        hue = colors[i % len(colors)]
        col_x = x + i * (col_w + gap)

        out.append(VisualElement(type="rect", x=col_x, y=card_y, w=col_w, h=card_h,
                                 fill=_tint(hue, 0.88), radius=True))
        # rangli tayanch chizig'i — kartochkani hue bilan bog'laydi
        out.append(VisualElement(type="rect", x=col_x, y=card_y + card_h - 0.09,
                                 w=col_w, h=0.09, fill=hue))
        out.extend(_icon_badge(col_x + (col_w - icon_d) / 2, top, icon_d, hue,
                               item.icon, item.title))

        _stack_text(out, item, col_x + 0.16, card_y + icon_d / 2 + 0.24, text_w,
                    card_y + card_h - 0.2, hue, title_box=title_box,
                    surface=_tint(hue, 0.88))
    return out


def _steps(items, x, y, w, h, colors):
    """Raqamlangan bosqichlar — har blokda tartib raqami va ikonka."""
    n = len(items)
    gap = 0.26 if n <= 4 else 0.18
    col_w = (w - gap * (n - 1)) / n
    band_h = min(0.62, h * 0.16)
    icon_d = min(1.0, col_w * 0.5, h * 0.26)
    text_w = col_w - 0.3

    title_box = _uniform_title(items, text_w)
    need = max(_natural_height(item, text_w, skip_value=True, title_box=title_box)
               for item in items)
    card_h = _clamp(band_h + 0.18 + icon_d + 0.2 + need + 0.24, 1.8, h)
    top = y + max((h - card_h) * 0.35, 0)

    out = []
    for i, item in enumerate(items):
        hue = colors[i % len(colors)]
        col_x = x + i * (col_w + gap)

        out.append(VisualElement(type="rect", x=col_x, y=top, w=col_w, h=card_h,
                                 fill=_tint(hue, 0.9)))
        out.append(VisualElement(type="rect", x=col_x, y=top, w=col_w, h=band_h, fill=hue))
        # Quti band balandligidan oshmasin: oshsa, raqam och kartochka
        # ustiga tushib, oq rangda ko'rinmay qolardi.
        out.append(VisualElement(type="text", x=col_x, y=top + band_h * 0.18,
                                 w=col_w, h=band_h * 0.7, align="center",
                                 text=item.value or f"{i + 1:02d}",
                                 size=min(20, band_h * 34), bold=True,
                                 color=_ink(hue)))
        out.extend(_icon_badge(col_x + (col_w - icon_d) / 2, top + band_h + 0.18,
                               icon_d, hue, item.icon, item.title))

        _stack_text(out, item, col_x + 0.15, top + band_h + 0.2 + icon_d + 0.2,
                    text_w, top + card_h - 0.15, hue, skip_value=True,
                    title_box=title_box)
    return out


def _timeline(items, x, y, w, h, colors):
    """Gorizontal vaqt chizig'i — belgilar chiziqda, matn navbatma-navbat yuqori/quyi."""
    n = len(items)
    d = min(0.9, w / (n * 2.2), h * 0.22)
    line_y = y + h / 2
    step = w / n
    half = (h / 2) - d / 2 - 0.26

    block_w_probe = min(step - 0.2, 2.9)
    need = max(_natural_height(item, block_w_probe) for item in items)
    if half < 0.62 or step < 1.2 or need > half:
        # Chiziqning ikki tomonida matnga joy qolmadi — bu quti vaqt chizig'i
        # uchun juda past yoki bandlar juda zich.
        return None

    out = [VisualElement(type="rect", x=x, y=line_y - 0.025, w=w, h=0.05, fill="D6DAE2")]
    for i, item in enumerate(items):
        hue = colors[i % len(colors)]
        cx = x + step * (i + 0.5)
        above = i % 2 == 0

        out.extend(_icon_badge(cx - d / 2, line_y - d / 2, d, hue, item.icon, item.title))

        block_w = min(step - 0.2, 2.9)
        block_x = _clamp(cx - block_w / 2, x, x + w - block_w)
        # Matn blokini chiziqqa yopishtiramiz: yuqoridagilari pastdan, pastdagilari
        # yuqoridan boshlanadi — orada bo'shliq qolmasin.
        content_h = min(_natural_height(item, block_w), half)
        if above:
            block_y = line_y - d / 2 - 0.2 - content_h
        else:
            block_y = line_y + d / 2 + 0.2

        # ikonkani matnga bog'lovchi qisqa poya
        stem_y = (block_y + content_h) if above else (line_y + d / 2)
        out.append(VisualElement(type="rect", x=cx - 0.015, y=stem_y,
                                 w=0.03, h=0.2, fill=_tint(hue, 0.45)))

        _stack_text(out, item, block_x, block_y, block_w, block_y + content_h + 0.05,
                    hue, align="center")
    return out


def _cycle(items, x, y, w, h, colors):
    """Halqa bo'ylab joylashgan ikonkalar — takrorlanadigan jarayon.

    Halqa qat'iy geometrik talab qo'yadi: har band matni o'z ikonkasidan
    tashqariga chiqishi va qo'shni bandga tegmasligi kerak. Slayd keng va past
    bo'lgani uchun bu har doim ham imkonli emas — imkonsiz bo'lsa None qaytadi
    va chaqiruvchi `cards` presetiga o'tadi.
    """
    n = len(items)
    if n < 3:
        return None

    cx = x + w / 2
    cy = y + h / 2
    d = min(0.95, h * 0.22)
    block_w = min(2.7, w / 2 - d - 0.5)
    if block_w < 1.4:
        return None
    text_h = max(_natural_height(item, block_w) for item in items)

    angles = [-math.pi / 2 + (2 * math.pi * i / n) for i in range(n)]
    side = [a for a in angles if abs(math.cos(a)) >= 0.4]
    vertical = [a for a in angles if abs(math.cos(a)) < 0.4]

    # Radiuslar eng chekka bandning talabidan kelib chiqadi.
    rx = w / 2 - d / 2 - 0.16 - block_w
    if side:
        rx = rx / max(abs(math.cos(a)) for a in side)
    ry = h / 2 - d / 2 - 0.16 - text_h
    if vertical:
        ry = ry / max(abs(math.sin(a)) for a in vertical)
    rx = min(rx, w / 2 - d / 2)
    ry = min(ry, h / 2 - d / 2)
    if rx < 0.6 or ry < 0.35:
        return None

    points = [(cx + rx * math.cos(a), cy + ry * math.sin(a)) for a in angles]
    for i in range(n):
        for j in range(i + 1, n):
            gap = math.dist(points[i], points[j])
            if gap < d + 0.12:
                return None

    out = [VisualElement(type="circle", x=cx - rx, y=cy - ry, w=2 * rx, h=2 * ry,
                         fill=None, line="D6DAE2")]
    for i, item in enumerate(items):
        hue = colors[i % len(colors)]
        angle = angles[i]
        ix, iy = points[i]

        out.extend(_icon_badge(ix - d / 2, iy - d / 2, d, hue, item.icon, item.title))

        if abs(math.cos(angle)) >= 0.4:
            on_right = math.cos(angle) > 0
            block_x = ix + d / 2 + 0.16 if on_right else ix - d / 2 - 0.16 - block_w
            block_y = iy - text_h / 2
            align = "left" if on_right else "right"
        else:
            block_x = ix - block_w / 2
            block_y = (iy - d / 2 - 0.16 - text_h if math.sin(angle) < 0
                       else iy + d / 2 + 0.16)
            align = "center"

        block_x = _clamp(block_x, x, x + w - block_w)
        block_y = _clamp(block_y, y, y + h - text_h)
        _stack_text(out, item, block_x, block_y, block_w, block_y + text_h + 0.05,
                    hue, align=align)
    return out


def _pyramid(items, x, y, w, h, colors):
    """Piramida — yuqoridan pastga kengayuvchi qatlamlar, chapda ikonka."""
    n = min(len(items), 5)
    items = items[:n]
    gap = 0.14
    row_h = (h - gap * (n - 1)) / n
    d = min(row_h * 0.66, 0.8)

    out = []
    for i, item in enumerate(items):
        hue = colors[i % len(colors)]
        row_w = w * (0.5 + 0.5 * (i + 1) / n)
        row_x = x + (w - row_w) / 2
        row_y = y + i * (row_h + gap)

        out.append(VisualElement(type="rect", x=row_x, y=row_y, w=row_w, h=row_h,
                                 fill=hue, radius=True))
        out.extend(_icon_badge(row_x + 0.22, row_y + (row_h - d) / 2, d, hue,
                               item.icon, item.title, glyph_only=True))

        text_x = row_x + 0.22 + d + 0.22
        text_w = row_w - (text_x - row_x) - 0.2
        # matn qatorning vertikal markazida tursin — ikonka bilan bir chiziqda
        content_h = min(_natural_height(item, text_w, skip_value=True), row_h - 0.12)
        text_y = row_y + max((row_h - content_h) / 2, 0.06)
        _stack_text(out, item, text_x, text_y, text_w, text_y + content_h + 0.05,
                    hue, on_fill=hue, skip_value=True)
    return out


# ─────────────────────────────────────────────────────── yordamchilar

def _icon_badge(x, y, d, hue, icon_name, fallback_text, glyph_only=False):
    """Rangli doira + ustida ikonka. `glyph_only` — fon allaqachon rangli."""
    glyph_color = _ink(hue)
    pad = d * 0.24
    elements = []
    if not glyph_only:
        elements.append(VisualElement(type="circle", x=x, y=y, d=d, fill=hue))
    elements.append(VisualElement(
        type="icon", x=x + pad, y=y + pad, w=d - 2 * pad, h=d - 2 * pad,
        icon=icon_name, text=fallback_text, color=glyph_color, shape="none",
    ))
    return elements


def _stack_text(out, item, x, y, w, bottom, hue, align="left",
                skip_value=False, on_fill=None, title_box=None, surface="FFFFFF"):
    """Sarlavha va matnni ustma-ust joylaydi, o'lchamni joyga moslab kichraytiradi."""
    cursor = y
    title_color = _ink(on_fill) if on_fill else "1B2A4A"
    body_color = _ink(on_fill) if on_fill else "52514E"

    if not skip_value and item.value and bottom - cursor >= 0.36:
        out.append(VisualElement(type="text", x=x, y=cursor, w=w, h=0.36,
                                 text=item.value, size=VALUE_PT, bold=True,
                                 align=align, color=_readable(hue, surface)))
        cursor += 0.38

    if item.title and bottom - cursor >= 0.24:
        room = min(0.62, bottom - cursor)
        if title_box and title_box[1] <= bottom - cursor:
            size, forced_h = title_box
            room = max(room, forced_h)
        else:
            forced_h = None
            size = _fit(item.title, w, room, start=TITLE_PT, minimum=11.5)
        title = item.title
        max_lines = max(int(room / (size * 1.28 / 72)), 1)
        if _reserved_lines(title, w, size) > max_lines:
            title = _trim_to_lines(title, w, size, max_lines)
        block_h = forced_h or _block_height(
            min(_reserved_lines(title, w, size), max_lines), size)
        out.append(VisualElement(type="text", x=x, y=cursor, w=w, h=block_h,
                                 text=title, size=size, bold=True,
                                 align=align, color=title_color))
        cursor += block_h + 0.08

    if item.text and bottom - cursor >= 0.24:
        available = bottom - cursor
        size = _fit(item.text, w, available, start=BODY_PT, minimum=MIN_BODY_PT)
        text = item.text
        lines = _reserved_lines(text, w, size)
        max_lines = max(int(available / (size * 1.28 / 72)), 1)
        if lines > max_lines:
            text = _trim_to_lines(text, w, size, max_lines)
            lines = min(_reserved_lines(text, w, size), max_lines)
        block_h = _block_height(lines, size)
        out.append(VisualElement(type="text", x=x, y=cursor, w=w, h=block_h,
                                 text=text, size=size, align=align, color=body_color))
        cursor += block_h
    return cursor


TITLE_PT = 14.5
BODY_PT = 12.5
VALUE_PT = 16.0


def _uniform_title(items, w: float) -> tuple[float, float] | None:
    """Barcha bandlar uchun bitta sarlavha o'lchami va balandligini tanlaydi.

    Har kartochka o'z sarlavhasiga qarab o'lchansa, matn tanalari turli
    balandlikda boshlanadi va qator tekis ko'rinmaydi.
    """
    titled = [item for item in items if item.title]
    if not titled:
        return None
    size = min(_fit(item.title, w, 0.62, start=TITLE_PT, minimum=11.5) for item in titled)
    lines = max(_reserved_lines(item.title, w, size) for item in titled)
    return size, _block_height(lines, size)


def _natural_height(item, w: float, skip_value: bool = False, title_box=None) -> float:
    """Band mazmuni cheklovsiz qancha joy egallashini hisoblaydi.

    Kartochka balandligi shu o'lchovdan kelib chiqadi — sobit balandlik uzun
    bo'sh quyi qism qoldirar edi.
    """
    total = 0.0
    if not skip_value and item.value:
        total += 0.38
    if item.title:
        total += (title_box[1] if title_box
                  else _block_height(_reserved_lines(item.title, w, TITLE_PT), TITLE_PT))
        total += 0.08
    if item.text:
        total += _block_height(_reserved_lines(item.text, w, BODY_PT), BODY_PT)
    return total


# O'rtacha belgi eni em ulushida. Calibri ≈ 0.47, Arial ≈ 0.44, DejaVu ≈ 0.51.
# Qiymat eng keng shriftdan ham yuqori olingan: 300 ta tasodifiy holatda
# haqiqiy shrift metrikasiga qarshi sinaldi va matn hech qayerda ajratilgan
# joydan chiqmadi. Kamaytirilsa — matn bloklari bir-biriga tegib ketadi.
_CHAR_EM = 0.58


def _chars_per_line(w_inches: float, size_pt: float) -> int:
    """Berilgan kenglikdagi bitta qatorga sig'adigan belgilar soni."""
    return max(int((w_inches * 72) / (size_pt * _CHAR_EM)), 6)


def _line_count(text: str, w: float, size: float) -> int:
    """Qatorlar sonini haqiqiy o'ralish algoritmi bilan hisoblaydi.

    Belgilarni oddiy bo'lish bilan sanash xato beradi: matn so'z chegarasida
    uziladi, shuning uchun qator oxirida bo'sh joy qoladi. Bu yerda xuddi
    PowerPoint kabi ochko'z (greedy) o'rash simulyatsiya qilinadi.
    """
    budget = _chars_per_line(w, size)
    total = 0
    for paragraph in (text or "").split("\n"):
        words = paragraph.split()
        if not words:
            total += 1
            continue
        current = 0
        for word in words:
            need = len(word) if current == 0 else len(word) + 1
            if current == 0 or current + need <= budget:
                current += need
            else:
                total += 1
                current = len(word)
        total += 1
    return total


def _reserved_lines(text: str, w: float, size: float) -> int:
    """Blok uchun ajratiladigan qator soni — bahodan bitta ko'p.

    Qator sonini belgilar soni bo'yicha baholash aniq emas: haqiqiy shrift
    metrikasi so'zma-so'z farq qiladi va bir qatorlik xato qo'shni blokka
    tegib ketishga olib keladi. Shu sababli o'ralgan matnga bitta zaxira
    qator ajratiladi — bo'sh joy ustma-ustlikdan afzal.
    """
    lines = _line_count(text, w, size)
    budget = _chars_per_line(w, size)
    longest = max((len(part) for part in (text or "").split("\n")), default=0)
    if lines > 1 or longest >= budget * 0.75:
        # Xato qatorlar soniga mutanosib o'sadi, shuning uchun zaxira ham.
        lines += max(1, math.ceil(lines * 0.25))
    return lines


def _block_height(lines: int, size: float) -> float:
    return max(lines * size * 1.28 / 72, 0.24)


def _fit(text: str, w: float, available_h: float, start: float, minimum: float) -> float:
    """Matn ajratilgan balandlikka sig'adigan eng katta shrift o'lchamini topadi."""
    size = start
    while size > minimum:
        if _block_height(_reserved_lines(text, w, size), size) <= available_h:
            return round(size, 1)
        size -= 0.5
    return minimum


def _without_text(item):
    """Bandning izohini olib tashlaydi — sarlavha va qiymat qoladi."""
    clone = item.model_copy(deep=True)
    clone.text = None
    return clone


def _is_truncated(out, items) -> bool:
    """Chiqqan bloklarda kesilgan matn bormi?

    Kesilgan matn "…" bilan tugaydi; manba matnining o'zi shunday tugagan
    bo'lsa, bu kesilish emas.
    """
    if not out:
        return False
    sources = set()
    for item in items:
        for value in (item.title, item.text, item.value):
            if value:
                sources.add(value.strip())
    for element in out:
        text = (element.text or "").strip()
        if text.endswith("…") and text not in sources:
            return True
    return False


def _trim_to_lines(text: str, w: float, size: float, max_lines: int) -> str:
    """Matnni berilgan qator soniga sig'guncha so'zma-so'z qisqartiradi.

    Belgilar soni bo'yicha kesish noto'g'ri natija berardi: tor ustunda uzun
    so'zlar qator oxirida ko'p bo'sh joy qoldiradi, shuning uchun bir xil
    belgi soni turlicha qator hosil qiladi. Bu yerda haqiqiy o'ralish
    hisoblanadi.
    """
    words = (text or "").split()
    if not words:
        return ""
    # Zaxira qatorni ham hisobga olamiz, shuning uchun `_reserved_lines`.
    kept = []
    for word in words:
        trial = kept + [word]
        if _reserved_lines(" ".join(trial) + "…", w, size) > max_lines:
            break
        kept = trial
    if not kept:
        return _trim(words[0], max(_chars_per_line(w, size) - 1, 4))
    if len(kept) == len(words):
        return text
    return " ".join(kept).rstrip(" ,;:.") + "…"


def _trim(text: str, limit: int) -> str:
    """Matnni oxirgi to'liq so'zda kesadi — so'z o'rtasidan kesilmasin."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:max(limit - 1, 1)]
    space = cut.rfind(" ")
    if space > limit * 0.5:
        cut = cut[:space]
    return cut.rstrip(" ,;:.") + "…"


def _colors(el: VisualElement, theme) -> list[str]:
    """Palitrani mavzu rangi bilan boshlaydi, so'ng validatsiyadan o'tgan qatorni davom ettiradi."""
    base = [c.lstrip("#") for c in PALETTE]
    primary = (getattr(theme, "primary", None) or "").lstrip("#")
    accent = (getattr(theme, "accent", None) or "").lstrip("#")
    lead = [c for c in (primary, accent) if len(c) == 6 and _usable_hue(c)]
    if el.fill:
        lead.insert(0, el.fill.lstrip("#"))
    # Mavzu rangi palitradagi biriga juda yaqin bo'lsa, ikkalasi ham qolsa
    # bitta slaydda deyarli bir xil ikki rang paydo bo'lardi.
    ordered = lead + [c for c in base if not any(_close(c, l) for l in lead)]
    return ordered or base


def _close(a: str, b: str, threshold: int = 60) -> bool:
    """Ikki rang ko'z bilan ajratib bo'lmaydigan darajada yaqinmi."""
    ar, ag, ab = _rgb(a)
    br, bg, bb = _rgb(b)
    return abs(ar - br) + abs(ag - bg) + abs(ab - bb) < threshold


def _usable_hue(hex_str: str) -> bool:
    """Rang kartochka rangi bo'la oladimi.

    Mavzu `primary` odatda to'q siyoh-ko'k bo'ladi — uni kartochka foniga
    aylantirsak, pastel variant kulrangga aylanadi va slayd o'liq ko'rinadi.
    """
    r, g, b = _rgb(hex_str)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    saturation = (max(r, g, b) - min(r, g, b)) / 255
    return 0.24 <= luminance <= 0.78 and saturation >= 0.18


def _rgb(hex_str: str) -> tuple[int, int, int]:
    h = (hex_str or "000000").lstrip("#").strip()
    if len(h) == 3:
        h = h[0] * 2 + h[1] * 2 + h[2] * 2
    if len(h) != 6:
        return (0, 0, 0)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return (0, 0, 0)


def _tint(hex_str: str, amount: float) -> str:
    """Rangni oqqa yaqinlashtiradi — kartochka foni uchun pastel variant."""
    r, g, b = _rgb(hex_str)
    def mix(c):
        return int(round(c + (255 - c) * amount))
    return f"{mix(r):02X}{mix(g):02X}{mix(b):02X}"


def _readable(hue: str, background: str, minimum: float = 4.5) -> str:
    """Rangni fon ustida o'qiladigan bo'lguncha to'qlashtiradi.

    Sariq yoki och yashil kategoriya rangi oq fonda matn sifatida
    ishlatilsa, kontrast 2.2 ga tushib ketadi — rang ko'rinadi, lekin
    yozuvni o'qib bo'lmaydi. Bu yerda rang o'z tusini saqlab, faqat
    yorqinligi pasaytiriladi.
    """
    r, g, b = _rgb(hue)
    for _ in range(12):
        if _contrast(f"{r:02X}{g:02X}{b:02X}", background) >= minimum:
            break
        r, g, b = int(r * 0.82), int(g * 0.82), int(b * 0.82)
    return f"{r:02X}{g:02X}{b:02X}"


def _relative_luminance(hex_str: str) -> float:
    channels = [c / 255 for c in _rgb(hex_str)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(first: str, second: str) -> float:
    a, b = _relative_luminance(first), _relative_luminance(second)
    high, low = max(a, b), min(a, b)
    return (high + 0.05) / (low + 0.05)


def _ink(fill: str | None) -> str:
    """Fon ustida o'qiladigan matn/ikonka rangi.

    Ilgari bu oddiy yorqinlik formulasi edi va yashil (#1baf7a) kabi o'rta
    ranglarda oqni tanlardi — kontrast 2.82, ya'ni o'qish qiyin. Endi
    ikkala variant ham haqiqiy kontrast bo'yicha o'lchanadi va kattasi
    olinadi.
    """
    fill = fill or "000000"
    dark, light = "1B2A4A", "FFFFFF"
    return dark if _contrast(dark, fill) >= _contrast(light, fill) else light


def _clamp(value, low, high):
    return max(low, min(high, value))
