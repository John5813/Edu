"""Mavzu bo'yicha katalogdan mos 3D modellarni topish (to'lovdan oldin, mavzu yozilishi bilan).

1. AI mavzuni kalit so'zlarga yoyadi (o'zbekcha va inglizcha: joy, davr, buyum, jonzot nomlari).
2. Katalogdagi modellar (serverdagilari va avtomatik yuklab olinadiganlari) nomi va teglari bo'yicha ball
   oladi — eng yaxshi 80 tasi.
3. AI ulardan mavzuga haqiqatan mosini tanlaydi: «asosiy» (mavzuning o'zi) va «yordamchi» (shu mavzuni
   ko'rsatishga yaraydigan yaqin buyum). Kamida bitta asosiy yoki uchta yordamchi bo'lsa — 3D taqdimot bo'ladi.

AI ishlamasa — faqat model nomida mavzuning aniq so'zi borlari olinadi (umumiy «qadimgi», «davri» yetmaydi).
"""
import io
import logging
import re
from typing import Dict, List, Optional, Sequence

from . import ai

log = logging.getLogger(__name__)

CANDIDATES = 80
MAX_PICK = 12
MAX_MB = 15.0                 # bitta modeldan og'iri taqdimotga olinmaydi (Telegram 50 MB chegarasi)
_STOP = {"va", "bilan", "uchun", "haqida", "hamda", "ham", "the", "of", "and", "in", "a", "an", "to", "for",
         "on", "de", "la", "le", "и", "в", "на", "о", "об", "по", "для", "с", "из", "mavzu", "taqdimot",
         "presentation", "тема", "презентация"}
# Mavzuni "ramkalaydigan" umumiy so'zlar: «Dinozavrlar davri», «Qadimgi Misr», «Avtomobil tarixi». Ular ko'p
# model nomida bor (qadimgi it, bronza davri...) — ballda kam vaznli, AI ishlamaganda esa hisobga olinmaydi.
_FRAME = {"qadimgi", "qadimiy", "qadim", "davr", "davri", "davrida", "davrlar", "davrlari", "asr", "asrlar", "asrda",
          "tarix", "tarixi", "tarixiy", "zamon", "zamonaviy", "tur", "turi", "turlari", "tuzilishi", "ahamiyati",
          "rivojlanish", "rivojlanishi", "xususiyatlari", "umumiy", "asosiy", "asoslari", "dunyo", "dunyosi", "olam",
          "olami", "hayot", "hayoti", "madaniyat", "madaniyati", "sivilizatsiya", "sivilizatsiyasi", "yangi", "buyuk",
          "mashhur", "ancient", "old", "history", "historical", "era", "age", "ages", "period", "modern", "type",
          "types", "world", "life", "culture", "civilization", "great", "famous", "new", "introduction", "basics",
          "древний", "древние", "древнего", "история", "истории", "эпоха", "эпохи", "век", "века", "мир",
          "мира", "жизнь", "культура", "цивилизация", "современный", "виды"}
_APOS = re.compile(r"[ʻʼ'`‘’]")
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def _tokens(text: str) -> List[str]:
    return [w for w in _WORD.findall(_APOS.sub("", str(text or "").lower())) if len(w) > 1 and w not in _STOP]


def _match(word: str, key: str) -> bool:
    """Qo'shimchalarga chidamli moslik: «misrlik» ~ «misr», «pyramids» ~ «pyramid»."""
    if word == key:
        return True
    if len(key) < 4 or len(word) < 4:
        return False
    stem = key[:max(4, len(key) - 2)]
    return word.startswith(stem) or key.startswith(word[:max(4, len(word) - 2)])


EXPAND_SYSTEM = """You help find 3D models for a school/university presentation.
Given a topic (any language), list search keywords that a museum/3D-model catalog would use for objects
that SHOW this topic: concrete places, buildings, artefacts, organisms, machines, instruments, people,
foods — and the general field. Include synonyms and singular nouns. No weapons.
Return ONLY JSON: {"en": ["15-30 English keywords"], "uz": ["10-20 Uzbek (Latin) keywords"],
"fan": ["1-3 of: tarix, biologiya, geografiya, fizika, kimyo, astronomiya, texnika, informatika, san'at,
arxitektura, musiqa, oshxona, transport, sport, tibbiyot, adabiyot, matematika"]}"""

