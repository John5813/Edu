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
    r"(?:презентация\s+)?(?:жоспар\w*|мазмұн\w*)|"
    r"(?:план\w*|содержани\w*|оглавлени\w*)(?:\s+презентации)?|"
    r"agenda|outline|contents|table\s+of\s+contents|presentation\s+(?:plan|outline))$",
    re.IGNORECASE)

PLAN_LABEL = {
    "uz": "Taqdimot rejasi",
    "uz-cyrl": "Тақдимот режаси",
    "kk": "Жоспар",
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


# ───────────────────────────────────────────────────────────────── rasm

_PHOTO = re.compile(r'<div\b[^>]*\bclass\s*=\s*["\'][^"\']*(?<![-\w])rasm(?![-\w])[^"\']*["\'][^>]*\bdata-prompt'
                    r'|<div\b[^>]*\bdata-prompt[^>]*\bclass\s*=\s*["\'][^"\']*(?<![-\w])rasm(?![-\w])'
                    r'|<img\b[^>]*\bdata-prompt', re.IGNORECASE)


def has_photo(body: str) -> bool:
    """Slaydda rasm bloki (data-prompt bilan) bormi."""
    return bool(_PHOTO.search(body or ""))


def photo_quota(total: int) -> int:
    """Nechta slaydda rasm bo'lishi kerak: har 10 ta asosiy slaydga 3 ta (yuqoriga yaxlitlanadi).

    `total` — muqova va reja bilan birga slaydlar soni; muqova va reja hisobga kirmaydi
    (muqovaga rasm alohida qo'yiladi).
    """
    main = max(int(total or 0) - 2, 0)
    return -(-main * 3 // 10)


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
        # Qisqartirilgan gap "...принциптері мен" kabi bog'lovchida uzilib qolmasin.
        words = clause.split()
        while len(words) > 3 and len(words[-1].strip(",.;:")) <= 3:
            words.pop()
        clause = " ".join(words)
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
    # Kartochka qancha ko'p bo'lsa, izoh shuncha qisqa: telefondagi shrift kengroq bo'lib,
    # ortiqcha qator kartochka chetidan chiqib ketmasin.
    total = len([1 for t, _ in items if short_title(t)])
    limit = 90 if total <= 4 else 70 if total <= 6 else 56
    items = pick_even([(short_title(t), short_note(n, limit)) for t, n in items if short_title(t)], 8)
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


# ──────────────────────────────────────── sarlavha harflari va ustunlar soni

# Davlat, qit'a va shahar nomlari: bosh harf bilan qoladi.
_PROPER_ROOTS = (
    "қазақстан", "өзбекстан", "ўзбекистан", "ресей", "қытай", "еуропа", "азия", "америка",
    "африка", "астана", "алматы", "ташкент", "ақш", "бнұ", "ұлыбритания",
    "o'zbekiston", "oʻzbekiston", "qozog'iston", "qozogʻiston", "rossiya", "xitoy",
    "yevropa", "osiyo", "amerika", "afrika", "toshkent", "samarqand", "buxoro",
    "россия", "казахстан", "узбекистан", "китай", "европа", "америка", "африка", "ташкент",
    "москва", "сша", "оон", "украина", "германия", "франция", "япония",
    "kazakhstan", "uzbekistan", "russia", "china", "europe", "asia", "america", "africa",
)
_TITLE_ELEMENT = re.compile(
    r'(<(h1|h2|h3|div|p|span)\b[^>]*\bclass\s*=\s*["\'][^"\']*(?<![-\w])(?:title|card-title|step-title)'
    r'(?![-\w])[^"\']*["\'][^>]*>)([^<]+)(</\2>)', re.IGNORECASE)
_WORD_TOKEN = re.compile(r"[^\W\d_][^\s]*", re.UNICODE)


def _is_proper(word: str, body_text: str) -> bool:
    core = word.strip(".,;:!?()«»\"'—–-").lower()
    if any(core.startswith(root) for root in _PROPER_ROOTS):
        return True
    # Matn ichida gap o'rtasida bosh harf bilan uchrasa — atoqli ot.
    for match in re.finditer(r"(?<![.!?]\s)(?<!^)(?<=\s)" + re.escape(word.strip(".,;:!?()«»\"'")), body_text or ""):
        return True
    return False


def sentence_case(title: str, body_text: str = "") -> str:
    """"Негізгі Макроэкономикалық Көрсеткіштер" → "Негізгі макроэкономикалық көрсеткіштер".

    Sarlavhaning deyarli har so'zi bosh harfda (inglizcha "Title Case") bo'lsa — qozoq, rus va
    o'zbek imlosida bunday yozilmaydi: faqat birinchi so'z va atoqli otlar bosh harf bilan. Qisqartma
    (ЖІӨ, ООН), raqamli va atoqli so'zlar o'zgarmaydi; oddiy sarlavhaga tegilmaydi.
    """
    text = (title or "").strip()
    words = text.split()
    if len(words) < 2:
        return title
    tail = [w for w in words[1:] if _WORD_TOKEN.match(w)]
    capitalised = [w for w in tail if w[:1].isupper() and not w.isupper() and not any(c.isdigit() for c in w)
                   and any(c.islower() for c in w[1:])]
    needed = 1 if len(words) == 2 else 2
    if len(capitalised) < needed or len(capitalised) < 0.6 * len(tail):
        return title
    out = [words[0]]
    for word in words[1:]:
        if word in capitalised and not _is_proper(word, body_text):
            word = word[:1].lower() + word[1:]
        out.append(word)
    return " ".join(out)


def fix_title_case(body: str) -> str:
    """Slayd sarlavhalari va kartochka sarlavhalarini adabiy yozuvga (birinchi so'z bosh harf) keltiradi."""
    if not body:
        return body
    # Atoqli otni aniqlash uchun sarlavhalarning o'zi hisobga olinmaydi (ular hammasi bosh harfda).
    text = plain(_TITLE_ELEMENT.sub(" ", body))

    def swap(match):
        original = match.group(3)
        fixed = sentence_case(html.unescape(original), text)
        if fixed == html.unescape(original):
            return match.group(0)
        return match.group(1) + html.escape(fixed, quote=False) + match.group(4)

    return _TITLE_ELEMENT.sub(swap, body)


_COLS_OPEN = re.compile(r'<div\b[^>]*\bclass\s*=\s*"([^"]*)"[^>]*>', re.IGNORECASE)
_DIV_TAG = re.compile(r"<div\b[^>]*>|</div\s*>", re.IGNORECASE)
_CARD_CHILD = re.compile(r'<div\b[^>]*\bclass\s*=\s*"[^"]*(?<![-\w])card(?![-\w])', re.IGNORECASE)


def _card_count(body: str, start: int) -> int:
    """`start` dagi `.cols` blokining bevosita `.card` bolalari soni."""
    depth, count = 0, 0
    for tag in _DIV_TAG.finditer(body, start):
        if tag.group(0).startswith("</"):
            depth -= 1
            if depth <= 0:
                break
        else:
            depth += 1
            if depth == 2 and _CARD_CHILD.match(tag.group(0)):
                count += 1
    return count


def balanced_columns(count: int, current: int) -> int:
    """`count` ta kartochka uchun ustun soni: oxirgi qatorda yolg'iz kartochka qolmasin."""
    if count <= 1:
        return max(current, 1)
    options = [n for n in (2, 3, 4) if count <= n or count % n != 1]
    if count <= 4:
        options = [n for n in options if n <= max(count, 2)] or options
    if current in options and (current <= count or count <= 2):
        return current
    return min(options, key=lambda n: (abs(n - current), n)) if options else current


def fix_columns(body: str) -> str:
    """`cols-3` da 4 ta kartochka (3+1) kabi yolg'iz qolgan kartochkani ustun sonini o'zgartirib tuzatadi."""
    result, pos = [], 0
    for match in _COLS_OPEN.finditer(body or ""):
        classes = match.group(1)
        if "cols" not in classes.split():
            continue
        number = re.search(r"(?<![-\w])cols-(\d)(?![-\w])", classes)
        if not number:
            continue
        current = int(number.group(1))
        count = _card_count(body, match.start())
        if count < 2:
            continue
        wanted = balanced_columns(count, current)
        if wanted == current:
            continue
        opening = match.group(0)
        fixed = re.sub(r"(?<![-\w])cols-\d(?![-\w])", f"cols-{wanted}", opening, count=1)
        result.append(body[pos:match.start()])
        result.append(fixed)
        pos = match.end()
    result.append(body[pos:])
    return "".join(result)


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
