"""Tibbiy 3D taqdimotni rejadan yig'adi: chapda matn, o'ngda 3D model, yorliq chiziqlari, Morph o'tishi.

Reja (keyinchalik AI tuzadi):

    {"scene": "skull",
     "slides": [
        {"title": "Bosh suyagi", "text": "...", "show": ["cranium", "mandible"], "rot": [0, 0, 0],
         "labels": ["frontal", "parietal_r", "mandible"]},
        {"title": "Pastki jag'", "text": "...", "show": ["mandible"], "rot": [70, 0, 0],
         "labels": ["incisors_lower", "molars_lower_l"], "exit": "up"}]}

- `show` — slaydda ko'rinadigan guruhlar; oldingi slaydda bo'lib, bunda yo'q guruh `exit` tomonga
  (sukut bo'yicha yuqoriga) slayddan chiqib ketadi — Morph uni silliq olib chiqadi.
- `focus` — kamera qaysi guruhlarga moslanadi (sukut — `show`); `rot` — gradus (X, Y, Z).
- Bir slayddagi hamma guruh bir xil ramka va aylanishda — qismlar bir-biriga aniq yopishadi.
"""
import logging
import os
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

from services.pro3d.build import add_entrances, add_morph, box, text

from . import ASSETS_DIR, load_scene
from .camera import Camera
from .pptx3d import add_model3d

log = logging.getLogger(__name__)

W, H = 13.333, 7.5
MORPH_MS = 2200
PAL = dict(bg="0B1220", ink="F3F6FB", muted="9FB0C8", accent="38BDF8", pill="14213A", pill_ink="E8F3FF",
           line="38BDF8")
TEXT_BOX = (0.65, 0.75, 4.35)                  # x, y, eni — chapdagi matn ustuni
MODEL_REGION = (7.05, 0.6, 4.2, 6.3)           # yorliqlar bo'lsa: ikki yonida yorliq ustunlari
MODEL_REGION_WIDE = (5.4, 0.45, 7.5, 6.6)      # yorliqsiz slayd: model kattaroq
FILL = 0.9
# 3D ramka tomoni (dyuym) — bundan katta ramkani PowerPoint juda katta tasvir sifatida chizadi
# (sekin va xira bo'lishi mumkin). Mayda organ uchun alohida, kichikroq sahna ishlatiladi.
MAX_FRAME = 26.0
LABEL_H, LABEL_GAP, LABEL_MAX_W = 0.36, 0.5, 3.0
LABEL_H2, LABEL_GAP2 = 0.54, 0.66              # ikki qatorli yorliq: o'zbekcha nom + lotincha nom
HIDDEN_SHARE = 0.08                            # organ yuzasining shundan kami ko'rinsa — yorliq qo'yilmaydi
ZOOM_LIMIT = 1.6                               # fokusga yaqinlashish: butun ko'rinishdan ko'pi bilan shuncha katta
LABEL_X_MIN, LABEL_X_MAX = 5.15, W - 0.2
EXITS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}


class Frame:
    """Bir slayddagi 3D ramka: markaz (dyuym), tomoni, aylanish."""

    def __init__(self, cx: float, cy: float, size: float, rot: Sequence[float]):
        self.cx, self.cy, self.size, self.rot = cx, cy, size, tuple(float(a) for a in rot)

    @property
    def left(self) -> float:
        return self.cx - self.size / 2

    @property
    def top(self) -> float:
        return self.cy - self.size / 2

    def to_slide(self, u: float, v: float) -> Tuple[float, float]:
        return self.cx + u * self.size, self.cy + v * self.size

    def moved_out(self, direction: str) -> "Frame":
        dx, dy = EXITS.get(direction, EXITS["up"])
        cx = self.cx + dx * (W + self.size) * 0.75 if dx else self.cx
        cy = -self.size / 2 - 0.4 if dy < 0 else (H + self.size / 2 + 0.4 if dy > 0 else self.cy)
        return Frame(cx, cy, self.size, self.rot)


