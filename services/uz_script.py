"""O'zbekcha yozuv: lotin, kirill va yangi lotin alifbosi.

Taqdimot mavzusi kirillda yozilsa, ilgari sarlavhalar, "Rahmat" va jadval
nomlari lotinda, qolgan matn kirillda chiqib, bir slaydning o'zida ikki
yozuv aralashib ketardi. Endi mijoz yozuvni tanlaydi, matnni modelga
shu yozuvda yozdirishga harakat qilamiz, tayyor faylda esa qolib ketgan
boshqa yozuvdagi so'zlarni shu yozuvga o'giramiz.

O'girish rus tilini emas, faqat o'zbek imlosini nazarda tutadi.

Yangi lotin alifbosi (2027-yil 22-apreldan kuchga kiradi): oʻ → ö, gʻ → ğ,
sh → ş, ch → ç, tutuq belgisi — ʼ. Modellar asosan eski lotinda o'qitilgan,
shuning uchun matn eski lotinda yozdiriladi va tayyor matn/fayl kod bilan
yangi alifboga o'giriladi (`to_latin_new`) — almashtirish qat'iy qoida.
"""
import contextvars
import re
from typing import Any, Optional

LATIN = "latin"
CYRILLIC = "cyrillic"
LATIN_NEW = "latin_new"           # yangi lotin alifbosi (ö, ğ, ş, ç)
SCRIPTS = (LATIN, CYRILLIC, LATIN_NEW)

# Premium oqimda til kodi shu ko'rinishda ham keladi.
UZ_CYRILLIC_LANG = "uz-cyrl"
UZ_NEW_LANG = "uz-yangi"          # o'zbekcha, yangi lotin alifbosida

_CYRILLIC_RE = re.compile(r"[Ѐ-ӿ]")
_APOSTROPHES = "ʻʼ’‘`´"

# ── kirill → lotin
_C2L = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "ё": "yo", "ж": "j", "з": "z",
    "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p",
    "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "x", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "shch", "ъ": "'", "ы": "i", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "ў": "o'", "қ": "q", "ғ": "g'", "ҳ": "h", "ҷ": "j", "ӯ": "o'",
}
_C_VOWELS = set("аеёиоуыэюяўАЕЁИОУЫЭЮЯЎ")

# ── lotin → kirill
_L_SIMPLE = {
    "a": "а", "b": "б", "d": "д", "f": "ф", "g": "г", "h": "ҳ", "i": "и", "j": "ж",
    "k": "к", "l": "л", "m": "м", "n": "н", "o": "о", "p": "п", "q": "қ", "r": "р",
    "s": "с", "t": "т", "u": "у", "v": "в", "w": "в", "x": "х", "y": "й", "z": "з",
    "c": "к",
}
_L_VOWELS = set("aeiou")


def has_cyrillic(text: str) -> bool:
    return bool(_CYRILLIC_RE.search(str(text or "")))


def _case(source: str, target: str, upper_all: bool) -> str:
    """Birinchi harf katta bo'lsa — natijaning birinchi harfi ham katta."""
    if not target:
        return target
    if source.isupper():
        return target.upper() if upper_all else target[0].upper() + target[1:]
    return target


# ───────────────────────────────────────────────────────── kirill → lotin

def _cyrillic_word_to_latin(word: str) -> str:
    out = []
    n = len(word)
    for i, char in enumerate(word):
        low = char.lower()
        if low == "е":
            prev = word[i - 1] if i else ""
            # So'z boshida, unli yoki ayiruv belgisidan keyin "ye"
            piece = "ye" if (not prev or prev in _C_VOWELS or prev in "ъЪ") else "e"
        elif low in _C2L:
            piece = _C2L[low]
        else:
            out.append(char)
            continue
        # Katta harf: "Ш" → "Sh"; butun so'z katta bo'lsa "SH"
        if char.isupper():
            following_upper = i + 1 < n and word[i + 1].isupper()
            piece = piece.upper() if (following_upper or (i and word[i - 1].isupper())) and len(piece) > 1 \
                else piece[:1].upper() + piece[1:]
        out.append(piece)
    return "".join(out)