SELECT_SYSTEM = """You choose real 3D models for a presentation on the given topic.
Candidates are lines "code | Uzbek name | original name | subject".
- "asosiy": the model directly shows the topic's subject (the place, artefact, organism, machine, person or
  object the topic is about, or a clear part of it).
- "yordamchi": not the subject itself but a clearly related item a teacher would gladly show in THIS
  presentation (same culture, era, field or process).
Never include unrelated models that only share a word, toys, or weapons. Order each list by usefulness.
At most 8 asosiy and 8 yordamchi.
Return ONLY JSON: {"asosiy": ["c3", ...], "yordamchi": ["c9", ...]}"""


def expand(topic: str, language: str = "uz") -> dict:
    user = f"Topic: {topic}\n"
    data = ai.call_json(EXPAND_SYSTEM, user, 500, language=language, model=ai.SEARCH_MODEL,
                        where="3D katalog qidiruv", temperature=0.2)
    words = []
    for key in ("en", "uz"):
        words += [str(w) for w in (data.get(key) or []) if isinstance(w, (str, int))]
    fan = [str(f) for f in (data.get("fan") or []) if isinstance(f, str)]
    return {"words": words, "fan": fan}


def score(topic: str, words: Sequence[str], fan: Sequence[str] = (), limit: int = CANDIDATES,
          available: Optional[frozenset] = None) -> List[tuple]:
    """[(ball, id)] — katalog modellarining kalit so'zlarga mosligi (eng yuqorisi birinchi)."""
    from services import katalog3d

    keys = []
    for w in [topic, *words]:
        for t in _tokens(w):
            if t not in keys:
                keys.append(t)
    if not keys:
        return []
    if available is None:
        from . import yukla

        available = yukla.mumkin()           # diskdagilar + avtomatik yuklab olinadiganlar
    have = available
    out = []
    for mid, m in katalog3d.katalog().items():
        if mid not in have or m.get("hajm", 0) > MAX_MB * 1e6:
            continue
        name = _tokens(m.get("nom_uz", "") + " " + m.get("nom", ""))
        tags = _tokens(" ".join(m.get("kalit", [])))
        total = 0.0
        for k in keys:
            weight = 0.3 if k in _FRAME else 1.0
            if any(_match(t, k) for t in name):
                total += 3 * weight
            elif any(_match(t, k) for t in tags):
                total += weight
        if total and m.get("fan") in fan:
            total += 0.5
        if total:
            out.append((total + m.get("sifat", 0) * 0.05, mid))
    out.sort(reverse=True)
    return out[:limit]


def select(topic: str, ids: Sequence[str], language: str = "uz") -> Dict[str, List[str]]:
    from services import katalog3d

    cat = katalog3d.katalog()
    codes = {f"c{i}": mid for i, mid in enumerate(ids)}
    lines = "\n".join(f"{c} | {cat[m]['nom_uz']} | {cat[m]['nom'][:70]} | {cat[m]['fan']}" for c, m in codes.items())
    data = ai.call_json(SELECT_SYSTEM, f"Topic: {topic}\n\nCandidates:\n{lines}\n", 400, language=language,
                        model=ai.SEARCH_MODEL, where="3D katalog qidiruv", temperature=0.1)
    out: Dict[str, List[str]] = {}
    seen = set()
    for key in ("asosiy", "yordamchi"):
        out[key] = []
        for c in data.get(key) or []:
            mid = codes.get(str(c).strip())
            if mid and mid not in seen:
                seen.add(mid)
                out[key].append(mid)
    return out


