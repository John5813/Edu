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
LIMITS = dict(title=64, kicker=28, subtitle=96, point=118, value=14, label=54, name=30, text=78, notes=420)

SYSTEM = """You write a stunning, factual educational presentation in which every slide shows REAL 3D models
(museum scans and detailed models). Write ALL text in the client's language. Use only facts you are sure
about — no invented numbers, dates or names.
The 3D models illustrate the topic; they are not precise diagrams: never describe or point at exact parts
of a model.

Exactly {count} slides. Slide 1 layout "muqova", the last slide "yakun". Between them use varied layouts:
- "chap" or "ong": title + 3-4 points; 1 model (text left / right).
- "qahramon": 1 model shown very large; title + 2 short points.
- "raqamlar": 2-4 stats (well-known values: dates, sizes, counts) + 1 model.
- "uchlik": exactly 3 models side by side; "items": 3 × {{model, name, text}}.
- "yakun": 2-3 takeaway points; 2-4 models shown together.
Never the same layout twice in a row. Use each model at least once when possible, put the most relevant
model on the cover, and sometimes keep a model on 2 neighbouring slides — it flies and turns between them.
Every model must match its slide's content.
Lengths: title ≤ 60 chars, kicker (short section name) ≤ 26, subtitle ≤ 90, point ≤ 110, stat value ≤ 12,
stat label ≤ 50, item name ≤ 28, item text ≤ 75. "notes": 2-3 sentences for the presenter.
Also choose one design "style" for the whole deck:
{styles}
Return ONLY JSON: {{"style": "key", "slides": [{{"layout": "...", "kicker": "...", "title": "...",
"subtitle": "...", "points": ["..."], "stats": [{{"value": "...", "label": "..."}}],
"items": [{{"model": "m1", "name": "...", "text": "..."}}], "models": ["m0"], "notes": "..."}}]}}"""

USER = """Topic: {topic}
Audience: {level}
Language: {language_rule}
{extra}
3D MODELS (code | Uzbek name | original name | subject):
{models}
"""

REVIEW_SYSTEM = """You are a fact-checker for an educational presentation. You get slides as JSON
[{"i": 0, "title": "...", "points": [...], "stats": [{"value": "...", "label": "..."}]}].
Fix ONLY factual errors (wrong dates, numbers, names) in the same language; keep length and meaning.
If a stat is doubtful and you cannot fix it reliably, set its value to "". Return everything else unchanged.
Return ONLY JSON: {"slides": [{"i": 0, "title": "...", "points": [...], "stats": [...]}]}"""


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
    return ai.call_json(system, user, 1200 + 420 * count, language=language, model=ai.MODEL)


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


def normalize(data: dict, count: int, ids: Sequence[str], codes: Dict[str, str]) -> dict:
    """AI rejasini tekshiradi va tuzatadi: kompozitsiya, matn uzunligi, modellar soni va hajmi."""
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
            lay = "chap"
        want = [codes.get(str(c).strip()) for c in (s.get("models") or [])]
        want = [m for m in want if m in allowed]
        out = {"layout": lay, "kicker": _clip(s.get("kicker"), LIMITS["kicker"]),
               "title": _clip(s.get("title"), LIMITS["title"]),
               "subtitle": _clip(s.get("subtitle"), LIMITS["subtitle"]),
               "notes": _clip(s.get("notes"), LIMITS["notes"]),
               "points": [_clip(p, LIMITS["point"]) for p in (s.get("points") or []) if str(p or "").strip()][:4],
               "stats": [], "items": []}
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
                        from services import katalog3d
                        items.append({"model": mid, "name": _clip(katalog3d.katalog()[mid]["nom_uz"], LIMITS["name"]),
                                      "text": ""})
            if len(items) < 3:
                lay = out["layout"] = "chap"
            else:
                out["items"] = items[:3]
                out["models"] = [i["model"] for i in out["items"]]
        if lay == "raqamlar" and len(out["stats"]) < 2:
            lay = out["layout"] = "chap"
        if lay != "uchlik":
            n = {"muqova": 2 if len(ids) > 1 and len(want) > 1 else 1, "yakun": min(4, max(2, len(want))) if len(ids) > 1 else 1}.get(lay, 1)
            out["models"] = pick(min(n, len(ids)), want)
        if lay in ("chap", "ong", "qahramon", "raqamlar") and not out["points"] and lay != "raqamlar":
            out["points"] = [out["subtitle"]] if out["subtitle"] else []
        for m in out["models"]:
            used[m] += 1
        slides.append(out)
    # Ketma-ket bir xil kompozitsiya bo'lmasin (matn tomoni almashadi — model slayd bo'ylab suzadi).
    for k in range(1, len(slides)):
        if slides[k]["layout"] == slides[k - 1]["layout"] and slides[k]["layout"] in ("chap", "ong", "qahramon"):
            slides[k]["layout"] = "ong" if slides[k - 1]["layout"] == "chap" else "chap"
    style = str(data.get("style") or "").strip()
    return {"style": style if style in STYLES else "", "slides": slides}


def review(plan: dict, language: str) -> int:
    """Ikkinchi o'qish: faktlardagi xatolar (sana, raqam, nom). Ishlamasa — reja o'zgarmaydi."""
    import json

    payload = json.dumps([{"i": i, "title": s["title"], "points": s["points"], "stats": s["stats"]}
                          for i, s in enumerate(plan["slides"])], ensure_ascii=False)
    try:
        data = ai.call_json(REVIEW_SYSTEM, payload, 300 * len(plan["slides"]), language=language,
                            where="3D katalog tekshiruv", temperature=0.1)
    except Exception as exc:                          # noqa: BLE001
        log.warning("3D katalog: fakt tekshiruvi o'tmadi (%s)", exc)
        return 0
    fixed = 0
    for row in data.get("slides") or []:
        try:
            s = plan["slides"][int(row["i"])]
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        title = _clip(row.get("title"), LIMITS["title"])
        if title and title != s["title"]:
            s["title"], fixed = title, fixed + 1
        pts = [_clip(p, LIMITS["point"]) for p in (row.get("points") or []) if str(p or "").strip()]
        if pts and len(pts) == len(s["points"]) and pts != s["points"]:
            s["points"], fixed = pts, fixed + 1
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
                    s["layout"] = "chap"
                    if not s["points"]:
                        s["points"] = [f"{st['value']} — {st['label']}" for st in new]
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
