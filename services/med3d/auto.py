"""3D Anatomiya: mavzu → AI reja → atlasdan 3D modellar → PowerPoint (Morph). To'liq avtomatik.

1. AI (tibbiy aniqlik va o'zbekcha atama uchun kuchli model — `MED3D_MODEL`, sukut bo'yicha Claude Sonnet 5;
   ishlamasa premium zanjiridagi keyingi modellar) mavzu tana tuzilishiga oidligini tekshiradi, tanani
   (erkak/ayol) va organlarni FAQAT lug'atdan (`lugat.py`) tanlaydi, slaydlar rejasini yozadi.
2. Reja tekshiriladi va tuzatiladi: noma'lum organ, bir-birini o'z ichiga olgan organlar, burchaklar, yorliqlar.
3. Slaydlar "sahna"larga bo'linadi: bir sahnadagi organlar umumiy chegara qutisida — Morph ularni harakatlantiradi;
   mayda organga yaqinlashish kerak bo'lsa yangi (kichikroq) sahna boshlanadi, aks holda 3D ramka juda katta.
4. Organ modellari so'rov paytida atlasdan yig'iladi (katta organlar soddalashtiriladi) va `deck.build` ga beriladi.
"""
import asyncio
import copy
import hashlib
import json
import logging
import os
import re
import tempfile
import zlib
from functools import lru_cache
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from . import ASSETS_DIR, manba
from .camera import Camera, sides
from .catalog import srgb
from .glb import Primitive, write_glb
from .lugat import BONE, BY_ID, CARTILAGE, MUSCLE, ORGANS, SOURCES, SUPPORT, TOOTH
from .simplify import simplify
from . import ao

log = logging.getLogger(__name__)

# Reja uchun model: tibbiy faktlar, o'zbekcha anatomik atamalar va qat'iy JSON — eng ishonchli model kerak.
# Admin paneldagi "premium model" tanlovi bunga ta'sir qilmaydi (u arzon model bo'lishi mumkin).
MODEL = os.getenv("MED3D_MODEL") or "anthropic/claude-sonnet-5"
SLIDE_OPTIONS = (5, 8, 10, 12, 15)
# Narx: zamonaviy taqdimot narxidan shuncha baravar (haqiqiy 3D modellar, Morph, lotincha nomli yorliqlar).
# 10 slayd — 25 000 so'm (5 baravar). `MED3D_PRICE_FACTOR` bilan o'zgartiriladi.
PRICE_FACTOR = float(os.getenv("MED3D_PRICE_FACTOR") or 5)


def price_for(slide_count: int) -> int:
    from services.premium_presentation import pipeline

    return int(round(pipeline.price_for(slide_count) * PRICE_FACTOR / 500.0)) * 500
MIN_SLIDES, MAX_SLIDES = 3, 15
# Sifat — imkon qadar maksimal: atlasdagi asl model (100%). Kamaytirish faqat ikki sababdan:
ORGAN_MAX_TRIS = 600000          # atlasdagi eng og'ir organdan ham katta — amalda hamma organ to'liq
SLIDE_MAX_TRIS = 1500000         # bir slayddagi hamma organlar birga (eng og'ir slayd ham to'liq sig'adi)
FILE_LIMIT_MB = float(os.getenv("MED3D_MAX_MB") or 45)   # Telegram bot 50 MB dan kattasini yubormaydi
TURN_MAX = 45                    # qo'shni slaydlar orasida eng katta burilish (gradus) — Morph silliq bo'lsin
MAX_SHOW, MAX_LABELS = 8, 6
STAGES = ("anatomy", "disease", "diagnosis", "treatment", "summary")
MAX_PICTURES = 2                 # kasallik slaydlaridagi AI rasmlar soni (kuchli model)
MAX_SCENES = 2                   # davolash slaydlaridagi bemor tasviri (arzon model)
LEXICON = os.path.join(ASSETS_DIR, "lugat.json")
CONTACT = 0.015                  # metr: organlar shu masofadan yaqin bo'lsa — tegib turibdi, bir-biriga soya tushiradi
HARD = (BONE, TOOTH, CARTILAGE)
WRAPPERS = {"skelet", "mushaklar", "teri", "arteriyalar", "venalar"}   # butun tana bo'ylab tizimlar


class NotAnatomy(RuntimeError):
    """Mavzu tana tuzilishiga oid emas — taqdimot qilinmaydi (pul qaytariladi)."""


class PicturesUnavailable(RuntimeError):
    """Kasallik mavzusi, lekin kasallik rasmini chizadigan xizmat ishlamayapti — 3D yig'ilmaydi, pul qaytariladi va
    mijozga keyinroq urinib ko'rish aytiladi (rasmsiz kasallik taqdimoti to'lagan narxiga yarasha emas)."""


@lru_cache(maxsize=1)
def lexicon() -> dict:
    with open(LEXICON, encoding="utf-8") as fh:
        return json.load(fh)


def _contains() -> Dict[str, set]:
    """Organ → u o'z ichiga oladigan organlar (qismlari to'liq ichida bo'lganlar) — ikkala tana bo'yicha."""
    out: Dict[str, set] = {}
    for body in lexicon()["bodies"].values():
        parts = {k: set(v["parts"]) for k, v in body.items()}
        for a, pa in parts.items():
            for b, pb in parts.items():
                if a != b and pb and pb <= pa:
                    out.setdefault(a, set()).add(b)
    return out


def organ_table() -> str:
    bodies = lexicon()["bodies"]
    rows = []
    for organ in ORGANS:
        have = [label for body, label in (("male", "male"), ("female", "female")) if organ["id"] in bodies[body]]
        if have:
            rows.append(f"{organ['id']} | {organ['uz']} | {organ['en']} | {'+'.join(have)}")
    return "\n".join(rows)


