"""Haqiqiy 3D model (GLB) PowerPoint slaydida: o'lcham/kamera formulalari, XML tartibi, fayl tuzilishi.

Formulalar PowerPoint saqlagan namunadan (Open XML SDK test fayli `3dtestdot.pptx`) tekshiriladi: o'sha
modelning chegaralaridan biz hisoblagan `meterPerModelUnit`, `preTrans` va kamera masofasi PowerPoint
yozgan qiymatlarga mos kelishi kerak.

    python test_pro3d_model.py
"""
import io, json, os, struct, sys, tempfile, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

import numpy as np
from lxml import etree
from PIL import Image
from pptx import Presentation
from pptx.util import Inches

from services.pro3d import build, content, model3d
from services.pro3d.images import Picture

print("1) PowerPoint namunasidagi qiymatlar")
# 3dtestdot.pptx: tugun masshtabi 0.01, mesh chegaralari quyidagicha; PowerPoint yozgan qiymatlar:
# meterPerModelUnit 61067647/1e6, preTrans (0, -2, 1153533), camera z 80938013.
ref = {"scene": 0, "scenes": [{"nodes": [0]}],
       "nodes": [{"children": [1], "scale": [0.01, 0.01, 0.01]}, {"mesh": 0}],
       "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
       "accessors": [{"min": [-0.8106792, -0.81876409, -0.86327815], "max": [0.8106792, 0.81876421, 0.75833672]}]}
f = model3d.fit(ref)
check("meterPerModelUnit = 1 / eng katta o'lcham", abs(f.meter_per_unit - 61.067647) / 61.067647 < 1e-4, f.meter_per_unit)
check("preTrans = −markaz (EMU)", abs(f.pre_trans[2] - 1153533) < 300 and abs(f.pre_trans[1]) < 5, f.pre_trans)
check("kamera: sfera 45° ga sig'adi", abs(f.camera_z - 80938013) / 80938013 < 1e-3, f.camera_z)

print("\n2) GLB va teksturalar")
def tiny_glb(texture_side=0):
    """Kub (8 uch) va ixtiyoriy PNG tekstura."""
    pos = np.array([[x, y, z] for x in (0, 2) for y in (0, 1) for z in (0, 1)], dtype=np.float32)
    binary = pos.tobytes()
    doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
           "nodes": [{"mesh": 0, "translation": [5, 0, 0]}],
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "mode": 0}]}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": 8, "type": "VEC3",
                          "min": [0, 0, 0], "max": [2, 1, 1]}],
           "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(binary)}],
           "buffers": [{"byteLength": len(binary)}]}
    if texture_side:
        png = io.BytesIO()
        Image.fromarray((np.random.RandomState(1).rand(texture_side, texture_side, 3) * 255).astype(np.uint8)).save(png, "PNG")
        doc["bufferViews"].append({"buffer": 0, "byteOffset": len(binary), "byteLength": len(png.getvalue())})
        doc["images"] = [{"bufferView": 1, "mimeType": "image/png"}]
        binary += png.getvalue()
        doc["buffers"][0]["byteLength"] = len(binary)
    return model3d.write_glb(doc, binary)

glb = tiny_glb(2048)
small = model3d.compress_textures(glb, 512)
doc, binary = model3d.read_glb(small)
bv = doc["bufferViews"][1]
tex = Image.open(io.BytesIO(binary[bv["byteOffset"]:bv["byteOffset"] + bv["byteLength"]]))
check("tekstura kichraydi va JPEG bo'ldi", tex.size == (512, 512) and doc["images"][0]["mimeType"] == "image/jpeg"
      and len(small) < len(glb) / 3, (tex.size, len(glb), len(small)))
pos = np.frombuffer(binary[:96], dtype=np.float32).reshape(8, 3)
check("geometriya o'zgarmadi", pos.max() == 2 and doc["accessors"][0]["max"] == [2, 1, 1])
fitted = model3d.fit(doc)
check("tugun siljishi hisobga olinadi (markaz x = 6)", abs(fitted.pre_trans[0] + 6 * 0.5 * 36e6) < 2, fitted.pre_trans)

