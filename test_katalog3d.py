"""Umumiy 3D katalog (katalog3d): ro'yxat butunligi, litsenziyalar, qidiruv va slaydga joylash.

- katalog.json: id lar takrorlanmaydi, faqat CC0 / CC BY 4.0, CC BY da muallif va attribution bor;
- har modelning preview rasmi bor, tanlov.jsonl bilan bir xil;
- nomlarda taqiqlangan narsa (o'yinchoq, anime, qurol...) yo'q;
- qidir(): o'zbekcha so'z bo'yicha topadi, fan filtri ishlaydi;
- joylash(): slaydda am3d model va ostida litsenziya yozuvi; model yo'q bo'lsa FileNotFoundError.

    python test_katalog3d.py
"""
import io, json, os, re, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

import numpy as np
from pptx import Presentation
from pptx.util import Inches

TMP = tempfile.mkdtemp()
os.environ["KATALOG3D_DIR"] = TMP
from services import katalog3d
from services.med3d import glb

print("1) Ro'yxat butunligi")
data = json.load(open(katalog3d.KATALOG_JSON, encoding="utf-8"))
mods = data["modellar"]
ids = [m["id"] for m in mods]
check("2000 dan ko'p model", len(mods) > 2000, len(mods))
check("soni maydoni to'g'ri", data["soni"] == len(mods))
check("id lar takrorlanmaydi", len(ids) == len(set(ids)))
check("faqat CC0 / CC BY 4.0", {m["litsenziya"] for m in mods} <= {"CC0 1.0", "CC BY 4.0"},
      {m["litsenziya"] for m in mods})
ccby = [m for m in mods if m["litsenziya"] == "CC BY 4.0"]
check("CC BY da muallif bor", all(m["muallif"] for m in ccby), [m["id"] for m in ccby if not m["muallif"]][:5])
check("CC BY attribution da muallif va litsenziya",
      all(m["muallif"] in m["attribution"] and "CC BY 4.0" in m["attribution"] for m in ccby))
check("har modelda attribution_full", all(m["attribution_full"] for m in mods))
check("fayl yo'li <fan>/<id>/model.glb", all(m["fayl"] == f"{m['fan'].replace(chr(39), '')}/{m['id']}/model.glb"
                                             for m in mods))
check("o'zbekcha nom bo'sh emas", all(m["nom_uz"].strip() for m in mods))
check("har modelning preview rasmi bor", all(katalog3d.preview_yoli(i) for i in ids),
      [i for i in ids if not katalog3d.preview_yoli(i)][:5])
tanlov = [json.loads(l) for l in open(os.path.join(HERE, "data", "katalog3d", "tanlov.jsonl"), encoding="utf-8")]
kids_data = json.load(open(os.path.join(HERE, "data", "katalog3d", "bolalar.json"), encoding="utf-8"))
kids = kids_data["modellar"]
check("tanlov.jsonl katalog (asosiy + bolalar) bilan bir xil",
      sorted(t["uid"] for t in tanlov) == sorted(ids + [m["id"] for m in kids]))
check("tanlovda manba URL yoki HF yo'li", all(t.get("url") or t.get("yol") for t in tanlov))
TAQIQ = ("toy", "doll", "anime", "cartoon", "rubik", "lowpoly", "low poly", "stylized", "weapon", "gun",
         "rifle", "sword", "fnaf", "pokemon", "minecraft", "o'yinchoq")
TAQIQ_RE = re.compile(r"(?<![a-z'])(" + "|".join(re.escape(w) for w in TAQIQ) + r")(?![a-z])")
bad = [m["nom"] for m in mods if TAQIQ_RE.search((m["nom"] + " " + m["nom_uz"]).lower())]
check("nomlarda taqiqlangan so'z yo'q", not bad, bad[:5])
check("bir nechta fan bor", len({m["fan"] for m in mods}) >= 10)
check("har modelda toifa (kategoriya) va tur", all(m.get("kategoriya") and m.get("tur") == "real" for m in mods),
      [m["id"] for m in mods if not m.get("kategoriya")][:5])