def fit_frame(cam: Camera, points, rot, region) -> Frame:
    u0, v0, u1, v1 = cam.extent(points, rot)
    rx, ry, rw, rh = region
    size = min(rw * FILL / max(u1 - u0, 1e-6), rh * FILL / max(v1 - v0, 1e-6), MAX_FRAME)
    return Frame(rx + rw / 2 - size * (u0 + u1) / 2, ry + rh / 2 - size * (v0 + v1) / 2, size, rot)


TEXT_EDGE = 5.15            # chapdagi matn ustuni shu yerda tugaydi — 3D model undan chapga o'tmasin


def keep_clear(cam: Camera, frame: Frame, focus_points, all_points, left: float = TEXT_EDGE) -> Frame:
    """Kamera bitta organga yaqinlashganda yonidagi katta organ matn ustiga chiqmasin.

    Avval ramka o'ngga suriladi (fokusdagi organ slayddan chiqib ketmaguncha), bo'lmasa — fokus atrofida
    kichraytiriladi. Yuqori, pastki va o'ng chetdan chiqib turish mumkin (kesilgan "yaqin plan" ko'rinishi).
    """
    for _ in range(12):
        u0 = cam.extent(all_points, frame.rot)[0]
        x0 = frame.cx + u0 * frame.size
        if x0 >= left - 1e-3:
            return frame
        f0, g0, f1, g1 = cam.extent(focus_points, frame.rot)
        shift = left - x0
        if frame.cx + f1 * frame.size + shift <= W - 0.25:
            return Frame(frame.cx + shift, frame.cy, frame.size, frame.rot)
        fu, fv = (f0 + f1) / 2, (g0 + g1) / 2
        fx, fy = frame.cx + fu * frame.size, frame.cy + fv * frame.size
        size = frame.size * 0.85
        frame = Frame(fx - fu * size, fy - fv * size, size, frame.rot)
    return frame


def _too_big(cam: Camera, frame: Frame, points) -> bool:
    """Kamera boshqa organga yaqinlashganda bu organ slayddan bir yarim barobar katta bo'lib ketadimi.

    Masalan, klapanlarga yaqinlashganda yonidagi aorta butun ekranni to'sib qo'yadi — bunday organ shu
    slayddan chiqariladi (Morph uni uchirib yuboradi), keyingi umumiy ko'rinishda qaytadi.
    """
    u0, v0, u1, v1 = cam.extent(points, frame.rot)
    return (u1 - u0) * frame.size > 1.5 * W or (v1 - v0) * frame.size > 1.5 * H


def _spread(ys: List[float], top: float, bottom: float, gap: float) -> List[float]:
    """Yorliqlarni anchor balandligiga yaqin, lekin ustma-ust tushmaydigan qilib joylaydi."""
    out = [min(max(y, top), bottom) for y in ys]
    for i in range(1, len(out)):
        out[i] = max(out[i], out[i - 1] + gap)
    if out and out[-1] > bottom:
        out[-1] = bottom
        for i in range(len(out) - 2, -1, -1):
            out[i] = min(out[i], out[i + 1] - gap)
    return out


def _near(seg, point, tol: float = 0.13) -> bool:
    """Chiziq (seg) boshqa yorliq nuqtasi ustidan o'tadimi."""
    (x1, y1), (x2, y2), (px, py) = seg[0], seg[1], point
    dx, dy = x2 - x1, y2 - y1
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy or 1e-9)))
    return (x1 + t * dx - px) ** 2 + (y1 + t * dy - py) ** 2 < tol * tol


def _cross(a, b) -> bool:
    """Ikki chiziq kesishadimi."""
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    (p1, p2), (q1, q2) = a, b
    return (orient(p1, p2, q1) * orient(p1, p2, q2) < 0) and (orient(q1, q2, p1) * orient(q1, q2, p2) < 0)