print("\n3) Slayd: am3d XML, fayl tuzilishi, Morph")
tmp = tempfile.mkdtemp()
glb_path = os.path.join(tmp, "kub.glb")
open(glb_path, "wb").write(tiny_glb())
model = model3d.load("kub", glb_path, "Kub")
pics = {}
views = {}
for rot in ((0, 0, 0), (10, 90, 0)):
    square = os.path.join(tmp, f"kub_{rot[1]}.png")
    im = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    im.paste((200, 50, 50, 255), (100, 150, 300, 250))
    im.save(square)
    model.renders[rot] = square
    crop = im.crop((100, 150, 300, 250)); cp = square.replace(".png", "_c.png"); crop.save(cp)
    views[rot] = Picture(cp, 200, 100, True, np.asarray(crop.split()[-1]), model=model, rot=rot,
                         crop=(0.25, 0.375, 0.75, 0.625))
first = views[(0, 0, 0)]; first.views = views
deck = content.normalize({"palette": "indigo", "slides": [
    {"layout": "cover", "title": "Kub", "subtitle": "Sinov", "object": {"id": "kub", "prompt": "kub"}},
    {"layout": "points", "title": "Punktlar", "object": {"id": "kub"}, "points": [{"head": "A", "text": "B"}]},
    {"layout": "conclusion", "title": "Xulosa", "points": ["Bir"]}]}, "Kub", 3)
for s, rot in zip(deck["slides"], ((0, 0, 0), (10, 90, 0), (0, 0, 0))):
    s["rot"] = rot
path = build.build(deck, {"kub": first}, {}, out_path=os.path.join(tmp, "kub.pptx"))
with zipfile.ZipFile(path) as z:
    names = z.namelist()
    types = z.read("[Content_Types].xml").decode()
    rels = [z.read(f"ppt/slides/_rels/slide{i}.xml.rels").decode() for i in (1, 2, 3)]
    slides = [z.read(f"ppt/slides/slide{i}.xml") for i in (1, 2, 3)]
check("bitta GLB fayl, uch slayd unga havola qiladi",
      [n for n in names if n.endswith(".glb")] == ["ppt/media/model3d1.glb"]
      and all("relationships/model3d\" Target=\"../media/model3d1.glb\"" in r for r in rels), names)
check("GLB turi PowerPoint yozganidek: model/gltf.binary", 'ContentType="model/gltf.binary"' in types)
NS = {"mc": "http://schemas.openxmlformats.org/markup-compatibility/2006", "am3d": model3d.AM3D_NS,
      "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
      "a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
root = etree.fromstring(slides[1])
m3d = root.find(".//am3d:model3d", NS)
order = [etree.QName(c).localname for c in m3d]
check("am3d:model3d bolalari sxema tartibida",
      order == ["spPr", "camera", "trans", "raster", "objViewport", "ambientLight", "ptLight", "ptLight", "ptLight"], order)
trans = [etree.QName(c).localname for c in m3d.find("am3d:trans", NS)]
check("am3d:trans tartibi", trans == ["meterPerModelUnit", "preTrans", "scale", "rot", "postTrans"], trans)
rot = m3d.find("am3d:trans/am3d:rot", NS)
check("burilish gradusning 1/60000 ulushida (10°, 90°)", (rot.get("ax"), rot.get("ay")) == ("600000", "5400000"),
      dict(rot.attrib))
frame = root.find(".//mc:Choice/p:graphicFrame", NS)
check("Morph nomi !!obj_kub", frame.find("p:nvGraphicFramePr/p:cNvPr", NS).get("name") == "!!obj_kub")
fallback = root.find(".//mc:Fallback/p:pic", NS)
check("zaxira rasm bir xil joyda", fallback is not None and fallback.find("p:spPr/a:xfrm/a:off", NS).attrib
      == frame.find("p:xfrm/a:off", NS).attrib)
ids = [int(v) for v in root.xpath("//p:cNvPr/@id", namespaces=NS)]
check("shakl raqamlari takrorlanmaydi (zaxira — modelning o'zi)", len(ids) - 1 == len(set(ids)), ids)
ext = frame.find("p:xfrm/a:ext", NS)
off = frame.find("p:xfrm/a:off", NS)
size = int(ext.get("cx"))
# Obyekt (crop 0.25..0.75) "points" joylashuvidagi qutiga tushadi: chap tomonda, 0.25..5.2 dyuym oralig'ida.
left = int(off.get("x")) + 0.25 * size
check("obyektning o'zi qutiga tushadi (ramka kvadrat, markaz saqlanadi)",
      Inches(0.2) <= left <= Inches(0.3) and ext.get("cx") == ext.get("cy"), (left / 914400, size / 914400))
check("fayl python-pptx bilan qayta ochiladi", len(Presentation(path).slides) == 3)

print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
