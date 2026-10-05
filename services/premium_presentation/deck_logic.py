"""Taqdimot mantig'ini tekshirish: takror, reja, jadval, diagramma.

Model slaydlarni 3 tadan bo'laklab yozadi va har bo'lak oldingilarning
matnini ko'rmaydi. Natijada:

  * reja slaydi (2-slayd) taqdimotda yo'q bo'limlarni sanardi;
  * bir xil mavzu ikki marta yozilardi (masalan 3- va 9-slaydda bir xil
    voqealar zanjiri);
  * o'rtada yana "Taqdimot rejasi" jadvali chiqib qolardi;
  * zich "tahlil jadvali" butun varaqni egallardi.

Bu modul hech narsani modeldan so'ramaydi — faqat yozilgan slaydlarni
o'qib, nimani qayta yozish kerakligini aytadi va rejani HAQIQIY slayd
sarlavhalaridan yig'adi.
"""

import difflib
import html
import re
from typing import Dict, List, Optional, Tuple

_TAG = re.compile(r"<[^>]+>")
_TITLE = re.compile(
    r'<h[12]\b[^>]*\bclass\s*=\s*["\'][^"\']*\btitle\b[^"\']*["\'][^>]*>(.*?)</h[12]>',
    re.IGNORECASE | re.DOTALL)
_WORD = re.compile(r"[^\W\d_]{4,}", re.UNICODE)

# "Taqdimot rejasi", "Reja", "Mundarija", "План", "Agenda"... — faqat 2-slayd.
_PLAN_TITLE = re.compile(
    r"^(?:taqdimot\s+|ish\s+)?(?:reja\w*|mundarija\w*|mazmun\w*|"
    r"(?:тақдимот\s+)?(?:режа\w*|мундарижа\w*)|"
    r"(?:план\w*|содержани\w*|оглавлени\w*)(?:\s+презентации)?|"
    r"agenda|outline|contents|table\s+of\s+contents|presentation\s+(?:plan|outline))$",
    re.IGNORECASE)

PLAN_LABEL = {
    "uz": "Taqdimot rejasi",
    "uz-cyrl": "Тақдимот режаси",
    "ru": "План презентации",
    "en": "Presentation outline",
}