SYSTEM = """You are an anatomy lecturer who designs 3D PowerPoint presentations about the HUMAN BODY.
Every slide shows real 3D organ models from an anatomical atlas (an adult male body and an adult female body)
next to a short text. Between slides PowerPoint Morph smoothly moves, turns and zooms the SAME organs; an organ
shown on one slide and missing on the next flies off the slide; an organ that appears again flies back in.

Return ONLY a JSON object:
{"anatomy": true, "reason": "", "body": "male" | "female", "kind": "anatomy" | "disease",
 "side": null | "right" | "left",
 "names": {"<organ_id>": "<anatomical name in the presentation language>"},
 "slides": [{"title": "...", "text": "...", "show": ["<organ_id>", ...], "focus": ["<organ_id>"],
             "rot": [x, y, z], "labels": ["<organ_id>", ...], "exit": "up" | "down" | "left" | "right",
             "stage": "anatomy" | "disease" | "diagnosis" | "treatment" | "summary",
             "lesion": ["<organ_id>"], "picture": "<English image prompt or empty>",
             "latin": "<Latin medical term of the disease/procedure in the title, or empty>",
             "scene": "<English photo prompt of a patient being treated, or empty>"}]}

RULES
1. "anatomy": false when the topic is NOT about the structure of the human body (history, economics, literature,
   physics, chemistry, technology, animals, plants, sport results...). Human organs, bones, muscles, body systems,
   their functions, and diseases/physiology of human organs ARE anatomy (show the organs involved).
   Also "anatomy": false when the topic IS about the body but the ORGANS table has nothing that shows it (e.g.
   cells, tissues under a microscope, blood tests, genetics, the retina in detail): the 3D atlas cannot show it.
   When false: "reason" = one polite sentence in the presentation language, "slides" = [].
2. Use ONLY organ ids from the ORGANS table and ONLY ones available for the chosen body.
   body = "female" for female-only organs (uterus, ovaries, placenta, mammary gland) and when it has organs the
   topic needs (lungs, spinal cord, kidney internal structure exist only in the female body);
   body = "male" for male-only organs and for stomach or esophagus (they exist only in the male body).
3. Exactly the requested number of slides. Slide 1 = overview of the topic's organ system (several organs
   together, labelled). The last slide = summary that reassembles the overview from a different angle.
   The first and the last slide have NO "focus" — the whole system must be visible.
4. Tell a story with motion: neighbouring slides share organs so Morph moves them. To study one organ, keep it
   in "show" and drop the others (they fly away in the "exit" direction), or keep them and put the organ in
   "focus" (the camera zooms to it). Bring organs back later to reassemble.
5. "show": 1-8 organs. Never put an organ together with an organ that contains it (e.g. "skelet" with
   "bosh_suyagi", "bosh_miya" with "miyacha", "yurak" with "yurak_bolmachalari", "mushaklar" with one muscle).
   "teri" (skin) hides everything inside it — show it only alone.
6. Group the slides by body region: finish one organ system before moving to the next and never jump back and
   forth between distant regions (every jump to a far region breaks the smooth motion).
7. "rot" degrees: x tilts (positive = seen from above, keep within -60..60); y turns around the vertical axis
   (0 = front view, 90 = the body's right side faces the viewer, -90 = its left side, 180 = back view);
   z = 0. Turn the view by 15-45 degrees between neighbouring slides, mostly in one direction (like walking
   around the body); never repeat the same view twice in a row.
8. "labels": 0-6 organ ids from "show" to point at with lines; do not label organs hidden behind others.
9. Heart topics: use "aorta_yoyi" and "yuqori_kovak_vena" (the parts next to the heart); "aorta" and
   "kovak_venalar" run through the whole trunk and make the heart look tiny — use them only for circulation of
   the whole body. Valves ("yurak_klapanlari") lie INSIDE the heart: to show them, view the heart from above
   (x 40-60) or remove "yurak"/"yurak_qorinchalari" from that slide.
10. "title": at most 6 words. "text": 2-4 sentences, at most 380 characters, accurate textbook facts, clear for the
   requested level. No invented statistics, never mention the current year or dates. For anatomy topics no
   treatment advice; for disease topics only standard textbook methods (no personal advice, no drug doses).
11. "names": for EVERY organ id you use, its correct anatomical name in the presentation language.
12. "kind" = "disease" when the topic is a disease, injury or condition (rotator cuff tear, myocardial infarction,
   herniated disc, gastritis...). Then medicine is taught as STRUCTURE -> DISEASE -> TREATMENT, every slide has a
   "stage", in this order:
   - "anatomy" (about one third): slide 1 = overview of the region, then the structures that get damaged,
     labelled, from the angle where they are best seen;
   - "disease" (about one third): what goes wrong — definition, types/stages, causes and risk factors, symptoms;
     "lesion" = ids of the damaged organs from "show" (the 3D model paints them red; label them too);
   - "diagnosis" and "treatment" (about one third): examination and tests, conservative treatment,
     surgery, rehabilitation, prevention and prognosis — keep showing the damaged region ("lesion" may stay);
   - the last slide "summary": the whole region again with the lesion.
   For "kind" = "anatomy" use "stage": "anatomy" (last slide "summary"), "lesion": [] and "picture": "".
13. "picture" (disease topics only, on 1-2 of the "disease"/"diagnosis" slides, otherwise ""): an English prompt for
   a medical illustration that shows what the 3D atlas cannot — the real shape of the pathology at the lesion,
   e.g. "close-up of a full-thickness tear of the supraspinatus tendon at the greater tubercle of the humerus,
   frayed tendon fibres, inflamed subacromial bursa". One structure, close-up, no people's faces, never genitals
   or nudity. A slide with a picture has a shorter "text" (at most 230 characters) and exactly one "lesion".
16. "scene" (disease topics only, on exactly 2 "treatment" slides, otherwise ""): an English prompt for a calm,
   realistic photo of a patient receiving that treatment, matching the slide, e.g. "a physiotherapist guiding a
   middle-aged man through shoulder rotation exercises with a resistance band in a bright rehabilitation room".
   No blood, no open wounds, no surgery close-ups, no nudity; people fully clothed.
15. "latin" (disease topics): on every "disease", "diagnosis" and "treatment" slide whose title names a disease,
   its form or a procedure — its Latin (international medical) term, e.g. "Ruptura manicae rotatorum",
   "Tendinopathia musculi supraspinati", "Syndroma conflictus subacromialis", "Arthroscopia". Otherwise "".
14. "side" = "right" for topics about one limb or joint (shoulder, elbow, wrist, hand, hip, knee, ankle, foot,
   their muscles and diseases): only the right side is shown, so the camera can come close to one joint.
   Otherwise null.
"""

USER = """Topic: {topic}
Number of slides: {count}
Audience level: {level}
Presentation language: {language_rule}
{extra}
ORGANS (id | Uzbek name | English name | available in body):
{table}
"""

LEVELS = {1: "school pupils (simple words)", 2: "university students", 3: "academic / medical professionals"}


def _plan_ai(topic: str, count: int, language: str, level: int, preferences: str) -> dict:
    from services.premium_presentation import llm_client, prompts

    extra = f"Client's wishes: {preferences[:500]}\n" if preferences else ""
    user = USER.format(topic=topic, count=count, level=LEVELS.get(level, LEVELS[2]),
                       language_rule=llm_client._language_instruction(language), extra=extra, table=organ_table())
    with prompts.use(language), llm_client.text_model(MODEL):
        return _call_json(SYSTEM, user, answer_tokens=3000 + 800 * count)


THINK_TOKENS = 2000     # Claude Sonnet 5 o'ylashga cheklovsiz token sarflaydi va javob bo'sh qaytadi — chegaralanadi