def _untangle(edges: List[float], anchors: List[Tuple[float, float]], ys: List[float]) -> List[float]:
    """Chiziq qo'shni nuqta ustidan o'tsa, ikki yorliq o'rnini almashtiradi (kesishishlar kamaysa)."""
    def conflicts(order):
        segs = [((e, y), a) for e, y, a in zip(edges, order, anchors)]
        n = len(segs)
        over = sum(_near(segs[i], anchors[j]) for i in range(n) for j in range(n) if i != j)
        return over + sum(_cross(segs[i], segs[j]) for i in range(n) for j in range(i + 1, n))

    ys = list(ys)
    for _ in range(len(ys) * 2):
        best, swap = conflicts(ys), None
        for i in range(len(ys) - 1):
            trial = ys[:i] + [ys[i + 1], ys[i]] + ys[i + 2:]
            score = conflicts(trial)
            if score < best:
                best, swap = score, trial
        if swap is None:
            break
        ys = swap
    return ys


def _rgb(hex_color: str) -> RGBColor:
    return RGBColor.from_string(hex_color)


def _label(slide, name: str, x: float, y: float, value: str, right_align: bool,
           latin: str = "") -> Tuple[object, float, float]:
    """Yorliq kartochkasi. x — ustun cheti (o'ng ustunda chap cheti, chapda o'ng cheti). (shakl, chap, eni).

    latin berilsa — ikkinchi qatorda lotincha nom (kursiv, kichikroq): tibbiyotda a'zolar lotincha ataladi.
    """
    size = 11 if len(value) <= 24 else 10                # uzun nom — biroz kichik shrift va kengroq kartochka
    small = 9 if len(latin) <= 28 else 8
    width = min(LABEL_MAX_W, max(1.0, len(value) * size * 0.56 / 72 + 0.36, len(latin) * small * 0.52 / 72 + 0.36))
    height = LABEL_H2 if latin else LABEL_H
    left = x - width if right_align else x
    shape = box(slide, name, left, y - height / 2, width, height, PAL["pill"], round_=0.5 if not latin else 0.35,
                line=PAL["accent"], line_pt=0.75)
    frame = shape.text_frame
    frame.margin_left = frame.margin_right = Inches(0.1)
    frame.margin_top = frame.margin_bottom = 0
    frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    frame.word_wrap = False
    para = frame.paragraphs[0]
    para.alignment = PP_ALIGN.CENTER
    run = para.add_run()
    run.text = value
    run.font.name = "Segoe UI"
    run.font.size = Pt(size)
    run.font.bold = True
    run.font.color.rgb = _rgb(PAL["pill_ink"])
    if latin:
        second = frame.add_paragraph()
        second.alignment = PP_ALIGN.CENTER
        lat = second.add_run()
        lat.text = latin
        lat.font.name = "Segoe UI"
        lat.font.size = Pt(small)
        lat.font.italic = True
        lat.font.color.rgb = _rgb(PAL["muted"])
    return shape, left, width


