"""Mijoz materialidan slaydga mos qismni tanlash (AI'siz).

Slayd so'roviga materialning faqat 4000 belgisi sig'adi. Ilgari doim BOSHI berilardi: 60 000 belgilik ma'ruza
matnining 1,5–2 sahifasi ishlatilib, qolgani slaydlarga yetib bormasdi. Endi material bo'laklarga bo'linadi va
har slayd guruhi uchun uning sarlavha va mazmuniga eng ko'p so'z o'zagi mos keladigan bo'laklar tanlanadi
(asl tartibda). O'zak — so'zning dastlabki 5 harfi: o'zbek va qozoq tilidagi qo'shimchalar («iqtisodiyotning»,
«iqtisodiy») bir o'zakka tushadi.
"""
import math
import re
from typing import List

CHUNK = 650                   # bo'lak uzunligi (belgi)
_WORD = re.compile(r"[^\W\d_]{4,}", re.UNICODE)
_STOP = {"bilan", "uchun", "hamda", "yoki", "lekin", "ammo", "bu", "shu", "ular", "that", "this", "with", "from",
         "which", "have", "were", "also", "этот", "также", "который", "которые", "были", "было", "для", "как"}


def _stems(text: str) -> set:
    clean = (text or "").lower().replace("ʻ", "'").replace("‘", "'").replace("’", "'").replace("'", "")
    return {w[:5] for w in _WORD.findall(clean) if w not in _STOP}


def chunks(text: str, size: int = CHUNK) -> List[str]:
    """Material → taxminan `size` belgilik bo'laklar (xatboshi, kerak bo'lsa gap chegarasida)."""
    parts: List[str] = []
    for para in re.split(r"\n\s*\n|\n(?=\s*[-•*\d]+[.)]?\s)", text or ""):
        para = para.strip()
        if not para:
            continue
        while len(para) > size * 2:                     # juda uzun xatboshi — gap chegarasida bo'linadi
            cut = para.rfind(". ", 0, size * 2)
            cut = cut + 1 if cut > size // 2 else size * 2
            parts.append(para[:cut].strip())
            para = para[cut:].strip()
        parts.append(para)
    out: List[str] = []
    for part in parts:                                   # kichik xatboshilar qo'shilib bo'lak bo'ladi
        if out and len(out[-1]) + len(part) < size:
            out[-1] = out[-1] + "\n" + part
        else:
            out.append(part)
    return out


def excerpt(text: str, query: str, limit: int = 4000) -> str:
    """Materialdan `query` ga (slayd sarlavhalari va mazmuni) eng mos qism, `limit` belgigacha, asl tartibda.

    Material qisqa bo'lsa — butunligicha; mos so'z umuman yo'q bo'lsa — boshidan."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    pieces = chunks(text)
    want = _stems(query)
    scored = []
    for index, piece in enumerate(pieces):
        have = _stems(piece)
        score = len(have & want) / math.sqrt(len(have) + 4) if want else 0.0
        scored.append((score, index))
    if not any(score > 0 for score, _ in scored):
        return text[:limit]
    chosen, used = set(), 0
    for score, index in sorted(scored, key=lambda x: (-x[0], x[1])):
        size = len(pieces[index]) + 3
        if used + size > limit:
            continue
        chosen.add(index)
        used += size
    return "\n…\n".join(pieces[i] for i in sorted(chosen))