def to_latin(text: str) -> str:
    """Kirilldagi so'zlarni o'zbek lotiniga o'giradi (lotin qismi tegilmaydi)."""
    return re.sub(r"[Ѐ-ӿ]+", lambda m: _cyrillic_word_to_latin(m.group(0)), str(text or ""))


# ───────────────────────────────────────────────────────── lotin → kirill

_NEW_LETTERS = "ÖöĞğŞşÇç"
_LATIN_WORD = re.compile(r"[A-Za-z" + _NEW_LETTERS + r"](?:[A-Za-z" + _NEW_LETTERS + r"]|['"
                         + re.escape(_APOSTROPHES) + r"](?=[A-Za-z" + _NEW_LETTERS + r"]))*")
# Yangi alifbo harflari eski lotin ko'rinishida (kirillga o'girishdan oldin).
_NEW_TO_OLD = {"ö": "o'", "Ö": "O'", "ğ": "g'", "Ğ": "G'", "ş": "sh", "Ş": "Sh", "ç": "ch", "Ç": "Ch"}


def _new_to_old(word: str) -> str:
    """Yangi alifbodagi so'z → eski lotin: "Şahar" → "Shahar", "ŞAHAR" → "SHAHAR"."""
    if not any(char in _NEW_LETTERS for char in word):
        return word.replace("ʼ", "'")
    upper_all = sum(char.isupper() for char in word) > 1 and word.upper() == word
    out = []
    for char in word:
        piece = _NEW_TO_OLD.get(char, char)
        out.append(piece.upper() if upper_all else piece)
    return "".join(out).replace("ʼ", "'")


def _latin_word_to_cyrillic(word: str) -> str:
    text = re.sub("[" + re.escape(_APOSTROPHES) + "]", "'", _new_to_old(word))
    low = text.lower()
    out = []
    i, n = 0, len(text)
    while i < n:
        two = low[i:i + 2]
        char = text[i]
        piece, step = None, 1
        nxt = low[i + 1:i + 2]
        after = low[i + 2:i + 3]
        if two in ("o'", "g'"):
            piece, step = ("ў" if two == "o'" else "ғ"), 2
        elif two == "sh":
            piece, step = "ш", 2
        elif two == "ch":
            piece, step = "ч", 2
        elif two == "ts":
            piece, step = "ц", 2
        elif two == "yo" and after != "'":
            piece, step = "ё", 2
        elif two == "yu":
            piece, step = "ю", 2
        elif two == "ya":
            piece, step = "я", 2
        elif two == "ye":
            piece, step = "е", 2
        elif low[i] == "e":
            prev = low[i - 1] if i else ""
            piece = "э" if (not prev or prev == "'") else "е"
        elif low[i] == "'":
            # Tutuq belgisi: "ma'no" → "маъно", "e'tibor" → "эътибор"
            piece = "ъ" if (i and i + 1 < n) else ""
        elif low[i] in _L_SIMPLE:
            piece = _L_SIMPLE[low[i]]
        else:
            piece = char
        source = text[i:i + step]
        if piece and source[:1].isupper():
            all_upper = (n > step and text[i:].isupper()) or (i and text[i - 1].isupper()) \
                or (i + step < n and text[i + step].isupper())
            piece = piece.upper() if (all_upper and len(piece) > 1) else piece[:1].upper() + piece[1:]
        out.append(piece)
        i += step
    return "".join(out)


_UNITS = {"mg", "kg", "km", "sm", "ml", "mm", "cm", "hz", "kw", "mb", "gb", "kb", "tb", "ph", "gr"}
_MATH_NEIGHBOUR = re.compile(r"[=+\-*/^()<>\d]")


