"""3D Pro taqdimotning mazmun rejasi: AI har slayd uchun joylashuv, matn va "asosiy 3D obyekt"ni beradi.

Taqdimotning kuchi — har slaydda bitta fonsiz 3D obyekt (skelet, o'pka, tanga, qal'a ...). Obyektni AI
mavzuga qarab o'zi tanlaydi: aniq mavzuda — haqiqiy narsa, mavhum mavzuda — ramziy narsa (tarozi, kalit,
kitob). Obyekt `id` bilan beriladi: qo'shni slaydlar bir xil `id` ni olsa (masalan "focus" — oldingi
obyektga yaqinlashish), rasm bir marta chiziladi va PowerPoint Morph uni bir slayddan ikkinchisiga
silliq olib o'tadi.
"""
import logging
import re
from typing import Dict, List

log = logging.getLogger(__name__)

# Joylashuvlar va har biri nima talab qilishi (kod `build.py` da).
LAYOUTS = ("cover", "callouts", "points", "table", "stats", "focus", "timeline", "conclusion")
CONTENT_LAYOUTS = ("callouts", "points", "table", "stats", "focus", "timeline")
PALETTES = ("indigo", "emerald", "violet", "crimson", "teal", "amber", "graphite")
STYLES = ("realistic", "stylized")

LIMITS = {          # (eng ko'p element, har birida so'z)
    "callouts": (4, 18),
    "points": (4, 24),
    "table": (5, 8),
    "stats": (3, 16),
    "timeline": (5, 16),
    "conclusion": (3, 16),
}

SYSTEM = """You are an award-winning presentation designer and subject expert. You plan a premium
"3D presentation": every slide is built around ONE photorealistic (or stylized) 3D object with a transparent
background — like a museum exhibit on stage — with very little, precise text around it. Slides change with
PowerPoint Morph, so objects glide between slides. Reply with JSON only."""

PROMPT = """Topic: "⟨topic⟩"
Audience: ⟨level⟩
Number of slides: exactly ⟨count⟩ (the first is "cover", the last is "conclusion").
⟨extra⟩
ALL visible text (titles, labels, texts, table cells, units) is written ⟨target⟩.
Only the object "prompt" and callout "part" fields are in English (they go to the image model).

LAYOUTS:
- "cover": title (the topic, 2-7 words), subtitle (one line, max 14 words), object.
- "callouts": the object in the centre with 2-4 labelled parts around it, lines point to the parts.
  callouts: [{"label": 1-3 words, "text": max 18 words, "part": English name of the visible part of the
  object the line points to}]. Best when the object has real, visible parts (organ, machine, building,
  plant, planet, device).
- "points": object on the left, 3-4 numbered points on the right: [{"head": 1-4 words, "text": max 24 words}].
- "table": object on the left, a short table: "columns": [2 headers], "rows": 3-5 rows of 2 cells (max 8
  words each).
- "stats": 2-3 big numbers: [{"value": number only, max 6 characters, "unit": "%"/"mln"/"km"/"" ,
  "label": 1-4 words, "text": max 16 words}] plus "text" (1 sentence, max 25 words). ONLY real, well-known
  figures you are sure about; otherwise do not use this layout.
- "focus": a close-up of the PREVIOUS slide's object (same object id — the camera zooms in):
  "lead" (max 14 words) and "text" (max 40 words) about one important detail.
- "timeline": 3-5 steps in time or order: [{"when": year/date/stage, max 3 words, "text": max 16 words}].
- "conclusion": title, "points": 3 key takeaways (max 16 words each); object: reuse the cover object id.

OBJECTS:
- "object": {"id": "o1", "prompt": "..."} — ONE concrete, physical, photogenic object, fully visible,
  described in English in 8-25 words (material, colour, key details). No scenes, no people crowds, no
  text, no logos, no flags with writing, no diagrams, no screens with text.
- For abstract ideas use a symbolic object (economy → stack of gold coins with a rising arrow sculpture;
  law → bronze scales of justice; literature → open antique book with a quill; history → the actual
  artefact, building or weapon of the period).
- MOTION — the most important rule. Slides change with PowerPoint Morph, which moves an object ONLY when
  the SAME object id is on the next slide: it glides from the centre to the left, grows into a close-up,
  shrinks into a corner. So the deck is a camera moving around a few objects: use each object id on 2-3
  CONSECUTIVE slides with different layouts (e.g. skull: "callouts" → "points" → "focus"; spine: "callouts"
  → "table"), then switch to the next object. A new object appears about every 2-3 slides; never put the same
  layout twice in a row. "focus" always reuses the previous slide's object; "conclusion" reuses the cover
  object.
- "render_style": "realistic" (science, medicine, technology, history, nature) or "stylized" (cute glossy
  clay-like 3D, for young children or playful topics).
- "palette": one of indigo, emerald, violet, crimson, teal, amber, graphite — the one that suits the topic.

CONTENT:
- The deck tells one story: from the hook, through the key parts, to the conclusion. Each slide says a
  NEW thing. Facts must be correct; prefer concrete names, numbers and examples.
- Mix layouts by content; prefer "callouts" whenever the object has visible parts (2-4 of them in a deck).
- Titles: 2-6 words, sentence case.

JSON: {"palette": "...", "render_style": "...", "slides": [{"layout": "...", "title": "...", ...,
"object": {"id": "...", "prompt": "..."}}]}"""

