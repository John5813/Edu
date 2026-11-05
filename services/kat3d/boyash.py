"""Rangsiz 3D modellarni boyash: teksturasiz oq (yoki kulrang) model slaydda «gips»dek ko'rinadi — uni mavzuga mos
rangga bo'yaymiz (teri, suyak, miya, a'zo, qum rangi...). Rangli modellarga tegilmaydi.

Rangsiz deb: hamma materialning asosiy rangi oq/kulrang (to'yinganligi past), rangli tekstura va nuqta ranglari
yo'q. Boyash faqat GLB ichidagi material rangini almashtiradi (`baseColorFactor`); tekstura bor bo'lsa uning
soya-yorug'ligi saqlanadi (rang unga ko'paytiriladi).
"""
import io
import json
import logging
import re
import struct
from typing import Dict, List, Optional, Sequence, Tuple

from services.med3d.glb import read_glb

log = logging.getLogger(__name__)

SAT_LIMIT = 0.10            # shundan past to'yinganlik — rangsiz
# (kalit so'zlar, rang): birinchi mos kelgani tanlanadi; so'zlar nom, kalit so'zlar va fan bo'yicha qidiriladi.
PALETTE: List[Tuple[Tuple[str, ...], str]] = [
    (("brain", "miya"), "E6A9A4"),
    (("skull", "bone", "skelet", "skeleton", "suyak", "jaw", "tooth", "teeth"), "EADFC9"),
    (("muscle", "anatom", "mushak", "écorché", "ecorche"), "C0645A"),
    (("heart", "lung", "liver", "kidney", "stomach", "organ", "yurak", "o'pka", "jigar"), "BB4A4A"),
    (("head", "face", "bust", "portrait", "man", "woman", "human", "person", "torso", "body", "hand", "foot", "baby",
      "child", "bosh", "yuz", "odam", "inson"), "E3B08F"),
    (("tree", "leaf", "plant", "flower", "daraxt", "o'simlik"), "6FA35B"),
    (("gold", "oltin", "crown", "coin", "tanga"), "D8B24A"),
    (("water", "ocean", "sea", "dengiz"), "5B9BD5"),
]
DEFAULT = "D6BE9A"          # issiq qum / tosh rangi


def _saturation(rgb: Sequence[float]) -> float:
    hi, lo = max(rgb[:3]), min(rgb[:3])
    return 0.0 if hi <= 1e-6 else (hi - lo) / hi


def _texture_saturation(doc: Dict, binary: bytes, tex: Dict) -> Optional[float]:
    """Tekstura o'rtacha to'yinganligi (0..1) yoki None (o'qib bo'lmadi)."""
    try:
        from PIL import Image

        image = doc["images"][doc["textures"][tex["index"]]["source"]]
        if "bufferView" not in image:
            return None
        view = doc["bufferViews"][image["bufferView"]]
        start = view.get("byteOffset", 0)
        with Image.open(io.BytesIO(binary[start:start + view["byteLength"]])) as im:
            im.thumbnail((48, 48))
            hsv = im.convert("RGB").convert("HSV")
            sat = [p[1] for p in hsv.getdata()]
        return sum(sat) / max(len(sat), 1) / 255.0
    except Exception as exc:                  # noqa: BLE001
        log.debug("Tekstura to'yinganligi o'qilmadi: %s", exc)
        return None


def is_colourless(doc: Dict, binary: bytes) -> bool:
    for mesh in doc.get("meshes", []):
        for prim in mesh.get("primitives", []):
            if "COLOR_0" in (prim.get("attributes") or {}):
                return False
    materials = doc.get("materials") or []
    for mat in materials:
        pbr = mat.get("pbrMetallicRoughness") or {}
        spec = (mat.get("extensions") or {}).get("KHR_materials_pbrSpecularGlossiness") or {}   # eski usul
        for factor, tex in ((pbr.get("baseColorFactor"), pbr.get("baseColorTexture")),
                            (spec.get("diffuseFactor"), spec.get("diffuseTexture"))):
            if _saturation(factor or [1, 1, 1, 1]) > SAT_LIMIT:
                return False
            if tex is not None:
                sat = _texture_saturation(doc, binary, tex)
                if sat is None or sat > SAT_LIMIT:     # tekstura o'qilmasa — tegilmaydi (rangli bo'lishi mumkin)
                    return False
    return True


def colour_for(info: Dict, fallback: str = DEFAULT) -> str:
    """Model nomi, kalit so'zlari va fani bo'yicha rang (hex)."""
    text = " ".join([str(info.get("nom", "")), str(info.get("nom_uz", "")), " ".join(info.get("kalit") or []),
                     str(info.get("fan", ""))]).lower()
    tokens = re.findall(r"[\w'’ʻ‘]+", text)             # so'zlar bo'yicha: «anatomiya» ichidagi «miya» miya emas
    for words, colour in PALETTE:
        # qisqa so'z (≤3) — aynan; uzunroq — so'z boshi (bones, anatomiyasi) mos
        if any(t == w or (len(w) >= 4 and t.startswith(w)) for t in tokens for w in words):
            return colour
    return fallback


