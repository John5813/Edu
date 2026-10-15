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
LABEL_H, LABEL_GAP, LABEL_MAX_W = 0.36, 0.5, 2.1
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
    size = min(rw * FILL / max(u1 - u0, 1e-6), rh * FILL / max(v1 - v0, 1e-6))
    return Frame(rx + rw / 2 - size * (u0 + u1) / 2, ry + rh / 2 - size * (v0 + v1) / 2, size, rot)


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


def _label(slide, name: str, x: float, y: float, value: str, right_align: bool) -> Tuple[object, float, float]:
    """Yorliq kartochkasi. x — ustun cheti (o'ng ustunda chap cheti, chapda o'ng cheti). (shakl, chap, eni)."""
    width = min(LABEL_MAX_W, max(1.0, len(value) * 11 * 0.56 / 72 + 0.36))
    left = x - width if right_align else x
    shape = box(slide, name, left, y - LABEL_H / 2, width, LABEL_H, PAL["pill"], round_=0.5,
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
    run.font.size = Pt(11)
    run.font.bold = True
    run.font.color.rgb = _rgb(PAL["pill_ink"])
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
        ax, ay = frame.to_slide(*cam.anchor(info["samples"], frame.rot))
        items.append((key, info["uz"], ax, ay))
    if not items:
        return []
    left, top, right, bottom = model_box
    mid = (left + right) / 2
    shapes = []
    for side in ("left", "right"):
        col = sorted((it for it in items if (it[2] < mid) == (side == "left")), key=lambda it: it[3])
        ys = _spread([it[3] for it in col], 0.75, H - 0.75, LABEL_GAP)
        if side == "left":
            edges = [max(LABEL_X_MIN + 1.0, min(left - 0.3, it[2] - 0.5)) for it in col]
        else:
            edges = [min(LABEL_X_MAX - 1.0, max(right + 0.3, it[2] + 0.5)) for it in col]
        ys = _untangle(edges, [(it[2], it[3]) for it in col], ys)
        for (key, uz, ax, ay), ly, edge in zip(col, ys, edges):
            if side == "left":
                pill, px, pw = _label(slide, f"lbl_{key}", edge, ly, uz, right_align=True)
                if px < LABEL_X_MIN:
                    pill.left = Inches(LABEL_X_MIN)
                    px = LABEL_X_MIN
                start = (px + pw, ly)
            else:
                pill, px, pw = _label(slide, f"lbl_{key}", edge, ly, uz, right_align=False)
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


def build(plan: dict, out_path: str, *, assets_dir: str = ASSETS_DIR) -> str:
    scene = load_scene(plan["scene"], assets_dir)
    cam = Camera(scene["bbox_min"], scene["bbox_max"])
    groups = scene["groups"]
    glbs: Dict[str, bytes] = {}
    for key, info in groups.items():
        with open(os.path.join(scene["dir"], info["file"]), "rb") as fh:
            glbs[key] = fh.read()

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(W), Inches(H)
    layout = prs.slide_layouts[6]
    slides = plan["slides"]
    prev: Optional[Tuple[Frame, List[str]]] = None
    for index, data in enumerate(slides):
        show = [g for g in (data.get("show") or list(groups)) if g in groups]
        focus = [g for g in (data.get("focus") or show) if g in show] or show
        labels = list(data.get("labels") or [])
        region = MODEL_REGION if labels else MODEL_REGION_WIDE
        points = [p for g in focus for p in groups[g]["samples"]]
        frame = fit_frame(cam, points, data.get("rot") or (0, 0, 0), region)

        slide = prs.slides.add_slide(layout)
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = _rgb(PAL["bg"])
        _text_column(slide, data, index, len(slides), scene["source"])

        if prev is not None:                         # chiqib ketayotgan qismlar: oldingi joyidan tashqariga
            prev_frame, prev_show = prev
            out = prev_frame.moved_out(data.get("exit") or "up")
            for g in prev_show:
                if g not in show:
                    add_model3d(slide, glbs[g], f"!!m3d_{g}", out.left, out.top, out.size, out.rot)
        for g in show:
            add_model3d(slide, glbs[g], f"!!m3d_{g}", frame.left, frame.top, frame.size, frame.rot)

        vis_points = [p for g in show for p in groups[g]["samples"]]
        u0, v0, u1, v1 = cam.extent(vis_points, frame.rot)
        model_box = (*frame.to_slide(u0, v0), *frame.to_slide(u1, v1))
        label_shapes = _labels(slide, cam, scene, frame, labels, show, model_box)
        steps = [(s, "fade", 250 + (i // 3) * 220) for i, s in enumerate(label_shapes)]
        if steps:
            add_entrances(slide, steps)
        if index:
            add_morph(slide, MORPH_MS)
        prev = (frame, show)

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
