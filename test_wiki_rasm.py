"""Haqiqiy foto: Vikipediya/Commons (litsenziya filtri, muallif yozuvi, AI zaxira).

    python test_wiki_rasm.py
"""
import asyncio, io, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

from PIL import Image
from services.premium_presentation import html_images, wiki_photos as wp, deck_style

def png(width=1400, height=900):
    buf = io.BytesIO(); Image.new("RGB", (width, height), (120, 160, 90)).save(buf, "PNG")
    return buf.getvalue()

def info(license_name="CC BY 4.0", artist="<a href='x'>Jasur Aliyev</a>", **extra):
    meta = {"LicenseShortName": {"value": license_name}, "Artist": {"value": artist}}
    meta.update({k: {"value": v} for k, v in extra.items()})
    return {"mime": "image/jpeg", "width": 1600, "height": 1000, "thumburl": "https://upload.example/t.jpg",
            "descriptionurl": "https://commons.example/File:X.jpg", "extmetadata": meta}

print("1) Litsenziya")
check("CC BY — mumkin, muallif yozuvi shart", (wp.judge(info()) or {}).get("credit_required") is True)
check("Public domain — yozuv shart emas", wp.judge(info("Public domain")) == {"license": "Public domain", "author": "Jasur Aliyev", "credit_required": False})
check("CC0 — mumkin", wp.judge(info("CC0 1.0")) and not wp.judge(info("CC0 1.0"))["credit_required"])
check("CC BY-SA — o'tkazib yuboriladi", wp.judge(info("CC BY-SA 4.0")) is None)
check("CC BY-NC — o'tkazib yuboriladi", wp.judge(info("CC BY-NC 2.0")) is None)
check("CC BY-ND — o'tkazib yuboriladi", wp.judge(info("CC BY-ND 3.0")) is None)
check("fair use / NonFree — o'tkazib yuboriladi", wp.judge(info("Fair use")) is None and wp.judge(info("CC BY 4.0", NonFree="true")) is None)
check("shaxs huquqi/tovar belgisi cheklovi — o'tkazib yuboriladi", wp.judge(info("CC BY 4.0", Restrictions="personality")) is None)
check("litsenziya yozilmagan — o'tkazib yuboriladi", wp.judge({"extmetadata": {}}) is None)
check("muallif yozuvi: teglar yo'q", wp.credit_line("CC BY 4.0", "Jasur Aliyev") == "Foto: Jasur Aliyev, CC BY 4.0, Wikimedia Commons")
check("uzun muallif nomi qisqartiriladi", len(wp.credit_line("CC BY 4.0", "A" * 200)) < 100)

print("\n2) Qidiruv (soxta tarmoq)")
calls = []
def fake_net(article, files, search, image=None):
    async def get_json(url, params):
        calls.append((url, params.get("titles") or params.get("gsrsearch")))
        if url == wp.WIKIPEDIA_API:
            if isinstance(article, Exception): raise article
            return article
        if params.get("titles"):
            return files
        return search
    async def get_bytes(url):
        return image or png()
    wp._get_json, wp._get_bytes = get_json, get_bytes

article_ok = {"query": {"pages": [{"title": "Registan", "pageimage": "Registan.jpg"}]}}
files_ok = {"query": {"pages": [{"title": "File:Registan.jpg", "imageinfo": [info("CC BY 4.0")]}]}}
empty = {"query": {"pages": []}}

wp._CACHE.clear(); fake_net(article_ok, files_ok, empty)
photo = asyncio.run(wp.find("Registan"))
check("maqolaning bosh rasmi olindi", photo and photo.uri.startswith("data:image/jpeg;base64,") and "CC BY 4.0" in photo.credit, photo)
check("muallif yozuvi Commons ko'rsatilgan", photo.credit == "Foto: Jasur Aliyev, CC BY 4.0, Wikimedia Commons", photo.credit)
before = len(calls); asyncio.run(wp.find("registan"))
check("ikkinchi so'rov keshdan (tarmoq yo'q)", len(calls) == before)

wp._CACHE.clear(); fake_net(article_ok, {"query": {"pages": [{"title": "File:R.jpg", "imageinfo": [info("CC BY-SA 4.0")]}]}},
                            {"query": {"pages": [{"index": 1, "title": "File:Other.jpg", "imageinfo": [info("Public domain")]}]}})
photo = asyncio.run(wp.find("Registan"))
check("bosh rasm litsenziyasi mos emas → Commons qidiruvi", photo and photo.title == "File:Other.jpg" and photo.credit == "", photo)

wp._CACHE.clear(); fake_net(empty, files_ok, {"query": {"pages": [{"title": "File:Small.jpg", "imageinfo": [dict(info(), width=400, height=300)]}]}})
check("kichik rasm olinmaydi", asyncio.run(wp.find("Something")) is None)

