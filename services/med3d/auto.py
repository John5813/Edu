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
import json
import logging
import os
import re
import tempfile
from functools import lru_cache
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from . import ASSETS_DIR, manba
from .camera import Camera
from .catalog import srgb
from .glb import Primitive, write_glb
from .lugat import BY_ID, ORGANS, SOURCES
from .simplify import simplify

log = logging.getLogger(__name__)

# Reja uchun model: tibbiy faktlar, o'zbekcha anatomik atamalar va qat'iy JSON — eng ishonchli model kerak.
# Admin paneldagi "premium model" tanlovi bunga ta'sir qilmaydi (u arzon model bo'lishi mumkin).
MODEL = os.getenv("MED3D_MODEL") or "anthropic/claude-sonnet-5"
SLIDE_OPTIONS = (5, 8, 10, 12, 15)
MIN_SLIDES, MAX_SLIDES = 3, 15
ORGAN_MAX_TRIS = 60000           # bitta organ modeli shundan katta bo'lsa soddalashtiriladi
SLIDE_MAX_TRIS = 160000          # bir slayddagi hamma organlar birga
MAX_SHOW, MAX_LABELS = 8, 6
LEXICON = os.path.join(ASSETS_DIR, "lugat.json")


class NotAnatomy(RuntimeError):
    """Mavzu tana tuzilishiga oid emas — taqdimot qilinmaydi (pul qaytariladi)."""


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
{"anatomy": true, "reason": "", "body": "male" | "female",
 "names": {"<organ_id>": "<anatomical name in the presentation language>"},
 "slides": [{"title": "...", "text": "...", "show": ["<organ_id>", ...], "focus": ["<organ_id>"],
             "rot": [x, y, z], "labels": ["<organ_id>", ...], "exit": "up" | "down" | "left" | "right"}]}