def _keep_latin(token: str, before: str, after: str) -> bool:
    """Kirillga o'tkazilmaydigan lotincha bo'laklar: qisqartma, o'zgaruvchi, birlik."""
    if len(token) == 1:
        # "x = 3", "2y" — o'zgaruvchi; "u" (o'zbekcha olmosh) esa matn ichida o'giriladi.
        near = (before.rstrip(" ")[-1:] if before.endswith(" ") or not before else before[-1:]) + \
               (after.lstrip(" ")[:1])
        return bool(_MATH_NEIGHBOUR.search(near)) or token.isupper()
    if len(token) == 2 and token.lower() in _UNITS:
        return True                       # mg, kg, sm
    if token.isupper() and len(token) <= 6:
        return True                       # AI, PDF, DNK, WHO
    if any(char.isdigit() for char in (before[-1:] + after[:1])):
        return True                       # H2O, B12, COVID19
    return False


# Havola, pochta va sayt nomlari o'zgarmaydi.
_PROTECTED = (r"\$[^$]*\$|&#?\w+;|https?://\S+|www\.\S+|[\w.+-]+@[\w-]+\.[\w.]+|"
              r"\b[\w-]+\.(?:uz|com|ru|org|net|me|edu|gov)\b\S*")


def to_cyrillic(text: str) -> str:
    """Lotindagi so'zlarni o'zbek kirillchasiga o'giradi (kirill qismi tegilmaydi).

    `$...$` ichidagi formulalar, HTML belgilar (&amp;), qisqartmalar, havolalar va qisqa belgilar
    (x, y, mg) o'zgarmaydi.
    """
    source = str(text or "")
    result = []
    for index, part in enumerate(re.split("(" + _PROTECTED + ")", source)):
        if index % 2:                     # himoyalangan bo'lak
            result.append(part)
            continue
        result.append(_LATIN_WORD.sub(
            lambda m: m.group(0) if _keep_latin(m.group(0), part[:m.start()], part[m.end():])
            else _latin_word_to_cyrillic(m.group(0)), part))
    return "".join(result)


# ───────────────────────────────────────────────────────── eski lotin ↔ yangi lotin

# Bitta so'z (lotin harflari, yangi harflar va so'z ichidagi tutuq/oʻ belgilari).
_LATIN_NEW_WORD = re.compile(r"[A-Za-z" + _NEW_LETTERS + r"](?:[A-Za-z" + _NEW_LETTERS + r"]|["
                             + re.escape("'" + _APOSTROPHES) + r"]{1,2}(?=[A-Za-z" + _NEW_LETTERS + r"]))*["
                             + re.escape("'" + _APOSTROPHES) + r"]?")
# "oʻ" va "gʻ" belgisi. ʼ (U+02BC) — tutuq belgisi, u "o" dan keyin ham tutuq bo'lib qoladi.
_OKINA = "'ʻ‘’`´"
_O_G = re.compile(r"([OoGg])[" + re.escape(_OKINA) + r"]")
_TUTUQ = re.compile(r"(?<=[A-Za-z" + _NEW_LETTERS + r"])[" + re.escape("'" + _APOSTROPHES) + r"](?=[A-Za-z"
                    + _NEW_LETTERS + r"])")
_NEW_SH_CH = {"sh": "ş", "ch": "ç"}


def _looks_foreign(word: str) -> bool:
    """O'zbek lotinida bo'lmaydigan birikmalar (w, yolg'iz c, th, ee, oo, ck) — chet tilidagi so'z."""
    return bool(re.search(r"w|c(?!h)|th|ee|oo|ck", word.lower()))


def _latin_word_to_new(word: str) -> str:
    """Eski lotindagi bitta so'z → yangi alifbo. "O'zbekiston" → "Özbekiston", "SHAHAR" → "ŞAHAR"."""
    upper_all = sum(char.isupper() for char in word) > 1 and word.upper() == word

    def o_g(match) -> str:
        letter = match.group(1)
        new = {"o": "ö", "g": "ğ"}[letter.lower()]
        return new.upper() if letter.isupper() else new

    text = _O_G.sub(o_g, word)
    text = _TUTUQ.sub("ʼ", text)

    def sh_ch(match) -> str:
        pair = match.group(0)
        new = _NEW_SH_CH[pair.lower()]
        return new.upper() if pair[0].isupper() else new

    text = re.sub(r"[Ss][Hh]|[Cc][Hh]", sh_ch, text)
    return text.upper() if upper_all else text