wp._CACHE.clear(); fake_net(RuntimeError("tarmoq yo'q"), files_ok, empty)
async def broken(url, params): raise RuntimeError("tarmoq yo'q")
wp._get_json = broken
check("tarmoq xatosi — None (xato ko'tarilmaydi)", asyncio.run(wp.find("Registan")) is None)
check("tarmoq xatosi keshga tushmaydi (keyingi safar qayta uriniladi)", "registan" not in wp._CACHE)
check("bo'sh so'rov — None", asyncio.run(wp.find("  ")) is None)
os.environ["WIKI_PHOTOS"] = "0"
check("WIKI_PHOTOS=0 — o'chiq", asyncio.run(wp.find("Registan")) is None and not wp.enabled())
os.environ.pop("WIKI_PHOTOS")
check("User-Agent aniq (Wikimedia talabi)", "EdufaylBot" in wp.user_agent() and "(" in wp.user_agent())

print("\n3) Slaydga qo'yish")
def page(prompt, wiki=""):
    attr = f' data-wiki="{wiki}"' if wiki else ""
    return ('<section class="slide"><div class="head"><h2 class="title">A</h2></div><div class="body">'
            f'<div class="split"><div class="list"><p>x</p></div><div class="rasm" data-prompt="{prompt}"{attr}>'
            '<p class="rasm-matn">zaxira matn</p></div></div></div></section>')

class Fake:
    def __init__(self, uri="data:image/jpeg;base64,WIKI", credit="Foto: A, CC BY 4.0, Wikimedia Commons"):
        self.uri, self.credit = uri, credit
async def wiki_found(query): return Fake()
async def wiki_pd(query): return Fake(credit="")
async def wiki_none(query): return None
generated = []
async def generate(prompt):
    generated.append(prompt)
    path = os.path.join("temp", "wiki_test.png"); os.makedirs("temp", exist_ok=True)
    Image.new("RGB", (800, 600), (10, 20, 30)).save(path)
    return path

pages = [page("an ancient madrasa in samarkand with blue domes", "Registan"), page("students in a library")]
out, placed = asyncio.run(html_images.fill_photos(pages, generate=generate, wiki=wiki_found))
check("data-wiki bor blokka haqiqiy foto, boshqasiga AI", placed == 2 and "WIKI" in out[0] and "WIKI" not in out[1] and len(generated) == 1, (placed, generated))
check("CC BY muallif yozuvi slaydga qo'shildi", out[0].count("photo-credit") == 1 and "Foto: A, CC BY 4.0" in out[0] and "photo-credit" not in out[1])
check("yozuv slayd ichida (</section> dan oldin)", out[0].rstrip().endswith("</p></div></section>"), out[0][-120:])

generated.clear()
out, placed = asyncio.run(html_images.fill_photos([page("p one two three", "Registan")], generate=generate, wiki=wiki_pd))
check("Public domain: yozuv qo'shilmaydi", placed == 1 and "photo-credit" not in out[0])

out, placed = asyncio.run(html_images.fill_photos([page("a wide shot of the old city", "Registan")], generate=generate, wiki=wiki_none))
check("Wikimedia topmasa — AI rasmga o'tadi", placed == 1 and "WIKI" not in out[0] and len(generated) == 1)

async def wiki_boom(query): raise RuntimeError("x")
out, placed = asyncio.run(html_images.fill_photos([page("a wide shot of the old city", "Registan")], generate=generate, wiki=wiki_boom))
check("Wikimedia xato bersa ham AI rasm qo'yiladi", placed == 1)

os.environ["PREMIUM_PHOTOS"] = "0"
out, placed = asyncio.run(html_images.fill_photos([page("a wide shot of the old city", "Registan")], wiki=wiki_found))
check("AI o'chiq bo'lsa ham Wikimedia rasmi qo'yiladi", placed == 1 and "WIKI" in out[0])
out, placed = asyncio.run(html_images.fill_photos([page("a wide shot of the old city")], wiki=wiki_found))
check("data-wiki yo'q va AI o'chiq — blok tegilmaydi", placed == 0 and out[0] == page("a wide shot of the old city"))
os.environ.pop("PREMIUM_PHOTOS")

check("model ko'rsatmasida data-wiki tushuntirilgan (ijobiy)", "data-wiki" in deck_style.BLOCKS and "INGLIZCHA maqola nomi" in deck_style.BLOCKS)
check("photo_blocks eski shaklda qaytadi", html_images.photo_blocks(page("x y z w", "R"))[0][2] == "x y z w")

print("\n" + ("✅ hammasi o'tdi" if not FAILS else f"❌ {len(FAILS)} ta xato: {FAILS}"))
sys.exit(1 if FAILS else 0)