check("toifalar 30 dan ko'p, 60 dan kam", 30 <= len({m["kategoriya"] for m in mods}) <= 60,
      len({m["kategoriya"] for m in mods}))

print("1b) Bolalar katalogi")
check("bolalar: 50 dan ko'p model", len(kids) >= 50, len(kids))
check("bolalar: soni maydoni to'g'ri", kids_data["soni"] == len(kids))
check("bolalar: hammasi tur=bolalar, fan=bolalar", all(m["tur"] == "bolalar" and m["fan"] == "bolalar" for m in kids))
check("bolalar: id asosiy katalog bilan kesishmaydi", not set(ids) & {m["id"] for m in kids})
check("bolalar: faqat CC0 / CC BY 4.0", {m["litsenziya"] for m in kids} <= {"CC0 1.0", "CC BY 4.0"})
check("bolalar: CC BY da muallif bor", all(m["muallif"] and m["muallif"] in m["attribution"] for m in kids
                                           if m["litsenziya"] == "CC BY 4.0"))
check("bolalar: preview va niqob bor", all(katalog3d.preview_yoli(m["id"]) and katalog3d.maska_yoli(m["id"]) for m in kids),
      [m["id"] for m in kids if not katalog3d.preview_yoli(m["id"])][:5])
check("bolalar: fayl yo'li bolalar/<id>/model.glb", all(m["fayl"] == f"bolalar/{m['id']}/model.glb" for m in kids))
check("bolalar: toifalari", {m["kategoriya"] for m in kids} == {"o'yinchoqlar", "o'yin maydonchasi",
      "chaqaloq buyumlari", "maktab va sinf", "bolalar xonasi", "hayvonchalar"}, {m["kategoriya"] for m in kids})

print("2) Qidiruv")
r = katalog3d.qidir("bosh suyagi")
check("'bosh suyagi' topiladi", r and all("bosh suyag" in m["nom_uz"].lower() for m in r[:5]), [m["nom_uz"] for m in r[:5]])
r = katalog3d.qidir("sher", fan="san'at")
check("fan filtri", r and all(m["fan"] == "san'at" for m in r))
check("bo'sh so'rov — bo'sh ro'yxat", katalog3d.qidir("  ") == [])
check("bolalar modeli oddiy qidiruvda chiqmaydi", all(m.get("tur") != "bolalar" for m in katalog3d.qidir("rezina o'rdakcha", limit=50)))
r = katalog3d.qidir("rezina o'rdakcha", bolalar=True)
check("bolalar=True bo'lsa topiladi", r and all(m["tur"] == "bolalar" for m in r[:2]), [m["nom_uz"] for m in r[:3]])
check("jiddiy qidiruvda bolalar modeli yo'q", all(m.get("tur") != "bolalar" for m in katalog3d.qidir("maktab", limit=50)))
check("apostrofsiz ham topadi", katalog3d.qidir("qal'a") and katalog3d.qidir("qala"))

print("3) Slaydga joylash")
mid = next(m["id"] for m in ccby)
m = katalog3d.katalog()[mid]
check("yuklanmagan model — None", katalog3d.model_yoli(mid) is None)
prs = Presentation(); prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
slide = prs.slides.add_slide(prs.slide_layouts[6])
try:
    katalog3d.joylash(slide, mid, 1, 1, 4)
    check("yuklanmagan model — FileNotFoundError", False)
except FileNotFoundError:
    check("yuklanmagan model — FileNotFoundError", True)
pos = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float32)
nrm = np.array([[0, 0, 1]] * 3, dtype=np.float32)
path = os.path.join(TMP, m["fayl"]); os.makedirs(os.path.dirname(path))
open(path, "wb").write(glb.write_glb([glb.Primitive(pos, nrm, np.array([0, 1, 2]), (0.8, 0.8, 0.8, 1))]))
katalog3d.joylash(slide, mid, 1, 1, 4)
buf = io.BytesIO(); prs.save(buf)
xml = slide.shapes._spTree.xml
check("am3d:model3d bor", "model3d" in xml)
check("ostida attribution yozuvi", any(s.has_text_frame and s.text_frame.text == m["attribution"] for s in slide.shapes))
check("GLB taqdimotga qo'shilgan", any(p.partname.endswith(".glb") for p in prs.part.package.iter_parts()))

