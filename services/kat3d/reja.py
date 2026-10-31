"""AI slaydlar rejasi: kompozitsiya, matn, raqamlar va har slaydda qaysi 3D model.

Katalog modellari mavzuni ko'rsatadi, lekin aniq sxema emas (anatomik atlas kabi emas) — shuning uchun
modelning qismlari yorliq-chiziqlar bilan nomlanmaydi; matn alohida, model — slaydning "qahramoni".
"""
import logging
import os
import re
from typing import Dict, List, Optional, Sequence

from . import ai
from .uslub import LAYOUTS, STYLES, style_guide

log = logging.getLogger(__name__)

LIMIT_MB = float(os.getenv("KAT3D_MAX_MB") or 42)    # Telegram bot 50 MB dan kattasini yubormaydi
REVIEW_ON = os.getenv("KAT3D_REVIEW", "1") != "0"
LEVELS = {1: "school pupils (simple words)", 2: "university students", 3: "academic audience (precise terms)"}
LIMITS = dict(title=70, kicker=28, subtitle=190, point=165, value=14, label=60, name=30, text=150, notes=900,
              para=440, date=18, event=125, col=30, col_point=115, quote=200, source=60, card=34, card_text=150,
              question=120, answer=430, step=44, step_text=140, table_cell=40)
MAX_POINTS = {"chap": 5, "ong": 5, "qahramon": 3, "raqamlar": 2, "yakun": 4}
BULLET_LAYOUTS = ("chap", "ong")

SYSTEM = """You write a rich, factual educational presentation in which every slide shows REAL 3D models
(museum scans and detailed models). Write ALL text in the client's language. Use only facts you are sure
about — no invented numbers, dates, names or quotes.
The 3D models illustrate the topic; they are not precise diagrams: never describe or point at exact parts
of a model.

The deck must be TEXT-RICH (students read and present from it) and VARIED: every slide has its own design
and its own kind of text. Do NOT make every slide a bullet list of the same size: mix prose paragraphs,
timelines, comparisons, cards, steps, numbers, a key idea, a question — and mix dense slides with lighter
ones. Sentences are complete and informative (facts, causes, examples, significance).

Exactly {count} slides. Slide 1 "muqova", the last slide "yakun". Every slide in between uses a DIFFERENT
layout (repeat only when there are more slides than layouts; never twice in a row). Bullet lists ("chap",
"ong") at most twice in the whole deck. Choose the layout that suits the content:
- "matn": prose, NO bullets — "paragraphs": 2 paragraphs of 2-3 sentences (200-420 chars each).
- "chap" / "ong": bullet list — "subtitle" (1-2 sentence intro, 100-180 chars) + 3-5 "points" (90-160 chars).
- "xronologiya": timeline — 3-5 "events" {{"date", "text" (1 sentence, ≤ 120 chars)}} in time order.
- "taqqoslash": comparison of two things, periods or sides — "columns": exactly 2 × {{"name", "points": 2-4
  (≤ 110 chars)}}.
- "kartalar": 3-4 "cards" {{"title", "text" (1-2 sentences, ≤ 150 chars)}} — types, features, aspects.
- "bosqichlar": a process or sequence — 3-5 "steps" {{"title", "text" (1 sentence, ≤ 135 chars)}}.
- "fikr": one key idea, or a famous, well-documented quote — "quote" (≤ 190 chars), "source" (author of the
  quote, or "" for a key idea), "text" (2-3 sentences explaining it).
- "savol": an intriguing "question" (≤ 110 chars, "Did you know...?" style) + "answer" (3-4 sentences, ≤ 420).
- "raqamlar": 2-4 "stats" {{"value" (≤ 12), "label" (≤ 55)}} (well-known values) + 1-2 "points" explaining them.
- "qahramon": the model shown very large — "subtitle" (1 sentence) + 2-3 "points".
- "jadval": a comparison table (countries, types, periods) — "table": {{"head": [3-4 column names],
  "rows": [3-5 rows of short cells, ≤ 30 chars each]}}.
- "uchlik": 3 models side by side — "items": 3 × {{"model", "name" (≤ 28), "text" (1-2 sentences, ≤ 150)}}.
- "yakun": 3-4 takeaway "points"; 2-4 models shown together.
Every slide except "uchlik" and "yakun" shows 1 model. Use each model at least once when possible, put the
most relevant model on the cover, and sometimes keep a model on 2 neighbouring slides — it flies and turns
between them. Every model must match its slide's content.
Lengths: title ≤ 65 chars, kicker (short section name) ≤ 26, cover "subtitle" ≤ 150. "notes": 4-6
sentences for the presenter (what to say, extra facts). Fill only the fields the layout uses.
Also choose one design "style" for the whole deck:
{styles}
Return ONLY JSON: {{"style": "key", "slides": [{{"layout": "...", "kicker": "...", "title": "...",
"subtitle": "...", "points": [], "paragraphs": [], "events": [], "columns": [], "cards": [], "steps": [],
"quote": "", "source": "", "text": "", "question": "", "answer": "", "stats": [], "items": [], "table": {{}},
"models": ["m0"], "notes": "..."}}]}}"""