def to_latin_new(text: str) -> str:
    """Matnni yangi o'zbek lotin alifbosiga o'giradi (kirill qismi ham).

    Formulalar (`$...$`), havolalar, pochta, HTML belgilar, raqamga yopishgan bo'laklar
    (CH4, H2O) va chet tilidagi so'zlar (w, c, th... bor) o'zgarmaydi.
    Bir necha marta qo'llansa ham natija o'zgarmaydi.
    """
    source = to_latin(text)
    result = []
    for index, part in enumerate(re.split("(" + _PROTECTED + ")", source)):
        if index % 2:                     # himoyalangan bo'lak
            result.append(part)
            continue
        if _looks_english_phrase(part):
            result.append(part)
            continue

        def word(match) -> str:
            token = match.group(0)
            before, after = part[:match.start()], part[match.end():]
            if any(char.isdigit() for char in (before[-1:] + after[:1])):
                return token              # CH4, B12
            if _looks_foreign(token):
                return token              # Chrome, Washington
            return _latin_word_to_new(token)

        result.append(_LATIN_NEW_WORD.sub(word, part))
    return "".join(result)


# Inglizcha jumla (ikki va undan ko'p inglizcha so'z, o'zbekchasi yo'q) butunlay tegilmaydi.
_ENGLISH_WORDS = {
    "the", "and", "of", "to", "in", "is", "for", "on", "with", "as", "by", "this", "that", "are", "be",
    "from", "or", "an", "it", "at", "which", "was", "were", "has", "have", "not", "but", "can", "will",
    "should", "children", "school", "teacher", "research", "change", "chapter", "show", "shop",
}


def _looks_english_phrase(text: str) -> bool:
    words = re.findall(r"[A-Za-z]+", text)
    if len(words) < 2 or any(mark in text for mark in "'ʻʼ‘’"):
        return False
    english = sum(1 for w in words if w.lower() in _ENGLISH_WORDS)
    return english >= 2 and english * 3 >= len(words)


def to_latin_old(text: str) -> str:
    """Kirill va yangi alifbodagi so'zlarni eski (amaldagi) o'zbek lotiniga keltiradi."""
    source = to_latin(text)
    if not any(char in _NEW_LETTERS for char in source):
        return source
    return re.sub(r"[A-Za-z" + _NEW_LETTERS + r"ʼ']+", lambda m: _new_to_old(m.group(0)), source)


# ───────────────────────────────────────────────────────── umumiy

def convert(text: str, script: Optional[str]) -> str:
    """Matnni tanlangan yozuvga keltiradi (yozuv noma'lum bo'lsa — o'zgarmaydi)."""
    if script == LATIN:
        return to_latin(text)
    if script == CYRILLIC:
        return to_cyrillic(text)
    if script == LATIN_NEW:
        return to_latin_new(text)
    return text


def convert_tree(value: Any, script: Optional[str], skip_keys=("layout", "image_prompt", "prompt",
                                                              "icon", "kind", "style", "type")) -> Any:
    """JSON ko'rinishidagi mazmun (dict/list/str) ichidagi hamma matnni o'giradi."""
    if script not in SCRIPTS:
        return value
    if isinstance(value, str):
        return convert(value, script)
    if isinstance(value, list):
        return [convert_tree(item, script, skip_keys) for item in value]
    if isinstance(value, dict):
        return {key: (item if key in skip_keys else convert_tree(item, script, skip_keys))
                for key, item in value.items()}
    return value


def script_of_language(language: str) -> Optional[str]:
    """Premium til kodidan yozuv: "uz" → lotin, "uz-cyrl" → kirill, "uz-yangi" → yangi lotin.

    "uz" bilan ishlayotgan oqimda yangi alifbo tanlangan bo'lsa (`use(LATIN_NEW)`) — yangi lotin.
    """
    if language == "uz":
        return LATIN_NEW if current() == LATIN_NEW else LATIN
    if language == UZ_CYRILLIC_LANG:
        return CYRILLIC
    if language == UZ_NEW_LANG:
        return LATIN_NEW
    return None