print()
print("4) Qidiruv tizimi: bolalar filtri va toifa")
try:
    from services.kat3d import qidiruv
except Exception as exc:                                   # noqa: BLE001  (AI kutubxonalari yo'q muhit)
    print("  o'tkazildi — qidiruv moduli import qilinmadi:", str(exc)[:80])
else:
    allv = frozenset(katalog3d.katalog())
    kid_ids = {m["id"] for m in kids}
    plain = qidiruv.score("maktab", ["school", "desk", "backpack", "teddy", "toy"], available=allv, limit=80)
    check("oddiy mavzuda bolalar modeli ball olmaydi", not ({i for _, i in plain} & kid_ids))
    kidr = qidiruv.score("bolalar tarbiyasi", ["school", "desk", "backpack", "teddy", "toy"], available=allv, limit=80,
                         kids=True)
    check("bolalar mavzusida bolalar modellari chiqadi", {i for _, i in kidr} & kid_ids)
    cats = qidiruv.categories()
    check("toifalar ro'yxatida bolalar toifalari bor", "o'yinchoqlar" in cats and "maktab va sinf" in cats, cats)
    boosted = dict((i, b) for b, i in qidiruv.score("x", ["skull"], available=allv, kategoriya=["Skeletlar va bosh suyaklari"],
                                                     limit=500))
    base = dict((i, b) for b, i in qidiruv.score("x", ["skull"], available=allv, limit=500))
    check("mos toifa qo'shimcha ball beradi", all(boosted[i] > base[i] for i in boosted
                                                   if katalog3d.katalog()[i]["kategoriya"] == "Skeletlar va bosh suyaklari"))
    check("kids_topic: bolalar", all(qidiruv.kids_topic(t) for t in ("Bola tarbiyasida atrof muhit", "Kids toys",
                                                                     "Детский сад", "Bog'cha o'yinlari")))
    check("kids_topic: jiddiy mavzular emas", not any(qidiruv.kids_topic(t) for t in ("Amir Temur", "Yurak anatomiyasi",
                                                                                      "Quyosh tizimi", "Iqtisodiyot")))