def plain(body: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", body or ""))).strip()


def title_of(body: str) -> str:
    match = _TITLE.search(body or "")
    return plain(match.group(1)) if match else ""


def _norm(text: str) -> str:
    text = re.sub(r"[‘’ʻʼ′'`´]", "", (text or "").lower())
    return re.sub(r"[^\w]+", " ", text, flags=re.UNICODE).strip()


def is_plan_title(title: str) -> bool:
    return bool(_PLAN_TITLE.match(_norm(title)))


def similar_titles(first: str, second: str) -> bool:
    """Ikki sarlavha bir narsani aytadimi ("... e'lon qilinishi" ikki marta)."""
    a, b = _norm(first), _norm(second)
    if not a or not b:
        return False
    if a == b:
        return True
    ta, tb = set(a.split()), set(b.split())
    short, long = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    # Biri ikkinchisining davomi: "Davlat ramzlari" / "Davlat ramzlari qabul qilinishi"
    if len(short) >= 2 and short <= long and len(long) <= len(short) + 2:
        return True
    if len(short) >= 3 and short <= long:
        return True
    union = ta | tb
    if union and len(ta & tb) / len(union) >= 0.65:
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.84


def _words(body: str) -> set:
    return {w.lower() for w in _WORD.findall(plain(body))}


def same_content(first: str, second: str) -> bool:
    """Ikki slaydning matni asosan bir xilmi (so'zlar ustma-ust tushishi)."""
    a, b = _words(first), _words(second)
    if len(a) < 12 or len(b) < 12:
        return False
    return len(a & b) / len(a | b) >= 0.5


def duplicates(bodies: List[str], skip: Tuple[int, ...] = ()) -> Dict[int, int]:
    """{keyingi_takror_indeksi: avvalgisi}. Muqova (0), reja (1) va yakun tekshirilmaydi."""
    last = len(bodies) - 1
    found: Dict[int, int] = {}
    for later in range(2, last):
        if later in skip:
            continue
        for earlier in range(2, later):
            if earlier in found:
                continue
            if similar_titles(title_of(bodies[earlier]), title_of(bodies[later])) \
                    or same_content(bodies[earlier], bodies[later]):
                found[later] = earlier
                break
    return found


def stray_plans(bodies: List[str]) -> List[int]:
    """2-slayddan boshqa joydagi "reja" slaydlari (o'rtada yoki oxirda takrorlangan)."""
    return [i for i, body in enumerate(bodies)
            if i != 1 and i != 0 and is_plan_title(title_of(body))]


# ───────────────────────────────────────────────────────────── jadval

_ROW = re.compile(r"<tr\b.*?</tr>", re.IGNORECASE | re.DOTALL)
_CELL = re.compile(r"<t[hd]\b[^>]*>(.*?)</t[hd]>", re.IGNORECASE | re.DOTALL)


def table_stats(body: str) -> Optional[Tuple[int, int, int]]:
    """(qatorlar, ustunlar, eng uzun katak so'zlari) — jadval yo'q bo'lsa None."""
    if "<table" not in (body or "").lower():
        return None
    rows = _ROW.findall(body)
    cells = [[plain(c) for c in _CELL.findall(row)] for row in rows]
    cells = [row for row in cells if row]
    if not cells:
        return None
    longest = max(len(c.split()) for row in cells for c in row)
    return len(cells), max(len(row) for row in cells), longest


def oversized_table(body: str) -> bool:
    """Qisqa jadval emas: 5 qatordan uzun, 3 ustundan keng yoki kataklari uzun."""
    stats = table_stats(body)
    if not stats:
        return False
    rows, cols, longest = stats
    return rows > 5 or cols > 3 or longest > 8


# ─────────────────────────────────────────────────────────── diagramma

_CHART = re.compile(r'class\s*=\s*["\'][^"\']*\b(?:chart|calc)\b', re.IGNORECASE)


def has_chart(body: str) -> bool:
    return bool(_CHART.search(body or ""))


def chart_count(bodies: List[str]) -> int:
    return sum(1 for b in bodies if has_chart(b))


def chart_quota(total: int) -> int:
    """Taqdimotda kamida nechta diagramma bo'lishi kerak."""
    if total < 6:
        return 0
    if total < 10:
        return 1
    if total < 16:
        return 2
    return 3


_SHARE = re.compile(r"ulush|foiz|tarkib|tuzilma|tasnif|turlari|guruh|tuzilish|состав|доля|структур|вид[ыа]|"
                    r"share|types|composition|structure|ҳисса|таркиб", re.IGNORECASE)
_TREND = re.compile(r"yil|davr|dinamika|rivoj|o'sish|osish|bosqich|tarix|tendensiya|taraqqiyot|"
                    r"динамик|рост|развит|этап|истори|тенденц|growth|trend|history|stage|development",
                    re.IGNORECASE)

KIND_TEXT = {
    "halqa": "halqa (donut): butunning ulushlari, `data-kind=\"donut\"`",
    "chiziqli": "chiziqli: vaqt bo'yicha o'zgarish, X o'qi yil/davr, `data-kind=\"line\"`",
    "ustunli": "ustunli: bir necha qiymatni solishtirish, `data-kind=\"bar\"`",
}


def chart_kind_for(text: str, order: int = 0) -> str:
    """Slayd mazmuniga mos diagramma turi: ulush → halqa, vaqt → chiziqli, qolgani — ustunli."""
    share, trend = bool(_SHARE.search(text or "")), bool(_TREND.search(text or ""))
    if share and not trend:
        return "halqa"
    if trend and not share:
        return "chiziqli"
    return ("halqa", "chiziqli", "ustunli")[order % 3]


# ───────────────────────────────────────────────────────────── reja slaydi

def short_title(text: str, limit: int = 7) -> str:
    """Reja bandi uchun qisqa sarlavha: ikki nuqtadan keyingi izoh va ortiqcha so'zlar tushadi."""
    text = plain(text)
    head = re.split(r"\s*[:—–]\s+|\s+-\s+", text, maxsplit=1)[0]
    if len(head.split()) >= 2:
        text = head
    words = text.split()
    if len(words) > limit:
        text = " ".join(words[:limit])
    return text.rstrip(" .,;:—–-")


def short_note(brief: str, limit: int = 90) -> str:
    brief = plain(brief)
    brief = re.sub(r"^\s*(?:\[[^\]]*\]|\([^)]*\))\s*", "", brief)
    clause = re.split(r"(?<=[.!?])\s|\s[—–-]\s|;\s", brief, maxsplit=1)[0]
    if len(clause) > limit:
        clause = clause[:limit].rsplit(" ", 1)[0]
    return clause.rstrip(" .,;:—–-")


def pick_even(items: List, count: int) -> List:
    """`count` tagacha elementni tartibini saqlab, teng oraliqda tanlaydi."""
    if count <= 0:
        return []
    if len(items) <= count:
        return list(items)
    if count == 1:
        return [items[len(items) // 2]]
    step = (len(items) - 1) / (count - 1)
    indices = sorted({round(i * step) for i in range(count)})
    return [items[i] for i in indices]


def plan_slide(items: List[Tuple[str, str]], language: str = "uz") -> str:
    """HAQIQIY slayd sarlavhalaridan reja slaydi. items = [(sarlavha, izoh), ...]."""
    items = pick_even([(short_title(t), short_note(n)) for t, n in items if short_title(t)], 8)
    count = len(items)
    columns = 2 if count == 4 else 4 if count >= 7 else 3
    cards = []
    for number, (title, note) in enumerate(items, 1):
        part = f'<div class="card line"><div class="card-num">{number:02d}</div>' \
               f'<div class="card-title">{html.escape(title, quote=False)}</div>'
        if note and note.lower() != title.lower():
            part += f'<div class="card-note">{html.escape(note, quote=False)}</div>'
        cards.append(part + "</div>")
    label = PLAN_LABEL.get(language, PLAN_LABEL["uz"])
    return (f'<section class="slide reja"><div class="head"><h2 class="title">{html.escape(label)}</h2>'
            f'<div class="rule"></div></div><div class="body"><div class="cols cols-{columns}">'
            + "".join(cards) + "</div></div></section>")


_CARD_NUM = re.compile(r'<div\b[^>]*\bclass\s*=\s*["\'][^"\']*\bcard-num\b[^"\']*["\'][^>]*>.*?</div>',
                       re.IGNORECASE | re.DOTALL)


def strip_numbering(body: str) -> str:
    """Kartochkalardagi 01/02/03 raqamlarini olib tashlaydi (reja slaydidan tashqari)."""
    if re.search(r'<section\b[^>]*class\s*=\s*["\'][^"\']*\breja\b', body or "", re.IGNORECASE):
        return body
    return _CARD_NUM.sub("", body)


# ───────────────────────────────────────────────────── umumlashtiruvchi gap

_HAS_LEAD = re.compile(r'class\s*=\s*["\'][^"\']*\blead\b', re.IGNORECASE)
_BODY_OPEN = re.compile(r'(<div\b[^>]*\bclass\s*=\s*["\'][^"\']*\bbody\b[^"\']*["\'][^>]*>)', re.IGNORECASE)
_SKIP_LEAD = re.compile(r'class\s*=\s*["\'][^"\']*\b(?:misol|quote|quote-mark|formula)\b', re.IGNORECASE)


def needs_lead(body: str) -> bool:
    if not body or _HAS_LEAD.search(body) or _SKIP_LEAD.search(body):
        return False
    if re.search(r'<section\b[^>]*class\s*=\s*["\'][^"\']*\b(?:reja|dark)\b', body, re.IGNORECASE):
        return False
    return bool(_BODY_OPEN.search(body))


def insert_lead(body: str, lead: str) -> str:
    lead = re.sub(r"\s+", " ", plain(lead)).strip()
    if not lead or not _BODY_OPEN.search(body):
        return body
    return _BODY_OPEN.sub(lambda m: m.group(1) + f'<p class="lead">{html.escape(lead, quote=False)}</p>',
                          body, count=1)
