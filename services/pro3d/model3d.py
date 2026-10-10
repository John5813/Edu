"""Haqiqiy 3D model (GLB) ni PowerPoint slaydiga qo'yish — u Morph bilan o'z o'qi atrofida aylanadi.

PowerPoint 3D modelni `am3d:model3d` sifatida saqlaydi (Office 2019+). Format PowerPoint'ning o'zi
saqlagan fayldan (Open XML SDK test fayli `3dtestdot.pptx`) olingan; qiymatlar ma'nosi:

- `meterPerModelUnit` = 1 / modelning eng katta o'lchami — model 1 metr kattalikka keltiriladi;
- `preTrans` = −markaz × meterPerModelUnit × 36 000 000 (EMU; 1 m = 36e6 EMU) — model markazga suriladi;
- kamera: modelni o'rab turgan sfera (radius = yarim diagonal) 45° ko'rish burchagiga to'liq sig'adigan
  masofada: z = r / sin(22.5°); `up` = 1 m (y o'qi);
- `rot ax/ay/az` — burilish, gradusning 1/60000 ulushida (Morph shu burchaklar orasini aylantiradi);
- `objViewport viewportSz` — shu kamera ko'radigan kvadrat maydonning o'lchami (EMU). Ramka shu kvadratning
  o'zi qilinadi: proyeksiya markazi ramka markazida bo'ladi, zaxira rasm ham aynan shu kvadrat.

Morph'ni bilmaydigan va 3D modelni ko'rsatmaydigan dasturlar (WPS, LibreOffice, eski PowerPoint, telefon)
`mc:Fallback` dagi oddiy rasmni ko'rsatadi — u shu burchakdan chizilgan model rasmi.
"""
import io
import json
import math
import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

EMU_PER_METER = 36_000_000
FOV_DEG = 45.0
CONTENT_TYPE = "model/gltf.binary"          # PowerPoint o'zi shunday yozadi (nuqta bilan)
RELTYPE = "http://schemas.microsoft.com/office/2017/06/relationships/model3d"
AM3D_NS = "http://schemas.microsoft.com/office/drawing/2017/model3d"


# ───────────────────────────────────────────────────────────── GLB o'qish / yozish

def read_glb(data: bytes) -> Tuple[dict, bytes]:
    magic, version, _ = struct.unpack("<III", data[:12])
    if magic != 0x46546C67 or version != 2:
        raise ValueError("GLB 2.0 emas")
    offset, doc, binary = 12, None, b""
    while offset < len(data):
        length, kind = struct.unpack("<II", data[offset:offset + 8])
        chunk = data[offset + 8:offset + 8 + length]
        if kind == 0x4E4F534A:
            doc = json.loads(chunk)
        elif kind == 0x004E4942:
            binary = chunk
        offset += 8 + length
    if doc is None:
        raise ValueError("GLB da JSON yo'q")
    return doc, binary


def write_glb(doc: dict, binary: bytes) -> bytes:
    text = json.dumps(doc, separators=(",", ":")).encode()
    text += b" " * (-len(text) % 4)
    binary += b"\0" * (-len(binary) % 4)
    total = 12 + 8 + len(text) + (8 + len(binary) if binary else 0)
    out = struct.pack("<III", 0x46546C67, 2, total) + struct.pack("<II", len(text), 0x4E4F534A) + text
    if binary:
        out += struct.pack("<II", len(binary), 0x004E4942) + binary
    return out


def compress_textures(data: bytes, max_side: int = 1024, quality: int = 86) -> bytes:
    """Teksturalarni kichraytiradi (PNG → JPEG, shaffofligi bo'lmasa). Geometriya o'zgarmaydi."""
    from PIL import Image

    doc, binary = read_glb(data)
    images = doc.get("images") or []
    if not images:
        return data
    replace: Dict[int, Tuple[bytes, str]] = {}
    for image in images:
        view = image.get("bufferView")
        if view is None:
            continue
        bv = doc["bufferViews"][view]
        raw = binary[bv.get("byteOffset", 0):bv.get("byteOffset", 0) + bv["byteLength"]]
        try:
            picture = Image.open(io.BytesIO(raw))
            picture.load()
        except Exception:
            continue
        if max(picture.size) > max_side:
            picture.thumbnail((max_side, max_side), Image.LANCZOS)
        buffer = io.BytesIO()
        has_alpha = picture.mode in ("RGBA", "LA") and picture.getchannel("A").getextrema()[0] < 250
        if has_alpha:
            picture.save(buffer, "PNG", optimize=True)
            mime = "image/png"
        else:
            picture.convert("RGB").save(buffer, "JPEG", quality=quality, optimize=True)
            mime = "image/jpeg"
        if len(buffer.getvalue()) < len(raw):
            replace[view] = (buffer.getvalue(), mime)
            image["mimeType"] = mime
    if not replace:
        return data
    # Bufer qaytadan yig'iladi: har bufferView o'z joyiga (4 baytga tekislab).
    chunks, offset = [], 0
    for index, bv in enumerate(doc["bufferViews"]):
        if bv.get("buffer", 0) != 0:
            continue
        piece = replace[index][0] if index in replace else \
            binary[bv.get("byteOffset", 0):bv.get("byteOffset", 0) + bv["byteLength"]]
        pad = -offset % 4
        chunks.append(b"\0" * pad)
        offset += pad
        bv["byteOffset"], bv["byteLength"] = offset, len(piece)
        chunks.append(piece)
        offset += len(piece)
    new_binary = b"".join(chunks)
    doc["buffers"][0]["byteLength"] = len(new_binary)
    return write_glb(doc, new_binary)


