"""Brave rasm qidiruvi va «🧠 AI nazorati».

- mavzuga Brave'ga faqat BITTA so'rov: muqova, slaydlar va qayta yaratish xotiradan oladi;
- stok saytlar, do'konlar va kichik rasmlar tashlab ketiladi;
- AI tanlovi takrorsiz; bitta rasm ikki slaydga tushmaydi;
- topilmagan slaydga AI chizadi, topilganiga chizilmaydi;
- kunlik hisob: saytdan / AI dan rasmlar va modellar ulushi foizda.

    python test_brave_rasm.py
"""
import asyncio
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

import database.database as dbmod

_db_dir = tempfile.mkdtemp()
dbmod.DATABASE_FILE = os.path.join(_db_dir, "test.db")

from PIL import Image

from services import ai_usage, photo_search
from services.premium_presentation import html_images


def _image(width=900, height=600):
    handle, path = tempfile.mkstemp(suffix=".jpg")
    os.close(handle)
    Image.new("RGB", (width, height), (90, 140, 60)).save(path)
    return path


def _result(i, source="example.org", width=1200, height=800, title=None):
    return {"title": title or f"photo {i}", "source": source, "url": f"https://{source}/page{i}",
            "properties": {"url": f"https://{source}/img{i}.jpg", "width": width, "height": height}}


print("1) Natijalarni saralash")
raw = [
    _result(0),
    _result(1, source="gettyimages.com"),
    _result(2, source="www.shutterstock.com"),
    _result(3, source="amazon.com"),
    _result(4, width=400, height=300),
    _result(5, width=3000, height=500),          # juda uzun panorama
    _result(0),                                   # takror
    {"title": "svg", "source": "x.org", "properties": {"url": "https://x.org/a.svg", "width": 900, "height": 600}},
    _result(6, source="upload.wikimedia.org"),
]
kept = photo_search.usable(raw)
check("faqat yaroqlilari qoldi (oddiy sayt va Wikimedia)",
      [c["url"] for c in kept] == ["https://example.org/img0.jpg", "https://upload.wikimedia.org/img6.jpg"],
      [c["url"] for c in kept])

print("\n2) AI javobini o'qish")
picks = photo_search.parse_picks({"picks": [
    {"slot": 1, "ids": [3, 3, 7, 8, 9]},
    {"slot": 2, "ids": [7, 2, "x", 99]},
    {"slot": 9, "ids": [1]},
    "buzuq",
]}, slots=3, candidates=10)
check("har slotga eng ko'pi 3 ta, takrorsiz, chegaradan tashqarisi yo'q",
      picks == [[3, 7, 8], [2], []], picks)

print("\n3) Mavzuga bitta Brave so'rovi")
photo_search.reset()
calls = []


async def search(query):
    calls.append(query)
    return [_result(i, title=f"heart anatomy photo {i}") for i in range(10)]


async def choose_first(system, user):
    # Har slotga ketma-ket nomzodlar: 1-slot → 0,1 ; 2-slot → 2,3 ...
    slots = [line for line in user.split("Search results:")[0].splitlines() if line[:1].isdigit()]
    ids = [int(line.split(".")[0]) for line in user.split("Search results:")[1].splitlines() if line[:1].isdigit()]
    return {"picks": [{"slot": n + 1, "ids": ids[n * 2:n * 2 + 2]} for n in range(len(slots))]}


downloads = []


async def fake_download(session, url):
    downloads.append(url)
    return None if url.endswith("img0.jpg") else _image()

real_download = photo_search._download
photo_search._download = fake_download
try:
    first = asyncio.run(photo_search.find_photos("Inson yuragi", ["Yurak tuzilishi", "Qon aylanishi"],
                                                 search=search, choose=choose_first))
    second = asyncio.run(photo_search.find_photos("  inson YURAGI ", ["Muqova"],
                                                  search=search, choose=choose_first))
finally:
    photo_search._download = real_download
check("ikkala murojaatga Brave'ga bitta so'rov", len(calls) == 1, calls)
check("1-slot: birinchi rasm yuklanmasa keyingisi olinadi", bool(first[0]) and downloads[0].endswith("img0.jpg")
      and downloads[1].endswith("img1.jpg"), downloads)
check("ikkala slotga rasm topildi", all(first), first)
used_urls = {u for u in downloads[1:4]}
check("keyingi murojaat oldin ishlatilgan rasmni qayta bermaydi",
      bool(second[0]) and downloads[-1] not in used_urls, downloads)
for path in first + second:
    if path:
        os.remove(path)


async def broken(query):
    calls.append(query)
    raise RuntimeError("tarmoq yo'q")

