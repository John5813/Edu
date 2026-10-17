"""Harakat rejissyori: har slayd uchun kompozitsiya va kamera harakati — taqdimot boshidan oxirigacha takrorlanmaydi.

Morph ikki slayd orasidagi farqni harakatga aylantiradi: model joyi, o'lchami va burilishi, matn va bezaklar
joyi. Shuning uchun "harakat" — bu keyingi slaydning qanday tuzilgani:

- kamera: orbita (40–80° aylanish), aylanish (150°+), yuqoridan/pastdan qarash, yaqinlashish, uzoqlashish;
- kompozitsiya almashishi: matn chapdan o'ngga o'tadi — model slayd bo'ylab suzadi (sayohat), qahramon kadr
  (model katta), markaz, karta, pastki tasma;
- portlash: organlar bir-biridan ajraladi va keyingi slaydda qayta yig'iladi (boylam bor slaydda — yo'q:
  boylam ikki suyakni bog'lab turadi, ajratilsa uzilgandek ko'rinadi);
- sahna almashganda: eski organlar bir tomonga uchib ketadi, yangilari boshqa tomondan kiradi (yo'nalish har
  safar boshqacha).

Har slaydning asosiy burchagi — "eng yaxshi ko'rinish": fokusdagi organ boshqa organlar ortida qolmaydigan va
kadrda katta ko'rinadigan burchak (AI taklif qilgan burchakka yaqin bo'lgani afzal).
"""
import hashlib
import math
import random
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .camera import Camera, rotation, sides
from .lugat import JOINT_IDS

CAMERA_MOVES = ("orbita", "aylanish", "yuqoridan", "pastdan", "yaqin", "uzoq", "tinch")
LAYOUTS = ("chap_matn", "ong_matn", "markaz", "qahramon", "karta", "pastki")
SIDE_FLIP = {"chap_matn": "ong_matn", "ong_matn": "chap_matn", "karta": "ong_matn"}
DOORS = (("left", "right"), ("up", "down"), ("right", "left"), ("down", "up"))
# Asosiy burchak nomzodlari (gradus, X, Y, Z): old, yon, yarim yon, orqa, tepadan-yon.
VIEWS = [(0, 0, 0), (0, 30, 0), (0, -30, 0), (0, 55, 0), (0, -55, 0), (0, 90, 0), (0, -90, 0), (0, 180, 0),
         (20, 25, 0), (20, -25, 0), (-15, 0, 0), (30, 0, 0)]


def _cam(body: dict, organs: Sequence[str]) -> Camera:
    lo = np.min([body[o]["min"] for o in organs], axis=0)
    hi = np.max([body[o]["max"] for o in organs], axis=0)
    return Camera(lo, hi)


def _toward_camera(rot) -> np.ndarray:
    """Model koordinatalarida kamera tomon yo'nalish (Camera.project: kamera +Z da)."""
    return rotation(rot)[2, :]


def facing(points, rot) -> float:
    """Yassi organ (chaynov, chakka mushagi) yuzi bilan qaralyaptimi: 1 — to'g'ri yuzidan, 0 — qirrasidan.
    Organ yassi bo'lmasa (yumaloq) — burchak farq qilmaydi, ta'sir kichik."""
    total, weight = 0.0, 0.0
    view = _toward_camera(rot)
    for part in sides(points):
        if len(part) < 6:
            continue
        vals, vecs = np.linalg.eigh(np.cov((part - part.mean(axis=0)).T))
        flat = 1.0 - math.sqrt(max(vals[0], 0.0) / max(vals[1], 1e-12))
        total += len(part) * flat * abs(float(vecs[:, 0] @ view))
        weight += len(part)
    return total / weight if weight else 0.0


def view_score(body: dict, show: Sequence[str], focus: Sequence[str], rot) -> float:
    """Burchak qanchalik yaxshi: fokus ko'rinishi (boshqa organlar ortida qolmasligi), kadrda egallagan joyi va
    yassi organ yuzi bilan ko'rinishi. Juft organda — yaxshiroq ko'rinayotgan tomoni hisoblanadi."""
    cam = _cam(body, show)
    pts = [p for o in focus for p in body[o]["samples"]]
    others = [p for o in show if o not in focus for p in body[o]["samples"]]
    if others:
        shares = []
        for o in focus:
            shares.append(max(cam.visible_share(part, rot, others) for part in sides(body[o]["samples"])))
        seen = float(np.mean(shares))
    else:
        seen = 1.0
    face = float(np.mean([facing(body[o]["samples"], rot) for o in focus]))
    f0, g0, f1, g1 = cam.extent(pts, rot)
    a0, b0, a1, b1 = cam.extent([p for o in show for p in body[o]["samples"]], rot)
    share = ((f1 - f0) * (g1 - g0)) / max((a1 - a0) * (b1 - b0), 1e-6)
    # Darslikdagidek: old va yon tomondan ko'rinish afzal, orqadan va juda qiya burchak — kamroq.
    y = (float(rot[1]) + 180) % 360 - 180
    back = 0.45 if abs(y) > 110 else 0.0
    tilt = 0.006 * max(0.0, abs(float(rot[0])) - 40)
    return 2.0 * seen + 0.6 * min(share, 1.0) + 0.9 * face - back - tilt


def _angle_gap(a, b) -> float:
    return math.sqrt(sum(((x - y + 180) % 360 - 180) ** 2 for x, y in zip(a, b)))