DOC_NEW_CODE = "uzn"              # hujjat tili tugmasi: "doc_lang_uzn"


def doc_language_choice(code: str) -> tuple:
    """Hujjat tili tugmasi → (til, yangi_alifbo). "uzn" → ("uz", True)."""
    if code == DOC_NEW_CODE:
        return "uz", True
    return code, False


def base_language(language: str) -> str:
    """Ichki oqimlar uchun til kodi: yangi alifbo — oddiy "uz" (matn eski lotinda yoziladi)."""
    return "uz" if language == UZ_NEW_LANG else language


# ───────────────────────────────────────────────────────── modelga qoida

def prompt_rule(script: Optional[str]) -> str:
    """Modelga yuboriladigan yozuv qoidasi (inglizcha: model uni aniqroq bajaradi)."""
    if script == CYRILLIC:
        return ("SCRIPT RULE: write every Uzbek word in the UZBEK CYRILLIC alphabet "
                "(ў, қ, ғ, ҳ), for example «Таҳлил», «Ўзбекистон», «Эътибор». Never use Latin "
                "letters for Uzbek words and never mix the two alphabets. JSON keys, layout "
                "names and technical identifiers stay exactly as specified in the instructions; "
                "internationally written abbreviations (AI, PDF) may stay.")
    if script in (LATIN, LATIN_NEW):
        # Yangi alifbo ham: model eski lotinda yozadi, natija kod bilan o'giriladi.
        return ("SCRIPT RULE: write every Uzbek word in the UZBEK LATIN alphabet "
                "(oʻ, gʻ written as o', g'). Never use Cyrillic letters, even if the topic was "
                "given in Cyrillic: transliterate it into Latin.")
    return ""


_current: contextvars.ContextVar = contextvars.ContextVar("uz_script", default="")


def use(script: Optional[str]):
    """Shu jarayon ichidagi barcha model so'rovlariga yozuv qoidasini qo'shadi.

    Qaytgan belgi bilan `reset` chaqiriladi.
    """
    return _current.set(script if script in SCRIPTS else "")


def reset(token) -> None:
    try:
        _current.reset(token)
    except Exception:
        pass


def current() -> str:
    return _current.get()


def with_rule(messages: list) -> list:
    """Xabarlar ro'yxatiga joriy yozuv qoidasini qo'shadi (qoida yo'q bo'lsa — o'zgarmaydi)."""
    rule = prompt_rule(current())
    if not rule or not messages:
        return messages
    out = [dict(m) for m in messages]
    for message in reversed(out):
        if message.get("role") == "user" and isinstance(message.get("content"), str):
            message["content"] = message["content"] + "\n\n" + rule
            return out
    return [{"role": "system", "content": rule}] + out


# ───────────────────────────────────────────────────────── fayl va HTML

def normalize_pptx(path: str, script: Optional[str]) -> int:
    """PPTX ichidagi hamma matnni tanlangan yozuvga keltiradi. O'zgargan bo'laklar soni."""
    if script not in SCRIPTS:
        return 0
    from pptx import Presentation

    prs = Presentation(path)
    changed = 0

    def fix_frame(frame) -> None:
        nonlocal changed
        for paragraph in frame.paragraphs:
            for run in paragraph.runs:
                new = convert(run.text, script)
                if new != run.text:
                    run.text = new
                    changed += 1

    def walk(shapes) -> None:
        for shape in shapes:
            if shape.shape_type == 6 and hasattr(shape, "shapes"):          # guruh
                walk(shape.shapes)
            if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
                fix_frame(shape.text_frame)
            if getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    for cell in row.cells:
                        fix_frame(cell.text_frame)

    for slide in prs.slides:
        walk(slide.shapes)
        if slide.has_notes_slide:
            fix_frame(slide.notes_slide.notes_text_frame)
    if changed:
        prs.save(path)
    return changed