# ───────────────────────────────────────────────────────────── o'lcham va markaz

def _node_matrix(node: dict) -> np.ndarray:
    if "matrix" in node:
        return np.array(node["matrix"], dtype=float).reshape(4, 4).T
    t = np.array(node.get("translation", [0, 0, 0]), dtype=float)
    x, y, z, w = node.get("rotation", [0, 0, 0, 1])
    s = np.array(node.get("scale", [1, 1, 1]), dtype=float)
    r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    m = np.eye(4)
    m[:3, :3] = r * s
    m[:3, 3] = t
    return m


def world_bbox(doc: dict) -> Tuple[np.ndarray, np.ndarray]:
    """Butun sahna (tugun o'zgarishlari bilan) chegaralari: (min, max)."""
    lows, highs = [], []
    nodes = doc.get("nodes") or []

    def walk(index: int, parent: np.ndarray):
        node = nodes[index]
        world = parent @ _node_matrix(node)
        if "mesh" in node:
            for prim in doc["meshes"][node["mesh"]]["primitives"]:
                acc = doc["accessors"][prim["attributes"]["POSITION"]]
                lo, hi = np.array(acc["min"], float), np.array(acc["max"], float)
                corners = np.array([[x, y, z, 1] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
                pts = (world @ corners.T).T[:, :3]
                lows.append(pts.min(0))
                highs.append(pts.max(0))
        for child in node.get("children", []):
            walk(child, world)

    scene = (doc.get("scenes") or [{"nodes": list(range(len(nodes)))}])[doc.get("scene", 0)]
    for root in scene.get("nodes", []):
        walk(root, np.eye(4))
    if not lows:
        raise ValueError("Modelda geometriya yo'q")
    return np.min(lows, 0), np.max(highs, 0)


@dataclass
class Fit:
    meter_per_unit: float
    pre_trans: Tuple[int, int, int]       # EMU
    camera_z: int                         # EMU
    radius_m: float


def fit(doc: dict) -> Fit:
    lo, hi = world_bbox(doc)
    size = hi - lo
    mpu = 1.0 / max(float(size.max()), 1e-9)
    centre = (lo + hi) / 2
    pre = tuple(int(round(-c * mpu * EMU_PER_METER)) for c in centre)
    radius = float(np.linalg.norm(size * mpu)) / 2
    camera = int(round(radius / math.sin(math.radians(FOV_DEG / 2)) * EMU_PER_METER))
    return Fit(mpu, pre, camera, radius)


# ───────────────────────────────────────────────────────────── slayd XML

_LIGHTS = (
    '<am3d:ambientLight><am3d:clr><a:scrgbClr r="50000" g="50000" b="50000"/></am3d:clr>'
    '<am3d:illuminance n="500000" d="1000000"/></am3d:ambientLight>'
    '<am3d:ptLight rad="0"><am3d:clr><a:scrgbClr r="100000" g="75000" b="50000"/></am3d:clr>'
    '<am3d:intensity n="9765625" d="1000000"/><am3d:pos x="21959998" y="70920001" z="16344003"/></am3d:ptLight>'
    '<am3d:ptLight rad="0"><am3d:clr><a:scrgbClr r="40000" g="60000" b="95000"/></am3d:clr>'
    '<am3d:intensity n="12250000" d="1000000"/><am3d:pos x="-37964106" y="51130435" z="57631972"/></am3d:ptLight>'
    '<am3d:ptLight rad="0"><am3d:clr><a:scrgbClr r="86837" g="72700" b="100000"/></am3d:clr>'
    '<am3d:intensity n="3125000" d="1000000"/><am3d:pos x="-37739122" y="58056624" z="-34769649"/></am3d:ptLight>')

_NS = ('xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
       'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
       'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"')


def frame_xml(shape_id: int, name: str, descr: str, x: int, y: int, size: int, model_rid: str, image_rid: str,
              fitted: Fit, rot_deg: Tuple[float, float, float]) -> str:
    """`mc:AlternateContent`: 3D model (am3d) va zaxira rasm. Ramka — kvadrat (proyeksiya maydoni)."""
    ax, ay, az = (int(round(v * 60000)) % 21600000 for v in rot_deg)
    px, py, pz = fitted.pre_trans
    descr = (descr or name).replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")
    name = name.replace("&", "&amp;").replace('"', "&quot;")
    return (
        f'<mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" {_NS}>'
        f'<mc:Choice xmlns:am3d="{AM3D_NS}" Requires="am3d">'
        f'<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="{shape_id}" name="{name}" descr="{descr}"/>'
        f'<p:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></p:cNvGraphicFramePr><p:nvPr/>'
        f'</p:nvGraphicFramePr><p:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{size}" cy="{size}"/></p:xfrm>'
        f'<a:graphic><a:graphicData uri="{AM3D_NS}"><am3d:model3d r:embed="{model_rid}">'
        f'<am3d:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{size}" cy="{size}"/></a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></am3d:spPr>'
        f'<am3d:camera><am3d:pos x="0" y="0" z="{fitted.camera_z}"/><am3d:up dx="0" dy="{EMU_PER_METER}" dz="0"/>'
        f'<am3d:lookAt x="0" y="0" z="0"/><am3d:perspective fov="{int(FOV_DEG * 60000)}"/></am3d:camera>'
        f'<am3d:trans><am3d:meterPerModelUnit n="{int(round(fitted.meter_per_unit * 1_000_000))}" d="1000000"/>'
        f'<am3d:preTrans dx="{px}" dy="{py}" dz="{pz}"/><am3d:scale><am3d:sx n="1000000" d="1000000"/>'
        f'<am3d:sy n="1000000" d="1000000"/><am3d:sz n="1000000" d="1000000"/></am3d:scale>'
        f'<am3d:rot ax="{ax}" ay="{ay}" az="{az}"/><am3d:postTrans dx="0" dy="0" dz="0"/></am3d:trans>'
        f'<am3d:raster rName="Office3DRenderer" rVer="16.0.8326"><am3d:blip r:embed="{image_rid}"/></am3d:raster>'
        f'<am3d:objViewport viewportSz="{size}"/>{_LIGHTS}</am3d:model3d></a:graphicData></a:graphic>'
        f'</p:graphicFrame></mc:Choice><mc:Fallback><p:pic><p:nvPicPr>'
        f'<p:cNvPr id="{shape_id}" name="{name}" descr="{descr}"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/>'
        f'</p:cNvPicPr><p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="{image_rid}"/><a:stretch><a:fillRect/>'
        f'</a:stretch></p:blipFill><p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{size}" cy="{size}"/></a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic></mc:Fallback></mc:AlternateContent>')


@dataclass
class Model:
    """Bitta 3D model: GLB (siqilgan) va har burchakdan chizilgan zaxira rasmlar."""
    key: str
    glb: bytes
    fitted: Fit
    descr: str = ""
    renders: Dict[Tuple[float, float, float], str] = field(default_factory=dict)   # burchak → kvadrat PNG
    _part: object = None


def load(key: str, path: str, descr: str = "", max_texture: int = 1024) -> Model:
    data = open(path, "rb").read()
    data = compress_textures(data, max_texture)
    doc, _ = read_glb(data)
    return Model(key, data, fit(doc), descr)


def _next_id(slide) -> int:
    ids = [int(v) for v in slide._element.xpath("//@id") if str(v).isdigit()]
    return max(ids + [1]) + 1


def add(slide, model: Model, name: str, x_in: float, y_in: float, size_in: float,
        rot: Tuple[float, float, float]) -> None:
    """Slaydga 3D model qo'yadi: (x, y) — kvadrat ramkaning chap-yuqori burchagi, dyuymda."""
    from lxml import etree
    from pptx.opc.packuri import PackURI
    from pptx.opc.package import Part
    from pptx.util import Inches

    part = slide.part
    if model._part is None:
        package = part.package
        partname = package.next_partname("/ppt/media/model3d%d.glb")
        model._part = Part(PackURI(str(partname)), CONTENT_TYPE, package, model.glb)
    model_rid = part.relate_to(model._part, RELTYPE)
    _, image_rid = part.get_or_add_image_part(model.renders[rot])
    xml = frame_xml(_next_id(slide), name, model.descr, int(Inches(x_in)), int(Inches(y_in)), int(Inches(size_in)),
                    model_rid, image_rid, model.fitted, rot)
    slide.shapes._spTree.append(etree.fromstring(xml))