LEVELS = {1: "school pupils — simple words", 2: "university students", 3: "specialists — precise terms"}


def _words(text, limit: int) -> str:
    words = str(text or "").replace("\n", " ").split()
    if len(words) <= limit:
        return " ".join(words)
    cut = " ".join(words[:limit]).rstrip(",;:—-")
    return cut + "…"


def _short(text, chars: int) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text if len(text) <= chars else text[:chars - 1].rstrip() + "…"


# AI maydon nomlarini ba'zan boshqacha yozadi ("steps" o'rniga "items", "text" o'rniga "description").
# Ilgari bunday slayd bo'sh qolardi: vaqt o'qi o'rnida faqat sarlavha turardi.
_LIST_KEYS = {
    "callouts": ("callouts", "labels", "parts", "items", "points"),
    "points": ("points", "items", "bullets", "list", "steps", "callouts"),
    "stats": ("stats", "numbers", "figures", "items", "metrics"),
    "steps": ("steps", "timeline", "events", "items", "stages", "milestones", "points"),
    "rows": ("rows", "data", "table", "items"),
}
_FIELD_KEYS = {
    "label": ("label", "title", "name", "head", "heading"),
    "head": ("head", "title", "heading", "label", "name"),
    "text": ("text", "description", "desc", "detail", "details", "body", "content", "event", "value_text"),
    "part": ("part", "target", "where", "anchor", "label", "name"),
    "when": ("when", "year", "date", "period", "stage", "time", "label", "title", "head"),
    "value": ("value", "number", "figure", "num"),
    "unit": ("unit", "units", "suffix"),
}


def _items(item: Dict, kind: str) -> List:
    for key in _LIST_KEYS[kind]:
        value = item.get(key)
        if isinstance(value, list) and value:
            return value
    return []


def _field(entry, name: str) -> str:
    if isinstance(entry, str):
        return entry if name in ("text", "label", "part") else ""
    if not isinstance(entry, dict):
        return ""
    for key in _FIELD_KEYS[name]:
        value = entry.get(key)
        if value not in (None, "", []):
            return str(value)
    return ""


def _object(raw, fallback_id: str, topic: str) -> Dict:
    raw = raw if isinstance(raw, dict) else {}
    oid = re.sub(r"[^A-Za-z0-9_-]", "", str(raw.get("id") or "")) or fallback_id
    prompt = _short(raw.get("prompt") or "", 300)
    return {"id": oid, "prompt": prompt}