photo_search.reset(); calls.clear()
asyncio.run(photo_search.find_photos("Fotosintez", ["Barg"], search=broken, choose=choose_first))
asyncio.run(photo_search.find_photos("Fotosintez", ["Ildiz"], search=broken, choose=choose_first))
check("Brave xatosida ham mavzuga ikkinchi so'rov yuborilmaydi", len(calls) == 1, calls)


async def choose_none(system, user):
    return {"picks": [{"slot": 1, "ids": []}]}

photo_search.reset()
none = asyncio.run(photo_search.find_photos("Ko'llar", ["Orol"], search=search, choose=choose_none))
check("AI mos rasm topmasa — None (keyin AI chizadi)", none == [None], none)

print("\n3b) Zaxira rasmlar: yuklanmagan yoki bo'sh qolgan slot to'ldiriladi")
check("zaxira ro'yxati slotlardagilarni takrorlamaydi",
      photo_search.parse_spare({"spare": [1, 4, 4, "x", 50, 5]}, [[1, 2], [3]], 10) == [4, 5])
photo_search.reset(); downloads.clear()


async def choose_with_spare(system, user):
    return {"picks": [{"slot": 1, "ids": [0]}, {"slot": 2, "ids": []}], "spare": [5, 6]}

photo_search._download = fake_download
try:
    got = asyncio.run(photo_search.find_photos("Amir Temur", ["Saltanat", "Me'morchilik"],
                                               search=search, choose=choose_with_spare))
finally:
    photo_search._download = real_download
check("1-slot rasmi yuklanmadi → zaxira, 2-slot bo'sh → keyingi zaxira",
      all(got) and [d.rsplit("/", 1)[1] for d in downloads] == ["img0.jpg", "img5.jpg", "img6.jpg"], downloads)
for path in got:
    if path:
        os.remove(path)

nameless = photo_search.usable([{"title": "", "source": "travel.uz", "url": "https://travel.uz/tours/gur-e-amir-mausoleum",
                                 "properties": {"url": "https://travel.uz/i/1.jpg", "width": 1200, "height": 800}}])
check("nomsiz natijaga sahifa manzilidan ishora", "gur e amir mausoleum" in photo_search._pick_prompt("t", ["s"], nameless),
      nameless)

os.environ.pop("BRAVE_API_KEY", None); os.environ.pop("BRAVE_SEARCH_API_KEY", None)
check("kalit yo'q bo'lsa qidiruv o'chiq", not photo_search.enabled())
os.environ["BRAVE_API_KEY"] = "k"; os.environ["PHOTO_SEARCH"] = "0"
check("PHOTO_SEARCH=0 bilan o'chiriladi", not photo_search.enabled())
os.environ.pop("PHOTO_SEARCH"); os.environ.pop("BRAVE_API_KEY")

print("\n4) Zamonaviy taqdimot: avval sayt, topilmaganini AI chizadi")
page = ('<html><head></head><body><section class="slide"><div class="body"><h2>Yurak <b>tuzilishi</b></h2>'
        '<div class="rasm" data-prompt="human heart close up"><p class="rasm-matn">A</p></div>'
        '<div class="rasm" data-prompt="doctor with stethoscope"><p class="rasm-matn">B</p></div>'
        '</div></section></body></html>')
asked, drawn = [], []


async def find(topic, slots):
    asked.append((topic, list(slots)))
    return [_image(), None]


async def draw(prompt):
    drawn.append(prompt)
    return _image(40, 30)

done, placed = asyncio.run(html_images.fill_photos([page], generate=draw, topic="Inson yuragi", find=find))
check("slot matni: sarlavha + rasm tavsifi",
      asked and asked[0][1][0] == "Yurak tuzilishi — human heart close up", asked)
check("2 ta rasm qo'yildi, AI faqat topilmaganini chizdi",
      placed == 2 and len(drawn) == 1 and "doctor" in drawn[0], (placed, drawn))
check("matn o'rnida rasm", done[0].count('class="photo"') == 2 and "rasm-matn" not in done[0])

cover = ('<html><head></head><body><section class="slide cover"><div class="body"><h1>Yurak</h1>'
         '</div></section><!-- end --></body></html>')
drawn.clear()


async def find_cover(topic, slots):
    return [_image()]

pages, ok = asyncio.run(html_images.fill_cover([cover], "Inson yuragi", generate=draw, find=find_cover))
check("muqova rasmi saytdan topilsa AI chizmaydi", ok and not drawn and "cover-photo" in pages[0], (ok, drawn))


async def find_nothing(topic, slots):
    return [None]

pages, ok = asyncio.run(html_images.fill_cover([cover], "Inson yuragi", generate=draw, find=find_nothing))
check("muqova rasmi topilmasa AI chizadi", ok and len(drawn) == 1, (ok, drawn))