def _call_json(system: str, user: str, answer_tokens: int) -> dict:
    """JSON so'rov: o'ylash (reasoning) uchun alohida cheklangan byudjet, javob uchun to'liq joy.

    Umumiy `_call_openrouter` Claude uchun o'ylashni cheklamaydi: model hamma tokenni o'ylashga sarflab,
    "token chegarasida kesildi, bo'sh javob" bilan qaytadi va zaxira modelga o'tiladi (vaqt va pul behuda).
    """
    from services.premium_presentation import llm_client

    payload = {
        "temperature": 0.4,
        "max_tokens": answer_tokens + THINK_TOKENS,
        "reasoning": {"max_tokens": THINK_TOKENS, "exclude": True},
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": llm_client._with_today(system)},
                     {"role": "user", "content": user}],
    }
    raw = llm_client._request("text", payload)["choices"][0]["message"]["content"]
    cleaned = llm_client._clean_json(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        salvaged = llm_client._salvage_partial_json(cleaned)
        if salvaged:
            return salvaged
        raise


def _num(value, low: float, high: float) -> float:
    try:
        return float(min(high, max(low, float(value))))
    except (TypeError, ValueError):
        return 0.0


def normalize(data: dict, count: int, language: str) -> dict:
    """AI javobini tekshiradi va tuzatadi. Mavzu anatomiya bo'lmasa — NotAnatomy."""
    if not isinstance(data, dict):
        raise ValueError("reja JSON obyekt emas")
    if data.get("anatomy") is False or str(data.get("anatomy")).lower() == "false":
        raise NotAnatomy(str(data.get("reason") or "").strip()[:300])
    bodies = lexicon()["bodies"]
    raw = [s for s in (data.get("slides") or []) if isinstance(s, dict)]
    used = {o for s in raw for key in ("show", "focus", "labels") for o in (s.get(key) or []) if isinstance(o, str)}
    body = data.get("body") if data.get("body") in bodies else "male"
    other = "female" if body == "male" else "male"
    if sum(o in bodies[other] for o in used) > sum(o in bodies[body] for o in used):
        body = other                              # AI tanani adashtirgan — organlar qaysida ko'proq bo'lsa o'sha
    have = bodies[body]
    contains = _contains()
    disease = str(data.get("kind") or "").lower() == "disease"

    slides = []
    for s in raw[:count]:
        show: List[str] = []
        for organ in s.get("show") or []:
            if organ not in have or organ in show:
                continue
            if any(organ in contains.get(o, ()) or o in contains.get(organ, ()) for o in show):
                continue                          # biri ikkinchisining ichida — birinchisi qoladi
            show.append(organ)
        if "teri" in show and len(show) > 1:
            show = [o for o in show if o != "teri"]
        show = show[:MAX_SHOW]
        if not show:
            show = list(slides[-1]["show"]) if slides else []
        if not show:
            continue
        support = add_support(show, have, contains)
        focus = [o for o in (s.get("focus") or []) if o in show]
        labels = [o for o in (s.get("labels") or []) if o in show][:MAX_LABELS]
        rot = list(s.get("rot") or [0, 0, 0])[:3] + [0, 0, 0]
        lesion = [o for o in (s.get("lesion") or []) if isinstance(o, str) and o in show][:3] if disease else []
        labels = list(dict.fromkeys(lesion + labels))[:MAX_LABELS]
        stage = (s.get("stage") if s.get("stage") in STAGES else "disease") if disease else ""
        picture = re.sub(r"\s+", " ", str(s.get("picture") or "")).strip()[:400] if disease and lesion else ""
        latin = re.sub(r"\s+", " ", str(s.get("latin") or "")).strip()[:80] if disease else ""
        if stage == "treatment":                  # davolash slaydida — bemor tasviri (arzon model), patologiya emas
            picture = ""
        scene = re.sub(r"\s+", " ", str(s.get("scene") or "")).strip()[:400] \
            if disease and stage == "treatment" else ""
        slides.append({
            "title": str(s.get("title") or "").strip()[:90],
            "text": re.sub(r"\s+\n", "\n", str(s.get("text") or "").strip())[:520],
            "show": show, "focus": focus or None, "labels": list(dict.fromkeys(labels)), "support": support,
            "rot": [_num(rot[0], -60, 60), _num(rot[1], -180, 180), _num(rot[2], -30, 30)],
            "exit": s.get("exit") if s.get("exit") in ("up", "down", "left", "right") else "up",
            "stage": stage, "lesion": lesion, "picture": picture, "latin": latin, "scene": scene,
        })
    pictures = scenes = 0
    for s in slides:                              # rasm — ko'pi bilan MAX_PICTURES ta (generatsiya vaqti va narxi)
        if s["picture"]:
            pictures += 1
            if pictures > MAX_PICTURES:
                s["picture"] = ""
        if s["scene"]:
            scenes += 1
            if scenes > MAX_SCENES:
                s["scene"] = ""
    if len(slides) < max(MIN_SLIDES, count - 1):
        raise ValueError(f"reja {len(slides)} slayd, {count} kerak")
    smooth_turns(slides)
    names = {}
    ai_names = data.get("names") if isinstance(data.get("names"), dict) else {}
    for organ in {o for s in slides for o in s["show"]}:
        if language == "uz":
            names[organ] = BY_ID[organ]["uz"]       # o'zbekcha nomlar — tekshirilgan lug'atdan
        else:
            names[organ] = str(ai_names.get(organ) or BY_ID[organ]["en"]).strip()[:40]
    side = data.get("side") if data.get("side") in SIDE_SIGN else None
    return {"body": body, "slides": slides, "names": names, "language": language, "side": side,
            "kind": "disease" if disease else "anatomy"}


def add_support(show: List[str], have: dict, contains: Dict[str, set]) -> List[str]:
    """Bo'g'im/boylam yoki tishlar ko'rsatilsa — ular bog'langan suyaklar ham qo'shiladi (`lugat.SUPPORT`): aks holda
    kapsula va boylamlar havoda suzib, tishlar jag'siz turadi. `show` joyida o'zgaradi; qaytaradi: qo'shilgan suyaklar.

    Suyak ko'rinishdagi organ ichida bo'lsa (skelet) — qo'shilmaydi. Tishlar faqat pastki jag' bilan bo'lsa (bosh
    suyagi qo'shib bo'lmaydi — u pastki jag'ni o'z ichiga oladi) — tishlar olinadi: yuqori qatori havoda qolardi."""
    added: List[str] = []
    for organ in list(show):
        for bone in SUPPORT.get(organ, ()):
            if bone not in have or bone in show or any(bone in contains.get(o, ()) for o in show):
                continue
            if any(o in contains.get(bone, ()) for o in show):
                if organ == "tishlar" and len(show) > 1:
                    show.remove(organ)
                continue
            show.append(bone)
            added.append(bone)
    return added


def smooth_turns(slides: List[dict]) -> None:
    """Burilishlarni silliqlaydi: qo'shni slaydlar orasida TURN_MAX dan ko'p emas, keskin teskari burilmaydi.

    AI ba'zan 30° → −60° → 180° → −120° kabi sakraydi: Morph modelni har o'tishda teskari aylantiradi va
    ko'z charchaydi. Har slayd oldingisidan AI so'ragan tomonga, lekin ko'pi bilan TURN_MAX ga buriladi.
    """
    prev = None
    for s in slides:
        x, y, z = s["rot"]
        y = (y + 180) % 360 - 180
        y = max(-100.0, min(100.0, y))               # orqadan ko'rinish deyarli kerak emas — old va yon tomonlar
        x = max(-45.0, min(45.0, x))
        if prev is not None:
            px, py = prev
            dy = (y - py + 180) % 360 - 180          # eng qisqa yo'l bilan
            y = py + max(-TURN_MAX, min(TURN_MAX, dy))
            x = px + max(-30.0, min(30.0, x - px))
        s["rot"] = [round(x, 1), round(y, 1), 0.0]
        prev = (x, y)


def plan(topic: str, count: int, language: str = "uz", level: int = 2, preferences: str = "") -> dict:
    """AI reja (sinxron). Ikki marta urinadi; mavzu anatomiya bo'lmasa — darhol NotAnatomy."""
    from services.premium_presentation import llm_client

    last = None
    for attempt in range(2):
        try:
            return normalize(_plan_ai(topic, count, language, level, preferences), count, language)
        except (NotAnatomy, llm_client.NoCredits):
            raise
        except Exception as exc:                  # noqa: BLE001 — keyingi urinish
            last = exc
            log.warning("3D Anatomiya reja (%d-urinish) yaroqsiz: %s", attempt + 1, exc)
    raise RuntimeError(f"Taqdimot rejasi tuzilmadi: {last}")


# ───────────────────────────────────────────── sahnalar va 3D modellar

def _bounds(body: dict, organs) -> Tuple[np.ndarray, np.ndarray]:
    lo = np.min([body[o]["min"] for o in organs], axis=0)
    hi = np.max([body[o]["max"] for o in organs], axis=0)
    return lo, hi


SIDE_SIGN = {"right": -1.0, "left": 1.0}     # atlasda tananing o'ng tomoni — x manfiy


def one_side(body: dict, side: Optional[str], atlas) -> dict:
    """Bitta tomon: yelka, tizza kabi mavzuda juft organlarning faqat o'ng (yoki chap) nusxasi qoladi — kamera
    ikki yelka orasidagi bo'sh joyga emas, bitta bo'g'imga yaqinlashadi. Toq organlar (umurtqa, bosh suyagi)
    o'zgarmaydi. Chegara qutisi qolgan qismlarning aniq chegarasidan (GLB langarlari u bilan mos bo'lishi shart)."""
    sign = SIDE_SIGN.get(side or "")
    if not sign:
        return body
    out = {}
    for organ, info in body.items():
        pts = np.asarray(info["samples"], float)
        meta = [atlas.by_id.get(p) for p in info["parts"]]
        if len(sides(pts)) != 2 or any(m is None or "bounds" not in m for m in meta):
            out[organ] = info
            continue
        keep = [m for m in meta if (m["bounds"][0][0] + m["bounds"][1][0]) * sign > 0]
        mine = pts[pts[:, 0] * sign > 0]
        if not keep or len(mine) < 3:
            out[organ] = info
            continue
        bounds = np.asarray([m["bounds"] for m in keep], float)
        out[organ] = dict(info, parts=[m["id"] for m in keep], samples=mine.tolist(),
                          min=bounds[:, 0].min(axis=0).tolist(), max=bounds[:, 1].max(axis=0).tolist())
    return out


def reveal_hidden(body: dict, slides: List[dict]) -> None:
    """Kamera yaqinlashgan organ boshqa organ ichida bo'lsa (lug'atdagi `inside`) — o'rab turgan organ chiqariladi.

    Masalan, fokus "klapanlar"da, lekin "qorinchalar" ham ko'rinishda: klapan ko'rinmaydi, ramka esa qorinchadan
    katta chiqadi. O'rab turgan organ olib tashlanadi — Morph uni uchirib yuboradi va ichidagisi ochiladi.
    """
    for s in slides:
        wrappers = {w for o in (s["focus"] or []) for w in BY_ID[o].get("inside", ())}
        drop = [o for o in s["show"] if o in wrappers and o not in (s["focus"] or [])]
        if drop:
            s["show"] = [o for o in s["show"] if o not in drop]
            s["labels"] = [o for o in s["labels"] if o not in drop]
            log.info("3D Anatomiya: %s ko'rinishi uchun olib tashlandi: %s", s["focus"], drop)


def split_runs(body: dict, slides: List[dict]) -> List[Tuple[List[int], np.ndarray, np.ndarray]]:
    """Slaydlarni sahnalarga bo'ladi: sahna ichida hamma slaydning 3D ramkasi MAX_FRAME dan oshmasin."""
    from .deck import MAX_FRAME, MODEL_REGION, MODEL_REGION_WIDE, fit_frame

    def fits(lo, hi, members) -> bool:
        cam = Camera(lo, hi)
        for i in members:
            s = slides[i]
            points = [p for o in (s["focus"] or s["show"]) for p in body[o]["samples"]]
            region = MODEL_REGION if s["labels"] else MODEL_REGION_WIDE
            u0, v0, u1, v1 = cam.extent(points, s["rot"])
            rx, ry, rw, rh = region
            need = min(rw * 0.9 / max(u1 - u0, 1e-6), rh * 0.9 / max(v1 - v0, 1e-6))
            if need > MAX_FRAME:
                return False
        return True

    runs: List[Tuple[List[int], np.ndarray, np.ndarray]] = []
    for i, s in enumerate(slides):
        lo, hi = _bounds(body, s["show"])
        if runs:
            members, rlo, rhi = runs[-1]
            nlo, nhi = np.minimum(rlo, lo), np.maximum(rhi, hi)
            if fits(nlo, nhi, members + [i]):
                runs[-1] = (members + [i], nlo, nhi)
                continue
        runs.append(([i], lo, hi))
    return runs


def _mesh(atlas, part_ids):
    pos, nrm, idx, base = [], [], [], 0
    for pid in part_ids:
        p, n, i = atlas._one(atlas.by_id[pid])
        pos.append(p)
        nrm.append(n)
        idx.append(i + base)
        base += len(p)
    return np.vstack(pos), np.vstack(nrm), np.concatenate(idx)


def _pieces(atlas, body: dict, organ: str) -> List[Tuple[str, list]]:
    """Organ → [(rang, qism id lari)]: union — tarkibidagi organlar rangida, `tones` — qism nomiga qarab."""
    info = BY_ID[organ]
    if info.get("union"):
        out = [(BY_ID[c]["color"], body[c]["parts"]) for c in info["union"] if c in body]
    else:
        out = [(info["color"], body[organ]["parts"])]
    tones = info.get("tones") or []
    if tones:
        split: Dict[str, list] = {}
        for color, ids in out:
            for pid in ids:
                name = str(atlas.by_id.get(pid, {}).get("name", ""))
                hue = next((c for rx, c in tones if re.search(rx, name, re.I)), color)
                split.setdefault(hue, []).append(pid)
        out = list(split.items())
    merged: Dict[str, list] = {}
    for color, ids in out:                        # bir xil rang — bitta material
        merged.setdefault(color, []).extend(i for i in ids if i not in merged.get(color, []))
    return [(c, ids) for c, ids in merged.items() if ids]


def organ_geometry(atlas, body: dict, organ: str, target: int) -> List[tuple]:
    """Organ → [(rang, nuqtalar, normallar, indekslar)]: soddalashtirilgan (sifatli usulda), hali soyasiz."""
    pieces = _pieces(atlas, body, organ)
    total = sum(sum(atlas._one(atlas.by_id[p])[2].size for p in ids) // 3 for _, ids in pieces) or 1
    meshes = []
    for color, ids in pieces:
        pos, nrm, idx = _mesh(atlas, ids)
        share = max(2000, int(target * (len(idx) // 3) / total))
        meshes.append((color, *simplify(pos, nrm, idx, share)))
    return meshes


def _joined(meshes: List[tuple]) -> Tuple[np.ndarray, np.ndarray, np.ndarray, List[int]]:
    offsets, base, pos, nrm, idx = [], 0, [], [], []
    for _, p, n, i in meshes:
        offsets.append(base)
        pos.append(p)
        nrm.append(n)
        idx.append(i + base)
        base += len(p)
    return np.vstack(pos), np.vstack(nrm), np.concatenate(idx), offsets


LUNGS = ("opkalar", "ong_opka", "chap_opka")


def texture_of(organ: str) -> str:
    """Organ to'qimasi naqshi: mushak — tolali, o'pka — g'ovak, suyak — donador."""
    info = BY_ID[organ]
    if organ in LUNGS:
        return "speckle"
    if info["color"] in (MUSCLE,) or organ.endswith("mushaklar") or organ.endswith("mushaklari") or organ in (
            "mushaklar", "diafragma", "deltasimon", "trapetsiyasimon", "kokrak_mushagi", "qovurgalararo"):
        return "fiber"
    if info["color"] in (BONE, TOOTH):
        return "grain"
    return ""


LESION = "#E3352B"                # kasallik slaydida zararlangan organ rangi (har uslubda bir xil — ajralib tursin)
CALM = "#C8C2BA"                  # o'sha slayddagi boshqa yumshoq to'qimalar shu rangga yaqinlashadi


def _blend(a: str, b: str, k: float) -> str:
    a, b = a.lstrip("#"), b.lstrip("#")
    mix = [round(int(a[i:i + 2], 16) * (1 - k) + int(b[i:i + 2], 16) * k) for i in (0, 2, 4)]
    return "#%02X%02X%02X" % tuple(mix)


def shaded_primitives(organ: str, meshes: List[tuple], neighbours: List[List[tuple]] = (),
                      tone: str = "real", paint: Optional[str] = None) -> List[Primitive]:
    """Soya butun organ bo'yicha (bo'lmacha qorinchaga soya tushiradi) va unga tegib turgan qo'shni organlar
    bilan birga (yurak aorta ildiziga) — yig'ilgan organlar bitta jismdek, bir xil yorug'likda ko'rinadi.

    tone — uslub ohangi (`design.tone`): real, pastel, ivory, xray, warm. Naqsh (tola, g'ovak) — organ turiga qarab.
    paint — butun organ shu rangda (zararlangan organ: `LESION`), uslub ohangi qo'llanmaydi."""
    from .design import tone as style_tone

    def recolor(value: str, kind: str) -> str:
        return paint if paint else style_tone(value, kind)

    allpos, allnrm, allidx, offsets = _joined(meshes)
    others = None
    if neighbours:
        opos, _, oidx, _ = _joined([m for group in neighbours for m in group])
        others = (opos, oidx)
    info = BY_ID[organ]
    base = np.array(srgb(recolor(info["color"], tone)))
    if info.get("shade"):
        tint = np.array(srgb(recolor(info["shade"], tone))) / np.maximum(base, 1e-3)
    else:
        tint = (0.62, 0.56, 0.58) if tone == "pastel" else ((0.45, 0.62, 0.7) if tone == "xray" else (0.55, 0.45, 0.45))
    hard = info["color"] in HARD    # suyak va tog'ay — xira, yumshoq a'zolar — nam yaltiroq
    shade = ao.colors(allpos, allnrm, allidx, tint=np.clip(tint, 0, 1),
                      mottle=0.04 if hard or tone in ("ivory", "xray") else (0.07 if organ == "jigar" else 0.12),
                      others=others, texture=texture_of(organ))
    rough = 0.75 if hard else 0.38
    if tone == "ivory":
        rough = 0.55
    prims = []
    for (color, pos, nrm, idx), start in zip(meshes, offsets):
        prims.append(Primitive(pos, nrm, idx, srgb(recolor(color, tone)), roughness=rough, name=organ,
                               colors=shade[start:start + len(pos)]))
    return prims


def organ_primitives(atlas, body: dict, organ: str, target: int) -> List[Primitive]:
    """Organ modeli: soddalashtirilgan va soyasi hisoblangan (egat, chuqurliklar qorong'i)."""
    return shaded_primitives(organ, organ_geometry(atlas, body, organ, target))


def neighbours(body: dict, organ: str, slides: List[dict]) -> List[str]:
    """Organga soya tushiradigan qo'shnilar: u bilan bir slaydda turadigan va unga TEGIB turgan organlar.

    Bir-birining ichidagisi (klapan — yurak), butun tizimlar (skelet, teri), suyak ↔ yumshoq to'qima olinmaydi:
    aks holda qo'shni uchib ketgan slaydda organda keraksiz qora dog' qoladi.
    """
    nested = _contains()
    hard = BY_ID[organ]["color"] in HARD
    together = {o for s in slides if organ in s["show"] for o in s["show"]} - {organ}
    mine = np.asarray(body[organ]["samples"], float)
    out = []
    for other in sorted(together):
        if (other in WRAPPERS or organ in WRAPPERS or other in nested.get(organ, ()) or organ in nested.get(other, ())
                or other in BY_ID[organ].get("inside", ()) or organ in BY_ID[other].get("inside", ())
                or (BY_ID[other]["color"] in HARD) != hard):
            continue
        theirs = np.asarray(body[other]["samples"], float)
        gap = np.sqrt(((mine[:, None, :] - theirs[None, :, :]) ** 2).sum(axis=2)).min()
        if gap < CONTACT:
            out.append(other)
    return out


SURFACE_MAX, SURFACE_MIN = 60000, 6000   # yorliq nuqtasi uchun organ yuzasidan nuqtalar (`camera.IdBuffer`)


def surface_points(meshes: List[tuple], count: int, seed: int = 0) -> np.ndarray:
    """Organ yuzasidan maydoniga mutanosib tasodifiy nuqtalar (uchburchaklar ichida) — z-bufer uchun."""
    pos, _, idx, _ = _joined(meshes)
    tri = pos[idx.reshape(-1, 3)]
    area = 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    if not len(tri) or area.sum() <= 0:
        return pos.astype(np.float32)
    rng = np.random.default_rng(seed)
    pick = rng.choice(len(tri), size=count, p=area / area.sum())
    a, b = rng.random(count), rng.random(count)
    flip = a + b > 1
    a[flip], b[flip] = 1 - a[flip], 1 - b[flip]
    t = tri[pick]
    return (t[:, 0] + a[:, None] * (t[:, 1] - t[:, 0]) + b[:, None] * (t[:, 2] - t[:, 0])).astype(np.float32)


def mesh_area(meshes: List[tuple]) -> float:
    pos, _, idx, _ = _joined(meshes)
    tri = pos[idx.reshape(-1, 3)]
    return float(0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1).sum())


OCCLUDER_POINTS = 2500           # yorliq uchun "qaysi organ yopilgan" hisobi: organ to'ridan shuncha nuqta


def _dense(meshes: List[tuple]) -> list:
    """Organ to'ridan teng tanlangan nuqtalar (to'suvchi sifatida): lug'atdagi 300 ta namuna katta organda siyrak."""
    pos = np.vstack([m[1] for m in meshes])
    step = max(1, len(pos) // OCCLUDER_POINTS)
    return pos[::step].tolist()


FOCUS_HIDDEN = 0.5               # fokusdagi organning shundan ko'pini boshqa organ yopsa — u shu slayddan olinadi


def reveal_focus(cam: Camera, slides: List[dict], dense: Dict[str, list]) -> None:
    """AI tanlagan burchakda fokusdagi organ boshqa organ ortida qolsa (o't yo'llari — jigar ortida), yopayotgan
    organ shu slayddan olinadi: joyida almashishda u so'nadi va fokusdagi organ ochiladi. `reveal_hidden` ning
    umumiy turi — u faqat lug'atdagi "ichida" munosabatini biladi, bu esa haqiqiy ko'rinishni tekshiradi."""
    for s in slides:
        focus = [o for o in (s.get("focus") or []) if o in dense]
        if not focus:
            continue
        target = [p for o in focus for p in dense[o]]
        drop = []
        for other in s["show"]:
            if other in focus or other not in dense or other in (s.get("support") or ()):
                continue                            # tayanch suyak qoladi — u holda bo'g'im havoda suzadi
            hidden = 1.0 - float(cam.visible_mask(target, s.get("rot") or (0, 0, 0), dense[other]).mean())
            if hidden > FOCUS_HIDDEN:
                drop.append(other)
        if drop and len(drop) < len(s["show"]):
            s["show"] = [o for o in s["show"] if o not in drop]
            s["labels"] = [o for o in s["labels"] if o not in drop]
            log.info("3D Anatomiya: %s ni yopib turgani uchun olib tashlandi: %s", focus, drop)


def set_id(organs) -> str:
    return "set" + hashlib.sha1("+".join(sorted(organs)).encode()).hexdigest()[:8]


def build_scenes(body_key: str, plan_: dict, atlas=None, quality: float = 1.0) -> Tuple[dict, Dict[str, dict]]:
    """Reja → (deck rejasi, xotiradagi sahnalar). atlas — test uchun almashtirsa bo'ladi.

    Haqiqiy 3D: slayddagi hamma organ BITTA modelda. PowerPoint har 3D modelni alohida qatlam qilib chizadi va
    modellar orasida chuqurlikni solishtirmaydi — alohida organlar bo'lsa tomir yurak orqasiga kirmay, ustiga
    chiqib qolardi. Bitta modelda kim kimni yopishi to'g'ri hisoblanadi.

    Harakat: organlar to'plami o'zgarmasa — bir xil nomli model, Morph uni silliq aylantiradi va yaqinlashtiradi.
    To'plam o'zgarsa — oraga yordamchi slayd qo'yiladi (o'zi o'tadi, raqamga kirmaydi): kamera joyida turadi,
    eski model so'nadi, yangisi o'sha joyda paydo bo'ladi (qolayotgan organlar ikkalasida bir xil — qimirlamaydi),
    keyin yangi model burilib yangi joyiga keladi.

    quality — uchburchaklar ulushi (1 — imkon qadar to'liq); fayl juda katta chiqsa `make_deck` kamaytiradi.
    """
    from .design import style as get_style

    slides = plan_["slides"]
    atlas = atlas or manba.atlas(body_key)
    body = one_side(lexicon()["bodies"][body_key], plan_.get("side"), atlas)
    reveal_hidden(body, slides)
    tone = get_style(plan_.get("style")).tone
    geometry: Dict[Tuple[str, int], list] = {}
    shaded: Dict[tuple, list] = {}
    scenes: Dict[str, dict] = {}
    placed = []
    for number, (members, lo, hi) in enumerate(split_runs(body, slides)):
        key = f"run{number}"
        organs = list(dict.fromkeys(o for i in members for o in slides[i]["show"]))
        heaviest = max(sum(min(body[o]["tris"], ORGAN_MAX_TRIS) for o in slides[i]["show"]) for i in members)
        scale = min(1.0, SLIDE_MAX_TRIS / max(heaviest, 1))
        targets = {o: int(max(6000, min(body[o]["tris"], ORGAN_MAX_TRIS) * scale * quality)) for o in organs}
        for organ in organs:
            if (organ, targets[organ]) not in geometry:
                geometry[(organ, targets[organ])] = organ_geometry(atlas, body, organ, targets[organ])
        run_slides = [slides[i] for i in members]
        prims, dense = {}, {}
        for organ in organs:
            # Soya organning o'zi va unga tegib turganlar bo'yicha — qaysi to'plamda bo'lmasin bir xil: almashishda
            # qolayotgan organ piksellari o'zgarmaydi.
            near = tuple(neighbours(body, organ, run_slides))
            cache_key = (organ, targets[organ], tuple((o, targets[o]) for o in near), tone)
            if cache_key not in shaded:
                shaded[cache_key] = shaded_primitives(organ, geometry[(organ, targets[organ])],
                                                      [geometry[(o, targets[o])] for o in near], tone=tone)
            prims[organ] = shaded[cache_key]
            dense[organ] = _dense(geometry[(organ, targets[organ])])
            if any(slides[i].get("lesion") and organ not in slides[i]["lesion"] and organ in slides[i]["show"]
                   for i in members) and BY_ID[organ]["color"] not in HARD:
                # Zararlangan organ bor slaydda qolgan yumshoq to'qimalar xira (kulrang-pushti): qizil o'choq
                # ko'zga darhol tashlansin — tibbiy illyustratsiyalardagidek.
                calm_key = cache_key + ("calm",)
                if calm_key not in shaded:
                    from .design import tone as style_tone
                    shaded[calm_key] = shaded_primitives(
                        organ, geometry[(organ, targets[organ])], [geometry[(o, targets[o])] for o in near],
                        tone=tone, paint=_blend(style_tone(BY_ID[organ]["color"], tone), CALM, 0.6))
                prims[(organ, "calm")] = shaded[calm_key]
            if any(organ in (slides[i].get("lesion") or ()) for i in members):
                sick_key = cache_key + ("lesion",)
                if sick_key not in shaded:
                    shaded[sick_key] = shaded_primitives(organ, geometry[(organ, targets[organ])],
                                                         [geometry[(o, targets[o])] for o in near], tone=tone,
                                                         paint=LESION)
                prims[(organ, "lesion")] = shaded[sick_key]
        reveal_focus(Camera(lo, hi), [slides[i] for i in members], dense)
        areas = {o: mesh_area(geometry[(o, targets[o])]) for o in organs}
        top = max(areas.values()) or 1.0
        surface = {o: surface_points(geometry[(o, targets[o])],
                                     int(np.clip(areas[o] / top * SURFACE_MAX, SURFACE_MIN, SURFACE_MAX)), seed=k)
                   for k, o in enumerate(organs)}
        groups, labels = {}, {}
        for i in members:
            show = sorted(slides[i]["show"])
            focus = slides[i].get("focus") or slides[i]["show"]
            names = plan_["names"]
            sick = set(slides[i].get("lesion") or ()) & set(show)

            def model_of(o):                       # zararlangan organ — qizil, qolgan yumshoq to'qima — xira
                if o in sick:
                    return prims[(o, "lesion")]
                if sick and (o, "calm") in prims:
                    return prims[(o, "calm")]
                return prims[o]

            def part_of(o):                        # portlashdagi bo'lak nomi (rangi boshqa nusxa — boshqa nom)
                if o in sick:
                    return f"part_{o}_x"
                return f"part_{o}_c" if sick and (o, "calm") in prims else f"part_{o}"
            if slides[i].get("explode") and len(show) >= 2:
                # Portlash: har organ alohida model (bo'laklar bir-biridan ajraladi, keyin qayta yig'iladi).
                parts = []
                for o in show:
                    pid = part_of(o)
                    parts.append(pid)
                    if pid not in groups:
                        groups[pid] = {"samples": body[o]["samples"], "surface": [(o, surface[o])],
                                       "glb": write_glb(model_of(o), anchors=(lo, hi), name=pid)}
                        labels[f"{pid}:{o}"] = {"uz": names.get(o, BY_ID[o]["uz"]), "la": BY_ID[o].get("la", ""),
                                                "group": pid, "samples": body[o]["samples"], "alert": o in sick,
                                                "organ": o}
                placed.append((i, key, ("parts", tuple(show), tuple(sorted(sick))), dict(
                    slides[i], scene=key, show=parts, focus=None,
                    focus_points=[p for o in show for p in body[o]["samples"]],
                    labels=[f"{part_of(o)}:{o}" for o in slides[i]["labels"] if o in show])))
                continue
            gid = set_id(show + [f"!{o}" for o in sorted(sick)] + (["~calm"] if sick else []))
            if gid not in groups:
                groups[gid] = {"samples": [p for o in show for p in body[o]["samples"]],
                               "surface": [(o, surface[o]) for o in show],
                               "glb": write_glb([p for o in show for p in model_of(o)], anchors=(lo, hi), name=gid)}
                for o in show:
                    labels[f"{gid}:{o}"] = {"uz": names.get(o, BY_ID[o]["uz"]), "la": BY_ID[o].get("la", ""),
                                            "group": gid, "samples": body[o]["samples"], "alert": o in sick,
                                            "organ": o,
                                            "occluders": [p for x in show if x != o for p in dense[x]]}
            support = set(slides[i].get("support") or ()) & set(show)
            placed.append((i, key, ("set", gid), dict(slides[i], scene=key, show=[gid], focus=None,
                                                      focus_points=[p for o in focus for p in body[o]["samples"]],
                                                      whole_points=[p for o in show if o not in support
                                                                    for p in body[o]["samples"]] if support else None,
                                                      labels=[f"{gid}:{o}" for o in slides[i]["labels"] if o in show])))
        source = SOURCES[body_key]
        if any(pid.startswith("ZA-") for o in organs for pid in body[o]["parts"]):
            source += "; " + SOURCES["zanatomy"]
        scenes[key] = {"bbox_min": lo.tolist(), "bbox_max": hi.tolist(), "source": source,
                       "groups": groups, "labels": labels}
    placed.sort(key=lambda item: item[0])
    deck_slides: List[dict] = []

    def helper(data: dict, show: list, frame_of: int) -> None:
        """Yordamchi slayd (o'zi o'tadi, raqamga kirmaydi): kamera `frame_of` slayddagidek."""
        deck_slides.append(dict(data, show=show, labels=[], fade=True, auto=True, explode=0, frame_of=frame_of))

    def organs_of(item) -> set:
        return set(slides[item[0]]["show"])

    for k, (_, key, form, data) in enumerate(placed):
        # Joyida almashish faqat umumiy organ qolganda kerak (u qimirlamay turadi). Umumiy organ bo'lmasa (pastki
        # jag' → bosh suyagi) — eskisi uchib chiqadi, yangisi uchib kiradi: yangi model eski kamerada ulkan bo'lib
        # lip etib ko'rinmaydi.
        if k and placed[k - 1][1] == key and placed[k - 1][2] != form and organs_of(placed[k - 1]) & organs_of(placed[k]):
            prev_form, prev = placed[k - 1][2], deck_slides[-1]
            if form[0] == "parts":
                # yig'ilgan model → o'sha joyda alohida bo'laklar (so'nib almashadi) → bo'laklar ajraladi
                helper(data, data["show"], len(deck_slides) - 1)
            elif prev_form[0] == "parts":
                # ajralgan bo'laklar o'sha joyda qayta yig'iladi → yaxlit modelga almashadi → yangi joyga
                helper(data, prev["show"], len(deck_slides) - 1)
                helper(data, data["show"], len(deck_slides) - 1)
            else:
                helper(data, data["show"], len(deck_slides) - 1)
        deck_slides.append(data)
    return {"scene": "run0", "slides": deck_slides, "style": plan_.get("style"),
            "language": plan_.get("language")}, scenes


def _safe(name: str) -> str:
    return re.sub(r"[^\w\-]+", "_", name, flags=re.UNICODE).strip("_")[:40] or "taqdimot"


def models_size(scenes: Dict[str, dict]) -> int:
    """Taqdimotdagi 3D modellar hajmi (bayt, PPTX ichidagidek siqilgan): bir xil GLB faylga bir marta yoziladi."""
    unique = {}
    for scene in scenes.values():
        for info in scene["groups"].values():
            key = hashlib.sha1(info["glb"]).hexdigest()
            if key not in unique:
                unique[key] = len(zlib.compress(info["glb"], 6))
    return sum(unique.values())


QUIZ_TEXT = {
    "uz": ("O'zingizni tekshiring", "Raqamlar bilan belgilangan a'zolarni ayting. Javoblar — bosganda chiqadi."),
    "uz-cyrl": ("Ўзингизни текширинг", "Рақамлар билан белгиланган аъзоларни айтинг. Жавоблар — босганда чиқади."),
    "ru": ("Проверьте себя", "Назовите органы, отмеченные цифрами. Ответы появятся по щелчку."),
    "en": ("Check yourself", "Name the organs marked with numbers. The answers appear on click."),
    "kk": ("Өзіңізді тексеріңіз", "Сандармен белгіленген мүшелерді атаңыз. Жауаптар басқанда шығады."),
}
QUIZ_MIN_SLIDES = 8


def add_quiz(plan_: dict) -> bool:
    """Xulosadan oldin bonus savol slaydi: eng ko'p yorliqli umumiy ko'rinish, nomlar o'rnida raqamlar,
    javoblar bosilganda chiqadi (o'qituvchi uchun tayyor mashq). 8 slayddan kam bo'lsa — qo'shilmaydi."""
    slides = plan_["slides"]
    if len(slides) < QUIZ_MIN_SLIDES or any(s.get("quiz") for s in slides):
        return False
    source = max(slides[:-1], key=lambda s: (len(s.get("labels") or []), len(s["show"])))
    if len(source.get("labels") or []) < 3:
        return False
    from services import uz_script

    lang = plan_.get("language") or "uz"
    key = "uz-cyrl" if lang == getattr(uz_script, "UZ_CYRILLIC_LANG", "uz-cyrl") else lang
    title, text = QUIZ_TEXT.get(key) or QUIZ_TEXT["en"]
    quiz = dict(copy.deepcopy(source), title=title, text=text, quiz=True, focus=None)
    slides.insert(len(slides) - 1, quiz)
    return True


def pick_style(topic: str) -> str:
    """Mijoz uslub tanlamagan bo'lsa: mavzuga qarab (har mavzu o'z uslubida, lekin bir xil mavzu — bir xil)."""
    from .design import STYLES

    keys = sorted(STYLES)
    return keys[int(hashlib.md5(topic.encode("utf-8")).hexdigest()[:6], 16) % len(keys)]


def make_deck(topic: str, plan_: dict, out_dir: Optional[str] = None, atlas=None,
              limit_mb: Optional[float] = None, style: Optional[str] = None) -> str:
    """Taqdimot fayli. Avval eng yuqori sifatda yig'iladi; fayl `limit_mb` dan oshsa — og'ir organlar
    kerakli ulushga kamaytirilib qayta yig'iladi (yengillari to'liq qoladi).

    style — dizayn uslubi (`design.STYLES`); berilmasa — rejadagisi yoki mavzuga qarab tanlanadi. Rejissyor
    (`director.direct`) har slaydga kompozitsiya va kamera harakatini bir marta beradi."""
    from .deck import build
    from .director import direct

    plan_["style"] = style or plan_.get("style") or pick_style(topic)
    if not plan_.get("directed"):
        add_quiz(plan_)
        body = one_side(lexicon()["bodies"][plan_["body"]], plan_.get("side"),
                        (atlas or manba.atlas(plan_["body"])) if plan_.get("side") else None)
        moves = direct(body, plan_["slides"], topic)
        plan_["directed"] = True
        log.info("3D Anatomiya: uslub %s, harakatlar: %s", plan_["style"], ", ".join(moves))
    limit = (limit_mb or FILE_LIMIT_MB) * 1e6
    quality = 1.0
    for attempt in range(5):
        deck_plan, scenes = build_scenes(plan_["body"], copy.deepcopy(plan_), atlas, quality)
        size = models_size(scenes)
        if size <= limit:
            break
        quality *= limit / size * 0.92            # hajm uchburchaklar soniga deyarli mutanosib
        log.info("3D Anatomiya: modellar %.1f MB > %.0f MB — sifat %.0f%% ga tushiriladi",
                 size / 1e6, limit / 1e6, quality * 100)
    deck_plan["seed"] = int(hashlib.md5(topic.encode("utf-8")).hexdigest()[:4], 16)
    out_dir = out_dir or tempfile.mkdtemp(prefix="med3d_")
    return build(deck_plan, os.path.join(out_dir, f"3D_{_safe(topic)}.pptx"), scenes=scenes)


async def build_deck(topic: str, slide_count: int, *, language: str = "uz", level: int = 2,
                     preferences: str = "", stage_cb: Optional[Callable[[str, Dict], None]] = None,
                     style: Optional[str] = None) -> Tuple[str, int]:
    """Bot uchun: (PPTX yo'li, slaydlar soni). Mavzu anatomiya bo'lmasa NotAnatomy, boshqa xatoda istisno."""
    def stage(name: str, **info) -> None:
        if stage_cb:
            try:
                stage_cb(name, info)
            except Exception:                     # noqa: BLE001
                log.debug("stage_cb xatosi", exc_info=True)

    loop = asyncio.get_running_loop()
    count = max(MIN_SLIDES, min(MAX_SLIDES, int(slide_count or 8)))
    stage("plan")
    plan_ = await asyncio.wait_for(loop.run_in_executor(
        None, lambda: plan(topic, count, language, level, preferences)), 6 * 60)
    log.info("3D Anatomiya: %s tana, %d slayd, organlar: %s", plan_["body"], len(plan_["slides"]),
             sorted({o for s in plan_["slides"] for o in s["show"]}))
    if any(s.get("picture") for s in plan_["slides"]):
        # Kasallik rasmlari 3D dan OLDIN: xizmat ishlamasa — mijozdan keyinroq urinib ko'rish so'raladi.
        stage("pictures")
        ready = await loop.run_in_executor(None, pictures_ready)
        if not ready or not await draw_pictures(plan_):
            raise PicturesUnavailable("kasallik rasmlari chizilmadi")
    if any(s.get("scene") for s in plan_["slides"]):
        await draw_scenes(plan_)                  # chizilmasa — slayd rasmsiz (bloklamaydi)
    stage("models", slides=len(plan_["slides"]))
    try:
        path = await asyncio.wait_for(loop.run_in_executor(None, lambda: make_deck(topic, plan_, style=style)),
                                      8 * 60)
    finally:
        for s in plan_["slides"]:
            for key in ("picture_path", "scene_path"):
                if s.get(key):
                    try:
                        os.remove(s[key])
                    except OSError:
                        pass
    return path, len(plan_["slides"])


# Kasallik rasmi uchun kuchli modellar (navbat bilan): Seedream 4 — realistik va tibbiy mavzuni moderatsiyada
# rad etmaydi, Nano Banana — mavzuni eng yaxshi tushunadi, FLUX — zaxira. `MED3D_IMAGE_MODELS` bilan almashtiriladi.
PICTURE_MODELS = ("ByteDance-Seed/Seedream-4.0,google/flash-image-2.5,black-forest-labs/FLUX.2-pro,"
                  "black-forest-labs/FLUX.1.1-pro")


def picture_models() -> List[str]:
    raw = os.getenv("MED3D_IMAGE_MODELS") or PICTURE_MODELS
    return [m.strip() for m in raw.split(",") if m.strip()]


def pictures_ready() -> bool:
    """Rasm xizmati ishga yaroqlimi (bepul tekshiruv: kalit bor va hisobda modellardan biri ochiq)."""
    if not os.getenv("TOGETHER_API_KEY"):
        return False
    from services.together_service import list_account_image_models

    have = list_account_image_models()
    if have is None:                              # ro'yxatni olib bo'lmadi — chizishda ko'riladi
        return True
    return any(m.lower() in have for m in picture_models())


PICTURE_STYLE = ("detailed medical textbook illustration, anatomically accurate, realistic 3D medical render, "
                 "close-up of the affected structure, soft studio lighting, dark neutral background, "
                 "no text, no letters, no labels, no arrows, no watermark, no people, no faces, no nudity, "
                 "no genitals")


async def draw_pictures(plan_: dict, timeout: float = 150.0) -> int:
    """Kasallik slaydlaridagi rasmlar (AI): 3D atlasda yo'q narsa — patologiyaning haqiqiy shakli (yirtilgan pay,
    churra, tromb). Parallel chiziladi; chizilmagani shunchaki rasmsiz qoladi. Qaytaradi: chizilganlar soni."""
    from services.together_service import get_together_service

    wanted = [s for s in plan_["slides"] if s.get("picture")]
    if not wanted:
        return 0
    try:
        together = get_together_service()
    except Exception as exc:                      # noqa: BLE001
        log.warning("3D Anatomiya: rasm xizmati yo'q: %s", exc)
        return 0

    async def one(slide: dict) -> None:
        prompt = f"{slide['picture']}. {PICTURE_STYLE}"
        try:
            path = await asyncio.wait_for(together.generate_with_models(prompt, picture_models(), stem="med3d_pic"),
                                          timeout)
        except Exception as exc:                  # noqa: BLE001
            log.warning("3D Anatomiya: rasm chizilmadi (%s): %s", slide["picture"][:60], exc)
            return
        if path and os.path.exists(path):
            slide["picture_path"] = path

    await asyncio.gather(*(one(s) for s in wanted))
    done = sum(1 for s in wanted if s.get("picture_path"))
    log.info("3D Anatomiya: kasallik rasmlari %d/%d", done, len(wanted))
    return done


SCENE_STYLE = ("realistic photograph, natural soft light, modern clinic or home setting, people fully clothed, "
               "calm and reassuring mood, no text, no letters, no logos, no watermark")


async def draw_scenes(plan_: dict, timeout: float = 120.0) -> int:
    """Davolash slaydlaridagi bemor tasvirlari — arzon model (admin tanlagan oddiy taqdimot modeli). Chizilmagani
    rasmsiz qoladi, jarayon to'xtamaydi."""
    from services.together_service import get_together_service

    wanted = [s for s in plan_["slides"] if s.get("scene")]
    if not wanted:
        return 0
    try:
        together = get_together_service()
    except Exception as exc:                      # noqa: BLE001
        log.warning("3D Anatomiya: rasm xizmati yo'q: %s", exc)
        return 0

    async def one(slide: dict) -> None:
        try:
            path = await asyncio.wait_for(together.generate_image(f"{slide['scene']}. {SCENE_STYLE}",
                                                                  aspect_ratio="16:9", target="presentation"),
                                          timeout)
        except Exception as exc:                  # noqa: BLE001
            log.warning("3D Anatomiya: davolash rasmi chizilmadi: %s", exc)
            return
        if path and os.path.exists(path):
            slide["scene_path"] = path

    await asyncio.gather(*(one(s) for s in wanted))
    done = sum(1 for s in wanted if s.get("scene_path"))
    log.info("3D Anatomiya: davolash rasmlari %d/%d", done, len(wanted))
    return done