RULES
1. "anatomy": false when the topic is NOT about the structure of the human body (history, economics, literature,
   physics, chemistry, technology, animals, plants, sport results...). Human organs, bones, muscles, body systems,
   their functions, and diseases/physiology of human organs ARE anatomy (show the organs involved).
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
6. "rot" degrees: x tilts (positive = seen from above, keep within -60..60); y turns around the vertical axis
   (0 = front view, 90 = the body's right side faces the viewer, -90 = its left side, 180 = back view);
   z = 0. Change the view by 20-90 degrees between neighbouring slides; never repeat the same view twice in a row.
7. "labels": 0-6 organ ids from "show" to point at with lines; do not label organs hidden behind others.
8. Heart topics: use "aorta_yoyi" and "yuqori_kovak_vena" (the parts next to the heart); "aorta" and
   "kovak_venalar" run through the whole trunk and make the heart look tiny — use them only for circulation of
   the whole body. Valves ("yurak_klapanlari") lie INSIDE the heart: to show them, view the heart from above
   (x 40-60) or remove "yurak"/"yurak_qorinchalari" from that slide.
9. "title": at most 6 words. "text": 2-4 sentences, at most 380 characters, accurate textbook facts, clear for the
   requested level. No diagnosis or treatment advice, no invented statistics, never mention the current year
   or dates.
10. "names": for EVERY organ id you use, its correct anatomical name in the presentation language.
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
        return llm_client._call_openrouter(SYSTEM, user, temperature=0.4, max_tokens=3000 + 800 * count)


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
        focus = [o for o in (s.get("focus") or []) if o in show]
        labels = [o for o in (s.get("labels") or []) if o in show][:MAX_LABELS]
        rot = list(s.get("rot") or [0, 0, 0])[:3] + [0, 0, 0]
        slides.append({
            "title": str(s.get("title") or "").strip()[:90],
            "text": re.sub(r"\s+\n", "\n", str(s.get("text") or "").strip())[:520],
            "show": show, "focus": focus or None, "labels": list(dict.fromkeys(labels)),
            "rot": [_num(rot[0], -60, 60), _num(rot[1], -180, 180), _num(rot[2], -30, 30)],
            "exit": s.get("exit") if s.get("exit") in ("up", "down", "left", "right") else "up",
        })
    if len(slides) < max(MIN_SLIDES, count - 1):
        raise ValueError(f"reja {len(slides)} slayd, {count} kerak")
    names = {}
    ai_names = data.get("names") if isinstance(data.get("names"), dict) else {}
    for organ in {o for s in slides for o in s["show"]}:
        if language == "uz":
            names[organ] = BY_ID[organ]["uz"]       # o'zbekcha nomlar — tekshirilgan lug'atdan
        else:
            names[organ] = str(ai_names.get(organ) or BY_ID[organ]["en"]).strip()[:40]
    return {"body": body, "slides": slides, "names": names}


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


def build_scenes(body_key: str, plan_: dict, atlas=None) -> Tuple[dict, Dict[str, dict]]:
    """Reja → (deck rejasi, xotiradagi sahnalar). atlas — test uchun almashtirsa bo'ladi."""
    body = lexicon()["bodies"][body_key]
    slides = plan_["slides"]
    reveal_hidden(body, slides)
    atlas = atlas or manba.atlas(body_key)
    meshes: Dict[Tuple[str, int], tuple] = {}
    scenes: Dict[str, dict] = {}
    deck_slides = []
    for number, (members, lo, hi) in enumerate(split_runs(body, slides)):
        key = f"run{number}"
        organs = list(dict.fromkeys(o for i in members for o in slides[i]["show"]))
        heaviest = max(sum(min(body[o]["tris"], ORGAN_MAX_TRIS) for o in slides[i]["show"]) for i in members)
        scale = min(1.0, SLIDE_MAX_TRIS / max(heaviest, 1))
        groups, labels = {}, {}
        for organ in organs:
            target = int(max(6000, min(body[organ]["tris"], ORGAN_MAX_TRIS) * scale))
            cache_key = (organ, target)
            if cache_key not in meshes:
                meshes[cache_key] = simplify(*_mesh(atlas, body[organ]["parts"]), target)
            pos, nrm, idx = meshes[cache_key]
            prim = Primitive(pos, nrm, idx, srgb(BY_ID[organ]["color"]), roughness=0.55, name=organ)
            groups[organ] = {"samples": body[organ]["samples"],
                             "glb": write_glb([prim], anchors=(lo, hi), name=organ)}
            labels[organ] = {"uz": plan_["names"].get(organ, BY_ID[organ]["uz"]), "group": organ,
                             "samples": body[organ]["samples"]}
        scenes[key] = {"bbox_min": lo.tolist(), "bbox_max": hi.tolist(), "source": SOURCES[body_key],
                       "groups": groups, "labels": labels}
        for i in members:
            deck_slides.append((i, dict(slides[i], scene=key)))
    deck_slides.sort(key=lambda item: item[0])
    return {"scene": "run0", "slides": [s for _, s in deck_slides]}, scenes


def _safe(name: str) -> str:
    return re.sub(r"[^\w\-]+", "_", name, flags=re.UNICODE).strip("_")[:40] or "taqdimot"


def make_deck(topic: str, plan_: dict, out_dir: Optional[str] = None, atlas=None) -> str:
    from .deck import build

    deck_plan, scenes = build_scenes(plan_["body"], plan_, atlas)
    out_dir = out_dir or tempfile.mkdtemp(prefix="med3d_")
    return build(deck_plan, os.path.join(out_dir, f"3D_{_safe(topic)}.pptx"), scenes=scenes)


async def build_deck(topic: str, slide_count: int, *, language: str = "uz", level: int = 2,
                     preferences: str = "", stage_cb: Optional[Callable[[str, Dict], None]] = None
                     ) -> Tuple[str, int]:
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
    stage("models", slides=len(plan_["slides"]))
    path = await asyncio.wait_for(loop.run_in_executor(None, lambda: make_deck(topic, plan_)), 8 * 60)
    return path, len(plan_["slides"])