print("\n5) Oddiy taqdimot: topilgan slaydga AI chizilmaydi")
from services import document_service as ds


class FakeTogether:
    def __init__(self):
        self.calls = []

    async def generate_cover_image(self, topic, language):
        self.calls.append("cover"); return _image()

    async def generate_slide_image(self, topic, title, language):
        self.calls.append(title); return _image()

    async def generate_panoramic_image(self, topic, title, language):
        self.calls.append(title); return _image()


service = ds.DocumentService.__new__(ds.DocumentService)
service.together = FakeTogether()
slides = [{"layout": "cover"}, {"layout": "text", "title": "Reja"}]
from services import slide_layouts
image_layouts = [name for name, spec in slide_layouts.CATALOG.items() if spec.image == "slide"]
slides += [{"layout": image_layouts[0], "title": "Yurak"}, {"layout": image_layouts[0], "title": "O'pka"}]
seen_slots = []


async def fake_find(topic, slots):
    seen_slots.append(list(slots))
    return [_image(), None, _image()]

old_enabled, old_find = photo_search.enabled, photo_search.find_photos
photo_search.enabled, photo_search.find_photos = (lambda: True), fake_find
try:
    images = asyncio.run(service._prefetch_slide_images(slides, "Inson organlari", "uz"))
finally:
    photo_search.enabled, photo_search.find_photos = old_enabled, old_find
check("rasm kerak slaydlar bitta ro'yxatda so'raldi (muqova + 2 slayd)",
      len(seen_slots) == 1 and len(seen_slots[0]) == 3 and seen_slots[0][1:] == ["Yurak", "O'pka"], seen_slots)
check("AI faqat topilmagan «Yurak» slaydini chizdi", service.together.calls == ["Yurak"], service.together.calls)
check("hamma rasm o'rni to'ldi", sorted(images) == [0, 2, 3], sorted(images))
for path in images.values():
    if isinstance(path, str) and os.path.exists(path):
        os.remove(path)

print("\n6) AI nazorati hisobi")
ai_usage.record("photo", ai_usage.PHOTO_SITE, 3)
ai_usage.record("photo", ai_usage.PHOTO_AI)
for _ in range(3):
    ai_usage.record("text", "anthropic/claude-sonnet-5")
ai_usage.record("text", "google/gemini-2.5-flash")
ai_usage.record("image", "black-forest-labs/FLUX.1-schnell")
today = asyncio.run(ai_usage.day_counts())
check("bugungi hisob (oldingi bo'limlardagi saytdan topilganlar ham qo'shiladi)",
      today["text"] == {"anthropic/claude-sonnet-5": 3, "google/gemini-2.5-flash": 1}
      and today["photo"].get(ai_usage.PHOTO_SITE, 0) >= 3, today)
fresh = {"photo": {"sayt": 3, "ai": 1}, "text": today["text"], "image": {"black-forest-labs/FLUX.1-schnell": 1}}
text = ai_usage.report_text(fresh, asyncio.run(ai_usage.photo_days(7)))
check("rasmlar foizda: saytdan 75%, AI 25%", "Saytdan (Brave): 3 ta — 75%" in text and "AI chizgan: 1 ta — 25%" in text, text)
check("eng ko'p ishlatilgan model birinchi, foizda",
      text.index("claude-sonnet-5 — 75%") < text.index("gemini-2.5-flash — 25%"), text)
check("7 kunlik jadval bor", "Oxirgi 7 kun" in text, text)

from services.premium_presentation import llm_client
before = asyncio.run(ai_usage.day_counts())["text"].get("test/model", 0)
llm_client._count_model("test/model")
after = asyncio.run(ai_usage.day_counts())["text"].get("test/model", 0)
check("premium matn modeli hisobga tushadi", after == before + 1, (before, after))

from services import together_service
together_service._count_image("test/flux")
counts = asyncio.run(ai_usage.day_counts())
check("chizilgan rasm modeli va «AI chizgan» hisobga tushadi",
      counts["image"].get("test/flux") == 1 and counts["photo"].get("ai") == 2, counts)

print("\n7) Admin panel")
from bot.keyboards import get_admin_keyboard
from bot.handlers import admin
check("admin menyusida «🧠 AI nazorati»",
      any(b.text == "🧠 AI nazorati" for row in get_admin_keyboard().keyboard for b in row))
check("tugma ishlovchisi bor", hasattr(admin, "handle_ai_control"))

print()
if FAILS:
    print(f"XATO: {len(FAILS)} ta"); sys.exit(1)
print("Hammasi to'g'ri")