def best_view(body: dict, slide: dict) -> Tuple[float, float, float]:
    """AI burchagiga yaqin, lekin fokusdagi organ yaxshi ko'rinadigan burchak."""
    show = [o for o in slide["show"] if o in body]
    focus = [o for o in (slide.get("focus") or show) if o in body] or show
    if not show:
        return tuple(slide.get("rot") or (0, 0, 0))
    ai = tuple(float(a) for a in (slide.get("rot") or (0, 0, 0)))
    best, best_score = ai, -1e9
    for cand in [ai] + VIEWS:
        score = view_score(body, show, focus, cand) - 0.004 * _angle_gap(cand, ai)
        if score > best_score + 1e-6:
            best, best_score = cand, score
    return tuple(float(a) for a in best)


def _seed(text: str) -> int:
    return int(hashlib.md5(text.encode("utf-8")).hexdigest()[:8], 16)


def direct(body: dict, slides: List[dict], topic: str = "") -> List[str]:
    """Slaydlarga kompozitsiya (`layout`), burchak (`rot`), yaqinlik (`zoom`), portlash (`explode`) va
    uchish yo'nalishi (`enter`/`exit`) beradi. Qaytaradi: har o'tishdagi harakat nomi (log va test uchun)."""
    rng = random.Random(_seed(topic or "".join(s.get("title", "") for s in slides)))
    n = len(slides)
    moves: List[str] = []
    used: Dict[str, int] = {}
    limit = max(2, math.ceil(n / 4))
    prev_layout, prev_move, prev_rot, prev_show = "", "", None, None
    exploded = 0
    for i, s in enumerate(slides):
        show = [o for o in s["show"] if o in body]
        focus = [o for o in (s.get("focus") or show) if o in body] or show
        labels = len(s.get("labels") or [])
        base = best_view(body, s)
        rot, zoom, explode, move = base, None, 0.0, "tinch"

        # Kompozitsiya: oldingisidan farqli; yorliq ko'p bo'lsa — yorliqqa joy ko'p kompozitsiya.
        if i == 0:
            lay = rng.choice(("qahramon", "chap_matn"))
        elif i == n - 1:
            lay = rng.choice([x for x in ("markaz", "qahramon", "chap_matn") if x != prev_layout])
        else:
            pool = [x for x in LAYOUTS if x != prev_layout]
            if labels >= 4:
                pool = [x for x in pool if x not in ("qahramon", "pastki")] or pool
            if labels == 0:
                pool = [x for x in pool if x in ("qahramon", "pastki", "chap_matn", "ong_matn")] or pool
            weights = [1.0 / (1 + used.get("lay:" + x, 0)) ** 2 for x in pool]
            lay = rng.choices(pool, weights)[0]
        used["lay:" + lay] = used.get("lay:" + lay, 0) + 1

        if i:
            # Kamera harakati: oldingisidan farqli va har biri ko'pi bilan `limit` marta.
            options = [m for m in CAMERA_MOVES if m != prev_move and used.get(m, 0) < limit]
            # Portlash: bir nechta organli slaydda (to'plam o'zgargan bo'lsa ham — yordamchi slayd o'sha joyda
            # bo'laklarga almashtiradi). 6+ slaydli taqdimotda kamida bittasi bo'ladi.
            can_explode = (exploded < (2 if n >= 10 else 1) and 2 <= len(show) <= 7 and labels >= 2
                           and i < n - 1 and prev_move != "portlash" and not JOINT_IDS.intersection(show))
            if can_explode and (rng.random() < 0.4 or (exploded == 0 and n >= 6 and i >= n // 2)):
                move = "portlash"
            elif i == n - 1:
                move = "uzoq" if "uzoq" in options else rng.choice(options or CAMERA_MOVES)
            else:
                move = rng.choice(options or CAMERA_MOVES)
            used[move] = used.get(move, 0) + 1

            if move in ("orbita", "aylanish") and prev_rot is not None:
                # Orbita: 40–85° burilish; aylanish: 110–160° — ikkalasida ham yangi burchak yaxshi ko'rinishli.
                lo_step, hi_step = (40, 85) if move == "orbita" else (110, 160)
                x = round(prev_rot[0] * 0.5 + base[0] * 0.5, 1)
                tries = []
                for dy in range(-160, 161, 10):
                    if lo_step <= abs(dy) <= hi_step:
                        cand = (x, prev_rot[1] + dy, 0.0)
                        tries.append((view_score(body, show, focus, cand) + rng.uniform(0, 0.05), cand))
                if tries:
                    score, cand = max(tries)
                    if score >= view_score(body, show, focus, base) - 0.5:
                        rot = cand
                    else:
                        move = "tinch"
            elif move == "yuqoridan":
                rot = (min(base[0] + 35.0, 60.0), base[1], 0.0)
            elif move == "pastdan":
                rot = (max(base[0] - 25.0, -40.0), base[1], 0.0)
            elif move == "yaqin":
                zoom = 1.32
            elif move == "uzoq":
                zoom = 0.8
            elif move == "portlash":
                explode = 0.75
                rot = prev_rot if prev_rot is not None else base
                exploded += 1
            if move == "tinch" and lay == prev_layout:
                lay = SIDE_FLIP.get(lay, "ong_matn")
        exit_, enter = DOORS[rng.randrange(len(DOORS))]
        s.update(layout=lay, rot=[round(a, 1) for a in rot], zoom=zoom, explode=explode, enter=enter, exit=exit_)
        moves.append(move)
        prev_layout, prev_move, prev_rot, prev_show = lay, move, rot, sorted(show)
    return moves