USER = """Topic: {topic}
Audience: {level}
Language: {language_rule}
{extra}
3D MODELS (code | Uzbek name | original name | subject):
{models}
"""

REVIEW_SYSTEM = """You are a fact-checker for an educational presentation. You get slides as JSON
[{"i": 0, "title": "...", "texts": ["..."], "stats": [{"value": "...", "label": "..."}]}].
Fix ONLY factual errors (wrong dates, numbers, names, misattributed quotes) in the same language; keep length,
meaning and the number and order of "texts". If a stat is doubtful and you cannot fix it reliably, set its
value to "". Return everything else unchanged.
Return ONLY JSON: {"slides": [{"i": 0, "title": "...", "texts": [...], "stats": [...]}]}"""


def _clip(value, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip().strip("•-–— ")
    if len(text) <= limit:
        return text
    cut = text[:limit - 1].rsplit(" ", 1)[0].rstrip(",;:—-")
    return cut + "…"


def _plan_ai(topic: str, count: int, codes: Dict[str, str], language: str, level: int, preferences: str) -> dict:
    from services import katalog3d

    cat = katalog3d.katalog()
    models = "\n".join(f"{c} | {cat[m]['nom_uz']} | {cat[m]['nom'][:70]} | {cat[m]['fan']}" for c, m in codes.items())
    extra = f"Client's wishes: {preferences[:500]}\n" if preferences else ""
    user = USER.format(topic=topic, level=LEVELS.get(level, LEVELS[2]), language_rule=ai.language_rule(language),
                       extra=extra, models=models)
    system = SYSTEM.format(count=count, styles=style_guide())
    return ai.call_json(system, user, 1500 + 750 * count, language=language, model=ai.MODEL)


def _fit_size(ids: List[str], limit_mb: float = LIMIT_MB) -> List[str]:
    """Bir xil model bir marta yoziladi; hammasi birga `limit_mb` dan oshmasin (muhimlari birinchi)."""
    from services import katalog3d

    cat = katalog3d.katalog()
    kept, total = [], 0.0
    for mid in ids:
        size = cat[mid].get("hajm", 0) / 1e6
        if kept and total + size > limit_mb:
            continue
        kept.append(mid)
        total += size
    return kept


def _sentence(text: str) -> str:
    text = text.strip()
    return text if not text or text[-1] in ".!?…" else text + "."


def _pairs(raw, a: str, b: str, la: int, lb: int, limit: int) -> List[dict]:
    """[{a, b}] — ikkala maydoni to'la yozuvlar."""
    out = []
    for it in raw or []:
        if isinstance(it, dict) and str(it.get(a) or "").strip() and str(it.get(b) or "").strip():
            out.append({a: _clip(it[a], la), b: _clip(it[b], lb)})
    return out[:limit]


_SENT = re.compile(r"(?<=[.!?…])\s+")


def _table(raw) -> dict:
    """{"head": [...], "rows": [[...]]} — 2-4 ustun, ko'pi bilan 6 qator, kataklar qisqartiriladi."""
    if not isinstance(raw, dict):
        return {}
    head = [_clip(h, 28) for h in (raw.get("head") or [])][:4]
    rows = [[_clip(c, LIMITS["table_cell"]) for c in r][:len(head)] for r in (raw.get("rows") or [])
            if isinstance(r, list) and len(r) >= len(head) >= 2][:6]
    if len(head) < 2 or len(rows) < 2:
        return {}
    # O'zbekiston (yoki AI ko'rsatgan qator) jadvalda ramka bilan ajratiladi
    mark = next((k for k, r in enumerate(rows) if re.search(r"o.?zbek|узбек|uzbek", r[0], re.I)), -1)
    return {"head": head, "rows": rows, "mark": mark}


def _texts(s: dict) -> List[str]:
    """Slaydning hamma matni oddiy gaplar ro'yxati bo'lib — kompozitsiya almashganda matn yo'qolmasin."""
    out = list(s["points"]) + [t for p in s["paragraphs"] for t in _SENT.split(p)]
    out += [f"{e['date']} — {e['text']}" for e in s["events"]]
    out += [f"{c['name']}: {p}" for c in s["columns"] for p in c["points"]]
    out += [f"{c['title']} — {c['text']}" for c in s["cards"]]
    out += [f"{c['title']} — {c['text']}" for c in s["steps"]]
    if s["question"] and s["answer"]:
        out += [s["question"]] + _SENT.split(s["answer"])
    if s["quote"]:
        out += [s["quote"] + (f" ({s['source']})" if s["source"] else "")]
    if s["text"]:
        out += _SENT.split(s["text"])
    out += [f"{st['value']} — {st['label']}" for st in s["stats"]]
    if s.get("table"):
        head = s["table"]["head"]
        out += ["; ".join(f"{h}: {c}" for h, c in zip(head, r)) for r in s["table"]["rows"]]
    return [t for t in out if t.strip()]


def _as_text(s: dict, layout: str) -> None:
    """Kompozitsiyani oddiy matnliga almashtiradi: "matn" — paragraflar, "chap"/"ong" — punktlar."""
    texts = _texts(s)
    s["layout"] = layout
    if layout == "matn":
        if not s["paragraphs"]:
            half = (len(texts) + 1) // 2
            s["paragraphs"] = [p for p in (" ".join(_sentence(t) for t in texts[:half]),
                                           " ".join(_sentence(t) for t in texts[half:])) if p]
        s["paragraphs"] = [_clip(p, LIMITS["para"]) for p in s["paragraphs"]][:2]
        if not s["paragraphs"] and s["subtitle"]:
            s["paragraphs"], s["subtitle"] = [s["subtitle"]], ""
    else:
        if not s["points"]:
            s["points"] = [_clip(t, LIMITS["point"]) for t in texts if len(t) > 2]
        s["points"] = s["points"][:MAX_POINTS.get(layout, 5)]


def _valid(s: dict) -> bool:
    lay = s["layout"]
    return {"matn": bool(s["paragraphs"]),
            "xronologiya": len(s["events"]) >= 3,
            "taqqoslash": len(s["columns"]) == 2,
            "kartalar": len(s["cards"]) >= 3,
            "bosqichlar": len(s["steps"]) >= 3,
            "fikr": bool(s["quote"]),
            "savol": bool(s["question"] and s["answer"]),
            "raqamlar": len(s["stats"]) >= 2,
            "uchlik": len(s["items"]) == 3,
            "jadval": bool(s.get("table"))}.get(lay, True)


def normalize(data: dict, count: int, ids: Sequence[str], codes: Dict[str, str]) -> dict:
    """AI rejasini tekshiradi va tuzatadi: kompozitsiya va uning maydonlari, xilma-xillik (ketma-ket bir xil
    dizayn yo'q, ro'yxatli slaydlar ko'pi bilan ikkita), matn uzunligi, modellar soni va hajmi."""
    from services import katalog3d

    ids = _fit_size(list(ids))
    allowed = set(ids)
    raw = [s for s in (data.get("slides") or []) if isinstance(s, dict)][:count]
    if len(raw) < 3:
        raise RuntimeError("AI reja juda qisqa")
    used: Dict[str, int] = {m: 0 for m in ids}

    def pick(n: int, prefer: Sequence[str] = ()) -> List[str]:
        out = [m for m in prefer if m in allowed][:n]
        for m in sorted(ids, key=lambda k: (used[k], ids.index(k))):
            if len(out) >= n:
                break
            if m not in out:
                out.append(m)
        return out

    slides = []
    for k, s in enumerate(raw):
        lay = str(s.get("layout") or "").strip().lower()
        if k == 0:
            lay = "muqova"
        elif k == len(raw) - 1:
            lay = "yakun"
        elif lay not in LAYOUTS or lay in ("muqova", "yakun"):
            lay = "matn" if s.get("paragraphs") else "chap"
        want = [codes.get(str(c).strip()) for c in (s.get("models") or [])]
        want = [m for m in want if m in allowed]
        out = {"layout": lay, "kicker": _clip(s.get("kicker"), LIMITS["kicker"]),
               "title": _clip(s.get("title"), LIMITS["title"]),
               "subtitle": _clip(s.get("subtitle"), LIMITS["subtitle"]),
               "notes": _clip(s.get("notes"), LIMITS["notes"]),
               "points": [_clip(p, LIMITS["point"]) for p in (s.get("points") or []) if str(p or "").strip()][:5],
               "paragraphs": [_clip(p, LIMITS["para"]) for p in (s.get("paragraphs") or [])
                              if isinstance(p, str) and p.strip()][:2],
               "events": _pairs(s.get("events"), "date", "text", LIMITS["date"], LIMITS["event"], 5),
               "cards": _pairs(s.get("cards"), "title", "text", LIMITS["card"], LIMITS["card_text"], 4),
               "steps": _pairs(s.get("steps"), "title", "text", LIMITS["step"], LIMITS["step_text"], 5),
               "columns": [], "stats": [], "items": [], "table": _table(s.get("table")),
               "quote": _clip(s.get("quote"), LIMITS["quote"]), "source": _clip(s.get("source"), LIMITS["source"]),
               "text": _clip(s.get("text"), LIMITS["answer"]),
               "question": _clip(s.get("question"), LIMITS["question"]),
               "answer": _clip(s.get("answer"), LIMITS["answer"])}
        for col in (s.get("columns") or [])[:2]:
            if isinstance(col, dict):
                pts = [_clip(p, LIMITS["col_point"]) for p in (col.get("points") or []) if str(p or "").strip()][:4]
                if str(col.get("name") or "").strip() and pts:
                    out["columns"].append({"name": _clip(col["name"], LIMITS["col"]), "points": pts})
        for st in (s.get("stats") or [])[:4]:
            if isinstance(st, dict) and str(st.get("value") or "").strip() and str(st.get("label") or "").strip():
                out["stats"].append({"value": _clip(st["value"], LIMITS["value"]),
                                     "label": _clip(st["label"], LIMITS["label"])})
        if lay == "uchlik":
            items = []
            for it in (s.get("items") or []):
                if not isinstance(it, dict):
                    continue
                mid = codes.get(str(it.get("model") or "").strip())
                if mid in allowed and mid not in [i["model"] for i in items]:
                    items.append({"model": mid, "name": _clip(it.get("name"), LIMITS["name"]),
                                  "text": _clip(it.get("text"), LIMITS["text"])})
            if len(items) < 3 and len(ids) >= 3:
                for mid in pick(3, [i["model"] for i in items]):
                    if mid not in [i["model"] for i in items]:
                        items.append({"model": mid, "name": _clip(katalog3d.katalog()[mid]["nom_uz"], LIMITS["name"]),
                                      "text": ""})
            if len(items) >= 3:
                out["items"] = items[:3]
                out["models"] = [i["model"] for i in out["items"]]
        if not _valid(out):                           # maydonlari to'lmagan kompozitsiya — oddiy matnliga
            _as_text(out, "matn" if out["paragraphs"] or len(_texts(out)) <= 2 else "chap")
        lay = out["layout"]
        if lay != "uchlik":
            n = {"muqova": 2 if len(ids) > 1 and len(want) > 1 else 1,
                 "yakun": min(4, max(2, len(want))) if len(ids) > 1 else 1}.get(lay, 1)
            out["models"] = pick(min(n, len(ids)), want)
        if lay in ("chap", "ong", "qahramon") and not out["points"] and out["subtitle"]:
            out["points"], out["subtitle"] = [out["subtitle"]], ""
        for m in out["models"]:
            used[m] += 1
        slides.append(out)
    _vary(slides)
    for s in slides:                                    # kompozitsiya sig'diradigan punktlar soni
        limit = MAX_POINTS.get(s["layout"], 5)
        if len(s["points"]) > limit:
            s["points"] = s["points"][:limit]
    style = str(data.get("style") or "").strip()
    return {"style": style if style in STYLES else "", "slides": slides}


def _vary(slides: List[dict]) -> None:
    """Har varoq boshqacha: ro'yxatli slaydlar ko'pi bilan 2 ta (ortig'i paragraflarga), ketma-ket bir xil
    kompozitsiya yo'q (chap↔ong almashadi, boshqasi oddiy matnga o'tadi)."""
    inner = slides[1:-1]
    bullets = [s for s in inner if s["layout"] in BULLET_LAYOUTS]
    allowed = max(2, len(inner) // 5)
    for s in bullets[allowed:]:
        _as_text(s, "matn")
    for k in range(2, len(slides) - 1):
        prev, cur, nxt = slides[k - 1], slides[k], slides[k + 1]
        if cur["layout"] != prev["layout"]:
            continue
        if cur["layout"] in BULLET_LAYOUTS:
            cur["layout"] = "ong" if prev["layout"] == "chap" else "chap"
        elif cur["layout"] != "matn":
            _as_text(cur, "matn")
        elif sum(s["layout"] in BULLET_LAYOUTS for s in inner) < allowed:
            _as_text(cur, "ong" if k % 2 else "chap")
        elif "qahramon" not in (prev["layout"], nxt["layout"]):
            _as_text(cur, "chap")
            cur["layout"] = "qahramon"                 # katta model + qisqa kirish va punktlar kartada
            if not cur["subtitle"] and len(cur["points"]) > 1:
                cur["subtitle"] = cur["points"].pop(0)


def _slots(s: dict) -> List[tuple]:
    """Fakt tekshiruvi uchun slayddagi har matn joyi: (maydon, indeks, kalit)."""
    out = [("points", i, None) for i in range(len(s["points"]))]
    if s.get("table"):
        out += [("table", i, j) for i in range(len(s["table"]["rows"])) for j in range(len(s["table"]["head"]))]
    out += [("paragraphs", i, None) for i in range(len(s["paragraphs"]))]
    for key, sub in (("events", "date"), ("events", "text"), ("cards", "text"), ("steps", "text"),
                     ("items", "text")):
        out += [(key, i, sub) for i in range(len(s[key]))]
    out += [("columns", i, j) for i, c in enumerate(s["columns"]) for j in range(len(c["points"]))]
    out += [(key, None, None) for key in ("subtitle", "quote", "source", "text", "question", "answer") if s[key]]
    return out


def _get(s: dict, slot: tuple) -> str:
    key, i, sub = slot
    if i is None:
        return s[key]
    if key == "columns":
        return s[key][i]["points"][sub]
    if key == "table":
        return s[key]["rows"][i][sub]
    return s[key][i] if sub is None else s[key][i][sub]


def _put(s: dict, slot: tuple, value: str) -> None:
    key, i, sub = slot
    if i is None:
        s[key] = value
    elif key == "columns":
        s[key][i]["points"][sub] = value
    elif key == "table":
        s[key]["rows"][i][sub] = value
    elif sub is None:
        s[key][i] = value
    else:
        s[key][i][sub] = value


_SLOT_LIMIT = {"points": "point", "paragraphs": "para", "subtitle": "subtitle", "quote": "quote",
               "source": "source", "text": "answer", "question": "question", "answer": "answer"}
_SUB_LIMIT = {("events", "date"): "date", ("events", "text"): "event", ("cards", "text"): "card_text",
              ("steps", "text"): "step_text", ("items", "text"): "text"}


def review(plan: dict, language: str) -> int:
    """Ikkinchi o'qish: faktlardagi xatolar (sana, raqam, nom, iqtibos muallifi). Ishlamasa — reja o'zgarmaydi."""
    import json

    slots = [_slots(s) for s in plan["slides"]]
    payload = json.dumps([{"i": i, "title": s["title"], "texts": [_get(s, t) for t in slots[i]], "stats": s["stats"]}
                          for i, s in enumerate(plan["slides"])], ensure_ascii=False)
    try:
        data = ai.call_json(REVIEW_SYSTEM, payload, 450 * len(plan["slides"]), language=language,
                            where="3D katalog tekshiruv", temperature=0.1)
    except Exception as exc:                          # noqa: BLE001
        log.warning("3D katalog: fakt tekshiruvi o'tmadi (%s)", exc)
        return 0
    fixed = 0
    for row in data.get("slides") or []:
        try:
            i = int(row["i"])
            s = plan["slides"][i]
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        title = _clip(row.get("title"), LIMITS["title"])
        if title and title != s["title"]:
            s["title"], fixed = title, fixed + 1
        texts = row.get("texts")
        if isinstance(texts, list) and len(texts) == len(slots[i]):
            for slot, value in zip(slots[i], texts):
                key, _, sub = slot
                limit = LIMITS["table_cell" if key == "table" else _SUB_LIMIT.get((key, sub)) or _SLOT_LIMIT.get(key)
                               or "col_point"]
                value = _clip(value, limit)
                if value and value != _get(s, slot):
                    _put(s, slot, value)
                    fixed += 1
        stats = row.get("stats")
        if isinstance(stats, list) and len(stats) == len(s["stats"]):
            new = []
            for old, st in zip(s["stats"], stats):
                value = _clip((st or {}).get("value"), LIMITS["value"]) if isinstance(st, dict) else old["value"]
                if value:
                    new.append({"value": value, "label": old["label"]})
            if new != s["stats"]:
                s["stats"], fixed = new, fixed + 1
                if s["layout"] == "raqamlar" and len(new) < 2:
                    _as_text(s, "chap")
    return fixed


def plan(topic: str, count: int, ids: Sequence[str], language: str = "uz", level: int = 2,
         preferences: str = "", style: Optional[str] = None) -> dict:
    ids = list(dict.fromkeys(ids))
    codes = {f"m{i}": mid for i, mid in enumerate(ids)}
    data = _plan_ai(topic, count, codes, language, level, preferences)
    out = normalize(data, count, ids, codes)
    if REVIEW_ON:
        n = review(out, language)
        if n:
            log.info("3D katalog: fakt tekshiruvi %d joyni tuzatdi", n)
    out["style"] = style if style in STYLES else (out["style"] or _style_for(ids))
    out["topic"] = topic
    out["language"] = language
    return out


def _style_for(ids: Sequence[str]) -> str:
    """AI uslub tanlamasa — asosiy modelning fani bo'yicha."""
    from services import katalog3d

    from .uslub import BY_FAN

    fan = katalog3d.katalog()[ids[0]].get("fan", "") if ids else ""
    return BY_FAN.get(fan, "vitrina")