def _labels(slide, cam: Camera, scene: dict, frame: Frame, keys: Sequence[str], visible: Sequence[str],
            model_box: Tuple[float, float, float, float]) -> List:
    known = scene["labels"]
    items = []
    for key in keys:
        info = known.get(key)
        if not info or info["group"] not in visible:
            log.warning("med3d: yorliq tashlab ketildi: %s", key)
            continue
        # Birlashgan modelda (bir nechta organ — bitta GLB) to'suvchilar yorliqning o'zida beriladi.
        others = info.get("occluders") or [p for g in visible if g != info["group"] for p in scene["groups"][g]["samples"]]
        radius = 0.12 / frame.size
        if others and cam.visible_share(info["samples"], frame.rot, others, radius) < HIDDEN_SHARE:
            log.info("med3d: organ boshqasi orqasida yopilgan, yorliq qo'yilmadi: %s", key)
            continue
        ax, ay = frame.to_slide(*cam.anchor(info["samples"], frame.rot, others, radius))
        if not (TEXT_EDGE <= ax <= W - 0.1 and 0.15 <= ay <= H - 0.15):
            log.info("med3d: yorliq nuqtasi slayddan tashqarida, qo'yilmadi: %s", key)
            continue
        items.append((key, info["uz"], ax, ay, info.get("la", "")))
    if not items:
        return []
    left, top, right, bottom = model_box
    mid = (left + right) / 2
    shapes = []
    for side in ("left", "right"):
        col = sorted((it for it in items if (it[2] < mid) == (side == "left")), key=lambda it: it[3])
        gap = LABEL_GAP2 if any(it[4] for it in col) else LABEL_GAP
        ys = _spread([it[3] for it in col], 0.75, H - 0.75, gap)
        if side == "left":
            edges = [max(LABEL_X_MIN + 1.0, min(left - 0.3, it[2] - 0.5)) for it in col]
        else:
            edges = [min(LABEL_X_MAX - 1.0, max(right + 0.3, it[2] + 0.5)) for it in col]
        ys = _untangle(edges, [(it[2], it[3]) for it in col], ys)
        for (key, uz, ax, ay, la), ly, edge in zip(col, ys, edges):
            if side == "left":
                pill, px, pw = _label(slide, f"lbl_{key}", edge, ly, uz, right_align=True, latin=la)
                if px < LABEL_X_MIN:
                    pill.left = Inches(LABEL_X_MIN)
                    px = LABEL_X_MIN
                start = (px + pw, ly)
            else:
                pill, px, pw = _label(slide, f"lbl_{key}", edge, ly, uz, right_align=False, latin=la)
                if px + pw > LABEL_X_MAX:
                    px = LABEL_X_MAX - pw
                    pill.left = Inches(px)
                start = (px, ly)
            line = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(start[0]), Inches(start[1]),
                                              Inches(ax), Inches(ay))
            line.name = f"lbl_{key}_line"
            line.line.color.rgb = _rgb(PAL["line"])
            line.line.width = Pt(1.25)
            dot = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(ax - 0.06), Inches(ay - 0.06), Inches(0.12),
                                         Inches(0.12))
            dot.name = f"lbl_{key}_dot"
            dot.fill.solid()
            dot.fill.fore_color.rgb = _rgb(PAL["accent"])
            dot.line.color.rgb = _rgb("FFFFFF")
            dot.line.width = Pt(1)
            dot.shadow.inherit = False
            shapes.extend([dot, line, pill])
    return shapes


def _text_column(slide, data: dict, index: int, total: int, source: str) -> List:
    x, y, w = TEXT_BOX
    box(slide, "!!accent", x, y, 0.9, 0.07, PAL["accent"], round_=0.5)
    title = text(slide, "!!title", x, y + 0.3, w, 1.7, data.get("title", ""), size=34, smallest=22, bold=True,
                 color=PAL["ink"], line=1.04)
    body = text(slide, "!!body", x, y + 2.15, w, 3.9, data.get("text", ""), size=16, smallest=12,
                color=PAL["muted"], line=1.25)
    text(slide, "!!page", x, H - 0.62, 1.2, 0.3, f"{index + 1:02d} / {total:02d}", size=10, color=PAL["muted"],
         spacing=1)
    text(slide, "!!source", x + 1.3, H - 0.62, 5.4, 0.3, f"3D: {source}", size=8, color=PAL["muted"])
    return [title, body]


def _model_name(scene_key: str, group: str, main: str) -> str:
    # Morph faqat bir xil nomli modellarni bog'laydi. Boshqa sahnadagi model (boshqa chegara qutisi)
    # bilan bog'lanmasligi uchun nomda sahna ham bor; asosiy sahnada — qisqa nom.
    return f"!!m3d_{group}" if scene_key == main else f"!!m3d_{scene_key}_{group}"