def normalize(data: Dict, topic: str, count: int) -> Dict:
    """AI rejasini tekshiradi va tuzatadi: soni, joylashuvlar, chegaralar, obyektlar."""
    data = data if isinstance(data, dict) else {}
    raw = [s for s in (data.get("slides") or []) if isinstance(s, dict)]
    palette = str(data.get("palette") or "").lower()
    style = str(data.get("render_style") or "").lower()
    slides: List[Dict] = []
    for index, item in enumerate(raw[:count]):
        layout = str(item.get("layout") or "").lower()
        if layout not in LAYOUTS:
            layout = "points"
        slide = {"layout": layout, "title": _short(item.get("title") or topic, 80),
                 "object": _object(item.get("object"), f"o{index + 1}", topic)}
        if layout == "cover":
            slide["subtitle"] = _words(item.get("subtitle"), 16)
        elif layout == "callouts":
            slide["callouts"] = [{"label": _short(_field(c, "label"), 28), "text": _words(_field(c, "text"), 18),
                                  "part": _short(_field(c, "part"), 60)}
                                 for c in _items(item, "callouts")[:4] if _field(c, "label")]
        elif layout == "points":
            slide["points"] = [{"head": _short(_field(p, "head"), 40), "text": _words(_field(p, "text"), 26)}
                               for p in _items(item, "points")[:4] if _field(p, "text") or _field(p, "head")]
        elif layout == "table":
            columns = [_short(c, 30) for c in (item.get("columns") or item.get("headers") or [])][:2]
            rows = []
            for r in _items(item, "rows")[:5]:
                if isinstance(r, dict):
                    r = list(r.values())
                if isinstance(r, (list, tuple)) and len(r) >= 2:
                    rows.append([_words(c, 9) for c in r][:2])
            slide["columns"], slide["rows"] = (columns + ["", ""])[:2], rows
        elif layout == "stats":
            slide["stats"] = [{"value": _short(_field(s, "value"), 7), "unit": _short(_field(s, "unit"), 8),
                               "label": _short(_field(s, "label"), 32), "text": _words(_field(s, "text"), 16)}
                              for s in _items(item, "stats")[:3] if _field(s, "value")]
            slide["text"] = _words(item.get("text") or item.get("description"), 28)
        elif layout == "focus":
            slide["lead"] = _words(item.get("lead"), 16)
            slide["text"] = _words(item.get("text"), 42)
        elif layout == "timeline":
            slide["steps"] = [{"when": _short(_field(s, "when"), 18), "text": _words(_field(s, "text"), 16)}
                              for s in _items(item, "steps")[:5] if _field(s, "text")]
        elif layout == "conclusion":
            slide["points"] = [_words(_field(p, "text") or _field(p, "head"), 16) for p in _items(item, "points")[:3]]
        slides.append(slide)

    # Kam element bo'lsa joylashuv o'zgaradi (bo'sh ko'rinmasin).
    for slide in slides:
        layout = slide["layout"]
        if layout == "callouts" and len(slide["callouts"]) < 2:
            slide["layout"], slide["points"] = "points", [
                {"head": c["label"], "text": c["text"]} for c in slide.pop("callouts")]
        elif layout == "table" and len(slide["rows"]) < 2:
            slide["layout"], slide["points"] = "points", [{"head": r[0], "text": r[1]} for r in slide["rows"]]
        elif layout == "stats" and not slide["stats"]:
            slide["layout"], slide["points"] = "points", []
        elif layout == "timeline" and len(slide["steps"]) < 2:
            slide["layout"], slide["points"] = "points", [{"head": s["when"], "text": s["text"]} for s in slide["steps"]]
        if slide["layout"] == "points" and not slide.get("points"):
            slide["points"] = [{"head": "", "text": slide.get("text") or slide.get("lead") or slide["title"]}]

    # Birinchisi — muqova, oxirgisi — xulosa.
    if not slides:
        raise ValueError("AI reja bermadi")
    if slides[0]["layout"] != "cover":
        slides[0] = {"layout": "cover", "title": _short(topic, 80), "subtitle": "",
                     "object": slides[0]["object"]}
    if len(slides) >= 3 and slides[-1]["layout"] != "conclusion":
        last = slides[-1]
        points = [p.get("text") for p in last.get("points", []) if isinstance(p, dict)] or [last.get("text", "")]
        slides[-1] = {"layout": "conclusion", "title": last["title"], "points": [p for p in points if p][:3],
                      "object": dict(slides[0]["object"])}
    for slide in slides[1:-1]:
        if slide["layout"] in ("cover", "conclusion"):
            slide["layout"] = "points"
            slide.setdefault("points", [{"head": "", "text": slide.get("subtitle") or slide["title"]}])
    # "focus" — oldingi obyektga yaqinlashish: id oldingi slaydniki bo'lsin.
    for index, slide in enumerate(slides):
        if slide["layout"] == "focus" and index > 0:
            slide["object"] = dict(slides[index - 1]["object"])
    # Promptsiz obyekt: shu id ning boshqa joydagi promptini olamiz, bo'lmasa mavzu.
    prompts_by_id = {s["object"]["id"]: s["object"]["prompt"] for s in slides if s["object"]["prompt"]}
    for slide in slides:
        obj = slide["object"]
        obj["prompt"] = obj["prompt"] or prompts_by_id.get(obj["id"]) or f"a symbolic object representing {topic}"
        prompts_by_id.setdefault(obj["id"], obj["prompt"])
    return {"palette": palette if palette in PALETTES else "indigo",
            "style": style if style in STYLES else "realistic",
            "slides": slides}


def plan(topic: str, count: int, language: str, level: int = 2, preferences: str = "",
         source_text: str = "") -> Dict:
    """AI dan reja so'raydi (sinxron — oqimda chaqiriladi)."""
    from services.premium_presentation import llm_client, prompts

    extra = ""
    if preferences:
        extra += f"Client's wishes: {preferences[:600]}\n"
    if source_text:
        extra += f"Client's material (use its facts):\n{source_text[:5000]}\n"
    user = prompts.fill(PROMPT, topic=topic, count=count, level=LEVELS.get(level, LEVELS[2]),
                        extra=extra, target=prompts.target(language))
    last_error = None
    for attempt in range(2):
        try:
            data = llm_client._call_openrouter(SYSTEM, user, temperature=0.7, max_tokens=900 + 380 * count)
            result = normalize(data, topic, count)
            if len(result["slides"]) >= max(3, count - 1):
                return result
            last_error = ValueError(f"reja {len(result['slides'])} slayd, {count} kerak")
        except llm_client.NoCredits:
            raise
        except Exception as exc:
            last_error = exc
        log.warning("3D Pro reja (%d-urinish) yaroqsiz: %s", attempt + 1, last_error)
    raise RuntimeError(f"Taqdimot rejasi tuzilmadi: {last_error}")


def objects(deck: Dict) -> Dict[str, str]:
    """Chiziladigan noyob obyektlar: id → prompt (birinchi uchragan tartibda)."""
    found: Dict[str, str] = {}
    for slide in deck["slides"]:
        obj = slide.get("object") or {}
        if obj.get("id") and obj["id"] not in found:
            found[obj["id"]] = obj["prompt"]
    return found
