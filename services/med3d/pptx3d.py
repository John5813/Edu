"""PowerPoint slaydiga haqiqiy 3D model (`.glb`) qo'yish — python-pptx buni bilmaydi, XML qo'lda yoziladi.

Tuzilish PowerPoint o'zi yozadigan bilan bir xil (MS-ODRAWXML 2.31, OfficeCLI dagi tekshirilgan namuna):
`mc:AlternateContent` → `p:graphicFrame` → `am3d:model3d` (kamera, aylanish, yorug'lik), GLB fayl
`ppt/media/` ga `model/gltf.binary` turi bilan. Zaxira rasm sifatida 1×1 bo'sh PNG — PowerPoint
modelni ochilganda o'zi chizadi.

Morph uchun: qo'shni slaydlarda model nomi bir xil (`!!` bilan boshlanadi) bo'lishi va har slaydga
GLB alohida qo'yilishi kerak (slaydni nusxalash modelni buzadi).
"""
import hashlib
import io
import math
from typing import Dict, Optional, Sequence

import numpy as np
from lxml import etree
from PIL import Image
from pptx.opc.package import Part
from pptx.oxml.ns import qn
from pptx.util import Inches

from . import glb

AM3D_NS = "http://schemas.microsoft.com/office/drawing/2017/model3d"
RT_MODEL3D = "http://schemas.microsoft.com/office/2017/06/relationships/model3d"
CT_GLB = "model/gltf.binary"
_FOV60K = 2700000
# Yorug'lik: PowerPoint'ning odatiy uch nuqtali sxemasi, lekin atrof yorug'ligi pastroq va asosiy (iliq,
# o'ng-tepa-old) chiroq kuchliroq — shakl soyalari aniqroq, ranglar to'qroq ko'rinadi.
AMBIENT = "300000"
_LIGHTS = (("100000", "88000", "72000", "15000000", "21959998", "70920001", "16344003"),
           ("40000", "60000", "95000", "7000000", "-37964106", "51130435", "57631972"),
           ("86837", "72700", "100000", "3125000", "-37739122", "58056624", "-34769649"))
# Uslubga mos yorug'lik to'plamlari: (atrof yorug'ligi, [(r, g, b, kuch, x, y, z), ...]).
# Koordinatalar PowerPoint'niki (36 000 000 — bir birlik): z musbat — kamera tomonda, manfiy — model ortida (kontur).
LIGHT_SETS = {
    "studio": (AMBIENT, _LIGHTS),
    "soft": ("460000", (("100000", "96000", "90000", "10500000", "21959998", "70920001", "36344003"),
                        ("80000", "88000", "100000", "7500000", "-37964106", "41130435", "57631972"),
                        ("100000", "100000", "100000", "4000000", "-7739122", "58056624", "-44769649"))),
    "rim": ("240000", (("100000", "86000", "66000", "13500000", "21959998", "60920001", "26344003"),
                       ("100000", "62000", "30000", "11000000", "-30000000", "40000000", "-60000000"),
                       ("60000", "75000", "100000", "3000000", "-37964106", "21130435", "57631972"))),
    "spot": ("170000", (("100000", "95000", "84000", "19000000", "4000000", "90000000", "30000000"),
                        ("70000", "70000", "80000", "2200000", "-37964106", "21130435", "57631972"),
                        ("100000", "92000", "70000", "3500000", "0", "40000000", "-60000000"))),
    "cool": ("260000", (("82000", "95000", "100000", "12000000", "21959998", "70920001", "36344003"),
                        ("20000", "90000", "100000", "12000000", "-26000000", "30000000", "-60000000"),
                        ("40000", "70000", "100000", "4000000", "-37964106", "51130435", "57631972"))),
    "warm": ("330000", (("100000", "84000", "62000", "14000000", "21959998", "70920001", "26344003"),
                        ("100000", "78000", "60000", "6000000", "-37964106", "51130435", "57631972"),
                        ("90000", "80000", "100000", "3000000", "-37739122", "58056624", "-34769649"))),
}


def _placeholder_png() -> bytes:
    out = io.BytesIO()
    Image.new("RGBA", (1, 1), (0, 0, 0, 0)).save(out, format="PNG")
    return out.getvalue()


_PNG = _placeholder_png()


def _next_id(spTree) -> int:
    ids = [int(v) for v in spTree.xpath("//@id") if str(v).isdigit()]
    return max(ids + [1]) + 1