_TEXT_NODE = re.compile(r">([^<>]+)<")
_ATTR_PLAIN = re.compile(r'(data-(?:labels|unit|xlabel)=")([^"]*)(")')
_ATTR_SERIES = re.compile(r'(data-series=")([^"]*)(")')


def _series_names(value: str, script: str) -> str:
    """"Nomi: 1,2,3|Boshqa: 4,5" — faqat nomlar o'giriladi, formula va raqamlar emas."""
    rows = []
    for row in value.split("|"):
        name, sep, rest = row.partition(":")
        rows.append(convert(name, script) + sep + rest)
    return "|".join(rows)


def normalize_html(html: str, script: Optional[str]) -> str:
    """Slayd HTML'idagi ko'rinadigan matnlarni tanlangan yozuvga keltiradi.

    Atributlardan faqat diagramma yorliqlari, birligi va qator nomlari o'giriladi;
    rasm tavsifi (`data-prompt`), ikonka nomi va formulalar tegilmaydi.
    """
    if script not in SCRIPTS or not html:
        return html
    html = _TEXT_NODE.sub(lambda m: ">" + convert(m.group(1), script) + "<", html)
    html = _ATTR_PLAIN.sub(lambda m: m.group(1) + convert(m.group(2), script) + m.group(3), html)
    html = _ATTR_SERIES.sub(lambda m: m.group(1) + _series_names(m.group(2), script) + m.group(3), html)
    return html


def normalize_docx(path: str, script: Optional[str]) -> int:
    """DOCX ichidagi hamma matnni (asosiy matn, jadval, yozuv maydoni, kolontitul, izoh) yozuvga keltiradi.

    Formulalar (OMML) va maydon kodlari tegilmaydi — faqat `w:t` matn bo'laklari.
    """
    if script not in SCRIPTS:
        return 0
    from docx import Document
    from docx.oxml.ns import qn

    doc = Document(path)
    changed = 0
    parts = [doc.part] + [rel.target_part for rel in doc.part.rels.values()
                          if not rel.is_external and hasattr(rel.target_part, "element")]
    seen = set()
    for part in parts:
        root = getattr(part, "element", None)
        if root is None or id(root) in seen:
            continue
        seen.add(id(root))
        for node in root.iter(qn("w:t")):
            if node.text:
                new = convert(node.text, script)
                if new != node.text:
                    node.text = new
                    changed += 1
    if changed:
        doc.save(path)
    return changed


def normalize_file(path: str, script: Optional[str]) -> int:
    """Tayyor DOCX/PPTX faylni yozuvga keltiradi (boshqa turdagi fayl — tegilmaydi)."""
    if not path or script not in SCRIPTS or not isinstance(path, str):
        return 0
    ext = path.lower().rsplit(".", 1)[-1]
    if ext == "docx":
        return normalize_docx(path, script)
    if ext == "pptx":
        return normalize_pptx(path, script)
    return 0


def wrap_file_methods(cls, names=(), prefix: str = "") -> None:
    """Fayl yo'lini qaytaradigan metodlarni o'raydi: yangi alifbo tanlangan bo'lsa natija o'giriladi.

    Yozuv `use(LATIN_NEW)` bilan shu jarayonga qo'yiladi (bot: `UzScriptMiddleware`, sayt: `web_jobs`).
    """
    import functools
    import inspect

    def wrap(func):
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                result = await func(*args, **kwargs)
                if current() == LATIN_NEW and isinstance(result, str):
                    import asyncio
                    await asyncio.to_thread(normalize_file, result, LATIN_NEW)
                return result
            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            if current() == LATIN_NEW and isinstance(result, str):
                normalize_file(result, LATIN_NEW)
            return result
        return sync_wrapper

    for name, func in list(vars(cls).items()):
        if name.startswith("__") or not inspect.isfunction(func):   # staticmethod va h.k. tegilmaydi
            continue
        if name in names or (prefix and name.startswith(prefix)):
            setattr(cls, name, wrap(func))
