"""Word hujjati matnidagi formulalar.

Aniq fan mavzusida model formulani LaTeX bilan `$...$` ichida, matritsa va determinantni esa
`$$\\begin{vmatrix} a & b \\\\ c & d \\end{vmatrix}$$` ko'rinishida yozadi (`ai_service.math_rule`).
Hujjatda LaTeX ni hech kim o'qib bermaydi, shuning uchun:

- qator ichidagi formula Unicode belgilarga o'giriladi: $a_{11} \\cdot a_{22}$ → a₁₁ · a₂₂;
- alohida qatordagi formula (`$$...$$`) markazda turadi; ichidagi matritsa qatorlari va ustunlari
  saqlanadi — hujjat yozuvchisi uni chegarasiz jadval qilib chizadi (`segments`).

Ilgari formulalar oddiy matn bo'lib tozalanardi va "A = a b c d", "(2 5) - (3 4)" bo'lib qolardi.
"""
import re
from typing import List, Tuple

from services.premium_presentation import deck_math

_ENV = re.compile(r"\\begin\{([pbvVB]?matrix|array)\}(?:\{[^{}]*\})?(.*?)\\end\{\1\}", re.DOTALL)
_DISPLAY = re.compile(r"\$\$(.+?)\$\$|\\\[(.+?)\\\]", re.DOTALL)
_INLINE = re.compile(r"\$([^$\n]+)\$|\\\((.+?)\\\)", re.DOTALL)
# `$` ichida haqiqatan formula bormi: "$5 va $10" kabi narx formula emas.
_MATHY = re.compile(r"[\\^_=+*/<>|]|^\s*[A-Za-z]{1,3}\s*$|\d\s*-\s*\d")

BRACKETS = {"pmatrix": ("(", ")"), "bmatrix": ("[", "]"), "vmatrix": ("|", "|"), "Vmatrix": ("‖", "‖"),
            "Bmatrix": ("{", "}"), "matrix": ("", ""), "array": ("", "")}


def _rows(body: str) -> List[List[str]]:
    rows = []
    for line in re.split(r"\\\\", body):
        line = re.sub(r"\\hline", "", line).strip()
        if line:
            rows.append([deck_math.plain(cell.strip()) for cell in line.split("&")])
    width = max((len(r) for r in rows), default=0)
    return [r + [""] * (width - len(r)) for r in rows]


def _linear(match) -> str:
    left, right = BRACKETS[match.group(1)]
    rows = _rows(match.group(2))
    return left + "; ".join(" ".join(cell for cell in row) for row in rows) + right


def plain(latex: str) -> str:
    """Bitta formula → bir qatorli matn (matritsa "|a b; c d|" bo'ladi)."""
    text = _ENV.sub(lambda m: "\x00" + _linear(m) + "\x00", latex or "")
    parts = text.split("\x00")
    # Matritsa allaqachon o'girilgan — qolgan bo'laklar o'giriladi.
    return "".join(part if index % 2 else deck_math.plain(part) for index, part in enumerate(parts)).strip()


def segments(latex: str) -> List[Tuple]:
    """Alohida qatordagi formula bo'laklari: ("text", matn) yoki ("matrix", tur, qatorlar)."""
    out: List[Tuple] = []
    at = 0
    for match in _ENV.finditer(latex or ""):
        before = deck_math.plain(latex[at:match.start()])
        if before:
            out.append(("text", before))
        rows = _rows(match.group(2))
        if rows:
            out.append(("matrix", match.group(1), rows))
        at = match.end()
    after = deck_math.plain((latex or "")[at:])
    if after:
        out.append(("text", after))
    return out


def inline(text: str) -> str:
    """Abzatsdagi qator ichidagi formulalarni belgilarga o'giradi; formula bo'lmagan `$` tegilmaydi."""
    def one(match):
        body = next(g for g in match.groups() if g is not None)
        return plain(body) if _MATHY.search(body) else match.group(0)

    return _INLINE.sub(one, text or "")


def blocks(paragraph: str) -> List[Tuple[str, str]]:
    """Abzatsni bo'laklaydi: ("text", matn) va alohida qatordagi formula ("math", latex).

    Abzats faqat bitta `$...$` dan iborat bo'lsa ham u alohida formula sanaladi.
    """
    paragraph = (paragraph or "").strip()
    whole = _INLINE.fullmatch(paragraph)
    if whole and _MATHY.search(next(g for g in whole.groups() if g is not None)):
        return [("math", next(g for g in whole.groups() if g is not None))]
    out: List[Tuple[str, str]] = []
    at = 0
    for match in _DISPLAY.finditer(paragraph):
        before = paragraph[at:match.start()].strip()
        if before:
            out.append(("text", inline(before)))
        out.append(("math", next(g for g in match.groups() if g is not None)))
        at = match.end()
    rest = paragraph[at:].strip()
    if rest:
        # Qator ichidagi matritsa ham alohida qatorga chiqadi — bir qatorda o'qib bo'lmaydi.
        inner = [m for m in _INLINE.finditer(rest) if _ENV.search(next(g for g in m.groups() if g is not None))]
        pos = 0
        for match in inner:
            before = rest[pos:match.start()].strip()
            if before:
                out.append(("text", inline(before)))
            out.append(("math", next(g for g in match.groups() if g is not None)))
            pos = match.end()
        tail = rest[pos:].strip()
        if tail:
            out.append(("text", inline(tail)))
    return out