def _model_xml(sid: int, name: str, x: int, y: int, cx: int, cy: int, rid_model: str, rid_png: str,
               lo: np.ndarray, hi: np.ndarray, rot: Sequence[float], lights: str = "studio") -> str:
    half = (hi - lo) / 2
    center = (hi + lo) / 2
    max_ext = float((hi - lo).max()) or 1.0
    mpu = 1.0 / max_ext
    radius = float(np.linalg.norm(half)) / (2 * float(half.max()) or 1.0)
    cam_z = int(radius / math.sin(math.radians(_FOV60K / 60000 / 2)) * 36000000)
    pre = [int(-c * mpu * 36000000) for c in center]
    ax, ay, az = (int(round(a * 60000)) for a in rot)
    ambient, preset = LIGHT_SETS.get(lights, LIGHT_SETS["studio"])
    lights = "".join(
        f'<am3d:ptLight rad="0"><am3d:clr><a:scrgbClr r="{r}" g="{g}" b="{b}"/></am3d:clr>'
        f'<am3d:intensity n="{i}" d="1000000"/><am3d:pos x="{px}" y="{py}" z="{pz}"/></am3d:ptLight>'
        for r, g, b, i, px, py, pz in preset)
    esc = name.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")
    return (
        '<mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006">'
        f'<mc:Choice xmlns:am3d="{AM3D_NS}" Requires="am3d">'
        '<p:graphicFrame xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<p:nvGraphicFramePr><p:cNvPr id="{sid}" name="{esc}"/>'
        '<p:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></p:cNvGraphicFramePr><p:nvPr/>'
        '</p:nvGraphicFramePr>'
        f'<p:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></p:xfrm>'
        f'<a:graphic><a:graphicData uri="{AM3D_NS}">'
        f'<am3d:model3d r:embed="{rid_model}">'
        f'<am3d:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></am3d:spPr>'
        f'<am3d:camera><am3d:pos x="0" y="0" z="{cam_z}"/><am3d:up dx="0" dy="36000000" dz="0"/>'
        f'<am3d:lookAt x="0" y="0" z="0"/><am3d:perspective fov="{_FOV60K}"/></am3d:camera>'
        f'<am3d:trans><am3d:meterPerModelUnit n="{int(mpu * 1000000)}" d="1000000"/>'
        f'<am3d:preTrans dx="{pre[0]}" dy="{pre[1]}" dz="{pre[2]}"/>'
        '<am3d:scale><am3d:sx n="1000000" d="1000000"/><am3d:sy n="1000000" d="1000000"/>'
        '<am3d:sz n="1000000" d="1000000"/></am3d:scale>'
        f'<am3d:rot ax="{ax}" ay="{ay}" az="{az}"/><am3d:postTrans dx="0" dy="0" dz="0"/></am3d:trans>'
        f'<am3d:raster rName="Office3DRenderer" rVer="16.0.8326"><am3d:blip r:embed="{rid_png}"/></am3d:raster>'
        f'<am3d:objViewport viewportSz="{max(cx, cy)}"/>'
        '<am3d:ambientLight><am3d:clr><a:scrgbClr r="50000" g="50000" b="50000"/></am3d:clr>'
        f'<am3d:illuminance n="{ambient}" d="1000000"/></am3d:ambientLight>'
        f'{lights}</am3d:model3d></a:graphicData></a:graphic></p:graphicFrame></mc:Choice>'
        '<mc:Fallback><p:pic xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<p:nvPicPr><p:cNvPr id="{sid}" name="{esc}"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr>'
        f'<p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="{rid_png}"/><a:stretch><a:fillRect/></a:stretch>'
        f'</p:blipFill><p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic></mc:Fallback></mc:AlternateContent>')


def add_model3d(slide, data: bytes, name: str, x: float, y: float, size: float,
                rot: Sequence[float] = (0, 0, 0), parts: Optional[Dict[str, Part]] = None, lights: str = "studio"):
    """Slaydga 3D model qo'yadi. x, y, size — dyuymda (kvadrat ramka); rot — gradus (X, Y, Z).

    parts — taqdimot bo'yicha umumiy lug'at: bir xil GLB bir necha slaydda bo'lsa, faylga BIR marta yoziladi
    (rasmlar kabi). Aks holda 10 slaydli taqdimot o'nlab MB bo'lib ketadi.
    """
    lo, hi = glb.bounds(data)
    package = slide.part.package
    key = hashlib.sha1(data).hexdigest()
    part = parts.get(key) if parts is not None else None
    if part is None:
        part = Part(package.next_partname("/ppt/media/model3d%d.glb"), CT_GLB, package, data)
        if parts is not None:
            parts[key] = part
    rid_model = slide.part.relate_to(part, RT_MODEL3D)
    _, rid_png = slide.part.get_or_add_image_part(io.BytesIO(_PNG))
    tree = slide.shapes._spTree
    side = int(Inches(size))
    node = etree.fromstring(_model_xml(_next_id(tree), name, int(Inches(x)), int(Inches(y)), side, side,
                                       rid_model, rid_png, lo, hi, rot, lights))
    # Eng orqa qatlamga (fondan keyin): katta shaffof ramka matnni bosishga xalaqit bermasin.
    after = tree.find(qn("p:grpSpPr"))
    models = [el for el in tree if etree.QName(el).localname == "AlternateContent"]
    (models[-1] if models else after).addnext(node)
    return node