def build(plan: dict, out_path: str, *, assets_dir: str = ASSETS_DIR, scenes: Optional[Dict[str, dict]] = None,
          share: bool = True) -> str:
    """Reja → PPTX. Slayd o'z sahnasini `scene` bilan tanlashi mumkin (sukut — rejaning `scene`).

    scenes — xotirada tayyorlangan sahnalar (avtomatik tizim): {kalit: {bbox_min, bbox_max, source,
    groups: {g: {samples, glb}}, labels}}; berilmasa — `assets_dir` dagi tayyor sahnalar o'qiladi.
    share — bir xil GLB slaydlar orasida bitta faylga yoziladi (taqdimot hajmi bir necha barobar kichik).
    """
    main = plan["scene"]
    ready = scenes or {}
    scenes = {}
    cams: Dict[str, Camera] = {}
    glbs: Dict[Tuple[str, str], bytes] = {}
    parts: Optional[Dict] = {} if share else None

    def use(key: str) -> dict:
        if key not in scenes:
            scenes[key] = ready[key] if key in ready else load_scene(key, assets_dir)
            cams[key] = Camera(scenes[key]["bbox_min"], scenes[key]["bbox_max"])
            for g, info in scenes[key]["groups"].items():
                if "glb" in info:
                    glbs[(key, g)] = info["glb"]
                else:
                    with open(os.path.join(scenes[key]["dir"], info["file"]), "rb") as fh:
                        glbs[(key, g)] = fh.read()
        return scenes[key]

    # 1-bosqich: har slaydning sahnasi, ramkasi va ko'rinadigan organlari.
    slides = plan["slides"]
    plans = []
    for data in slides:
        key = data.get("scene") or main
        scene, cam = use(key), cams[key]
        groups = scene["groups"]
        show = [g for g in (data.get("show") or list(groups)) if g in groups]
        focus = [g for g in (data.get("focus") or show) if g in show] or show
        labels = list(data.get("labels") or [])
        region = MODEL_REGION if labels else MODEL_REGION_WIDE
        points = data.get("focus_points") or [p for g in focus for p in groups[g]["samples"]]
        if data.get("frame_of") is not None:         # kamera aynan oldingi slayddagidek (joyida almashish)
            frame = plans[data["frame_of"]]["frame"]
        else:
            rot = data.get("rot") or (0, 0, 0)
            everything = [p for g in show for p in groups[g]["samples"]]
            frame = fit_frame(cam, points, rot, region)
            whole = fit_frame(cam, everything, rot, region)
            if frame.size > whole.size * ZOOM_LIMIT:     # haddan tashqari yaqin: qo'shni organlar kesilib qoladi
                f0, g0, f1, g1 = cam.extent(points, rot)
                fx, fy = frame.to_slide((f0 + f1) / 2, (g0 + g1) / 2)
                size = whole.size * ZOOM_LIMIT
                frame = Frame(fx - (f0 + f1) / 2 * size, fy - (g0 + g1) / 2 * size, size, rot)
            frame = keep_clear(cam, frame, points, everything)
        show = [g for g in show if g in focus or not _too_big(cam, frame, groups[g]["samples"])]
        plans.append({"key": key, "scene": scene, "cam": cam, "frame": frame, "show": show,
                      "labels": labels, "names": {_model_name(key, g, main): (key, g)
                                                                            for g in show}})

    # 2-bosqich: slaydlar. Har o'tishda harakat bo'lsin: ketayotgan organ slayddan uchib chiqadi, keladigani
    # chetdan uchib kiradi (o'chib-yonmaydi). Sahna almashganda eskisi chapga ketadi, yangisi o'ngdan keladi.
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(W), Inches(H)
    layout = prs.slide_layouts[6]
    for index, (data, cur) in enumerate(zip(slides, plans)):
        key, scene, cam, frame, show = cur["key"], cur["scene"], cur["cam"], cur["frame"], cur["show"]
        slide = prs.slides.add_slide(layout)
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = _rgb(PAL["bg"])
        # Yordamchi (avtomatik o'tadigan) slaydlar raqamga kirmaydi: u keyingi slaydning raqamini ko'rsatadi.
        number = sum(1 for s in slides[:index] if not s.get("auto"))
        _text_column(slide, data, number, sum(1 for s in slides if not s.get("auto")), scene["source"])

        placed = set(cur["names"])
        # fade — bu slaydga o'tishda organlar uchib kelmaydi, o'z joyida asta almashadi (Morph o'zi so'ndiradi).
        if index and not data.get("fade"):           # oldingi slayddan ketayotganlar
            before = plans[index - 1]
            way = (data.get("exit") or "up") if before["key"] == key else "left"
            out = before["frame"].moved_out(way)
            for name, (k, g) in before["names"].items():
                if name not in placed:
                    add_model3d(slide, glbs[(k, g)], name, out.left, out.top, out.size, out.rot, parts)
                    placed.add(name)
        if index + 1 < len(plans) and not slides[index + 1].get("fade"):   # keyingilari — hozircha tashqarida
            after = plans[index + 1]
            way = "down" if after["key"] == key else "right"
            incoming = after["frame"].moved_out(way)
            for name, (k, g) in after["names"].items():
                if name not in placed:
                    add_model3d(slide, glbs[(k, g)], name, incoming.left, incoming.top, incoming.size,
                                incoming.rot, parts)
                    placed.add(name)
        # Har model alohida qatlam: PowerPoint ular orasida chuqurlikni solishtirmaydi. Uzoqdagisi avval
        # (orqaga), yaqinidagisi keyin qo'yiladi — masalan, oldinda turgan aorta o'pka arteriyasini yopadi.
        def depth(item):
            k, g = item[1]
            return float(np.median(cams[k].project(scenes[k]["groups"][g]["samples"], frame.rot)[1]))
        for name, (k, g) in sorted(cur["names"].items(), key=depth):
            add_model3d(slide, glbs[(k, g)], name, frame.left, frame.top, frame.size, frame.rot, parts)

        groups = scene["groups"]
        vis_points = [p for g in show for p in groups[g]["samples"]]
        u0, v0, u1, v1 = cam.extent(vis_points, frame.rot)
        model_box = (*frame.to_slide(u0, v0), *frame.to_slide(u1, v1))
        label_shapes = _labels(slide, cam, scene, frame, cur["labels"], show, model_box)
        steps = [(s, "fade", 250 + (i // 3) * 220) for i, s in enumerate(label_shapes)]
        if steps:
            add_entrances(slide, steps)
        if index:
            add_morph(slide, MORPH_MS)
            if data.get("auto"):                     # yordamchi slayd: o'tish tugashi bilan keyingisiga o'tadi
                for node in slide._element.iter("{http://schemas.openxmlformats.org/presentationml/2006/main}transition"):
                    node.set("advClick", "0")
                    node.set("advTm", "0")

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    prs.save(out_path)
    return out_path


DEMO_PLAN = {
    "scene": "skull",
    "slides": [
        {"title": "Bosh suyagi",
         "text": "Bosh suyagi miya qutisi va yuz suyaklaridan iborat. U miyani himoya qiladi, sezgi "
                 "a'zolari va chaynov apparatiga tayanch bo'ladi. Pastki jag' — bosh suyagining yagona "
                 "harakatchan suyagi.",
         "show": ["cranium", "mandible"], "rot": [0, 0, 0],
         "labels": ["frontal", "parietal_r", "temporal_l", "zygomatic_r", "nasal", "maxilla_l", "mandible"]},
        {"title": "Pastki jag' suyagi",
         "text": "Pastki jag' chakka suyagi bilan bo'g'im hosil qiladi va chaynashda harakatlanadi. "
                 "Yuqoridan qaraganda tishlar taqasimon ravoq bo'lib joylashgan: oldinda kesuv tishlar, "
                 "yonlarida qoziq va oziq tishlar.",
         "show": ["mandible"], "rot": [70, 0, 0], "exit": "up",
         "labels": ["incisors_lower", "canine_lower_l", "premolars_lower_l", "molars_lower_r"]},
        {"title": "Yon tomondan ko'rinish",
         "text": "Qismlar qayta birlashganda bosh suyagining yon tomoni ko'rinadi: chakka suyagi, ensa "
                 "suyagi va pastki jag'ning chakka-pastki jag' bo'g'imi.",
         "show": ["cranium", "mandible"], "rot": [0, 90, 0],
         "labels": ["frontal", "parietal_r", "temporal_r", "occipital", "zygomatic_r", "mandible"]},
    ],
}
