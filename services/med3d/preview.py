"""3D model rasmi (PNG) — 3D ko'rsatmaydigan dasturlar uchun zaxira (telefon, WPS, Google Slides, LibreOffice).

PowerPoint 3D modelni o'zi chizadi, boshqa dasturlar esa `mc:Fallback` dagi rasmni ko'rsatadi. Ilgari u
shaffof 1×1 rasm edi — telefonda 3D organlar umuman ko'rinmasdi. Endi model xuddi PowerPoint'dagi kamera
(`camera.Camera`: o'sha markaz, masshtab, ko'rish burchagi va aylanish) bilan oddiy rasm qilib chiziladi:
uchburchaklar uzoqdan yaqinga (rassom usuli), har biri yorug'likka qarab soyalanadi. Tez (bitta model —
0,1–0,5 soniya), qo'shimcha kutubxona kerak emas (numpy va Pillow).
"""
import hashlib
import io
from collections import OrderedDict
from typing import Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw

from . import glb as glb_mod
from .camera import Camera, rotation

_TYPES = {5121: np.uint8, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
_WIDTH = {"SCALAR": 1, "VEC3": 3, "VEC4": 4}
_LIGHT = np.array([-0.35, 0.45, 0.82]) / np.linalg.norm([-0.35, 0.45, 0.82])
DPI = 72                    # rasm aniqligi: ramkaning har dyuymiga shuncha piksel
MIN_PX, MAX_PX = 160, 1100
_CACHE: "OrderedDict[tuple, bytes]" = OrderedDict()


def _accessor(doc: dict, binary: bytes, index: int) -> np.ndarray:
    acc = doc["accessors"][index]
    view = doc["bufferViews"][acc["bufferView"]]
    kind, width = _TYPES[acc["componentType"]], _WIDTH[acc["type"]]
    arr = np.frombuffer(binary, kind, acc["count"] * width, view.get("byteOffset", 0) + acc.get("byteOffset", 0))
    arr = arr.reshape(-1, width) if width > 1 else arr
    if acc.get("normalized") and kind != np.float32:
        arr = arr.astype(np.float32) / np.iinfo(kind).max
    return arr


def _meshes(data: bytes):
    doc, binary = glb_mod.read_glb(data)
    for mesh in doc.get("meshes", []):
        for prim in mesh.get("primitives", []):
            attrs = prim["attributes"]
            if prim.get("mode", 4) != 4 or "indices" not in prim:
                continue
            pos = _accessor(doc, binary, attrs["POSITION"]).astype(float)
            idx = _accessor(doc, binary, prim["indices"]).astype(np.int64).reshape(-1, 3)
            material = doc["materials"][prim["material"]] if "material" in prim else {}
            color = np.array((material.get("pbrMetallicRoughness") or {}).get("baseColorFactor",
                                                                                 [0.8, 0.8, 0.8, 1])[:3], float)
            shade = _accessor(doc, binary, attrs["COLOR_0"])[:, :3].astype(float) if "COLOR_0" in attrs else None
            yield pos, idx, color, shade


def render(data: bytes, rot: Sequence[float], px: int, supersample: int = 2) -> Image.Image:
    """Model `rot` burchakda, kvadrat `px`×`px` rasmda (shaffof fon) — PowerPoint ramkasidagidek joylashuv."""
    lo, hi = glb_mod.bounds(data)
    cam = Camera(lo, hi)
    n = px * supersample
    turn = rotation(rot)
    tris, colors, depth = [], [], []
    for pos, idx, color, shade in _meshes(data):
        p = (pos - cam.center) / cam.unit @ turn.T
        dist = cam.distance - p[:, 2]
        xy = (np.stack([p[:, 0], -p[:, 1]], 1) / dist[:, None] / cam.tan * 0.5 + 0.5) * n
        a, b, c = p[idx[:, 0]], p[idx[:, 1]], p[idx[:, 2]]
        normal = np.cross(b - a, c - a)
        length = np.linalg.norm(normal, axis=1)
        ok = length > 1e-12
        normal[ok] /= length[ok, None]
        keep = ok & (normal[:, 2] > -0.05)               # orqasi kameraga qaragan uchburchaklar chizilmaydi
        light = 0.38 + 0.62 * np.clip(np.abs(normal @ _LIGHT), 0, 1)
        base = color[None, :] * (shade[idx].mean(1) if shade is not None else 1.0)
        rgb = np.clip(base * light[:, None] * 1.08, 0, 1)
        tri = xy[idx][keep]
        area = np.abs((tri[:, 1, 0] - tri[:, 0, 0]) * (tri[:, 2, 1] - tri[:, 0, 1])
                      - (tri[:, 2, 0] - tri[:, 0, 0]) * (tri[:, 1, 1] - tri[:, 0, 1]))
        big = area > 0.05
        tris.append(tri[big])
        colors.append(rgb[keep][big])
        depth.append(((a + b + c) / 3)[keep][big][:, 2])
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    if tris:
        tri = np.concatenate(tris)
        col = (np.concatenate(colors) * 255).astype(int)
        draw = ImageDraw.Draw(img)
        for k in np.argsort(np.concatenate(depth)):      # uzoqdan yaqinga
            t, c = tri[k], tuple(int(v) for v in col[k]) + (255,)
            draw.polygon([(t[0, 0], t[0, 1]), (t[1, 0], t[1, 1]), (t[2, 0], t[2, 1])], fill=c, outline=c)
    return img.resize((px, px), Image.LANCZOS) if supersample > 1 else img


def fallback_png(data: bytes, rot: Sequence[float], size_in: float) -> bytes:
    """Ramkaga (`size_in` dyuym) mos zaxira rasm baytlari; bir xil model va burchak qayta chizilmaydi."""
    px = int(min(MAX_PX, max(MIN_PX, size_in * DPI)))
    key = (hashlib.sha1(data).hexdigest(), tuple(round(float(a), 2) for a in rot), px)
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key]
    img = render(data, rot, px, supersample=2 if px <= 700 else 1)
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    _CACHE[key] = out.getvalue()
    while len(_CACHE) > 48:
        _CACHE.popitem(last=False)
    return _CACHE[key]


def on_slide(x: float, y: float, size: float, slide: Tuple[float, float]) -> bool:
    """Ramka slaydga tegadimi (tashqarida kutib turgan — uchib kiradigan/chiqadigan nusxaga rasm kerak emas)."""
    return x + size > 0 and y + size > 0 and x < slide[0] and y < slide[1]