def _linear(hex_colour: str) -> List[float]:
    return [round((int(hex_colour[i:i + 2], 16) / 255.0) ** 2.2, 4) for i in (0, 2, 4)]


def _pack(doc: Dict, binary: bytes) -> bytes:
    js = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    js += b" " * (-len(js) % 4)
    out = struct.pack("<II", len(js), 0x4E4F534A) + js
    if binary:
        out += struct.pack("<II", len(binary), 0x004E4942) + binary
    return struct.pack("<III", 0x46546C67, 2, 12 + len(out)) + out


def png_is_colourless(png: bytes) -> bool:
    """Model rasmi (shaffof PNG) deyarli rangsizmi (oq/kulrang gips) — GLB tekstura formatini o'qib bo'lmaganda
    ham modelni boyash kerakligini ko'rsatadi."""
    try:
        import numpy as np
        from PIL import Image

        with Image.open(io.BytesIO(png)) as im:
            rgba = np.asarray(im.convert("RGBA")).astype(np.float32)
        solid = rgba[..., 3] > 200
        if solid.sum() < 200:
            return False
        rgb = rgba[..., :3][solid]
        hi, lo = rgb.max(axis=1), rgb.min(axis=1)
        return float(np.mean((hi - lo) / np.maximum(hi, 1.0))) < 0.08
    except Exception:                         # noqa: BLE001
        return False


def paint(raw: bytes, info: Dict, force: bool = False) -> Tuple[bytes, Optional[str]]:
    """Rangsiz modelni boyaydi: (yangi GLB baytlari, rang) yoki (asl baytlar, None) — rangli/o'qib bo'lmasa.
    `force` — rangsizligi boshqa yo'l bilan (rasmidan) aniqlangan: GLB tekshiruvi o'tkazib yuboriladi."""
    try:
        doc, binary = read_glb(raw)
        if not force and not is_colourless(doc, binary):
            return raw, None
        colour = colour_for(info)
        factor = [*_linear(colour), 1.0]
        materials = doc.setdefault("materials", [])
        if not materials:
            materials.append({})
        for mat in materials:
            pbr = mat.setdefault("pbrMetallicRoughness", {})
            pbr["baseColorFactor"] = factor
            pbr["metallicFactor"] = 0.0
            pbr["roughnessFactor"] = max(float(pbr.get("roughnessFactor", 0.7)), 0.7)
            mat.pop("extensions", None)           # yaltiroq/shaffoflik kengaytmalari rangni buzmasin
        for mesh in doc.get("meshes", []):
            for prim in mesh.get("primitives", []):
                prim.setdefault("material", 0)
        return _pack(doc, binary), colour
    except Exception as exc:                      # noqa: BLE001 — boyalmasa model asl holicha qoladi
        log.warning("Rangsiz model boyalmadi: %s", exc)
        return raw, None


def tint_png(png: bytes, colour: str) -> bytes:
    """Rangsiz model rasmini (shaffof PNG, 3D ko'rinmaydigan telefon va WPS'da model o'rnida turadi) ham boyaydi:
    yorug'lik-soya saqlanadi (kontrast cho'ziladi), rang `colour` ga o'tadi, shaffoflik o'zgarmaydi."""
    import numpy as np
    from PIL import Image

    try:
        with Image.open(io.BytesIO(png)) as im:
            rgba = np.asarray(im.convert("RGBA")).astype(np.float32)
        solid = rgba[..., 3] > 16
        if solid.sum() < 50:
            return png
        lum = (rgba[..., 0] * 0.3 + rgba[..., 1] * 0.59 + rgba[..., 2] * 0.11)
        lo, hi = np.percentile(lum[solid], (2, 98))
        norm = np.clip((lum - lo) / max(hi - lo, 8.0), 0.0, 1.0)
        shade = 0.42 + 0.58 * norm                                     # soya qorayib ketmasin
        tint = np.array([int(colour[i:i + 2], 16) for i in (0, 2, 4)], np.float32)
        out = rgba.copy()
        out[..., :3] = np.clip(tint[None, None, :] * shade[..., None] * 1.05, 0, 255)
        buf = io.BytesIO()
        Image.fromarray(out.astype(np.uint8), "RGBA").save(buf, "PNG", optimize=True)
        return buf.getvalue()
    except Exception as exc:                  # noqa: BLE001 — boyalmasa asl rasm qoladi
        log.warning("Model rasmi boyalmadi: %s", exc)
        return png