def by_name(topic: str, ids: Sequence[str], limit: int = 6) -> List[str]:
    """AIsiz tanlov (ehtiyotkor): model nomida mavzuning aniq so'zlari bor — 1-2 so'zli mavzuda hammasi,
    uzunida kamida ikkitasi («Qadimgi Misr» → misr; «qadimgi» yetmaydi; «Samarqand me'morchiligi» uchun
    London bezagi olinmaydi). Ko'proq so'zi mos kelgani birinchi."""
    from services import katalog3d

    cat = katalog3d.katalog()
    keys = [k for k in dict.fromkeys(_tokens(topic)) if k not in _FRAME]
    need = min(len(keys), 2)
    found = []
    for order, mid in enumerate(ids):
        name = _tokens(cat[mid].get("nom_uz", "") + " " + cat[mid].get("nom", ""))
        hits = sum(any(_match(t, k) for t in name) for k in keys)
        if keys and hits >= need:
            found.append((-hits, order, mid))
    return [mid for *_, mid in sorted(found)[:limit]]


def top(topic: str, language: str = "uz") -> dict:
    """Mavzu tekshiruvi: {ok, ids (taqdimot uchun, muhimi birinchi), asosiy, checked}.

    ok — taqdimot qilish mumkin (kamida 1 asosiy yoki 3 yordamchi model)."""
    try:
        exp = expand(topic, language)
    except Exception as exc:                          # noqa: BLE001
        log.warning("3D katalog: kalit so'zlar olinmadi (%s) — faqat mavzu so'zlari", exc)
        exp = {"words": [], "fan": []}
    ranked = score(topic, exp["words"], exp["fan"])
    if not ranked:
        return {"ok": False, "ids": [], "asosiy": [], "checked": True}
    try:
        picked = select(topic, [mid for _, mid in ranked], language)
    except Exception as exc:                          # noqa: BLE001
        log.warning("3D katalog: AI tanlovi o'tmadi (%s) — nom bo'yicha", exc)
        strong = by_name(topic, [mid for _, mid in ranked])
        return {"ok": bool(strong), "ids": strong, "asosiy": strong, "checked": False}
    asosiy, yordamchi = picked["asosiy"], picked["yordamchi"]
    ok = len(asosiy) >= 1 or len(yordamchi) >= 3
    ids = (asosiy + yordamchi)[:MAX_PICK]
    log.info("3D katalog: «%s» — %d nomzod, %d asosiy, %d yordamchi", topic, len(ranked), len(asosiy),
             len(yordamchi))
    return {"ok": ok, "ids": ids if ok else [], "asosiy": asosiy if ok else [], "checked": True}


def collage(ids: Sequence[str], language: str = "uz", limit: int = 8) -> Optional[bytes]:
    """Topilgan modellar rasmi (mijozga to'lovdan oldin ko'rsatiladi): 4 ustunli to'r, ostida nomi."""
    from PIL import Image, ImageDraw, ImageFont

    from services import katalog3d

    cat = katalog3d.katalog()
    items = [(i, katalog3d.preview_yoli(i)) for i in ids[:limit]]
    items = [(i, p) for i, p in items if p]
    if not items:
        return None
    cols = min(4, len(items))
    rows = (len(items) + cols - 1) // cols
    cell, label = 300, 46
    sheet = Image.new("RGB", (cols * cell, rows * (cell + label)), (242, 242, 240))
    draw = ImageDraw.Draw(sheet)
    font = None
    for name in ("DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "arial.ttf"):
        try:
            font = ImageFont.truetype(name, 17)
            break
        except OSError:
            continue
    font = font or ImageFont.load_default()
    for k, (mid, path) in enumerate(items):
        x, y = (k % cols) * cell, (k // cols) * (cell + label)
        with Image.open(path) as im:
            sheet.paste(im.convert("RGB").resize((cell, cell)), (x, y))
        name = cat[mid]["nom_uz"] if language in ("uz", "uz_cyrl", "kk") else cat[mid]["nom"]
        name = name if len(name) <= 30 else name[:29] + "…"
        draw.text((x + 10, y + cell + 12), name, fill=(40, 40, 46), font=font)
    buf = io.BytesIO()
    sheet.save(buf, "JPEG", quality=85)
    return buf.getvalue()