print("5) O'zimizning modellar: serverda GLB yasash (RDKit va tarmoqsiz), katalog, reja tuzatishlari")
if True:
    import builtins
    import subprocess

    code = r"""
import builtins, json, os, sys
real = builtins.__import__
def imp(n, *a, **k):
    if n.startswith("rdkit"):
        raise ImportError("rdkit yo'q")
    return real(n, *a, **k)
builtins.__import__ = imp
from tools.katalog3d.ozimiz import yasash
from services import katalog3d
made = yasash.yetishmaganlar()
again = yasash.yetishmaganlar()
ours = [i for i, m in katalog3d.katalog().items() if m.get("manba") == "edufayl"]
have = katalog3d.mavjud(ttl=0)
print(json.dumps({"made": made, "again": again, "ours": len(ours), "missing": [i for i in ours if i not in have]}))
"""
    env = dict(os.environ, KATALOG3D_DIR=os.path.join(TMP, "ozimiz_glb"))
    res = subprocess.run([sys.executable, "-c", code], cwd=os.path.dirname(os.path.abspath(__file__)), env=env,
                         capture_output=True, text=True, timeout=900)
    try:
        r = json.loads(res.stdout.strip().splitlines()[-1])
    except Exception:
        r = {"made": 0, "again": -1, "ours": 0, "missing": ["?"], "err": res.stderr[-800:]}
    check("bo'sh serverda hamma o'zimizning GLB yasaldi (RDKit'siz)", r["made"] == r["ours"] >= 150 and not r["missing"], r)
    check("ikkinchi marta hech narsa qayta yasalmaydi", r["again"] == 0, r)
    ours = [m for m in katalog3d.katalog().values() if m.get("manba") == "edufayl"]
    check("har o'zimizning modelda preview va niqob bor", all(
        os.path.isfile(os.path.join(katalog3d.PREVIEW_DIR, m["id"] + ".jpg"))
        and os.path.isfile(os.path.join(katalog3d.MASK_DIR, m["id"] + ".png")) for m in ours))
    check("begona teksturali modellarda CC BY muallifi yozilgan",
          all("Solar System Scope" in m["attribution"] for m in ours if m["id"].startswith("ast_") and m["id"] != "ast_yer"))

    from services.kat3d import reja
    S = "Bu jumla yetarlicha uzun bo'lgan sinov gapidir."
    ids = [m["id"] for m in ours[:4]]
    codes = {f"m{i}": m for i, m in enumerate(ids)}
    item = lambda c, n: {"model": c, "name": n, "text": f"{n} haqida {S}"}
    raw = {"slides": [{"layout": "muqova", "title": "T", "models": ["m0"]},
                      {"layout": "uchlik", "title": "U1", "items": [item("m0", "Alfa"), item("m1", "Beta"), item("m2", "Gamma")]},
                      {"layout": "uchlik", "title": "U2", "items": [item("m1", "Delta"), item("m2", "Epsilon"), item("m3", "Zeta")]},
                      {"layout": "matn", "title": "Modelsiz", "paragraphs": [S]},
                      {"layout": "yakun", "title": "Y", "points": [S]}]}
    p = reja.normalize(raw, 5, ids, codes)
    u2 = p["slides"][2]
    alltext = " ".join(u2["points"] + u2["paragraphs"] + [u2["subtitle"]])
    check("ketma-ket uchlik matnga o'tganda nomlar va matnlar yo'qolmadi",
          u2["layout"] != "uchlik" and all(w in alltext for w in ("Delta", "Epsilon", "Zeta")), u2)
    check("uchlikdan o'tgan slaydda bitta model qoladi", len(u2["models"]) <= 1 and not u2["items"], u2)
    check("AI model qo'ymagan slaydga tasodifiy model qo'yilmadi", not p["slides"][3]["models"], p["slides"][3])

    # mijoz modellarni o'zi tanlagan («chosen»): reja AI'ga model nima ekanini aniq aytadi, uchlik begona model bilan to'lmaydi
    from services.kat3d import ai as kai
    seen = {}
    def fake_call(system, user, *a, **k):
        seen["system"], seen["user"] = system, user
        return raw
    old_call = kai.call_json
    kai.call_json = fake_call
    try:
        reja.plan("Hujayra", 5, ids, "uz", chosen=True, review_ok=False)
    finally:
        kai.call_json = old_call
    check("chosen: AI ga «modellar atrofida, har varaq o'z modeli haqida» qoidasi", "HAND-PICKED" in seen.get("system", "")
          and "MIXED DECK" not in seen.get("system", ""))
    check("chosen: model qatorida bo'lim va kalit so'zlar", katalog3d.katalog()[ids[0]].get("kategoriya", "") in seen.get("user", ""))
    one = {"slides": [{"layout": "muqova", "title": "T", "models": ["m0"]},
                      {"layout": "uchlik", "title": "U", "items": [item("m1", "Faqat bitta")]},
                      {"layout": "matn", "title": "M", "paragraphs": [S]},
                      {"layout": "yakun", "title": "Y", "points": [S]}]}
    st = reja.normalize(one, 4, ids, codes, strict=True)["slides"][1]
    check("chosen: uchlikka AI yozmagan model qo'shilmadi (matnli slaydga o'tdi)", st["layout"] != "uchlik"
          and "Faqat bitta" in " ".join(st["points"] + st["paragraphs"] + [st["subtitle"]]), st)

print("HAMMASI OK" if not FAILS else f"{len(FAILS)} ta XATO: {FAILS}")
sys.exit(1 if FAILS else 0)
